from fastapi import Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.model import User
from api.auth.service import get_current_user
from api.stations.schema import (
    NearestStationResponse,
    StationCreateRequest,
    StationPatchRequest,
    StationResponse,
    StationUpdateRequest,
)
from api.stations.service import StationService
from db.database import get_db_session


async def get_all_stations(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> list[StationResponse]:
    """ดึงรายชื่อสถานีโซลาร์ฟาร์มที่เปิดใช้งานอยู่ทั้งหมด"""
    stations = await StationService.get_all_stations(db, include_archived=False, limit=limit, offset=offset)
    return [StationResponse.model_validate(s) for s in stations]


async def get_archived_stations(
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> list[StationResponse]:
    """ดึงรายชื่อสถานีที่ถูกระงับการใช้งาน (Soft-deleted) ทั้งหมด"""
    stations = await StationService.get_archived_stations(db)
    return [StationResponse.model_validate(s) for s in stations]


async def get_station_by_id(
    station_id: str,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> StationResponse:
    """ดึงข้อมูลรายละเอียดและสเปกของสถานีตาม ID"""
    station = await StationService.get_station_by_id(db, station_id)
    return StationResponse.model_validate(station)


async def create_station(
    payload: StationCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> StationResponse:
    """ลงทะเบียนสถานีโรงไฟฟ้าโซลาร์แห่งใหม่"""
    station = await StationService.create_station(db, payload)
    return StationResponse.model_validate(station)


async def update_station(
    station_id: str,
    payload: StationUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> StationResponse:
    """อัปเดตข้อมูลสเปกของสถานีทั้งหมด (Full Update)"""
    station = await StationService.update_station(db, station_id, payload)
    return StationResponse.model_validate(station)


async def patch_station(
    station_id: str,
    payload: StationPatchRequest,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> StationResponse:
    """แก้ไขเฉพาะบางฟิลด์ของสถานี (Partial Update)"""
    station = await StationService.patch_station(db, station_id, payload)
    return StationResponse.model_validate(station)


async def soft_delete_station(
    station_id: str,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> StationResponse:
    """ปิดการใช้งานสถานีชั่วคราว (Soft-Delete) โดยไม่ลบประวัติใน DB"""
    station = await StationService.soft_delete_station(db, station_id)
    return StationResponse.model_validate(station)


async def restore_station(
    station_id: str,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> StationResponse:
    """กู้คืนสถานีที่เคยถูกระงับการใช้งานกลับมาทำงานใหม่ (Restore)"""
    station = await StationService.restore_station(db, station_id)
    return StationResponse.model_validate(station)


async def find_nearest_station(
    lat: float = Query(..., ge=-90.0, le=90.0),
    lon: float = Query(..., ge=-180.0, le=180.0),
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> NearestStationResponse:
    """ค้นหาสถานีโซลาร์ฟาร์มที่อยู่ใกล้พิกัด Latitude/Longitude มากที่สุด (Nearest Mapping)"""
    return await StationService.find_nearest_station(db, lat, lon)
