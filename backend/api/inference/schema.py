from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class InferenceRequest(BaseModel):
    station_id: str = Field(default="ST-001", description="ID of registered solar station", example="ST-001")
    target_power_kw: Optional[float] = Field(None, description="Optional target power in kW (uses station spec if omitted)", example=5000.0)
    model_version: str = Field(default="latest", description="Model version in MLflow registry", example="latest")


class InferenceResponse(BaseModel):
    job_id: str
    status: str = "queued"


class PredictionResultData(BaseModel):
    job_id: str
    station_id: str
    station_name: str
    predicted_at: datetime
    forecast_horizon_hours: int = 3
    ghi_forecast_curve: list[float] = Field(..., description="18 points of final GHI (W/m^2) every 10 mins modulated with ConvLSTM cloud index")
    ghi_forecast_lstm_raw: Optional[list[float]] = Field(None, description="18 points of raw GHI from Time-Series LSTM before cloud modulation")
    cloud_indices: Optional[list[float]] = Field(None, description="18 points of Cloud Index (0.0 - 1.0) extracted from Center ROI by ConvLSTM")
    estimated_power_kw: float
    target_power_kw: float
    delta_p_kw: float
    cloud_trend: str  # Clear, Inward, Outward, Overcast
    confidence: float
    alert_level: str  # Normal, Early Warning, Critical Alert, Recovery
    recommendation_text: str
    bess_advisory: Optional[str] = Field(None, description="Specific BESS battery storage advisory derived from cloud motion")
    satellite_image_url: Optional[str] = None
    data_time: Optional[datetime] = Field(None, description="Timestamp of the newest weather observation used as model input")


class InferenceResultResponse(BaseModel):
    job_id: str
    status: str  # "queued" | "in_progress" | "complete" | "not_found"
    result: Optional[PredictionResultData] = None
