from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class StationBase(BaseModel):
    name: str = Field(..., example="Saraburi Solar Farm 1")
    latitude: float = Field(..., ge=-90.0, le=90.0, example=14.5283)
    longitude: float = Field(..., ge=-180.0, le=180.0, example=100.9128)
    panel_area: float = Field(..., gt=0, description="Panel surface area in m^2", example=50000.0)
    efficiency: float = Field(..., gt=0, le=1.0, description="Panel efficiency eta (0.0 to 1.0)", example=0.185)
    target_capacity_kw: float = Field(..., gt=0, description="Target generation capacity in kW", example=10000.0)


class StationCreateRequest(StationBase):
    id: Optional[str] = Field(None, description="Custom ID (e.g. ST-001). Auto-generated if omitted.", example="ST-001")


class StationUpdateRequest(StationBase):
    pass


class StationPatchRequest(BaseModel):
    name: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)
    panel_area: Optional[float] = Field(None, gt=0)
    efficiency: Optional[float] = Field(None, gt=0, le=1.0)
    target_capacity_kw: Optional[float] = Field(None, gt=0)


class StationResponse(StationBase):
    id: str
    is_active: bool
    deleted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    current_pgen_kw: Optional[float] = None
    alert_level: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class NearestStationResponse(BaseModel):
    station_id: str
    name: str
    latitude: float
    longitude: float
    target_capacity_kw: float
    distance_km: float
