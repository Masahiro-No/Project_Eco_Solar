from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class EnqueueRequest(BaseModel):
    function_name: str
    job_data: str


class EnqueueResponse(BaseModel):
    job_id: str
    status: str = "queued"


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    result: Optional[str] = None


class TrainRequest(BaseModel):
    model_type: str = "lstm"  # "lstm" or "convlstm"
    epochs: int = 10
    batch_size: int = 32
    start_time: Optional[datetime] = None


class TrainResponse(BaseModel):
    job_id: str
    status: str = "queued"
    scheduled_at: Optional[datetime] = None


# ─── Redis Queue Management Schemas ──────────────────────────────────────────

class QueueSummaryResponse(BaseModel):
    queue_name: str
    pending: int
    active: int
    failed: int
    total_keys: int


class QueueJobsResponse(BaseModel):
    queue_name: str
    count: int
    jobs: list[str]


class CancelJobResponse(BaseModel):
    job_id: str
    status: str = "canceled"
    message: str


class RetryJobResponse(BaseModel):
    job_id: str
    status: str = "requeued"
    message: str


class ClearQueueResponse(BaseModel):
    queue_name: str
    message: str = "cleared"
    removed_count: int
