"""Satellite Image Preprocessor for ConvLSTM Cloud Nowcasting.

Extracts localized 64x64 georeferenced satellite patches from Himawari-8/9
centered precisely on target solar station coordinates using the official
geostationary projection formula (latlon_to_pixel).

Prepares past 12 consecutive 10-minute satellite frames (2 hours lookback)
into normalized [0.0, 1.0] grayscale tensor with shape (1, 12, 1, 64, 64).

Missing-data policy (no synthetic frames, no repeated frames):
  1. Use the newest window of 12 consecutive real frames.
  2. If a frame inside it is missing, shift the window back in time, at most
     SATELLITE_MAX_SHIFT_MIN minutes from the newest published frame (time shift).
  3. If no complete window exists, report status "missing": the caller then gives the
     satellite branch a weight of 0 and uses the LSTM alone.
"""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import io
import logging
import math
import os
from typing import Optional, Tuple
import urllib.error
import urllib.request

import numpy as np
from PIL import Image

logger = logging.getLogger("satellite_preprocessor")

FULL_DIM = 1100  # level-2d full disk; one pixel is ~15 km (E-W) x ~11 km (N-S) over Thailand
SEQ_LEN = 12
FRAME_STEP = timedelta(minutes=10)
CACHE_BUCKET = "satellite-cache"

# NICT publishes a frame roughly 20-30 minutes after the scan, so the newest frame is always a bit behind
MAX_FEED_AGE_MIN = int(os.environ.get("SATELLITE_MAX_FEED_AGE_MIN", "60"))
MAX_SHIFT_MIN = int(os.environ.get("SATELLITE_MAX_SHIFT_MIN", "30"))
FETCH_TIMEOUT_S = float(os.environ.get("SATELLITE_FETCH_TIMEOUT_S", "8"))
MAX_NETWORK_ERRORS = 2  # give up early when NICT is unreachable instead of timing out on every frame

_TILE_CACHE: dict[datetime, np.ndarray] = {}  # full B03 tile per scan time, shared by all stations
_TILE_CACHE_MAX = 36


@dataclass
class SatelliteWindow:
    frames: Optional[np.ndarray]     # (1, 12, 1, 64, 64) in [0, 1], or None
    end_time: Optional[datetime]     # scan time of the last frame
    status: str                      # ok | shifted | missing
    shift_minutes: int = 0           # how far the window was moved back from the newest published frame
    reason: Optional[str] = None


def latlon_to_pixel(lat_deg: float, lon_deg: float, full_disk_size: int = FULL_DIM) -> Tuple[int, int]:
    """Convert (latitude, longitude) to pixel coordinates in Himawari Level-2d 1100x1100 grid.

    Mathematical formulation for geostationary Himawari sub-satellite point (140.7° E):
    - Upper-left tile `2d/550/_0_0.png` spans col: [0, 550], row: [0, 550], covering
      Thailand, Indochina, and Southeast Asia.
    """
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


def _fetch_b03_tile(utc_dt: datetime) -> tuple[str, Optional[np.ndarray]]:
    """Download the Band 03 tile of one scan. Returns ("ok", tile) | ("not_found", None) | ("error", None)."""
    if utc_dt in _TILE_CACHE:
        return "ok", _TILE_CACHE[utc_dt]

    url = (
        "https://himawari8-dl.nict.go.jp/himawari8/img/FULL_24h/B03/2d/550/"
        f"{utc_dt:%Y}/{utc_dt:%m}/{utc_dt:%d}/{utc_dt:%H%M%S}_0_0.png"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SolarForecastDSS/1.0"})
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_S) as resp:
            content = resp.read()
        arr = np.array(Image.open(io.BytesIO(content)))
        # B03 tile may have 2 channels (grayscale + alpha) or 3 channels (RGB)
        band = arr[:, :, 1] if (arr.ndim == 3 and arr.shape[2] >= 2) else arr
        if band.ndim == 3:
            band = band[:, :, 0]
    except urllib.error.HTTPError as e:
        if e.code == 404:  # not published (yet)
            return "not_found", None
        logger.warning(f"[Satellite Preprocessor] NICT answered HTTP {e.code} for {url}")
        return "error", None
    except Exception as e:
        logger.warning(f"[Satellite Preprocessor] Failed to fetch B03 from {url}: {e}")
        return "error", None

    if len(_TILE_CACHE) >= _TILE_CACHE_MAX:
        for old in sorted(_TILE_CACHE)[: len(_TILE_CACHE) - _TILE_CACHE_MAX + 1]:
            del _TILE_CACHE[old]
    _TILE_CACHE[utc_dt] = band
    return "ok", band


