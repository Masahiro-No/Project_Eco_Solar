from pydantic import BaseModel


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


class SubmitSatelliteAnnotationRequest(BaseModel):
    """Payload สำหรับส่งผลการตรวจสอบภาพถ่ายดาวเทียม (Non-time-series)."""
    station_id: str
    timestamp: str
    cloud_condition: str  # Clear, Inward, Outward, Overcast
    cloud_index: float | None = None
    sequence_id: str | None = None
    notes: str | None = None


class SubmitSatelliteAnnotationResponse(BaseModel):
    task_id: int
    annotation_id: int
    station_id: str
    accumulated_count: int
    threshold: int
    retrain_enqueued: bool
    retrain_status: str
