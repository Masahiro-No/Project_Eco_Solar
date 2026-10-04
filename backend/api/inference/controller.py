from typing import Optional
from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.model import User
from api.auth.service import get_current_user, get_optional_current_user
from api.inference.schema import (
    InferenceRequest,
    InferenceResponse,
    InferenceResultResponse,
    PredictionResultData,
)
from api.inference.service import InferenceService
from db.database import get_db_session


async def predict(
    payload: InferenceRequest,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> InferenceResponse:
    """สั่งคำขอพยากรณ์ไฟฟ้าล่วงหน้า 3 ชม. (Enqueue to inference_queue)"""
    job_id = await InferenceService.enqueue_solar_inference(
        station_id=payload.station_id,
        target_power_kw=payload.target_power_kw,
        model_version=payload.model_version,
        db=db,
    )
    return InferenceResponse(job_id=job_id, status="queued")


async def get_result(
    job_id: str,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> InferenceResultResponse:
    """ดึงผลลัพธ์การพยากรณ์เมื่อ Worker ประมวลผลเสร็จ"""
    data = await InferenceService.get_result(job_id, db=db)
    return InferenceResultResponse(
        job_id=data["job_id"],
        status=data["status"],
        result=data["result"],
    )


async def get_latest_prediction(
    station_id: str,
    db: AsyncSession = Depends(get_db_session),
    _: Optional[User] = Depends(get_optional_current_user),
) -> PredictionResultData:
    """ดึงผลการพยากรณ์รอบล่าสุดของสถานีขึ้นแสดงบน Dashboard ทันที"""
    return await InferenceService.get_latest_prediction(station_id, db=db)


async def get_prediction_history(
    station_id: str,
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    _: Optional[User] = Depends(get_optional_current_user),
) -> list[PredictionResultData]:
    """ดึงประวัติผลพยากรณ์ย้อนหลังเพื่อนำไปพลอตกราฟเปรียบเทียบ"""
    return await InferenceService.get_prediction_history(station_id, db=db, limit=limit)
