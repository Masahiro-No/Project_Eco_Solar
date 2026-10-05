import asyncio
import json

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.model import User
from api.auth.service import require_admin
from api.frame_review.service import rejected_total
from api.jobs.service import JobService
from api.retrain import service
from api.retrain.schema import RetrainStatusResponse
from core.config import settings
from db.database import get_db_session


async def get_retrain_status(
    history_limit: int = Query(30, ge=1, le=100, description="Newest runs per model"),
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
) -> RetrainStatusResponse:
    """Deployed versions, what is pending and the retrain history of the LSTM and the ConvLSTM."""
    pending = {"lstm_scheduled": False, "lstm_running": False, "convlstm_scheduled": False, "convlstm_running": False}
    batch: dict = {}
    try:
        pool = await JobService.get_pool()
        try:
            pending["lstm_scheduled"] = bool(await pool.exists(service.LSTM_SCHEDULED_KEY))
            pending["lstm_running"] = bool(await pool.exists(service.LSTM_LOCK_KEY))
            pending["convlstm_scheduled"] = bool(await pool.exists(service.CONVLSTM_SCHEDULED_KEY))
            pending["convlstm_running"] = bool(await pool.exists(service.CONVLSTM_RUNNING_KEY))
            raw = await pool.get(service.CONVLSTM_STATUS_KEY)
            batch = json.loads(raw) if raw else {}
        finally:
            await pool.close()
    except Exception:  # noqa: BLE001  Redis down: the deployed models and the history are still reported
        pass

    history, history_error = await asyncio.to_thread(service.read_history, history_limit)
    return RetrainStatusResponse(
        retrain_enabled=settings.enable_retrain,
        lstm={**service.deployed_lstm(), "scheduled": pending["lstm_scheduled"], "running": pending["lstm_running"]},
        convlstm={
            **service.deployed_convlstm(),
            "new_scans": batch.get("new_scans"),
            "batch_size": batch.get("batch_size", settings.convlstm_retrain_threshold),
            "newest_scan": batch.get("newest_scan"),
            "checked_at": batch.get("checked_at"),
            "scheduled": pending["convlstm_scheduled"],
            "running": pending["convlstm_running"],
            "rejected_frames_total": await rejected_total(db),
        },
        history=history,
        history_error=history_error,
    )
