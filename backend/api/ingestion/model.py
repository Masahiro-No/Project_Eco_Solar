from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


# One stored row per key. The rounds check before they insert, but two writers at the same moment (a round and a
# manual catch-up) passed that check together and stored rows twice; the database now refuses the second one.
WEATHER_KEY = ("station_id", "timestamp", "source")
FRAME_KEY = ("station_id", "frame_timestamp")


class WeatherHistory(Base):
    __tablename__ = "weather_history"
    __table_args__ = (UniqueConstraint(*WEATHER_KEY, name="uq_weather_history_station_time_source"),)

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
    __table_args__ = (UniqueConstraint(*FRAME_KEY, name="uq_satellite_frames_station_time"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    station_id: Mapped[str] = mapped_column(String(50), ForeignKey("stations.id"), index=True, nullable=False)
    frame_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    image_url: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


UNIQUE_RULES = (
    (WeatherHistory, WEATHER_KEY, "uq_weather_history_station_time_source"),
    (SatelliteFrameMetadata, FRAME_KEY, "uq_satellite_frames_station_time"),
)


def insert_once(db, objects: list):
    """INSERT for new WeatherHistory / SatelliteFrameMetadata objects that leaves an already stored key alone.

    Returns the statement; its result's rowcount is the number of rows really stored.
    """
    model = type(objects[0])
    key = next(k for m, k, _ in UNIQUE_RULES if m is model)
    columns = [c.name for c in model.__table__.columns if c.name not in ("id", "created_at")]
    rows = [{name: getattr(obj, name) for name in columns} for obj in objects]
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    return insert(model).values(rows).on_conflict_do_nothing(index_elements=list(key))
