"""Endpoints รับ ground-truth GHI (แก้เอง / อัปโหลดไฟล์) -> Label Studio -> นัด retrain LSTM."""

import asyncio
from datetime import date as date_type
from typing import Optional

from fastapi import Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.model import User
from api.auth.service import require_admin
from api.ingestion.service import IngestionService
from api.label_studio import file_import
from api.label_studio.ground_truth import (
    CALIBRATION_RUNNING_KEY,
    CALIBRATION_SCHEDULED_KEY,
    TH_TZ,
    GroundTruthStore,
    parse_label_timestamp,
    schedule_calibration_check,
    schedule_retrain,
    validate_value,
)
from api.label_studio.schema import (
    BatchSubmitGroundTruthRequest,
    CalibrationStatusResponse,
    BatchSubmitGroundTruthResponse,
    SubmitGroundTruthRequest,
    SubmitGroundTruthResponse,
    UploadGroundTruthResponse,
    UploadPreviewResponse,
)
from api.stations.model import Station
from db.database import get_db_session


async def _require_station(db: AsyncSession, station_id: str) -> None:
    res = await db.execute(select(Station.id).where(Station.id == station_id))
    if res.first() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Solar station '{station_id}' not found.")


async def store_labels(db: AsyncSession, station_id: str, raw_items: list[dict], source: str):
    """validate -> upsert เข้า Label Studio -> ดึงสภาพอากาศของวันที่ยังไม่มี -> นัด retrain.

    คืน (summary, rejected, enqueued, retrain_status, weather) โดย weather คือผลของ
    IngestionService.backfill_weather_for_days: ค่าวัดจริงของวันที่ระบบไม่มีสภาพอากาศใช้ retrain ไม่ได้
    จึงดึงสภาพอากาศของวันนั้นจาก Open-Meteo มาเติมเฉพาะช่องที่ยังไม่มี
    """
    rejected: list[dict] = []
    rows: dict = {}  # slot -> (index, slot, ghi, extra); ช่องซ้ำในชุดเดียวกัน: ค่าหลังสุดชนะ
    for i, raw in enumerate(raw_items):
        try:
            slot = parse_label_timestamp(raw["timestamp"])
        except (KeyError, ValueError, TypeError):
            rejected.append({"index": i, "reason": "invalid_timestamp"})
            continue
        reason = validate_value(raw.get("ghi_actual"), slot)
        if reason:
            rejected.append({"index": i, "reason": reason})
            continue
        rows[slot] = (i, slot, float(raw["ghi_actual"]), {"notes": raw.get("notes"), "source": source,
                                                         "temperature": raw.get("temperature"),
                                                         "relative_humidity": raw.get("relative_humidity")})

    try:
        summary = await asyncio.to_thread(GroundTruthStore().upsert, station_id, list(rows.values()))
    except Exception as e:  # noqa: BLE001  (Label Studio ล่ม / token หมดอายุ / ฯลฯ)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"Label Studio error: {e}") from None

    try:
        weather = await IngestionService.backfill_weather_for_days(
            db, station_id, sorted({slot.astimezone(TH_TZ).date() for slot in rows})
        )
    except Exception as e:  # noqa: BLE001  ค่าวัดจริงถูกบันทึกแล้ว: การดึงสภาพอากาศไม่สำเร็จไม่ทำให้การบันทึกล้ม
        weather = {"rows_added": 0, "status": "failed", "message": str(e)}

    # สภาพอากาศที่เพิ่งเติมทำให้ค่าวัดจริงที่บันทึกไว้ก่อนใช้ได้: นับวันใหม่อีกครั้งแม้ label ไม่เปลี่ยน
    enqueued, retrain_status = await schedule_retrain(station_id, summary.changed + weather["rows_added"])
    await schedule_calibration_check(summary.changed)  # สูตรแสงของสถานีนี้เทียบกับค่าวัดจริงแล้วหรือยัง
    return summary, rejected + summary.rejected, enqueued, retrain_status, weather


def _batch_response(station_id: str, received: int, summary, rejected, enqueued, retrain_status, weather) -> dict:
    return {
        "station_id": station_id,
        "received": received,
        "created": summary.count("created"),
        "updated": summary.count("updated"),
        "unchanged": summary.count("unchanged"),
        "rejected": rejected,
        "retrain_enqueued": enqueued,
        "retrain_status": retrain_status,
        "weather_rows_added": weather["rows_added"],
        "weather_status": weather["status"],
        "weather_message": weather["message"],
    }


async def submit_ground_truth(
    payload: SubmitGroundTruthRequest,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
) -> SubmitGroundTruthResponse:
    """ส่ง GHI จริง 1 ค่า -> Label Studio (สร้าง/อัปเดต) -> นัด retrain."""
    await _require_station(db, payload.station_id)
    summary, rejected, enqueued, retrain_status, _weather = await store_labels(
        db, payload.station_id, [payload.model_dump()], source="manual"
    )
    if rejected:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=rejected[0]["reason"])
    item = summary.items[0]
    return SubmitGroundTruthResponse(
        task_id=item.task_id,
        annotation_id=item.annotation_id or 0,
        station_id=payload.station_id,
        timestamp=payload.timestamp,
        ghi_actual=payload.ghi_actual,
        retrain_enqueued=enqueued,
        retrain_status=retrain_status,
    )


