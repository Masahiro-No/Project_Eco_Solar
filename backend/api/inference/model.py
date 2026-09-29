from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    station_id: Mapped[str] = mapped_column(String(50), ForeignKey("stations.id"), index=True, nullable=False)
    predicted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    forecast_horizon_hours: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    
    # Forecast numerical curve (array of 6 floats every 30 mins)
    ghi_forecast_curve: Mapped[list] = mapped_column(JSON, nullable=False)
    
    # Power and reserve values in kW
    estimated_power_kw: Mapped[float] = mapped_column(Float, nullable=False)
    target_power_kw: Mapped[float] = mapped_column(Float, nullable=False)
    delta_p_kw: Mapped[float] = mapped_column(Float, nullable=False)
    
    # Cloud classification
    cloud_trend: Mapped[str] = mapped_column(String(50), nullable=False)  # Clear, Inward, Outward, Overcast
    confidence: Mapped[float] = mapped_column(Float, nullable=False)  # 0.0 to 1.0
    
    # Decision support output
    alert_level: Mapped[str] = mapped_column(String(50), nullable=False)  # Normal, Early Warning, Critical Alert, Recovery
    recommendation_text: Mapped[str] = mapped_column(Text, nullable=False)
    
    satellite_frame_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
