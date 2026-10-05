from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


class WeatherHistory(Base):
    __tablename__ = "weather_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    station_id: Mapped[str] = mapped_column(String(50), ForeignKey("stations.id"), index=True, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    
    ghi: Mapped[float] = mapped_column(Float, nullable=False)
    dni: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    dhi: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    clearsky_ghi: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    clearsky_index: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    solar_zenith_angle: Mapped[float] = mapped_column(Float, default=90.0, nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    relative_humidity: Mapped[float] = mapped_column(Float, nullable=False)
    wind_speed: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cloud_cover: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    surface_pressure: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    source: Mapped[str] = mapped_column(String(50), nullable=False)  # "open_meteo" (live), "open_meteo_catchup"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SatelliteFrameMetadata(Base):
    __tablename__ = "satellite_frames"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    station_id: Mapped[str] = mapped_column(String(50), ForeignKey("stations.id"), index=True, nullable=False)
    frame_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    image_url: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