def _crop(tile: np.ndarray, lat: float, lon: float, crop_size: int = 64) -> Optional[np.ndarray]:
    col, row = latlon_to_pixel(lat, lon)
    half = crop_size // 2
    crop = tile[row - half : row + half, col - half : col + half]
    if crop.shape != (crop_size, crop_size):  # station too close to the tile border
        return None
    return crop.astype(np.float32) / 255.0


def fetch_b03_crop(utc_dt: datetime, lat: float, lon: float, crop_size: int = 64) -> Optional[np.ndarray]:
    """Fetch Himawari Band 03 (0.64µm visible reflectance) and crop 64x64 centered at (lat, lon).

    Returns:
        np.ndarray of shape (64, 64) with float32 values normalized in [0.0, 1.0], or None on error.
    """
    status, tile = _fetch_b03_tile(utc_dt)
    return _crop(tile, lat, lon, crop_size) if status == "ok" else None


def fetch_rgb_crop(utc_dt: datetime, lat: float, lon: float, crop_size: int = 64) -> Optional[Image.Image]:
    """Fetch Himawari true-color composite (D531106) and crop 64x64 centered at (lat, lon)."""
    url = (
        "https://himawari8-dl.nict.go.jp/himawari8/img/D531106/2d/550/"
        f"{utc_dt:%Y}/{utc_dt:%m}/{utc_dt:%d}/{utc_dt:%H%M%S}_0_0.png"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SolarForecastDSS/1.0"})
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_S) as resp:
            content = resp.read()
        tile = Image.open(io.BytesIO(content))
        col, row = latlon_to_pixel(lat, lon)
        half = crop_size // 2
        return tile.crop((col - half, row - half, col + half, row + half))
    except Exception as e:
        logger.warning(f"[Satellite Preprocessor] Failed to fetch RGB from {url}: {e}")
        return None


def load_and_preprocess_single_frame(image_bytes: bytes, target_size: Tuple[int, int] = (64, 64)) -> np.ndarray:
    """Convert raw image bytes to normalized (64, 64) float32 array in [0.0, 1.0]."""
    img = Image.open(io.BytesIO(image_bytes)).convert("L")
    if img.size != target_size:
        img = img.resize(target_size, Image.Resampling.BILINEAR)
    arr = np.array(img, dtype=np.float32) / 255.0
    return np.clip(arr, 0.0, 1.0)


def frame_object_name(station_id: str, ts: datetime) -> str:
    return f"{station_id}/b03_{ts:%Y%m%d_%H%M%S}.png"


def connect_minio() -> Optional[object]:
    """MinIO client for the frame cache, or None when MinIO is not reachable (frames then come straight from NICT)."""
    try:
        import urllib3
        from minio import Minio

        http_client = urllib3.PoolManager(
            timeout=urllib3.Timeout(connect=0.8, read=1.5),
            retries=urllib3.Retry(total=1, connect=1, read=1),
        )
        for ep in [e for e in (os.environ.get("MINIO_ENDPOINT"), "minio:9000", "localhost:9000") if e]:
            try:
                client = Minio(
                    ep,
                    access_key=os.environ.get("MINIO_ACCESS_KEY", "admin"),
                    secret_key=os.environ.get("MINIO_SECRET_KEY", "password"),
                    secure=False,
                    http_client=http_client,
                )
                if not client.bucket_exists(CACHE_BUCKET):
                    client.make_bucket(CACHE_BUCKET)
                return client
            except Exception:
                continue
    except Exception:
        pass
    return None


