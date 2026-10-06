from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class AlertBreakdown(BaseModel):
    green: int = 0
    yellow: int = 0
    red: int = 0


class DashboardSummaryResponse(BaseModel):
    total_power_kw: float
    total_target_kw: float
    total_delta_p_kw: float
    active_stations_count: int
    alert_summary: AlertBreakdown
    last_updated: datetime


class StationDashboardResponse(BaseModel):
    station_id: str
    station_name: str
    latitude: float
    longitude: float
    target_capacity_kw: float
    current_ghi_w_m2: float
    forecast_curve_3h: list[float]
    cloud_trend: str  # cloud impact level: low, medium, high, unknown
    cloud_coverage_now_pct: Optional[float] = None
    estimated_power_kw: float
    delta_p_kw: float
    alert_level: str
    recommendation_text: str
    satellite_image_url: Optional[str] = None
    last_updated: datetime


class AlertFeedItem(BaseModel):
    station_id: str
    station_name: str
    alert_level: str
    event: str
    delta_p_needed_kw: float
    recommendation: str
    timestamp: datetime


class GrafanaLinksResponse(BaseModel):
    grafana_url: str
    operations_dashboard_url: str
