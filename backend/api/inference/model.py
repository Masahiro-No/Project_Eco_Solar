from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    station_id: Mapped[str] = mapped_column(String(50), ForeignKey("stations.id"), index=True, nullable=False)
    predicted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    forecast_horizon_hours: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    # Final GHI forecast (W/m2), 18 steps of 10 minutes: LSTM blended with the satellite cloud forecast
    ghi_forecast_curve: Mapped[list] = mapped_column(JSON, nullable=False)
    # LSTM forecast before blending, same steps
    ghi_forecast_lstm_raw: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # Weight of the satellite branch per step (0 = LSTM only)
    blend_weight: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Power and reserve values in kW (computed from the blended GHI)
    estimated_power_kw: Mapped[float] = mapped_column(Float, nullable=False)
    target_power_kw: Mapped[float] = mapped_column(Float, nullable=False)
    delta_p_kw: Mapped[float] = mapped_column(Float, nullable=False)   # largest shortfall in the horizon, 0 if none
    reserve_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # shortfall + uncertainty buffer

    # Cloud cover in the AOI around the station
    cloud_trend: Mapped[str] = mapped_column(String(50), nullable=False)  # impact level: low, medium, high, unknown
    cloud_coverage_pct: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)       # forecast per step, null = no satellite
    cloud_coverage_now_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # newest real frame
    sat_ghi_loss_pct: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)          # expected loss of GHI per step from the satellite branch
    sat_ghi_loss_now_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_profile_kw: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)         # target that follows the sun, per step
    satellite_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)  # ok, shifted, observed_only, missing, low_sun, night
    satellite_lag_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # legacy column, no longer written

    # Decision support output
    alert_level: Mapped[str] = mapped_column(String(50), nullable=False)  # night, normal, watch, warning, critical
    recommendation_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_night: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    satellite_frame_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    # 'model' = produced by the inference worker (real ONNX run). NULL = legacy row from before real predictions.
    source: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    # Timestamp of the newest weather observation the model was fed with
    data_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
