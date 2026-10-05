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

MODEL_SOURCE = "model"  # real ONNX forecast fed with real weather data


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


def _floats(values: Any) -> Optional[list]:
    """List of floats, keeping None where the worker had no value for a step."""
    if values is None:
        return None
    return [None if v is None else float(v) for v in values]


async def save_model_prediction(
    db: AsyncSession,
    job_id: str,
    result: dict[str, Any],
    data_time: Optional[datetime] = None,
    satellite_frame_url: Optional[str] = None,
) -> Optional[Prediction]:
    """Insert the worker result as a Prediction row (no-op if job_id already saved).

    Only results that come from the deployed LSTM fed with real weather features are stored;
    anything else returns None so it can never be served as a forecast.
    """
    existing = (await db.execute(select(Prediction).where(Prediction.job_id == job_id))).scalars().first()
    if existing:
        return existing

    station_id = result.get("station_id")
    curve = result.get("ghi_forecast_curve")
    if not station_id or not curve:
        return None
    if result.get("lstm_source") != "onnx" or result.get("input_source") != "weather_features":
        return None
    station = (await db.execute(select(Station).where(Station.id == station_id))).scalar_one_or_none()
    if station is None:
        return None

    reserve = result.get("reserve_kw")
    cloud_now = result.get("cloud_coverage_now_pct")
    loss_now = result.get("sat_ghi_loss_now_pct")
    pred = Prediction(
        job_id=job_id,
        station_id=station_id,
        predicted_at=parse_dt(result.get("predicted_at")) or datetime.now(timezone.utc),
        forecast_horizon_hours=int(result.get("forecast_horizon_hours", 3)),
        ghi_forecast_curve=[float(v) for v in curve],
        ghi_forecast_lstm_raw=_floats(result.get("ghi_forecast_lstm_raw")),
        blend_weight=_floats(result.get("blend_weight")),
        estimated_power_kw=float(result["estimated_power_kw"]),
        target_power_kw=float(result["target_power_kw"]),
        delta_p_kw=float(result["delta_p_kw"]),
        reserve_kw=float(reserve) if reserve is not None else None,
        cloud_trend=str(result.get("cloud_impact_level") or "unknown"),
        cloud_coverage_pct=_floats(result.get("cloud_coverage_pct")),
        cloud_coverage_now_pct=float(cloud_now) if cloud_now is not None else None,
        sat_ghi_loss_pct=_floats(result.get("sat_ghi_loss_pct")),
        sat_ghi_loss_now_pct=float(loss_now) if loss_now is not None else None,
        target_profile_kw=_floats(result.get("target_profile_kw")),
        ghi_forecast_lower=_floats(result.get("ghi_forecast_lower")),
        ghi_forecast_upper=_floats(result.get("ghi_forecast_upper")),
        satellite_status=result.get("satellite_status"),
        satellite_lag_minutes=result.get("satellite_lag_minutes"),
        alert_level=str(result["alert_level"]),
        recommendation_text=str(result["recommendation_text"]),
        is_night=bool(result.get("is_night", False)),
        satellite_frame_url=satellite_frame_url or f"/api/storage/download/satellite-cache/{station_id}_latest.png",
        model_version=result.get("model_version"),
        source=MODEL_SOURCE,
        data_time=data_time or parse_dt(result.get("forecast_origin")),
    )
    db.add(pred)
    await db.commit()
    return pred
