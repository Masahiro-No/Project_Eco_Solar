"""Persistence helpers for real model predictions.

The inference worker has no database access, so its result (stored by ARQ in Redis) is
saved to the `predictions` table by whoever collects it: the ingestion worker's
collector cron, or `GET /inference/result/{job_id}`. Saving is idempotent per job_id.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.inference.model import Prediction
from api.stations.model import Station

MODEL_SOURCE = "model"          # real ONNX forecast fed with real weather data
DEGRADED_SOURCE = "degraded"    # worker fell back to simulation / nominal inputs (never served as real)


def parse_dt(value: Any) -> Optional[datetime]:
    """Parse ISO strings/datetimes into timezone-aware UTC datetimes."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def save_model_prediction(
    db: AsyncSession,
    job_id: str,
    result: dict[str, Any],
    data_time: Optional[datetime] = None,
    satellite_frame_url: Optional[str] = None,
) -> Optional[Prediction]:
    """Insert the worker result as a Prediction row (no-op if job_id already saved)."""
    existing = (await db.execute(select(Prediction).where(Prediction.job_id == job_id))).scalars().first()
    if existing:
        return existing

    station_id = result.get("station_id")
    curve = result.get("ghi_forecast_curve")
    if not station_id or not curve:
        return None
    station = (await db.execute(select(Station).where(Station.id == station_id))).scalar_one_or_none()
    if station is None:
        return None

    is_real = result.get("lstm_source") == "onnx" and result.get("input_source") == "weather_features"

    pred = Prediction(
        job_id=job_id,
        station_id=station_id,
        predicted_at=parse_dt(result.get("predicted_at")) or datetime.now(timezone.utc),
        forecast_horizon_hours=int(result.get("forecast_horizon_hours", 3)),
        ghi_forecast_curve=[float(v) for v in curve],
        estimated_power_kw=float(result["estimated_power_kw"]),
        target_power_kw=float(result["target_power_kw"]),
        delta_p_kw=float(result["delta_p_kw"]),
        cloud_trend=str(result["cloud_trend"]),
        confidence=float(result["confidence"]),
        alert_level=str(result["alert_level"]),
        recommendation_text=str(result["recommendation_text"]),
        satellite_frame_url=satellite_frame_url or f"/api/storage/download/satellite-cache/{station_id}_latest.png",
        source=MODEL_SOURCE if is_real else DEGRADED_SOURCE,
        data_time=data_time,
    )
    db.add(pred)
    await db.commit()
    return pred
