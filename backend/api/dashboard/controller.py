from typing import Optional
from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.model import User
from api.auth.service import get_current_user, get_optional_current_user
from api.dashboard.schema import (
    AlertFeedItem,
    DashboardSummaryResponse,
    GrafanaLinksResponse,
    StationDashboardResponse,
)
from api.dashboard.service import DashboardService
from db.database import get_db_session


async def get_dashboard_summary(
    db: AsyncSession = Depends(get_db_session),
    _: Optional[User] = Depends(get_optional_current_user),
) -> DashboardSummaryResponse:
    """สรุปภาพรวมทั้งระบบขึ้นหน้าแรก (KPI Cards, กำลังผลิตรวม, ความเสี่ยงรวม)"""
    return await DashboardService.get_summary(db)


async def get_station_dashboard(
    station_id: str,
    db: AsyncSession = Depends(get_db_session),
    _: Optional[User] = Depends(get_optional_current_user),
) -> StationDashboardResponse:
    """ดึงข้อมูลแดชบอร์ดเฉพาะสถานี (กราฟพยากรณ์ 3 ชม., ทัศนวิสัยเมฆ, คำแนะนำ ΔP)"""
    return await DashboardService.get_station_dashboard(db, station_id)


async def get_dashboard_alerts(
    severity: Optional[str] = Query(None, description="Filter by severity: 'high'"),
    db: AsyncSession = Depends(get_db_session),
    _: Optional[User] = Depends(get_optional_current_user),
) -> list[AlertFeedItem]:
    """ดึงรายการแจ้งเตือนด่วน (Real-time Alert Feeds) ที่ต้องการเฝ้าระวังหรือเร่งสำรองไฟ"""
    return await DashboardService.get_active_alerts(db, severity=severity)


async def get_grafana_links(
    _: User = Depends(get_current_user),
) -> GrafanaLinksResponse:
    """ดึง URL สำหรับ Embed หรือเปิดดู Grafana Dashboards"""
    return DashboardService.get_grafana_links()
