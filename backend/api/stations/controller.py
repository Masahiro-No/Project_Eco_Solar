from typing import Optional
from fastapi import Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.model import User
from api.auth.service import get_current_user, require_admin
from api.inference.model import Prediction
from api.stations.schema import (
    NearestStationResponse,
    StationCreateRequest,
    StationPatchRequest,
    StationResponse,
    StationUpdateRequest,
)
from api.stations.service import StationService
from db.database import get_db_session


async def _enrich_station_response(db: AsyncSession, station) -> StationResponse:
    """Helper to attach live operational prediction power and alert level to StationResponse."""
    dto = StationResponse.model_validate(station)
    if not station.is_active:
        dto.current_pgen_kw = 0.0
        dto.alert_level = "Offline"
        return dto

    pred_stmt = (
        select(Prediction)
        .where(Prediction.station_id == station.id, Prediction.source == "model")
        .order_by(Prediction.predicted_at.desc())
        .limit(1)
    )
    pred_res = await db.execute(pred_stmt)
    latest_pred = pred_res.scalar_one_or_none()

    if latest_pred:
        dto.current_pgen_kw = round(latest_pred.estimated_power_kw, 1)
        dto.alert_level = latest_pred.alert_level
    else:
        # No real model run yet: leave unknown instead of fabricating a value
        dto.current_pgen_kw = None
        dto.alert_level = None

    return dto


async def get_all_stations(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    include_archived: bool = Query(False),
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> list[StationResponse]:
    """ดึงรายชื่อสถานีโซลาร์ฟาร์มทั้งหมด พร้อมข้อมูลกำลังผลิตจริงจากฐานข้อมูล"""
    stations = await StationService.get_all_stations(
        db, include_archived=include_archived, limit=limit, offset=offset
    )
    return [await _enrich_station_response(db, s) for s in stations]


async def get_archived_stations(
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
) -> list[StationResponse]:
    """ดึงรายชื่อสถานีที่ถูกระงับการใช้งาน (Soft-deleted) ทั้งหมด"""
    stations = await StationService.get_archived_stations(db)
    return [await _enrich_station_response(db, s) for s in stations]


async def get_station_by_id(
    station_id: str,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> StationResponse:
    """ดึงข้อมูลรายละเอียดและสเปกของสถานีตาม ID พร้อมค่ากำลังผลิตล่าสุด"""
    station = await StationService.get_station_by_id(db, station_id)
    return await _enrich_station_response(db, station)


async def create_station(
    payload: StationCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
) -> StationResponse:
    """ลงทะเบียนสถานีโรงไฟฟ้าโซลาร์แห่งใหม่"""
    station = await StationService.create_station(db, payload)
    return await _enrich_station_response(db, station)


async def update_station(
    station_id: str,
    payload: StationUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
) -> StationResponse:
    """อัปเดตข้อมูลสเปกของสถานีทั้งหมด (Full Update)"""
    station = await StationService.update_station(db, station_id, payload)
    return await _enrich_station_response(db, station)


async def patch_station(
    station_id: str,
    payload: StationPatchRequest,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
) -> StationResponse:
    """แก้ไขเฉพาะบางฟิลด์ของสถานี (Partial Update)"""
    station = await StationService.patch_station(db, station_id, payload)
    return await _enrich_station_response(db, station)


async def soft_delete_station(
    station_id: str,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
) -> StationResponse:
    """ปิดการใช้งานสถานีชั่วคราว (Soft-Delete) โดยไม่ลบประวัติใน DB"""
    station = await StationService.soft_delete_station(db, station_id)
    return await _enrich_station_response(db, station)


async def restore_station(
    station_id: str,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
) -> StationResponse:
    """กู้คืนสถานีที่เคยถูกระงับการใช้งานกลับมาทำงานใหม่ (Restore)"""
    station = await StationService.restore_station(db, station_id)
    return await _enrich_station_response(db, station)


async def find_nearest_station(
    lat: float = Query(..., ge=-90.0, le=90.0),
    lon: float = Query(..., ge=-180.0, le=180.0),
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> NearestStationResponse:
    """ค้นหาสถานีโซลาร์ฟาร์มที่อยู่ใกล้พิกัด Latitude/Longitude มากที่สุด (Nearest Mapping)"""
    return await StationService.find_nearest_station(db, lat, lon)
