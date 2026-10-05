import io
import json
import os
import uuid
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.ingestion.model import SatelliteFrameMetadata, WeatherHistory
from api.ingestion.normalizer import WeatherDataNormalizer
from api.ingestion.schema import IngestTriggerResponse, IngestionStatusResponse, SatelliteFrameItem, WeatherRecentItem
from api.ingestion.solar_calculator import SolarCalculator
from api.stations.model import Station
from api.stations.service import StationService
from api.storage.service import StorageService
from core.config import settings

NICT_LATEST_JSON = "https://himawari8-dl.nict.go.jp/himawari8/img/D531106/latest.json"
NICT_BASE_IMG_URL = "https://himawari8-dl.nict.go.jp/himawari8/img/D531106"
SATELLITE_BUCKET = "satellite-cache"
# Open-Meteo answers in km/h unless told otherwise; the LSTM was trained on m/s (NSRDB), so every request asks for m/s.
# Rows stored before 5 Oct 2026 were km/h and were converted once with scripts/convert_wind_speed_to_ms.py.
OPEN_METEO_WIND_UNIT = "wind_speed_unit=ms"


NICT_B03_BASE_URL = "https://himawari8-dl.nict.go.jp/himawari8/img/FULL_24h/B03"
BLANK_TILE_MIN_SUN_ELEVATION_DEG = 6.0  # same daylight limit as service/workers/satellite_preprocessor.py (cos zenith 0.10)


def latlon_to_pixel(lat_deg: float, lon_deg: float, full_disk_size: int = 1100) -> tuple[int, int]:
    """Convert (latitude, longitude) to pixel coordinates in Himawari Level-2d 1100x1100 grid."""
    import math

    sub_lon = 140.7
    scale = full_disk_size / 5500.0
    cfac = 20466275
    lfac = 20466275
    coff = 2750.5 * scale
    loff = 2750.5 * scale
    req = 6378.1370
    rpol = 6356.7523

    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    sub_lon_r = math.radians(sub_lon)

    c_lat = math.atan(((rpol**2) / (req**2)) * math.tan(lat))
    rc = rpol / math.sqrt(1.0 - (((req**2 - rpol**2) / (req**2)) * (math.cos(c_lat)**2)))

    rx = 42164.0 - rc * math.cos(c_lat) * math.cos(lon - sub_lon_r)
    ry = -rc * math.cos(c_lat) * math.sin(lon - sub_lon_r)
    rz = rc * math.sin(c_lat)

    x = math.atan(-ry / rx)
    y = math.asin(rz / math.sqrt(rx**2 + ry**2 + rz**2))

    col = coff + x * (2**-16) * cfac * (180.0 / math.pi) * scale
    row = loff - y * (2**-16) * lfac * (180.0 / math.pi) * scale
    return int(round(col)), int(round(row))


