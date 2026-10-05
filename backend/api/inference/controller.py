import asyncio
from datetime import date as date_type
from typing import Optional
from fastapi import Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.model import User
from api.auth.service import get_current_user, require_admin
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
    _: User = Depends(require_admin),
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
    _: User = Depends(get_current_user),
) -> PredictionResultData:
    """ดึงผลการพยากรณ์รอบล่าสุดของสถานีขึ้นแสดงบน Dashboard ทันที"""
    return await InferenceService.get_latest_prediction(station_id, db=db)


async def get_prediction_history(
    station_id: str,
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> list[PredictionResultData]:
    """ดึงประวัติผลพยากรณ์ย้อนหลังเพื่อนำไปพลอตกราฟเปรียบเทียบ"""
    return await InferenceService.get_prediction_history(station_id, db=db, limit=limit)


async def get_predictions_by_date(
    station_id: str,
    date: date_type = Query(..., description="วันที่ (เวลาไทย) รูปแบบ YYYY-MM-DD"),
    lead_minutes: Optional[int] = Query(
        None, ge=10, le=180, multiple_of=10,
        description="กราฟทั้งวัน: ช่องเวลาที่ผ่านมาแล้วใช้ค่าที่ทำนายไว้ล่วงหน้าอย่างน้อยกี่นาที (ไม่ระบุ = รอบล่าสุดทุกช่อง)",
    ),
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> PredictionsByDateResponse:
    """ค่าพยากรณ์ + GHI จาก weather_history ของวันที่เลือก (เรียงตามเวลาจริง) + ค่าจริงที่ label ไว้แล้ว

    ใช้ทั้งหน้า labeling (predicted_ghi = รอบล่าสุด) และกราฟทั้งวันของหน้าพยากรณ์ (forecast_* ตาม lead_minutes).
    """
    from api.label_studio.ground_truth import GroundTruthStore, th_day_bounds

    agg = await InferenceService.get_aligned_predictions(station_id, date, db=db, lead_minutes=lead_minutes)
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
    view = agg["view"]
    slots = sorted(set(agg["pred"]) | set(agg["weather"]) | set(labels) | set(view))
    points = [
        {
            "timestamp": s,
            "predicted_ghi": agg["pred"].get(s),
            "predicted_ghi_lstm": agg["pred_lstm"].get(s),
            "weather_ghi": agg["weather"].get(s),
            "label_ghi": labels.get(s),
            "clearsky_ghi": agg["clearsky"].get(s),
            "forecast_ghi": view[s]["ghi"] if s in view else None,
            "forecast_ghi_lstm": view[s]["lstm"] if s in view else None,
            "forecast_lead_minutes": view[s]["lead"] if s in view else None,
            "forecast_target_kw": view[s]["target"] if s in view else None,
            "forecast_cloud_pct": view[s]["cloud"] if s in view else None,
            "forecast_sat_loss_pct": view[s]["loss"] if s in view else None,
        }
        for s in slots
    ]
    # error of the day-view line at the requested lead time, on the same slots for both models
    seen = [s for s in labels if s in view and view[s]["lstm"] is not None]
    view_errs = [abs(view[s]["ghi"] - labels[s]) for s in seen]
    view_lstm_errs = [abs(view[s]["lstm"] - labels[s]) for s in seen]
    errs = [abs(agg["pred"][s] - labels[s]) for s in labels if s in agg["pred"]]
    # same slots for both models, so the two errors can be compared
    both = [s for s in labels if s in agg["pred"] and s in agg["pred_lstm"]]
    lstm_errs = [abs(agg["pred_lstm"][s] - labels[s]) for s in both]
    return PredictionsByDateResponse(
        station_id=station_id,
        date=date.isoformat(),
        prediction_runs=agg["runs"],
        label_count=len(labels),
        matched_label_count=len(errs),
        mae_vs_label=round(sum(errs) / len(errs), 2) if errs else None,
        mae_lstm_vs_label=round(sum(lstm_errs) / len(lstm_errs), 2) if lstm_errs and len(both) == len(errs) else None,
        label_error=label_error,
        lead_minutes=lead_minutes,
        view_matched_label_count=len(seen),
        view_mae_vs_label=round(sum(view_errs) / len(view_errs), 2) if view_errs else None,
        view_mae_lstm_vs_label=round(sum(view_lstm_errs) / len(view_lstm_errs), 2) if view_lstm_errs else None,
        points=points,
    )

