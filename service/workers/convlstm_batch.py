"""Real satellite frames available for ConvLSTM retraining, and the "new batch is complete" rule.

The ConvLSTM is retrained only on real Himawari Band 03 frames: the 64x64 crops that the inference
worker caches in MinIO ('satellite-cache/<station_id>/b03_<YYYYmmdd_HHMMSS>.png').

Batch rule: one "image" is one satellite scan time (every station gets a crop of the same scan).
Only daytime scans count, because a night frame is black and carries no cloud information.
A retrain is due when the number of new daytime scans since the last retrain reaches the batch size.

This module has no torch dependency so the ingestion worker can use it for the trigger.
"""

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from service.workers.satellite_preprocessor import CACHE_BUCKET
from service.workers.solar_geometry import cos_zenith_at

FRAME_INTERVAL = timedelta(minutes=10)

# Sun at least ~6 degrees above the horizon: darker frames show no usable cloud texture
MIN_COS_ZENITH_TRAIN = float(os.environ.get("CONVLSTM_MIN_COS_ZENITH", "0.10"))

# Redis keys shared by the trigger (ingestion worker) and the trainer
LAST_FRAME_KEY = "convlstm:retrain:last_frame_time"   # newest scan time covered by the last retrain attempt
SCHEDULED_KEY = "convlstm:retrain:scheduled"          # a retrain job is queued or running
RUNNING_KEY = "convlstm:retrain:running"
STATUS_KEY = "convlstm:retrain:status"            # JSON: what the trigger saw in the last ingestion round
LAST_RESULT_KEY = "convlstm:retrain:last_result"  # JSON: summary of the last retrain run

_FRAME_RE = re.compile(r"^(?P<station>[^/]+)/b03_(?P<ts>\d{8}_\d{6})\.png$")


def list_cached_scans(minio_client) -> dict[str, list[datetime]]:
    """Scan times of the real frames in the cache, per station, sorted."""
    scans: dict[str, list[datetime]] = {}
    for obj in minio_client.list_objects(CACHE_BUCKET, recursive=True):
        m = _FRAME_RE.match(obj.object_name)
        if not m:
            continue
        ts = datetime.strptime(m["ts"], "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
        scans.setdefault(m["station"], []).append(ts)
    for times in scans.values():
        times.sort()
    return scans


def is_daytime(ts: datetime, lat: float, lon: float, min_cos: float = MIN_COS_ZENITH_TRAIN) -> bool:
    return cos_zenith_at(lat, lon, ts) >= min_cos


def daytime_scans(
    scans: dict[str, list[datetime]],
    coords: dict[str, tuple[float, float]],
    min_cos: float = MIN_COS_ZENITH_TRAIN,
) -> dict[str, list[datetime]]:
    """Keep the scans taken in daylight at their station. Stations without coordinates are dropped."""
    out: dict[str, list[datetime]] = {}
    for station_id, times in scans.items():
        if station_id not in coords:
            continue
        lat, lon = coords[station_id]
        kept = [ts for ts in times if is_daytime(ts, lat, lon, min_cos)]
        if kept:
            out[station_id] = kept
    return out


def batch_status(
    scans: dict[str, list[datetime]],
    coords: dict[str, tuple[float, float]],
    since: Optional[datetime],
    batch_size: int,
) -> dict:
    """How many new daytime scans arrived after `since`, and whether a retrain is due."""
    day = daytime_scans(scans, coords)
    all_times = sorted({ts for times in day.values() for ts in times})
    new_times = [ts for ts in all_times if since is None or ts > since]
    return {
        "new_scans": len(new_times),
        "batch_size": batch_size,
        "due": len(new_times) >= batch_size,
        "since": since.isoformat() if since else None,
        "newest_scan": all_times[-1].isoformat() if all_times else None,
        "daytime_scans_total": len(all_times),
        "stations": {station_id: len(times) for station_id, times in sorted(day.items())},
    }


def find_sequences(
    times: list[datetime],
    length: int,
    stride: int = 1,
) -> list[datetime]:
    """Start times of runs of `length` consecutive 10-minute scans (no gap inside a run)."""
    have = set(times)
    starts: list[datetime] = []
    last_start: Optional[datetime] = None
    for ts in times:
        if last_start is not None and ts < last_start + stride * FRAME_INTERVAL:
            continue
        if all(ts + k * FRAME_INTERVAL in have for k in range(length)):
            starts.append(ts)
            last_start = ts
    return starts


def parse_time(value) -> Optional[datetime]:
    """Redis/JSON value -> aware UTC datetime (None when empty or unreadable)."""
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode()
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
