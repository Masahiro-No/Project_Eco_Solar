import asyncio
from datetime import date as date_type
from typing import Optional
from fastapi import Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.model import User
from api.auth.service import get_current_user, get_optional_current_user
from api.inference.schema import (
    InferenceRequest,
    InferenceResponse,
    InferenceResultResponse,
    PredictionResultData,
    PredictionsByDateResponse,
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


async def get_predictions_by_date(
    station_id: str,
    date: date_type = Query(..., description="วันที่ (เวลาไทย) รูปแบบ YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> PredictionsByDateResponse:
    """ค่าพยากรณ์ + GHI จาก weather_history ของวันที่เลือก (เรียงตามเวลาจริง) + ค่าจริงที่ label ไว้แล้ว สำหรับหน้า labeling."""
    from api.label_studio.ground_truth import GroundTruthStore, th_day_bounds

    agg = await InferenceService.get_aligned_predictions(station_id, date, db=db)
    start, end = th_day_bounds(date)

    labels: dict = {}
    label_error: Optional[str] = None
    try:
        store = GroundTruthStore()
        pid = await asyncio.to_thread(store.project_id)
        found = await asyncio.to_thread(store.index, pid, station_id, start, end)
        labels = {slot: item.ghi for slot, item in found.items()}
    except Exception as e:  # noqa: BLE001  Label Studio ใช้ไม่ได้ก็ยังต้องแสดงค่าพยากรณ์ได้
        label_error = str(e)

    # รวมช่องที่มีแค่ข้อมูล weather ด้วย: วันที่ไม่มีรอบพยากรณ์ก็ยังกรอกค่าจริงได้ (trainer ใช้ label ทับ weather_history ที่ช่องนั้น)
    slots = sorted(set(agg["pred"]) | set(agg["weather"]) | set(labels))
    points = [
        {
            "timestamp": s,
            "predicted_ghi": agg["pred"].get(s),
            "weather_ghi": agg["weather"].get(s),
            "label_ghi": labels.get(s),
        }
        for s in slots
    ]
    errs = [abs(agg["pred"][s] - labels[s]) for s in labels if s in agg["pred"]]
    return PredictionsByDateResponse(
        station_id=station_id,
        date=date.isoformat(),
        prediction_runs=agg["runs"],
        label_count=len(labels),
        matched_label_count=len(errs),
        mae_vs_label=round(sum(errs) / len(errs), 2) if errs else None,
        label_error=label_error,
        points=points,
    )

