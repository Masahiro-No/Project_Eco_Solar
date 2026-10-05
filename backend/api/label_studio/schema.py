from typing import Literal

from pydantic import BaseModel, Field


class CreateProjectRequest(BaseModel):
    title: str
    label_config: str  # XML config สำหรับ labeling interface


class ProjectResponse(BaseModel):
    id: int
    title: str
    task_number: int | None = None


class ImportTaskRequest(BaseModel):
    data: dict  # task data payload เช่น {"image": "https://..."}


class TaskResponse(BaseModel):
    id: int
    data: dict


class CreateAnnotationRequest(BaseModel):
    result: list[dict]
    ground_truth: bool = True


class AnnotationResponse(BaseModel):
    id: int
    task_id: int | None = None
    result: list[dict] | None = None


class SubmitGroundTruthRequest(BaseModel):
    """Payload สำหรับส่งค่ารังสีจริง (GHI Ground Truth) จากหน้าเว็บ."""
    station_id: str
    timestamp: str  # ISO-8601 string, e.g. "2026-09-30T16:10:00"
    ghi_actual: float  # W/m2 from pyranometer
    temperature: float | None = None
    relative_humidity: float | None = None
    notes: str | None = None


class SubmitGroundTruthResponse(BaseModel):
    task_id: int
    annotation_id: int
    station_id: str
    timestamp: str
    ghi_actual: float
    retrain_enqueued: bool
    retrain_status: str


class GroundTruthItem(BaseModel):
    timestamp: str  # ISO-8601; ไม่มี timezone = เวลาไทย (UTC+7); ระบบปัดลงเป็นช่อง 10 นาที
    ghi_actual: float
    notes: str | None = None


class BatchSubmitGroundTruthRequest(BaseModel):
    station_id: str
    items: list[GroundTruthItem] = Field(min_length=1, max_length=2000)
    source: Literal["manual", "file"] = "manual"


class RejectedItem(BaseModel):
    index: int
    reason: str


class BatchSubmitGroundTruthResponse(BaseModel):
    station_id: str
    received: int
    created: int
    updated: int
    unchanged: int
    rejected: list[RejectedItem]
    retrain_enqueued: bool
    retrain_status: str


class UploadPreviewResponse(BaseModel):
    filename: str
    headers: list[str]
    guessed_timestamp: str | None = None
    guessed_ghi: str | None = None
    sample_rows: list[list[str]]
    total_rows: int


class UploadGroundTruthResponse(BatchSubmitGroundTruthResponse):
    filename: str
    date: str
    total_rows: int
    invalid_rows: int
    outside_day: int
    duplicates_collapsed: int
    clamped_negative: int

