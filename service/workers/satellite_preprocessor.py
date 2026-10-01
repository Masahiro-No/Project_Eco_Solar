"""Satellite Image Preprocessor for ConvLSTM Cloud Nowcasting.

Extracts localized 64x64 georeferenced satellite patches from Himawari-8/9
centered precisely on target solar station coordinates using the official
geostationary projection formula (latlon_to_pixel).

Prepares past 12 consecutive 10-minute satellite frames (2 hours lookback)
into normalized [0.0, 1.0] grayscale tensor with shape (1, 12, 1, 64, 64).
"""

from datetime import datetime, timezone, timedelta
import io
import logging
import math
import os
from typing import Optional, Tuple

import numpy as np
from PIL import Image

logger = logging.getLogger("satellite_preprocessor")

FULL_DIM = 1100

# Canonical coordinates for known stations in Thailand
STATION_COORDINATES = {
    "ST-001": (7.0086, 100.4988),  # PSU Hat Yai Solar Farm
    "ST-002": (6.9310, 100.3690),  # ศูนย์บริการวิชาการที่ 10 (จ.สงขลา) พพ.
    "ST-003": (14.7710, 98.6290),  # สถานีอุตุนิยมวิทยาทองผาภูมิ
}


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


def fetch_b03_crop(utc_dt: datetime, lat: float, lon: float, crop_size: int = 64) -> Optional[np.ndarray]:
    """Fetch Himawari Band 03 (0.64µm visible reflectance) and crop 64x64 centered at (lat, lon).

    Returns:
        np.ndarray of shape (64, 64) with float32 values normalized in [0.0, 1.0], or None on error.
    """
    import urllib.request

    yyyy = utc_dt.strftime("%Y")
    mm = utc_dt.strftime("%m")
    dd = utc_dt.strftime("%d")
    hhmmss = utc_dt.strftime("%H%M%S")
    url = f"https://himawari8-dl.nict.go.jp/himawari8/img/FULL_24h/B03/2d/550/{yyyy}/{mm}/{dd}/{hhmmss}_0_0.png"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SolarForecastDSS/1.0"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            content = resp.read()

        img = Image.open(io.BytesIO(content))
        arr = np.array(img)
        # B03 tile may have 2 channels (grayscale + alpha) or 3 channels (RGB)
        band_data = arr[:, :, 1] if (arr.ndim == 3 and arr.shape[2] >= 2) else arr
        if band_data.ndim == 3:
            band_data = band_data[:, :, 0]

        col, row = latlon_to_pixel(lat, lon)
        half = crop_size // 2
        crop = band_data[row - half : row + half, col - half : col + half]

        if crop.shape != (crop_size, crop_size):
            # Safe border clamp
            crop = np.array(Image.fromarray(crop).resize((crop_size, crop_size), Image.Resampling.BILINEAR))

        return crop.astype(np.float32) / 255.0
    except Exception as e:
        logger.warning(f"[Satellite Preprocessor] Failed to fetch B03 from {url}: {e}")
        return None


def fetch_rgb_crop(utc_dt: datetime, lat: float, lon: float, crop_size: int = 64) -> Optional[Image.Image]:
    """Fetch Himawari true-color composite (D531106) and crop 64x64 centered at (lat, lon)."""
    import urllib.request

    yyyy = utc_dt.strftime("%Y")
    mm = utc_dt.strftime("%m")
    dd = utc_dt.strftime("%d")
    hhmmss = utc_dt.strftime("%H%M%S")
    url = f"https://himawari8-dl.nict.go.jp/himawari8/img/D531106/2d/550/{yyyy}/{mm}/{dd}/{hhmmss}_0_0.png"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SolarForecastDSS/1.0"})
        with urllib.request.urlopen(req, timeout=12) as resp:
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


def generate_synthetic_satellite_sequence() -> np.ndarray:
    """Generate realistic synthetic 12-frame sequence when no satellite imagery is available."""
    base = np.random.uniform(0.08, 0.18, size=(64, 64)).astype(np.float32)
    frames = []
    for step in range(12):
        noise = np.random.normal(0.0, 0.015, size=(64, 64)).astype(np.float32)
        frame = np.clip(base + (step * 0.003) + noise, 0.0, 1.0)
        frames.append(frame)

    seq = np.stack(frames, axis=0)       # (12, 64, 64)
    seq = np.expand_dims(seq, axis=1)    # (12, 1, 64, 64)
    seq = np.expand_dims(seq, axis=0)    # (1, 12, 1, 64, 64)
    return seq