async def batch_submit_ground_truth(
    payload: BatchSubmitGroundTruthRequest,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
) -> BatchSubmitGroundTruthResponse:
    """ส่ง GHI จริงหลายค่า (จากตารางหน้าเว็บ)."""
    await _require_station(db, payload.station_id)
    summary, rejected, enqueued, retrain_status, weather = await store_labels(
        db, payload.station_id, [i.model_dump() for i in payload.items], source=payload.source
    )
    return BatchSubmitGroundTruthResponse(
        **_batch_response(payload.station_id, len(payload.items), summary, rejected, enqueued, retrain_status, weather)
    )


async def preview_ground_truth_file(
    file: UploadFile = File(...),
    _: User = Depends(require_admin),
) -> UploadPreviewResponse:
    """อ่านหัวตาราง + ตัวอย่างแถวของไฟล์ และเดาคอลัมน์เวลา/GHI ให้ผู้ใช้เลือกยืนยัน."""
    content = await file.read()
    try:
        return UploadPreviewResponse(**file_import.preview(file.filename or "", content))
    except file_import.FileImportError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from None


async def upload_ground_truth_file(
    station_id: str = Form(...),
    date: date_type = Form(...),
    timestamp_col: Optional[str] = Form(None),
    ghi_col: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
) -> UploadGroundTruthResponse:
    """นำเข้า GHI จริงจากไฟล์ CSV/XLSX ตามคอลัมน์ที่ผู้ใช้ระบุ: ทุกแถวตั้งแต่วันเริ่มต้น `date` เป็นต้นไป (เวลาไทย).

    ไฟล์เดียวมีได้หลายวัน แถวก่อนวันเริ่มต้นถูกข้าม
    """
    await _require_station(db, station_id)
    content = await file.read()
    try:
        parsed = file_import.parse_ground_truth_file(
            file.filename or "", content, timestamp_col=timestamp_col or None, ghi_col=ghi_col or None, start_day=date
        )
    except file_import.FileImportError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from None
    if not parsed.items:
        in_file = (
            f" ข้อมูลในไฟล์อยู่ในช่วงวันที่ {parsed.file_first_day.isoformat()} ถึง {parsed.file_last_day.isoformat()}"
            if parsed.file_first_day else ""
        )
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"ไม่มีแถวที่ใช้ได้ตั้งแต่วันที่ {date.isoformat()} (อยู่ก่อนวันเริ่มต้น {parsed.before_start} แถว, ใช้ไม่ได้ {len(parsed.invalid)} แถว){in_file}",
        )

    summary, rejected, enqueued, retrain_status, weather = await store_labels(db, station_id, parsed.items, source="file")
    return UploadGroundTruthResponse(
        **_batch_response(station_id, len(parsed.items), summary, rejected, enqueued, retrain_status, weather),
        filename=file.filename or "",
        date=date.isoformat(),
        first_date=parsed.days[0].isoformat(),
        last_date=parsed.days[-1].isoformat(),
        days=len(parsed.days),
        total_rows=parsed.total_rows,
        invalid_rows=len(parsed.invalid),
        before_start=parsed.before_start,
        duplicates_collapsed=parsed.duplicates_collapsed,
        clamped_negative=parsed.clamped_negative,
    )


async def get_calibration_status(
    station_id: str = Query(...),
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
) -> CalibrationStatusResponse:
    """สูตรแสงจากภาพดาวเทียมเทียบกับค่าวัดจริงของสถานีนี้แล้วหรือยัง (ผลของงาน check_satellite_calibration ที่รันเองหลังบันทึกค่าวัดจริง)."""
    from api.inference.service import read_calibration_file
    from api.jobs.service import JobService

    await _require_station(db, station_id)
    pending = False
    try:
        pool = await JobService.get_pool()
        try:
            pending = bool(await pool.exists(CALIBRATION_SCHEDULED_KEY)) or bool(await pool.exists(CALIBRATION_RUNNING_KEY))
        finally:
            await pool.close()
    except Exception:  # noqa: BLE001  Redis ล่ม: ยังบอกผลล่าสุดในไฟล์ได้
        pass

    data = read_calibration_file()
    if data is None:
        return CalibrationStatusResponse(station_id=station_id, state="no_calibration", pending=pending)
    common = {"station_id": station_id, "min_pairs": int(data.get("min_pairs") or 30), "checked_at": data.get("checked_at"), "pending": pending}
    checked = (data.get("checked") or {}).get(station_id)
    if station_id in (data.get("stations") or []):
        return CalibrationStatusResponse(state="fitted", pairs=(checked or {}).get("pairs", data.get("pairs")), mae=(checked or {}).get("mae", data.get("mae_leave_one_day_out")), **common)
    if checked:
        return CalibrationStatusResponse(state="checked", pairs=checked.get("pairs"), mae=checked.get("mae"), **common)
    short = (data.get("insufficient") or {}).get(station_id)
    if short is not None:
        return CalibrationStatusResponse(state="insufficient", pairs=int(short.get("pairs") or 0), **common)
    return CalibrationStatusResponse(state="not_checked", **common)

