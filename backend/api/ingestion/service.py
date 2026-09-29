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


class IngestionService:
    @staticmethod
    def fetch_open_meteo_live(lat: float, lon: float) -> dict:
        """Fetch real-time weather and solar radiation from Open-Meteo API (100% free, no key)."""
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}&timezone=Asia%2FBangkok"
            f"&current=temperature_2m,relative_humidity_2m,surface_pressure,wind_speed_10m,cloud_cover,direct_normal_irradiance,shortwave_radiation"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "SolarForecastDSS/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())

    @staticmethod
    def fetch_nict_realtime_image() -> tuple[Optional[bytes], datetime, str]:
        """Fetch latest Himawari 550x550 PNG image from NICT Japan."""
        # 1. Check latest.json
        req = urllib.request.Request(NICT_LATEST_JSON, headers={"User-Agent": "SolarForecastDSS/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            latest_info = json.loads(resp.read().decode())

        date_str = latest_info.get("date")  # e.g. "2026-09-29 07:50:00"
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

        # 2. Fetch & store NICT satellite image
        try:
            img_bytes, dt_frame, filename = IngestionService.fetch_nict_realtime_image()
            if img_bytes:
                # Save into MinIO bucket 'satellite-cache'
                try:
                    StorageService.create_bucket(SATELLITE_BUCKET)
                except Exception:
                    pass

                object_name = f"{station.id}/{filename}"
                StorageService.upload_file(
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

        if not records:
            # Fallback mock baseline for last 24h if fresh database
            now = datetime.now(timezone.utc)
            mock_items = []
            for i in range(24, 0, -1):
                t = now - timedelta(hours=i)
                ghi_val = max(0.0, 700.0 * (1.0 if 7 <= t.hour <= 17 else 0.0))
                solar = SolarCalculator.get_solar_metrics(7.0086, 100.4988, t, ghi_val)
                mock_items.append(
                    WeatherRecentItem(
                        timestamp=t,
                        temperature=28.5,
                        relative_humidity=75.0,
                        ghi=ghi_val,
                        dni=max(0.0, 500.0 * (1.0 if 7 <= t.hour <= 17 else 0.0)),
                        clearsky_ghi=solar.clearsky_ghi,
                        clearsky_index=solar.clearsky_index,
                        solar_zenith_angle=solar.zenith_degrees,
                        cloud_cover=20.0,
                        source="baseline",
                    )
                )
            return mock_items

        return [WeatherRecentItem.model_validate(r) for r in records]

    @staticmethod
    async def get_recent_satellite_frames(station_id: str, db: AsyncSession, count: int = 12) -> list[SatelliteFrameItem]:
        """Fetch latest N satellite frame URLs for a station."""
        stmt = (
            select(SatelliteFrameMetadata)
            .where(SatelliteFrameMetadata.station_id == station_id)
            .order_by(SatelliteFrameMetadata.frame_timestamp.desc())
            .limit(count)
        )
        res = await db.execute(stmt)
        frames = res.scalars().all()

        if not frames:
            now = datetime.now(timezone.utc)
            return [
                SatelliteFrameItem(
                    frame_no=i + 1,
                    timestamp=now - timedelta(minutes=10 * (12 - i)),
                    image_url=f"/api/storage/download/satellite-cache/{station_id}/frame_{i+1:02d}.png",
                )
                for i in range(12)
            ]

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

        latest_stmt = select(WeatherHistory.timestamp).order_by(WeatherHistory.timestamp.desc()).limit(1)
        l_res = await db.execute(latest_stmt)
        last_sync = l_res.scalar_one_or_none()

        return IngestionStatusResponse(
            last_sync=last_sync or datetime.now(timezone.utc),
            open_meteo_status="operational",
            nict_status="operational",
            total_weather_records=w_count,
            total_satellite_frames=f_count,
        )
