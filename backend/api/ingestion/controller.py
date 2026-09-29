from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.model import User
from api.auth.service import get_current_user
from api.ingestion.schema import (
    IngestTriggerRequest,
    IngestTriggerResponse,
    IngestionStatusResponse,
    SatelliteFrameItem,
    WeatherRecentItem,
)
from api.ingestion.service import IngestionService
from db.database import get_db_session


async def trigger_ingestion(
    payload: IngestTriggerRequest,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> IngestTriggerResponse:
    """สั่งดึงข้อมูลสภาพอากาศแบบ Real-time (Open-Meteo) และภาพดาวเทียม Himawari (NICT) เข้าสู่ระบบทันที"""
    return await IngestionService.trigger_ingest(station_id=payload.station_id or "ST-001", db=db)


async def get_recent_weather(
    station_id: str,
    hours: int = Query(24, ge=1, le=168, description="จำนวนชั่วโมงย้อนหลัง"),
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> list[WeatherRecentItem]:
    """ดึงข้อมูลสภาพอากาศย้อนหลังระดับ Canonical Schema เพื่อใช้เป็น Input สำหรับโมเดล LSTM"""
    return await IngestionService.get_recent_weather(station_id=station_id, db=db, hours=hours)


async def get_recent_satellite_frames(
    station_id: str,
    count: int = Query(12, ge=1, le=48, description="จำนวนเฟรมภาพดาวเทียมย้อนหลัง (12 เฟรม = 2 ชม.)"),
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> list[SatelliteFrameItem]:
    """ดึงประวัติ URL ภาพถ่ายดาวเทียม Himawari ล่าสุดเพื่อใช้ส่งให้ ConvLSTM Cloud Motion Model"""
    return await IngestionService.get_recent_satellite_frames(station_id=station_id, db=db, count=count)


async def get_ingestion_status(
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> IngestionStatusResponse:
    """ตรวจสอบสถานะสุขภาพและการเชื่อมต่อ Data Source (Open-Meteo, NICT Himawari) และจำนวนข้อมูลในระบบ"""
    return await IngestionService.get_status(db=db)