def get_satellite_sequence_12(
    station_id: str = "ST-001",
    minio_client: Optional[object] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    target_dt_utc: Optional[datetime] = None,
) -> np.ndarray:
    """Fetch the latest 12 consecutive 10-min satellite frames cropped centered on station coords.

    Strategy:
    1. Resolve (lat, lon) coordinates for station.
    2. Check MinIO cache for pre-cropped station frames.
    3. If cache is incomplete, fetch real high-res B03 crops directly from NICT Japan.
    4. Store fetched frames in MinIO for high-speed subsequent lookups.
    5. Fallback gracefully to synthetic baseline if completely offline.

    Returns:
        np.ndarray of shape (1, 12, 1, 64, 64) in range [0.0, 1.0], dtype float32.
    """
    if lat is None or lon is None:
        coords = STATION_COORDINATES.get(station_id, (7.0086, 100.4988))
        lat, lon = coords[0], coords[1]

    # Initialize MinIO client if needed
    if minio_client is None:
        try:
            import urllib3
            from minio import Minio
            endpoints = [os.environ.get("MINIO_ENDPOINT"), "minio:9000", "localhost:9000"]
            endpoints = [e for e in endpoints if e]
            http_client = urllib3.PoolManager(
                timeout=urllib3.Timeout(connect=0.8, read=1.5),
                retries=urllib3.Retry(total=1, connect=1, read=1),
            )
            for ep in endpoints:
                try:
                    candidate = Minio(
                        ep,
                        access_key=os.environ.get("MINIO_ACCESS_KEY", "admin"),
                        secret_key=os.environ.get("MINIO_SECRET_KEY", "password"),
                        secure=False,
                        http_client=http_client,
                    )
                    candidate.bucket_exists("satellite-cache")
                    minio_client = candidate
                    break
                except Exception:
                    continue
        except Exception:
            minio_client = None

    # Step 1: Check MinIO satellite-cache bucket for pre-existing station crops
    bucket = "satellite-cache"
    frames = []
    if minio_client is not None:
        try:
            if minio_client.bucket_exists(bucket):
                prefix = f"{station_id}/"
                objects = [
                    o for o in minio_client.list_objects(bucket, prefix=prefix, recursive=True)
                    if o.object_name.endswith(".png") and "b03" in o.object_name
                ]
                if len(objects) >= 12 and target_dt_utc is None:
                    objects.sort(key=lambda x: x.object_name)
                    target_objs = objects[-12:]
                    for obj in target_objs:
                        resp = minio_client.get_object(bucket, obj.object_name)
                        img_bytes = resp.read()
                        resp.close()
                        resp.release_conn()
                        frames.append(load_and_preprocess_single_frame(img_bytes))

                    if len(frames) == 12:
                        seq = np.stack(frames, axis=0)[np.newaxis, :, np.newaxis, :, :]
                        logger.info(f"[Satellite Preprocessor] Loaded 12 cropped frames from MinIO for station '{station_id}'")
                        return seq
        except Exception as e:
            logger.warning(f"[Satellite Preprocessor] MinIO check error: {e}")

    # Step 2: Live / historical fetch from NICT Japan using teammate's geocoded crop method
    now_utc = target_dt_utc if target_dt_utc is not None else datetime.now(timezone.utc)
    # Align to 10-minute mark (Himawari-8/9 updates at :00, :10, :20, :30, :40, :50)
    minute_aligned = (now_utc.minute // 10) * 10
    ref_dt = now_utc.replace(minute=minute_aligned, second=0, microsecond=0)

    # 12 consecutive 10-minute timestamps ending at ref_dt
    timestamps_12 = [ref_dt - timedelta(minutes=10 * (11 - i)) for i in range(12)]
    logger.info(f"[Satellite Preprocessor] Fetching 12 B03 cropped frames for station '{station_id}' ({lat}, {lon}) ending at {ref_dt} UTC...")

    online_frames = []
    for idx, ts in enumerate(timestamps_12):
        crop = fetch_b03_crop(ts, lat, lon, crop_size=64)
        if crop is not None:
            online_frames.append((ts, crop))
            # Cache to MinIO if connected
            if minio_client is not None:
                try:
                    if not minio_client.bucket_exists(bucket):
                        minio_client.make_bucket(bucket)
                    fn = f"b03_{ts.strftime('%Y%m%d_%H%M%S')}.png"
                    obj_name = f"{station_id}/{fn}"
                    img_pil = Image.fromarray((crop * 255.0).astype(np.uint8))
                    buf = io.BytesIO()
                    img_pil.save(buf, format="PNG")
                    buf.seek(0)
                    minio_client.put_object(
                        bucket,
                        obj_name,
                        buf,
                        length=buf.getbuffer().nbytes,
                        content_type="image/png",
                    )
                except Exception:
                    pass

    if len(online_frames) >= 6:
        # If we got at least 6 frames, interpolate / backfill to 12
        frames_list = [f[1] for f in online_frames]
        if len(frames_list) < 12:
            deficit = 12 - len(frames_list)
            frames_list = [frames_list[0]] * deficit + frames_list
        seq = np.stack(frames_list, axis=0)[np.newaxis, :, np.newaxis, :, :]
        logger.info(f"[Satellite Preprocessor] Real B03 geocoded sequence assembled: shape {seq.shape}, mean CI={float(np.mean(seq)):.3f}")

        # Also attempt to cache latest RGB crop for visual display
        if minio_client is not None:
            try:
                rgb_crop = fetch_rgb_crop(timestamps_12[-1], lat, lon, crop_size=64)
                if rgb_crop is not None:
                    buf_rgb = io.BytesIO()
                    rgb_crop.save(buf_rgb, format="PNG")
                    buf_rgb.seek(0)
                    minio_client.put_object(
                        bucket,
                        f"{station_id}_latest.png",
                        buf_rgb,
                        length=buf_rgb.getbuffer().nbytes,
                        content_type="image/png",
                    )
            except Exception:
                pass

        return seq

    # Step 3: Graceful synthetic baseline if NICT network is unreachable
    logger.warning(f"[Satellite Preprocessor] Could not fetch real NICT frames. Using synthetic baseline for '{station_id}'.")
    return generate_synthetic_satellite_sequence()
