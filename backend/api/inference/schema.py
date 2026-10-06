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
    ghi_forecast_curve: list[float] = Field(..., description="Final GHI (W/m^2) per 10-minute step: LSTM blended with the satellite cloud forecast")
    ghi_forecast_lstm_raw: Optional[list[float]] = Field(None, description="GHI from the time-series LSTM before blending, same steps")
    blend_weight: Optional[list[float]] = Field(None, description="Weight of the satellite branch per step (0 = LSTM only)")
    cloud_coverage_pct: Optional[list[Optional[float]]] = Field(None, description="Forecast cloud cover (%) in the AOI per step; null where no satellite forecast covers the step")
    cloud_coverage_now_pct: Optional[float] = Field(None, description="Cloud cover (%) in the AOI on the newest real satellite frame")
    sat_ghi_loss_pct: Optional[list[Optional[float]]] = Field(None, description="Expected loss of GHI (%) against clear sky per step, from the satellite branch")
    sat_ghi_loss_now_pct: Optional[float] = Field(None, description="Expected loss of GHI (%) on the newest real satellite frame")
    sat_calibration_verified: Optional[bool] = Field(None, description="True when the satellite-to-irradiance relation was fitted on, or checked against, measured GHI of this station; false = applied without a local check")
    sat_calibration_check: Optional[dict] = Field(None, description="When verified: {fitted, pairs, mae} - fitted on this station, or the line of another station checked here (error in clear-sky index)")
    target_profile_kw: Optional[list[float]] = Field(None, description="Target per step: min(P_target, share of the clear-sky output at that time)")
    ghi_forecast_lower: Optional[list[float]] = Field(None, description="Lower edge of the typical error range: forecast - RMSE of the model at that lead time")
    ghi_forecast_upper: Optional[list[float]] = Field(None, description="Upper edge of the typical error range, at most 1.2 x clear-sky GHI")
    cloud_impact_level: Optional[str] = Field(None, description="low | medium | high from the expected loss of GHI (10% / 30%); null when there is no satellite information")
    satellite_status: Optional[str] = Field(None, description="ok | shifted | gap_skipped | observed_only | missing | low_sun | night | model_unavailable")
    satellite_lag_minutes: Optional[int] = Field(None, description="Age of the newest satellite frame relative to the forecast origin")
    is_night: Optional[bool] = None
    estimated_power_kw: float = Field(..., description="P_gen at the first forecast step, from the blended GHI")
    target_power_kw: float
    delta_p_kw: float = Field(..., description="Largest shortfall against the target in the horizon (0 if the target is met)")
    reserve_kw: Optional[float] = Field(None, description="Recommended reserve: shortfall plus the forecast-uncertainty buffer")
    cloud_trend: str = Field(..., description="Same as cloud_impact_level ('unknown' when null); kept for older clients")
    alert_level: str  # night, normal, watch, warning, critical
    recommendation_text: str
    satellite_image_url: Optional[str] = None
    model_version: Optional[str] = None
    data_time: Optional[datetime] = Field(None, description="Timestamp of the newest weather observation used as model input")


class InferenceResultResponse(BaseModel):
    job_id: str
    status: str  # "queued" | "in_progress" | "complete" | "not_found"
    result: Optional[PredictionResultData] = None


class AlignedForecastPoint(BaseModel):
    timestamp: datetime  # ช่อง 10 นาที (UTC)
    predicted_ghi: Optional[float] = Field(None, description="ค่าพยากรณ์สุดท้ายของช่องเวลานี้ (LSTM รวมกับภาพดาวเทียม, รอบพยากรณ์ล่าสุด)")
    predicted_ghi_lstm: Optional[float] = Field(None, description="ค่าพยากรณ์ของ LSTM อย่างเดียวในรอบเดียวกัน")
    weather_ghi: Optional[float] = Field(None, description="GHI ใน weather_history (ค่าประมาณจาก API)")
    label_ghi: Optional[float] = Field(None, description="GHI จริงที่ label ไว้แล้วใน Label Studio")
    clearsky_ghi: Optional[float] = Field(None, description="GHI กรณีฟ้าใสของช่องเวลานี้ (จาก weather_history)")
    forecast_ghi: Optional[float] = Field(None, description="เส้นสำหรับกราฟทั้งวัน: อดีต = รอบล่าสุดที่ทำนายล่วงหน้าอย่างน้อย lead_minutes, อนาคต = รอบล่าสุด")
    forecast_ghi_lstm: Optional[float] = Field(None, description="LSTM อย่างเดียวของรอบเดียวกับ forecast_ghi")
    forecast_lead_minutes: Optional[int] = Field(None, description="forecast_ghi ถูกทำนายไว้ล่วงหน้ากี่นาที")
    forecast_target_kw: Optional[float] = Field(None, description="เป้ากำลังผลิตของช่องเวลานี้ในรอบเดียวกัน")
    forecast_cloud_pct: Optional[float] = Field(None, description="% เมฆใน AOI ที่ทำนายไว้ในรอบเดียวกัน")
    forecast_sat_loss_pct: Optional[float] = Field(None, description="แสงที่คาดว่าลด (%) จากฝั่งดาวเทียมในรอบเดียวกัน")


class PredictionsByDateResponse(BaseModel):
    station_id: str
    date: str
    timezone: str = "Asia/Bangkok"
    prediction_runs: int
    label_count: int
    matched_label_count: int
    mae_vs_label: Optional[float] = None
    mae_lstm_vs_label: Optional[float] = Field(None, description="MAE ของ LSTM อย่างเดียว บนช่องเวลาเดียวกับ mae_vs_label")
    label_error: Optional[str] = Field(None, description="ถ้าอ่าน label จาก Label Studio ไม่ได้ จะบอกสาเหตุที่นี่")
    lead_minutes: Optional[int] = Field(None, description="ระยะพยากรณ์ที่ขอสำหรับกราฟทั้งวัน (null = รอบล่าสุดทุกช่อง)")
    view_matched_label_count: int = Field(0, description="ช่องเวลาที่ผ่านมาแล้วซึ่งมีทั้ง forecast_ghi และค่าจริง")
    view_mae_vs_label: Optional[float] = Field(None, description="MAE ของ forecast_ghi เทียบกับค่าจริง ที่ระยะพยากรณ์ที่ขอ")
    view_mae_lstm_vs_label: Optional[float] = Field(None, description="MAE ของ LSTM อย่างเดียว บนช่องเวลาเดียวกัน")
    points: list[AlignedForecastPoint]

