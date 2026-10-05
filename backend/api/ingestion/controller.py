import asyncio
from datetime import date as date_type
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.model import User
from api.auth.service import get_current_user, require_admin
from api.ingestion.forecast_frames import read_forecast_frames
from api.ingestion.schema import (
    DayFramesResponse,
    IngestTriggerRequest,
    IngestTriggerResponse,
    IngestionStatusResponse,
    SatelliteFrameItem,
    WeatherRecentItem,
)
from api.ingestion.service import IngestionService
from api.stations.service import StationService
from api.storage.service import StorageService
from db.database import get_db_session

TH_TZ = timezone(timedelta(hours=7))


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


async def get_day_satellite_frames(
    station_id: str,
    date: date_type = Query(..., description="Day in Thai time, YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> DayFramesResponse:
    """Real Band 03 frames of one station and day, and for today the frames the ConvLSTM predicted in the newest round."""
    from api.frame_review import service as frames

    station = await StationService.get_station_by_id(db, station_id)
    if station is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Station '{station_id}' not found")
    try:
        items, night = await asyncio.to_thread(frames.read_day_frames, station_id, station.latitude, station.longitude, date)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"Could not read the frame cache: {e}") from None

    real = [it for it in items if "blank" not in it["flags"]]
    forecast = None
    if date == datetime.now(TH_TZ).date():
        try:
            forecast = await asyncio.to_thread(read_forecast_frames, station_id)
        except Exception:  # noqa: BLE001  the real frames are still worth showing
            forecast = None
        if forecast is not None:
            forecast["model_version"] = frames.deployed_convlstm()["model_version"]
    return DayFramesResponse(
        station_id=station_id,
        date=date.isoformat(),
        frames=[{"timestamp": it["timestamp"], "cloud_pct": it["cloud_pct"], "image_b64": it["image_b64"]} for it in real],
        night_frames=night,
        blank_frames=len(items) - len(real),
        forecast=forecast,
    )
