"""Endpoints รับ ground-truth GHI (แก้เอง / อัปโหลดไฟล์) -> Label Studio -> นัด retrain LSTM."""

import asyncio
from datetime import date as date_type
from typing import Optional

from fastapi import Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.model import User
from api.auth.service import require_admin
from api.label_studio import file_import
from api.label_studio.ground_truth import (
    GroundTruthStore,
    parse_label_timestamp,
    schedule_retrain,
    validate_value,
)
from api.label_studio.schema import (
    BatchSubmitGroundTruthRequest,
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


async def store_labels(station_id: str, raw_items: list[dict], source: str):
    """validate -> upsert เข้า Label Studio -> นัด retrain. คืน (summary, rejected, enqueued, retrain_status)."""
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

    enqueued, retrain_status = await schedule_retrain(station_id, summary.changed)
    return summary, rejected + summary.rejected, enqueued, retrain_status


def _batch_response(station_id: str, received: int, summary, rejected, enqueued, retrain_status) -> dict:
    return {
        "station_id": station_id,
        "received": received,
        "created": summary.count("created"),
        "updated": summary.count("updated"),
        "unchanged": summary.count("unchanged"),
        "rejected": rejected,
        "retrain_enqueued": enqueued,
        "retrain_status": retrain_status,
    }


async def submit_ground_truth(
    payload: SubmitGroundTruthRequest,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
) -> SubmitGroundTruthResponse:
    """ส่ง GHI จริง 1 ค่า -> Label Studio (สร้าง/อัปเดต) -> นัด retrain."""
    await _require_station(db, payload.station_id)
    summary, rejected, enqueued, retrain_status = await store_labels(
        payload.station_id, [payload.model_dump()], source="manual"
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
    summary, rejected, enqueued, retrain_status = await store_labels(
        payload.station_id, [i.model_dump() for i in payload.items], source=payload.source
    )
    return BatchSubmitGroundTruthResponse(
        **_batch_response(payload.station_id, len(payload.items), summary, rejected, enqueued, retrain_status)
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
    """นำเข้า GHI จริงจากไฟล์ CSV/XLSX เฉพาะแถวที่อยู่ในวันที่เลือก (เวลาไทย) ตามคอลัมน์ที่ผู้ใช้ระบุ."""
    await _require_station(db, station_id)
    content = await file.read()
    try:
        parsed = file_import.parse_ground_truth_file(
            file.filename or "", content, timestamp_col=timestamp_col or None, ghi_col=ghi_col or None, day=date
        )
    except file_import.FileImportError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from None
    if not parsed.items:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"ไม่มีแถวที่ใช้ได้ในวันที่ {date.isoformat()} (อยู่นอกวันที่เลือก {parsed.outside_day} แถว, ใช้ไม่ได้ {len(parsed.invalid)} แถว)",
        )

    summary, rejected, enqueued, retrain_status = await store_labels(station_id, parsed.items, source="file")
    return UploadGroundTruthResponse(
        **_batch_response(station_id, len(parsed.items), summary, rejected, enqueued, retrain_status),
        filename=file.filename or "",
        date=date.isoformat(),
        total_rows=parsed.total_rows,
        invalid_rows=len(parsed.invalid),
        outside_day=parsed.outside_day,
        duplicates_collapsed=parsed.duplicates_collapsed,
        clamped_negative=parsed.clamped_negative,
    )
