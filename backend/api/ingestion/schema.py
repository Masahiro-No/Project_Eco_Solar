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
    dhi: Optional[float] = None
    clearsky_ghi: float = 0.0
    clearsky_index: float = 0.0
    solar_zenith_angle: float = 90.0
    wind_speed: float = 0.0
    surface_pressure: Optional[float] = None
    cloud_cover: float
    source: str

    model_config = ConfigDict(from_attributes=True)


class DayFrame(BaseModel):
    timestamp: datetime = Field(..., description="Scan time (UTC)")
    cloud_pct: Optional[float] = Field(None, description="Cloud cover in the 5x5 px AOI; null when the sun is too low")
    image_b64: str = Field(..., description="The 64x64 Band 03 PNG, base64")


class ForecastFrame(DayFrame):
    lead_minutes: int = Field(..., description="Minutes after the newest real frame")


class ForecastFrameSet(BaseModel):
    """Frames the ConvLSTM predicted in the newest forecast round (empty when it did not run)."""

    end_time: Optional[datetime] = Field(None, description="Newest real frame the forecast starts from")
    created_at: Optional[datetime] = None
    status: str = Field(..., description="Satellite status of that round: ok | shifted | observed_only | missing | low_sun | night")
    reason: Optional[str] = None
    model_version: Optional[str] = None
    frames: list[ForecastFrame]


class DayFramesResponse(BaseModel):
    station_id: str
    date: str
    timezone: str = "Asia/Bangkok"
    frames: list[DayFrame] = Field(..., description="Real daytime frames of the day, oldest first")
    night_frames: int = Field(..., description="Frames taken with the sun down: black by nature, not returned")
    blank_frames: int = Field(..., description="Scans NICT published as an all-black tile: no observation, not returned")
    forecast: Optional[ForecastFrameSet] = Field(None, description="Only for today; null when no round has stored frames yet")


class IngestionStatusResponse(BaseModel):
    last_sync: Optional[datetime] = None
    open_meteo_status: str = "ok"
    nict_status: str = "ok"
    total_weather_records: int = 0
    total_satellite_frames: int = 0


class CatchupRequest(BaseModel):
    station_id: Optional[str] = Field("ST-001", description="Station ID to catch up (default: ST-001)")
    max_gap_days: Optional[int] = Field(7, ge=1, le=30, description="Maximum days of gap to backfill")


class CatchupResponse(BaseModel):
    status: str
    message: str
    station_id: str
    gap_hours: Optional[float] = 0.0
    records_inserted: int = 0
    latest_timestamp: Optional[str] = None
    from_timestamp: Optional[str] = None
    to_timestamp: Optional[str] = None

