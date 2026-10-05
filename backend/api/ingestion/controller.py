import asyncio

from fastapi import Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.model import User
from api.auth.service import get_current_user, require_admin
from api.ingestion.schema import (
    IngestTriggerRequest,
    IngestTriggerResponse,
    IngestionStatusResponse,
    SatelliteFrameItem,
    WeatherRecentItem,
)
from api.ingestion.service import IngestionService
from api.storage.service import StorageService
from db.database import get_db_session


async def trigger_ingestion(
    payload: IngestTriggerRequest,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
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


async def trigger_auto_catchup(
    payload: IngestTriggerRequest,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
) -> dict:
    """สั่งตรวจสอบ Gap ของข้อมูลและดึงข้อมูลย้อนหลังทั้ง Weather Time-Series และภาพถ่ายดาวเทียม 12 เฟรมอัตโนมัติ"""
    station_id = payload.station_id or "ST-001"
    w_res = await IngestionService.auto_catchup_weather(db=db, station_id=station_id)
    s_res = await IngestionService.auto_catchup_satellite(db=db, station_id=station_id, count=12)
    return {
        "station_id": station_id,
        "weather": w_res,
        "satellite": s_res,
    }



async def get_latest_satellite_crop(
    station_id: str,
    _: User = Depends(get_current_user),
) -> Response:
    """ภาพดาวเทียมจริงล่าสุดรอบสถานี (true-colour 64x64 พิกเซล) ที่ inference worker เก็บไว้ใน MinIO."""
    def read() -> tuple[bytes, str]:
        resp = StorageService().download_file("satellite-cache", f"{station_id}_latest.png")
        try:
            return resp.read(), resp.headers.get("Last-Modified", "")
        finally:
            resp.close()
            resp.release_conn()

    try:
        data, last_modified = await asyncio.to_thread(read)
    except Exception:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"No satellite image stored yet for station '{station_id}'.") from None
    headers = {"Cache-Control": "no-store"}
    if last_modified:
        headers["Last-Modified"] = last_modified
    return Response(content=data, media_type="image/png", headers=headers)