class _FrameSource:
    """Real frames of one station: MinIO cache first, then NICT (and the result is cached)."""

    def __init__(self, station_id: str, lat: float, lon: float, minio_client: Optional[object]):
        self.station_id, self.lat, self.lon, self.minio = station_id, lat, lon, minio_client
        self._seen: dict[datetime, Optional[np.ndarray]] = {}
        self.network_errors = 0

    def get(self, ts: datetime) -> Optional[np.ndarray]:
        if ts in self._seen:
            return self._seen[ts]
        frame = self._from_cache(ts)
        if frame is None and self.network_errors < MAX_NETWORK_ERRORS:
            status, tile = _fetch_b03_tile(ts)
            if status == "ok":
                frame = _crop(tile, self.lat, self.lon)
                if frame is not None:
                    self._to_cache(ts, frame)
            elif status == "error":
                self.network_errors += 1
        self._seen[ts] = frame
        return frame

    def _from_cache(self, ts: datetime) -> Optional[np.ndarray]:
        if self.minio is None:
            return None
        try:
            resp = self.minio.get_object(CACHE_BUCKET, frame_object_name(self.station_id, ts))
            try:
                return load_and_preprocess_single_frame(resp.read())
            finally:
                resp.close()
                resp.release_conn()
        except Exception:
            return None

    def _to_cache(self, ts: datetime, frame: np.ndarray) -> None:
        if self.minio is None:
            return
        try:
            buf = io.BytesIO()
            Image.fromarray((frame * 255.0).astype(np.uint8)).save(buf, format="PNG")
            buf.seek(0)
            self.minio.put_object(
                CACHE_BUCKET, frame_object_name(self.station_id, ts), buf,
                length=buf.getbuffer().nbytes, content_type="image/png",
            )
        except Exception as e:
            logger.warning(f"[Satellite Preprocessor] Could not cache frame {ts:%H:%M} of '{self.station_id}': {e}")


def floor_10min(dt: datetime) -> datetime:
    dt = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    return dt.replace(minute=(dt.minute // 10) * 10, second=0, microsecond=0)


def load_satellite_window(
    station_id: str,
    lat: float,
    lon: float,
    origin_utc: datetime,
    minio_client: Optional[object] = None,
) -> SatelliteWindow:
    """Newest window of 12 consecutive real frames ending at or before `origin_utc`.

    Returns frames with shape (1, 12, 1, 64, 64) and the scan time of the last frame, or status
    "missing" with the reason. Never fabricates or repeats frames.
    """
    if minio_client is None:
        minio_client = connect_minio()
    source = _FrameSource(station_id, lat, lon, minio_client)

    newest_end = floor_10min(origin_utc)
    oldest_end = newest_end - timedelta(minutes=MAX_FEED_AGE_MIN)
    newest_published: Optional[datetime] = None

    end = newest_end
    while end >= oldest_end:
        last = source.get(end)
        if last is not None:
            if newest_published is None:
                newest_published = end
            shift = int((newest_published - end).total_seconds() // 60)
            if shift > MAX_SHIFT_MIN:
                break
            frames = [source.get(end - FRAME_STEP * (SEQ_LEN - 1 - i)) for i in range(SEQ_LEN)]
            if all(f is not None for f in frames):
                seq = np.stack(frames, axis=0)[np.newaxis, :, np.newaxis, :, :].astype(np.float32)
                _cache_latest_rgb(station_id, lat, lon, end, minio_client)
                logger.info(
                    f"[Satellite Preprocessor] '{station_id}': 12 real frames ending {end:%H:%M} UTC"
                    f" (shift {shift} min, {int((newest_end - end).total_seconds() // 60)} min behind the forecast origin)"
                )
                return SatelliteWindow(seq, end, "shifted" if shift else "ok", shift)
        if source.network_errors >= MAX_NETWORK_ERRORS and minio_client is None:
            break
        end -= FRAME_STEP

    if source.network_errors >= MAX_NETWORK_ERRORS:
        reason = "nict_unreachable"
    elif newest_published is None:
        reason = f"no_frame_published_in_last_{MAX_FEED_AGE_MIN}_min"
    else:
        reason = f"no_complete_window_within_{MAX_SHIFT_MIN}_min_shift"
    logger.warning(f"[Satellite Preprocessor] '{station_id}': no usable satellite window ({reason})")
    return SatelliteWindow(None, None, "missing", 0, reason)


def _cache_latest_rgb(station_id: str, lat: float, lon: float, ts: datetime, minio_client: Optional[object]) -> None:
    """Keep the newest true-colour crop for display on the dashboard."""
    if minio_client is None:
        return
    try:
        rgb = fetch_rgb_crop(ts, lat, lon, crop_size=64)
        if rgb is None:
            return
        buf = io.BytesIO()
        rgb.save(buf, format="PNG")
        buf.seek(0)
        minio_client.put_object(
            CACHE_BUCKET, f"{station_id}_latest.png", buf,
            length=buf.getbuffer().nbytes, content_type="image/png",
        )
    except Exception:
        pass
