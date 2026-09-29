from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class IngestTriggerRequest(BaseModel):
    station_id: Optional[str] = Field("ST-001", description="Station ID to fetch data for (all if None)")


class IngestTriggerResponse(BaseModel):
    job_id: str
    status: str = "fetching"
    message: str


class SatelliteFrameItem(BaseModel):
    frame_no: int
    timestamp: datetime
    image_url: str

    model_config = ConfigDict(from_attributes=True)


class WeatherRecentItem(BaseModel):
    timestamp: datetime
    temperature: float
    relative_humidity: float
    ghi: float
    dni: float
    clearsky_ghi: float = 0.0
    clearsky_index: float = 0.0
    solar_zenith_angle: float = 90.0
    cloud_cover: float
    source: str

    model_config = ConfigDict(from_attributes=True)


class IngestionStatusResponse(BaseModel):
    last_sync: Optional[datetime] = None
    open_meteo_status: str = "ok"
    nict_status: str = "ok"
    total_weather_records: int = 0
    total_satellite_frames: int = 0