class IngestionService:
    @staticmethod
    def fetch_open_meteo_live(lat: float, lon: float) -> dict:
        """Fetch real-time weather and solar radiation from Open-Meteo API (100% free, no key)."""
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}&timezone=UTC"
            f"&current=temperature_2m,relative_humidity_2m,surface_pressure,wind_speed_10m,cloud_cover,direct_normal_irradiance,shortwave_radiation"
            f"&{OPEN_METEO_WIND_UNIT}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "SolarForecastDSS/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())

    @staticmethod
    def fetch_nict_realtime_image() -> tuple[Optional[bytes], datetime, str]:
        """Fetch latest Himawari 550x550 PNG image from NICT Japan."""
        req = urllib.request.Request(NICT_LATEST_JSON, headers={"User-Agent": "SolarForecastDSS/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            latest_info = json.loads(resp.read().decode())

        date_str = latest_info.get("date")
        dt_utc = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)

        yyyy = dt_utc.strftime("%Y")
        mm = dt_utc.strftime("%m")
        dd = dt_utc.strftime("%d")
        hhmmss = dt_utc.strftime("%H%M%S")

        img_url = f"{NICT_BASE_IMG_URL}/1d/550/{yyyy}/{mm}/{dd}/{hhmmss}_0_0.png"
        img_req = urllib.request.Request(img_url, headers={"User-Agent": "SolarForecastDSS/1.0"})
        with urllib.request.urlopen(img_req, timeout=20) as img_resp:
            content = img_resp.read()

        filename = f"nict_{yyyy}{mm}{dd}_{hhmmss}.png"
        return content, dt_utc, filename

    @staticmethod
    def fetch_nict_historical_image(target_dt: datetime) -> tuple[Optional[bytes], datetime, str]:
        """Fetch a specific Himawari 550x550 PNG image from NICT Japan by UTC timestamp."""
        minute = (target_dt.minute // 10) * 10
        dt_utc = target_dt.replace(minute=minute, second=0, microsecond=0)
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)

        yyyy = dt_utc.strftime("%Y")
        mm = dt_utc.strftime("%m")
        dd = dt_utc.strftime("%d")
        hhmmss = dt_utc.strftime("%H%M%S")

        img_url = f"{NICT_BASE_IMG_URL}/1d/550/{yyyy}/{mm}/{dd}/{hhmmss}_0_0.png"
        img_req = urllib.request.Request(img_url, headers={"User-Agent": "SolarForecastDSS/1.0"})
        try:
            with urllib.request.urlopen(img_req, timeout=15) as img_resp:
                content = img_resp.read()
            filename = f"nict_{yyyy}{mm}{dd}_{hhmmss}.png"
            return content, dt_utc, filename
        except Exception:
            return None, dt_utc, ""

    @staticmethod
    def fetch_station_b03_crop(
        target_dt: datetime, lat: float, lon: float, crop_size: int = 64
    ) -> tuple[Optional[bytes], datetime, str]:
        """Fetch Himawari Level-2d B03 tile and crop 64x64 patch centered on station coordinates."""
        from PIL import Image
        import numpy as np

        minute = (target_dt.minute // 10) * 10
        dt_utc = target_dt.replace(minute=minute, second=0, microsecond=0)
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)

        yyyy = dt_utc.strftime("%Y")
        mm = dt_utc.strftime("%m")
        dd = dt_utc.strftime("%d")
        hhmmss = dt_utc.strftime("%H%M%S")

        img_url = f"{NICT_B03_BASE_URL}/2d/550/{yyyy}/{mm}/{dd}/{hhmmss}_0_0.png"
        img_req = urllib.request.Request(img_url, headers={"User-Agent": "SolarForecastDSS/1.0"})
        try:
            with urllib.request.urlopen(img_req, timeout=15) as img_resp:
                raw_bytes = img_resp.read()
            img = Image.open(io.BytesIO(raw_bytes))
            arr = np.array(img)
            band_data = arr[:, :, 1] if (arr.ndim == 3 and arr.shape[2] >= 2) else arr
            if band_data.ndim == 3:
                band_data = band_data[:, :, 0]

            col, row = latlon_to_pixel(lat, lon)
            half = crop_size // 2
            crop_arr = band_data[row - half : row + half, col - half : col + half]
            if crop_arr.shape != (crop_size, crop_size):
                crop_arr = np.array(Image.fromarray(crop_arr).resize((crop_size, crop_size), Image.Resampling.BILINEAR))

            # NICT answers a scan it has no image for (not processed yet, or the daily 02:40 / 14:40 UTC gap)
            # with an all-black tile. With the sun up that is not an observation: nothing is stored for it.
            _, elevation_deg = SolarCalculator.calculate_solar_position(lat, lon, dt_utc)
            if int(crop_arr.max()) == 0 and elevation_deg >= BLANK_TILE_MIN_SUN_ELEVATION_DEG:
                return None, dt_utc, ""

            buf = io.BytesIO()
            Image.fromarray(crop_arr).save(buf, format="PNG")
            cropped_bytes = buf.getvalue()
            filename = f"b03_{yyyy}{mm}{dd}_{hhmmss}.png"
            return cropped_bytes, dt_utc, filename
        except Exception:
            return None, dt_utc, ""

    @staticmethod
    def fetch_station_rgb_crop(
        target_dt: datetime, lat: float, lon: float, crop_size: int = 64
    ) -> tuple[Optional[bytes], datetime, str]:
        """Fetch Himawari Level-2d true-color RGB tile and crop 64x64 centered on station."""
        from PIL import Image

        minute = (target_dt.minute // 10) * 10
        dt_utc = target_dt.replace(minute=minute, second=0, microsecond=0)
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)

        yyyy = dt_utc.strftime("%Y")
        mm = dt_utc.strftime("%m")
        dd = dt_utc.strftime("%d")
        hhmmss = dt_utc.strftime("%H%M%S")

        img_url = f"{NICT_BASE_IMG_URL}/2d/550/{yyyy}/{mm}/{dd}/{hhmmss}_0_0.png"
        img_req = urllib.request.Request(img_url, headers={"User-Agent": "SolarForecastDSS/1.0"})
        try:
            with urllib.request.urlopen(img_req, timeout=15) as img_resp:
                raw_bytes = img_resp.read()
            tile = Image.open(io.BytesIO(raw_bytes))
            col, row = latlon_to_pixel(lat, lon)
            half = crop_size // 2
            crop_img = tile.crop((col - half, row - half, col + half, row + half))
            buf = io.BytesIO()
            crop_img.save(buf, format="PNG")
            return buf.getvalue(), dt_utc, f"rgb_{yyyy}{mm}{dd}_{hhmmss}.png"
        except Exception:
            return None, dt_utc, ""

    @staticmethod
    async def trigger_ingest(station_id: str, db: AsyncSession) -> IngestTriggerResponse:
        """Trigger an immediate live ingestion of weather + satellite imagery."""
        station = await StationService.get_station_by_id(db, station_id)
        job_id = f"ingest-{uuid.uuid4().hex[:12]}"

        # 1. Fetch & normalize Open-Meteo weather
        try:
            raw_weather = IngestionService.fetch_open_meteo_live(station.latitude, station.longitude)
            canonical = WeatherDataNormalizer.normalize_open_meteo(
                raw_weather, station.id, lat=station.latitude, lon=station.longitude
            )

            weather_record = WeatherHistory(
                station_id=station.id,
                timestamp=canonical.timestamp,
                ghi=canonical.ghi,
                dni=canonical.dni,
                dhi=canonical.dhi,
                clearsky_ghi=canonical.clearsky_ghi,
                clearsky_index=canonical.clearsky_index,
                solar_zenith_angle=canonical.solar_zenith_angle,
                temperature=canonical.temperature,
                relative_humidity=canonical.relative_humidity,
                wind_speed=canonical.wind_speed,
                cloud_cover=canonical.cloud_cover,
                surface_pressure=canonical.surface_pressure,
                source=canonical.source,
            )
            db.add(weather_record)
        except Exception as e:
            print(f"[Ingest Warning] Failed to fetch weather: {e}")

        # 2. Fetch & store NICT satellite image (Cropped B03 for station)
        try:
            img_bytes, dt_frame, filename = IngestionService.fetch_station_b03_crop(
                datetime.now(timezone.utc), station.latitude, station.longitude
            )
            if not img_bytes:
                img_bytes, dt_frame, filename = IngestionService.fetch_nict_realtime_image()
            if img_bytes:
                storage = StorageService()
                try:
                    storage.create_bucket(SATELLITE_BUCKET)
                except Exception:
                    pass

                object_name = f"{station.id}/{filename}"
                storage.upload_file(
                    bucket_name=SATELLITE_BUCKET,
                    object_name=object_name,
                    data=io.BytesIO(img_bytes),
                    length=len(img_bytes),
                    content_type="image/png",
                )

                # Save metadata
                frame_meta = SatelliteFrameMetadata(
                    station_id=station.id,
                    frame_timestamp=dt_frame,
                    image_url=f"/api/storage/download/{SATELLITE_BUCKET}/{object_name}",
                )
                db.add(frame_meta)
        except Exception as e:
            print(f"[Ingest Warning] Failed to fetch NICT image: {e}")

        await db.commit()
        return IngestTriggerResponse(
            job_id=job_id,
            status="completed",
            message=f"Successfully ingested live data for station '{station.id}'",
        )

    @staticmethod
    async def get_recent_weather(station_id: str, db: AsyncSession, hours: int = 24) -> list[WeatherRecentItem]:
        """Fetch normalized recent weather data for a station."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        stmt = (
            select(WeatherHistory)
            .where(WeatherHistory.station_id == station_id, WeatherHistory.timestamp >= cutoff)
            .order_by(WeatherHistory.timestamp.asc())
        )
        res = await db.execute(stmt)
        records = res.scalars().all()

        return [WeatherRecentItem.model_validate(r) for r in records]

    @staticmethod
    async def get_recent_satellite_frames(station_id: str, db: AsyncSession, count: int = 12) -> list[SatelliteFrameItem]:
        """Fetch latest N satellite frame URLs for a station."""
        stmt = (
            select(SatelliteFrameMetadata)
            .where(SatelliteFrameMetadata.station_id == station_id)
            .distinct(SatelliteFrameMetadata.frame_timestamp)
            .order_by(SatelliteFrameMetadata.frame_timestamp.desc())
            .limit(count)
        )
        res = await db.execute(stmt)
        frames = res.scalars().all()

        # Return ordered from oldest to newest (1 to count)
        frames_reversed = list(reversed(frames))
        return [
            SatelliteFrameItem(
                frame_no=idx + 1,
                timestamp=f.frame_timestamp,
                image_url=f.image_url,
            )
            for idx, f in enumerate(frames_reversed)
        ]

    @staticmethod
    async def get_status(db: AsyncSession) -> IngestionStatusResponse:
        """Check overall ingestion health and record counts."""
        weather_count_stmt = select(func.count(WeatherHistory.id))
        w_res = await db.execute(weather_count_stmt)
        w_count = w_res.scalar_one() or 0

        frame_count_stmt = select(func.count(SatelliteFrameMetadata.id))
        f_res = await db.execute(frame_count_stmt)
        f_count = f_res.scalar_one() or 0

        last_sync = (await db.execute(select(func.max(WeatherHistory.timestamp)))).scalar_one_or_none()
        last_frame = (await db.execute(select(func.max(SatelliteFrameMetadata.frame_timestamp)))).scalar_one_or_none()

        def feed_status(newest: Optional[datetime], max_age_min: int) -> str:
            # derived from the age of the newest stored record, not assumed
            if newest is None:
                return "no_data"
            newest = newest if newest.tzinfo else newest.replace(tzinfo=timezone.utc)
            age_min = (datetime.now(timezone.utc) - newest).total_seconds() / 60.0
            return "operational" if age_min <= max_age_min else "stale"

        return IngestionStatusResponse(
            last_sync=last_sync,
            open_meteo_status=feed_status(last_sync, 30),
            nict_status=feed_status(last_frame, 60),
            total_weather_records=w_count,
            total_satellite_frames=f_count,
        )

    @staticmethod
    async def auto_catchup_weather(
        db: AsyncSession, station_id: str = "ST-001", max_gap_days: int = 7
    ) -> dict:
        """Detect gap since latest recorded weather and automatically backfill missing 10-minute intervals.

        Interpolates Open-Meteo data to exact 10-minute intervals and computes
        astronomical solar metrics. Runs on startup and on-demand.
        """
        import math
        import pandas as pd

        try:
            station = await StationService.get_station_by_id(db, station_id)
        except Exception:
            return {
                "status": "error",
                "message": f"Station '{station_id}' not found.",
                "station_id": station_id,
            }

        now_utc = datetime.now(timezone.utc)

        # 1. Query latest recorded timestamp
        stmt = select(func.max(WeatherHistory.timestamp)).where(WeatherHistory.station_id == station_id)
        res = await db.execute(stmt)
        latest_ts = res.scalar_one_or_none()

        if latest_ts is not None and latest_ts.tzinfo is None:
            latest_ts = latest_ts.replace(tzinfo=timezone.utc)

        is_fresh = latest_ts is None
        if is_fresh:
            # Fresh station: fetch last 2 days to satisfy 144-step lookback for LSTM
            latest_ts = now_utc - timedelta(days=2)

        gap_seconds = (now_utc - latest_ts).total_seconds()
        # If gap is less than 15 minutes and not fresh, we are up-to-date
        if gap_seconds < 900 and not is_fresh:
            return {
                "status": "up_to_date",
                "message": f"Station '{station_id}' is already up-to-date (last record: {latest_ts.isoformat()}).",
                "station_id": station_id,
                "gap_hours": 0.0,
                "records_inserted": 0,
                "latest_timestamp": latest_ts.isoformat(),
            }

        gap_hours = max(0.5, gap_seconds / 3600.0)
        past_days = min(max_gap_days, max(1, math.ceil(gap_hours / 24.0) + 1))

        lat, lon = station.latitude, station.longitude
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}&past_days={past_days}"
            f"&minutely_15=temperature_2m,relative_humidity_2m,surface_pressure,wind_speed_10m,cloud_cover,direct_normal_irradiance,shortwave_radiation"
            f"&timezone=UTC&{OPEN_METEO_WIND_UNIT}"
        )

        req = urllib.request.Request(url, headers={"User-Agent": "SolarForecastDSS/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode())
        except Exception as e:
            return {
                "status": "failed",
                "message": f"Failed to fetch Open-Meteo historical data: {e}",
                "station_id": station_id,
            }

        minutely = data.get("minutely_15", {})
        if not minutely or "time" not in minutely:
            return {
                "status": "failed",
                "message": "No minutely_15 data received from Open-Meteo.",
                "station_id": station_id,
            }

        df = pd.DataFrame(minutely)
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df.set_index("time", inplace=True)

        # Resample to 10-minute cadence
        df_10m = df.resample("10min").interpolate(method="time").ffill().bfill()

        # Filter for timestamps strictly greater than latest_ts and <= now_utc
        df_missing = df_10m[(df_10m.index > latest_ts) & (df_10m.index <= now_utc)].copy()

        if df_missing.empty:
            return {
                "status": "up_to_date",
                "message": "No new 10-minute records needed after resampling.",
                "station_id": station_id,
                "records_inserted": 0,
            }

        records = []
        for row_time, row in df_missing.iterrows():
            dt = row_time.to_pydatetime()
            raw_ghi = max(0.0, float(row.get("shortwave_radiation", 0.0) or 0.0))
            solar = SolarCalculator.get_solar_metrics(lat=lat, lon=lon, dt_utc=dt, measured_ghi=raw_ghi)

            if not solar.is_daylight or solar.zenith_degrees >= 90.0:
                ghi = 0.0
                dni = 0.0
                dhi = 0.0
            else:
                ghi = raw_ghi
                dni = max(0.0, float(row.get("direct_normal_irradiance", 0.0) or 0.0))
                cos_z = max(0.01, math.cos(math.radians(solar.zenith_degrees)))
                dhi = max(0.0, ghi - dni * cos_z)

            record = WeatherHistory(
                station_id=station.id,
                timestamp=dt,
                ghi=round(ghi, 2),
                dni=round(dni, 2),
                dhi=round(dhi, 2),
                clearsky_ghi=round(solar.clearsky_ghi, 2),
                clearsky_index=round(solar.clearsky_index, 4),
                solar_zenith_angle=round(solar.zenith_degrees, 2),
                temperature=round(float(row.get("temperature_2m", 25.0)), 2),
                relative_humidity=round(float(row.get("relative_humidity_2m", 50.0)), 2),
                wind_speed=round(float(row.get("wind_speed_10m", 0.0) or 0.0), 2),
                cloud_cover=round(float(row.get("cloud_cover", 0.0) or 0.0), 2),
                surface_pressure=round(float(row.get("surface_pressure", 1013.25) or 1013.25), 2),
                source="open_meteo_catchup",
            )
            records.append(record)

        db.add_all(records)
        await db.commit()

        return {
            "status": "backfilled",
            "message": f"Successfully auto-backfilled {len(records)} missing records ({round(gap_hours, 1)}h gap recovered).",
            "station_id": station_id,
            "gap_hours": round(gap_hours, 2),
            "from_timestamp": latest_ts.isoformat(),
            "to_timestamp": now_utc.isoformat(),
            "records_inserted": len(records),
        }

    @staticmethod
    async def auto_catchup_satellite(
        db: AsyncSession, station_id: str = "ST-001", count: int = 12
    ) -> dict:
        """Ensure station has the latest N consecutive 10-minute satellite frames.

        If any frames are missing in the past 2 hours (e.g. after a system shutdown),
        it automatically fetches them from NICT Archive and uploads to MinIO + registers in DB.
        """
        now_utc = datetime.now(timezone.utc)

        # 1. Determine latest available satellite frame timestamp
        latest_dt = None
        try:
            req = urllib.request.Request(NICT_LATEST_JSON, headers={"User-Agent": "SolarForecastDSS/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                latest_info = json.loads(resp.read().decode())
            date_str = latest_info.get("date")
            latest_dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except Exception:
            approx = now_utc - timedelta(minutes=20)
            approx_min = (approx.minute // 10) * 10
            latest_dt = approx.replace(minute=approx_min, second=0, microsecond=0)

        # Required consecutive 10-min timestamps: e.g. 12 frames = 2 hours
        required_timestamps = [
            latest_dt - timedelta(minutes=10 * i)
            for i in range(count - 1, -1, -1)
        ]

        # 2. Check which timestamps exist in PostgreSQL for this station
        stmt = select(SatelliteFrameMetadata.frame_timestamp).where(
            SatelliteFrameMetadata.station_id == station_id,
            SatelliteFrameMetadata.frame_timestamp.in_(required_timestamps),
        )
        res = await db.execute(stmt)
        existing_ts = set(res.scalars().all())

        missing_ts = [ts for ts in required_timestamps if ts not in existing_ts]
        if not missing_ts:
            return {
                "status": "up_to_date",
                "message": f"Station '{station_id}' already has all {count} recent satellite frames.",
                "station_id": station_id,
                "frames_present": count,
                "frames_backfilled": 0,
            }

        # 3. Fetch missing frames from NICT Archive
        storage = StorageService()
        try:
            storage.create_bucket(SATELLITE_BUCKET)
        except Exception:
            pass

        # Retrieve station for localized coordinates
        station = await StationService.get_station_by_id(db, station_id)

        backfilled_count = 0
        for ts in missing_ts:
            # only the station's own crop counts: a scan NICT has no image for stays missing
            img_bytes, dt_frame, filename = IngestionService.fetch_station_b03_crop(
                ts, station.latitude, station.longitude
            )
            if img_bytes and filename:
                object_name = f"{station_id}/{filename}"
                storage.upload_file(
                    bucket_name=SATELLITE_BUCKET,
                    object_name=object_name,
                    data=io.BytesIO(img_bytes),
                    length=len(img_bytes),
                    content_type="image/png",
                )
                frame_meta = SatelliteFrameMetadata(
                    station_id=station_id,
                    frame_timestamp=dt_frame,
                    image_url=f"/api/storage/download/{SATELLITE_BUCKET}/{object_name}",
                )
                db.add(frame_meta)
                backfilled_count += 1

        # the dashboard preview ('<station>_latest.png') is written with the newest scan only, never with a backfilled one

        await db.commit()
        return {
            "status": "backfilled",
            "message": f"Successfully backfilled {backfilled_count}/{len(missing_ts)} missing satellite frames for '{station_id}'.",
            "station_id": station_id,
            "frames_present": len(existing_ts) + backfilled_count,
            "frames_backfilled": backfilled_count,
            "target_frames": count,
        }


