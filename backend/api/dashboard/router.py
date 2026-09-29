from fastapi import APIRouter, status

from api.dashboard.controller import (
    get_dashboard_alerts,
    get_dashboard_summary,
    get_grafana_links,
    get_station_dashboard,
)
from api.dashboard.schema import (
    AlertFeedItem,
    DashboardSummaryResponse,
    GrafanaLinksResponse,
    StationDashboardResponse,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

router.add_api_route(
    "/summary",
    get_dashboard_summary,
    methods=["GET"],
    response_model=DashboardSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="System-wide Dashboard Overview (KPI Cards)",
)
router.add_api_route(
    "/alerts",
    get_dashboard_alerts,
    methods=["GET"],
    response_model=list[AlertFeedItem],
    status_code=status.HTTP_200_OK,
    summary="Real-time Alert Feeds for Critical / Warning Stations",
)
router.add_api_route(
    "/grafana-links",
    get_grafana_links,
    methods=["GET"],
    response_model=GrafanaLinksResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Observability Grafana Dashboard Links",
)
router.add_api_route(
    "/station/{station_id}",
    get_station_dashboard,
    methods=["GET"],
    response_model=StationDashboardResponse,
    status_code=status.HTTP_200_OK,
    summary="Station-Specific Dashboard Detail (Forecast Curve + Cloud Trend)",
)
