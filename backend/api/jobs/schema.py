from datetime import datetime

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
    result: str | None = None


class TrainRequest(BaseModel):
    dataset_name: str = "conll2003"
    model_name: str = "bert-base-cased"
    start_time: datetime | None = None  # ถ้าไม่ส่งมา = รันทันที


class TrainResponse(BaseModel):
    job_id: str
    status: str = "queued"
    scheduled_at: datetime | None = None
