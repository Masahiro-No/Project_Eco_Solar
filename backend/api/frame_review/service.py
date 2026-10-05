"""Human review of the real satellite frames the ConvLSTM is retrained on.

The ConvLSTM learns to predict the next frames, so its "labels" are the real frames themselves. What a
person can add is whether a frame is a valid observation: a frame marked as rejected is left out of the
training sequences (service/training/retrain_convlstm.py reads the satellite_frame_reviews table).

The automatic flags only point the reviewer to frames worth a look; they never reject a frame by themselves.
"""

import base64
import io
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.frame_review.model import SatelliteFrameReview
from api.ingestion.solar_calculator import SolarCalculator
from api.label_studio.ground_truth import th_day_bounds
from api.storage.service import StorageService

CACHE_BUCKET = "satellite-cache"
MIN_SUN_ELEVATION_DEG = 6.0     # below this a visible-band frame is dark by nature and is not reviewed
MIN_COS_ZENITH_CLOUD = 0.30     # same limit as the cloud cover in service/workers/cloud_coverage.py
CLOUD_THRESHOLD = 0.25
AOI = slice(30, 35)             # the 5x5 px box at the centre of the 64x64 crop
JUMP_BRIGHTNESS = 0.15          # change of sun-normalised brightness against both neighbours that is worth a look

# Redis keys written by the ingestion worker and the trainer (service/workers/convlstm_batch.py)
STATUS_KEY = "convlstm:retrain:status"
LAST_RESULT_KEY = "convlstm:retrain:last_result"
CONVLSTM_META = Path("/app/model/convlstm/cloud_seq2seq_metadata.json")


def analyse_frame(png: bytes, lat: float, lon: float, ts: datetime) -> Optional[dict[str, Any]]:
    """Statistics and automatic flags of one daytime frame; None for a frame taken with the sun down."""
    zenith_deg, elevation_deg = SolarCalculator.calculate_solar_position(lat, lon, ts)
    if elevation_deg < MIN_SUN_ELEVATION_DEG:
        return None
    arr = np.asarray(Image.open(io.BytesIO(png)).convert("L"), dtype=np.float32) / 255.0
    cos_z = math.cos(math.radians(zenith_deg))

    flags = []
    zero_share = float((arr == 0.0).mean())
    if zero_share == 1.0:
        flags.append("blank")          # NICT's "no image" tile
    elif zero_share > 0.05:
        flags.append("partial")        # part of the tile is missing
    if float((arr >= 0.98).mean()) > 0.20:
        flags.append("saturated")
    return {
        "brightness": round(float(arr.mean()), 4),
        "rho": float(arr.mean() / cos_z),
        "cloud_pct": round(100.0 * float((arr[AOI, AOI] / cos_z >= CLOUD_THRESHOLD).mean()), 1) if cos_z >= MIN_COS_ZENITH_CLOUD else None,
        "flags": flags,
    }


def flag_jumps(items: list[dict[str, Any]]) -> None:
    """Add 'jump' to a frame whose brightness differs strongly from the frames 10 minutes before and after."""
    by_time = {it["timestamp"]: it for it in items}
    step = timedelta(minutes=10)
    for it in items:
        before, after = by_time.get(it["timestamp"] - step), by_time.get(it["timestamp"] + step)
        if before is None or after is None or "blank" in it["flags"]:
            continue
        if "blank" in before["flags"] or "blank" in after["flags"]:
            continue
        if min(abs(it["rho"] - before["rho"]), abs(it["rho"] - after["rho"])) > JUMP_BRIGHTNESS:
            it["flags"].append("jump")


def read_day_frames(station_id: str, lat: float, lon: float, day: date) -> tuple[list[dict[str, Any]], int]:
    """Daytime frames of one Thai day from the frame cache (blocking: call in a thread). Returns (frames, night count)."""
    start, end = th_day_bounds(day)
    client = StorageService().client
    names = set()
    for utc_day in {start.date(), (end - timedelta(seconds=1)).date()}:
        for obj in client.list_objects(CACHE_BUCKET, prefix=f"{station_id}/b03_{utc_day:%Y%m%d}", recursive=True):
            names.add(obj.object_name)

    items, night = [], 0
    for name in sorted(names):
        try:
            ts = datetime.strptime(name.rsplit("b03_", 1)[1][:15], "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if not (start <= ts < end):
            continue
        resp = client.get_object(CACHE_BUCKET, name)
        try:
            png = resp.read()
        finally:
            resp.close()
            resp.release_conn()
        stats = analyse_frame(png, lat, lon, ts)
        if stats is None:
            night += 1
            continue
        items.append({"timestamp": ts, "image_b64": base64.b64encode(png).decode("ascii"), **stats})
    flag_jumps(items)
    return items, night


async def reviews_for(db: AsyncSession, station_id: str, start: datetime, end: datetime) -> dict[datetime, SatelliteFrameReview]:
    rows = (
        await db.execute(
            select(SatelliteFrameReview).where(
                SatelliteFrameReview.station_id == station_id,
                SatelliteFrameReview.frame_timestamp >= start,
                SatelliteFrameReview.frame_timestamp < end,
            )
        )
    ).scalars().all()
    return {r.frame_timestamp.astimezone(timezone.utc): r for r in rows}


async def save_reviews(db: AsyncSession, station_id: str, items: list, reviewer: str) -> dict[str, int]:
    counts = {"saved": 0, "rejected": 0, "accepted": 0}
    for item in items:
        ts = item.timestamp.astimezone(timezone.utc) if item.timestamp.tzinfo else item.timestamp.replace(tzinfo=timezone.utc)
        ts = ts.replace(second=0, microsecond=0)
        existing = (
            await db.execute(
                select(SatelliteFrameReview).where(
                    SatelliteFrameReview.station_id == station_id, SatelliteFrameReview.frame_timestamp == ts
                )
            )
        ).scalar_one_or_none()
        reason = item.reason if item.status == "rejected" else None
        if existing is None:
            db.add(SatelliteFrameReview(station_id=station_id, frame_timestamp=ts, status=item.status, reason=reason, reviewed_by=reviewer))
        else:
            existing.status, existing.reason, existing.reviewed_by = item.status, reason, reviewer
        counts["saved"] += 1
        counts[item.status] += 1
    await db.commit()
    return counts


async def rejected_total(db: AsyncSession) -> int:
    return int((await db.execute(select(func.count()).select_from(SatelliteFrameReview).where(SatelliteFrameReview.status == "rejected"))).scalar_one())


def deployed_convlstm() -> dict[str, Optional[str]]:
    try:
        meta = json.loads(CONVLSTM_META.read_text(encoding="utf-8"))
        return {"model_version": str(meta.get("version")), "retrained_at": meta.get("retrained_at")}
    except (OSError, ValueError):
        return {"model_version": None, "retrained_at": None}
