from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dashboard.schema import (
    AlertBreakdown,
    AlertFeedItem,
    DashboardSummaryResponse,
    GrafanaLinksResponse,
    StationDashboardResponse,
)
from api.inference.decision_engine import evaluate_decision_support
from api.inference.model import Prediction
from api.stations.model import Station
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
                .where(Prediction.station_id == station.id)
                .order_by(Prediction.predicted_at.desc())
                .limit(1)
            )
            pred_res = await db.execute(pred_stmt)
            latest_pred = pred_res.scalar_one_or_none()

            if latest_pred:
                total_power += latest_pred.estimated_power_kw
                total_delta_p += latest_pred.delta_p_kw
                if latest_pred.alert_level == "Critical Alert":
                    red_count += 1
                elif latest_pred.alert_level in ("Early Warning", "Steady Low"):
                    yellow_count += 1
                else:
                    green_count += 1
            else:
                # Default baseline if no prediction run yet
                green_count += 1

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
            .where(Prediction.station_id == station.id)
            .order_by(Prediction.predicted_at.desc())
            .limit(1)
        )
        pred_res = await db.execute(pred_stmt)
        latest_pred = pred_res.scalar_one_or_none()

        if latest_pred:
            current_ghi = latest_pred.ghi_forecast_curve[0] if latest_pred.ghi_forecast_curve else 500.0
            return StationDashboardResponse(
                station_id=station.id,
                station_name=station.name,
                latitude=station.latitude,
                longitude=station.longitude,
                target_capacity_kw=station.target_capacity_kw,
                current_ghi_w_m2=current_ghi,
                forecast_curve_3h=latest_pred.ghi_forecast_curve,
                cloud_trend=latest_pred.cloud_trend,
                confidence=latest_pred.confidence,
                estimated_power_kw=latest_pred.estimated_power_kw,
                delta_p_kw=latest_pred.delta_p_kw,
                alert_level=latest_pred.alert_level,
                recommendation_text=latest_pred.recommendation_text,
                satellite_image_url=latest_pred.satellite_frame_url,
                last_updated=latest_pred.predicted_at,
            )

        # Baseline fallback if station was just created
        baseline_ghi = 600.0
        decision = evaluate_decision_support(
            panel_area_m2=station.panel_area,
            efficiency=station.efficiency,
            current_ghi_w_m2=baseline_ghi,
            target_power_kw=station.target_capacity_kw,
            cloud_trend="Clear",
        )
        simulated_curve = [600.0, 580.0, 550.0, 480.0, 390.0, 250.0]

        return StationDashboardResponse(
            station_id=station.id,
            station_name=station.name,
            latitude=station.latitude,
            longitude=station.longitude,
            target_capacity_kw=station.target_capacity_kw,
            current_ghi_w_m2=baseline_ghi,
            forecast_curve_3h=simulated_curve,
            cloud_trend="Clear",
            confidence=0.92,
            estimated_power_kw=decision.estimated_power_kw,
            delta_p_kw=decision.recommended_delta_p_kw,
            alert_level=decision.alert_level.value,
            recommendation_text=decision.recommendation_text,
            satellite_image_url=None,
            last_updated=datetime.now(timezone.utc),
        )

    @staticmethod
    async def get_active_alerts(db: AsyncSession, severity: Optional[str] = None) -> list[AlertFeedItem]:
        """Fetch alert feeds across stations."""
        active_stations = await StationService.get_all_stations(db, include_archived=False)
        alerts: list[AlertFeedItem] = []

        for station in active_stations:
            pred_stmt = (
                select(Prediction)
                .where(Prediction.station_id == station.id)
                .order_by(Prediction.predicted_at.desc())
                .limit(1)
            )
            pred_res = await db.execute(pred_stmt)
            pred = pred_res.scalar_one_or_none()

            if pred and pred.alert_level in ("Early Warning", "Critical Alert"):
                if severity == "high" and pred.alert_level != "Critical Alert":
                    continue
                alerts.append(
                    AlertFeedItem(
                        station_id=station.id,
                        station_name=station.name,
                        alert_level=pred.alert_level,
                        event=f"Cloud Motion: {pred.cloud_trend}",
                        delta_p_needed_kw=pred.delta_p_kw,
                        recommendation=pred.recommendation_text,
                        timestamp=pred.predicted_at,
                    )
                )

        return alerts

    @staticmethod
    def get_grafana_links() -> GrafanaLinksResponse:
        """Return Grafana dashboard URLs."""
        base_grafana = "http://localhost:3000"
        return GrafanaLinksResponse(
            system_health_dashboard_url=f"{base_grafana}/d/system-health/solar-system-metrics",
            model_performance_dashboard_url=f"{base_grafana}/d/model-monitoring/solar-model-drift",
        )
