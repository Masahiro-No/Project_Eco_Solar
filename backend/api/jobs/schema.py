from typing import Optional

from pydantic import BaseModel


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    result: Optional[str] = None


# ─── Redis Queue Management Schemas ──────────────────────────────────────────

class QueueSummaryResponse(BaseModel):
    queue_name: str
    pending: int
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
