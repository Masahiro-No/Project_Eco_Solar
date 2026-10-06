from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dashboard.schema import (
    AlertBreakdown,
    AlertFeedItem,
    DashboardSummaryResponse,
    GrafanaLinksResponse,
    StationDashboardResponse,
)
from api.inference.model import Prediction
from core.config import settings

GRAFANA_DASHBOARD_UID = "solardss-operations"  # uid in observability/grafana/provisioning/dashboards
from api.stations.service import StationService


class DashboardService:
    @staticmethod
    async def get_summary(db: AsyncSession) -> DashboardSummaryResponse:
        """Aggregate total power, targets, and alerts across all active stations."""
        active_stations = await StationService.get_all_stations(db, include_archived=False)
        
        total_power = 0.0
        total_target = 0.0
        total_delta_p = 0.0
        green_count = 0
        yellow_count = 0
        red_count = 0

        for station in active_stations:
            total_target += station.target_capacity_kw

            # Query latest prediction
            pred_stmt = (
                select(Prediction)
                .where(Prediction.station_id == station.id, Prediction.source == "model")
                .order_by(Prediction.predicted_at.desc())
                .limit(1)
            )
            pred_res = await db.execute(pred_stmt)
            latest_pred = pred_res.scalar_one_or_none()

            if latest_pred:
                total_power += latest_pred.estimated_power_kw
                total_delta_p += latest_pred.delta_p_kw
                if latest_pred.alert_level == "critical":
                    red_count += 1
                elif latest_pred.alert_level in ("watch", "warning"):
                    yellow_count += 1
                else:  # normal, night
                    green_count += 1
            # a station without a model forecast yet is not counted in any colour

        return DashboardSummaryResponse(
            total_power_kw=round(total_power, 2),
            total_target_kw=round(total_target, 2),
            total_delta_p_kw=round(total_delta_p, 2),
            active_stations_count=len(active_stations),
            alert_summary=AlertBreakdown(green=green_count, yellow=yellow_count, red=red_count),
            last_updated=datetime.now(timezone.utc),
        )

    @staticmethod
    async def get_station_dashboard(db: AsyncSession, station_id: str) -> StationDashboardResponse:
        """Fetch dashboard detail for a specific station."""
        station = await StationService.get_station_by_id(db, station_id)

        # Query latest prediction
        pred_stmt = (
            select(Prediction)
            .where(Prediction.station_id == station.id, Prediction.source == "model")
            .order_by(Prediction.predicted_at.desc())
            .limit(1)
        )
        pred_res = await db.execute(pred_stmt)
        latest_pred = pred_res.scalar_one_or_none()

        if latest_pred is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No model prediction available yet for station '{station_id}'.",
            )

        curve = latest_pred.ghi_forecast_curve or []
        return StationDashboardResponse(
            station_id=station.id,
            station_name=station.name,
            latitude=station.latitude,
            longitude=station.longitude,
            target_capacity_kw=station.target_capacity_kw,
            current_ghi_w_m2=curve[0] if curve else 0.0,
            forecast_curve_3h=curve,
            cloud_trend=latest_pred.cloud_trend,
            cloud_coverage_now_pct=latest_pred.cloud_coverage_now_pct,
            estimated_power_kw=latest_pred.estimated_power_kw,
            delta_p_kw=latest_pred.delta_p_kw,
            alert_level=latest_pred.alert_level,
            recommendation_text=latest_pred.recommendation_text,
            satellite_image_url=latest_pred.satellite_frame_url,
            last_updated=latest_pred.predicted_at,
        )

    @staticmethod
    async def get_active_alerts(db: AsyncSession, severity: Optional[str] = None) -> list[AlertFeedItem]:
        """Fetch alert feeds across stations."""
        active_stations = await StationService.get_all_stations(db, include_archived=False)
        alerts: list[AlertFeedItem] = []

        for station in active_stations:
            pred_stmt = (
                select(Prediction)
                .where(Prediction.station_id == station.id, Prediction.source == "model")
                .order_by(Prediction.predicted_at.desc())
                .limit(1)
            )
            pred_res = await db.execute(pred_stmt)
            pred = pred_res.scalar_one_or_none()

            if pred and pred.alert_level in ("watch", "warning", "critical"):
                if severity == "high" and pred.alert_level != "critical":
                    continue
                alerts.append(
                    AlertFeedItem(
                        station_id=station.id,
                        station_name=station.name,
                        alert_level=pred.alert_level,
                        event=f"cloud_impact:{pred.cloud_trend}",
                        delta_p_needed_kw=pred.reserve_kw if pred.reserve_kw is not None else pred.delta_p_kw,
                        recommendation=pred.recommendation_text,
                        timestamp=pred.predicted_at,
                    )
                )

        return alerts

    @staticmethod
    def get_grafana_links() -> GrafanaLinksResponse:
        """Where Grafana is and the one dashboard this project provisions (observability/grafana/provisioning)."""
        base = settings.grafana_url.rstrip("/")
        return GrafanaLinksResponse(grafana_url=base, operations_dashboard_url=f"{base}/d/{GRAFANA_DASHBOARD_UID}")
