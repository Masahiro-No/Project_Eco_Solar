import asyncio
import json
from datetime import date as date_type

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.model import User
from api.auth.service import require_admin
from api.frame_review import service
from api.frame_review.schema import (
    ConvLstmStatusResponse,
    FrameItem,
    FrameListResponse,
    FrameReview,
    SubmitReviewsRequest,
    SubmitReviewsResponse,
)
from api.jobs.service import JobService
from api.label_studio.ground_truth import th_day_bounds
from api.stations.service import StationService
from core.config import settings
from db.database import get_db_session


async def _station(db: AsyncSession, station_id: str):
    station = await StationService.get_station_by_id(db, station_id)
    if station is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Station '{station_id}' not found")
    return station


async def list_frames(
    station_id: str = Query(...),
    date: date_type = Query(..., description="Day in Thai time, YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
) -> FrameListResponse:
    """Real daytime satellite frames of one station and day, with automatic hints and the saved reviews."""
    station = await _station(db, station_id)
    try:
        items, night = await asyncio.to_thread(service.read_day_frames, station_id, station.latitude, station.longitude, date)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"Could not read the frame cache: {e}") from None

    start, end = th_day_bounds(date)
    reviews = await service.reviews_for(db, station_id, start, end)
    frames = []
    for it in items:
        r = reviews.get(it["timestamp"])
        frames.append(
            FrameItem(
                timestamp=it["timestamp"],
                cloud_pct=it["cloud_pct"],
                brightness=it["brightness"],
                flags=it["flags"],
                image_b64=it["image_b64"],
                review=FrameReview(status=r.status, reason=r.reason, reviewed_by=r.reviewed_by, reviewed_at=r.reviewed_at) if r else None,
            )
        )
    return FrameListResponse(
        station_id=station_id,
        date=date.isoformat(),
        daytime_frames=len(frames),
        night_frames=night,
        flagged=sum(1 for f in frames if f.flags),
        rejected=sum(1 for f in frames if f.review and f.review.status == "rejected"),
        frames=frames,
    )


async def submit_reviews(
    payload: SubmitReviewsRequest,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_admin),
) -> SubmitReviewsResponse:
    """Save the reviewer's verdicts. Rejected frames are left out of the next ConvLSTM retrain."""
    await _station(db, payload.station_id)
    counts = await service.save_reviews(db, payload.station_id, payload.items, reviewer=user.email)
    return SubmitReviewsResponse(station_id=payload.station_id, **counts)


async def convlstm_status(
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
) -> ConvLstmStatusResponse:
    """Batch counter of new satellite scans, the deployed ConvLSTM and the result of the last retrain."""
    batch, last = {}, None
    try:
        pool = await JobService.get_pool()
        try:
            raw_status, raw_last = await pool.get(service.STATUS_KEY), await pool.get(service.LAST_RESULT_KEY)
        finally:
            await pool.close()
        batch = json.loads(raw_status) if raw_status else {}
        last = json.loads(raw_last) if raw_last else None
    except Exception:  # noqa: BLE001  Redis down: the deployed model is still reported
        pass
    return ConvLstmStatusResponse(
        retrain_enabled=settings.enable_retrain,
        batch_size=batch.get("batch_size", settings.convlstm_retrain_threshold),
        new_scans=batch.get("new_scans"),
        newest_scan=batch.get("newest_scan"),
        checked_at=batch.get("checked_at"),
        last_result=last,
        rejected_frames_total=await service.rejected_total(db),
        **service.deployed_convlstm(),
    )
