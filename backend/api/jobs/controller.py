from fastapi import Depends

from api.auth.model import User
from api.auth.service import require_admin
from api.jobs.schema import (
    CancelJobResponse,
    ClearQueueResponse,
    EnqueueRequest,
    EnqueueResponse,
    JobStatusResponse,
    QueueJobsResponse,
    QueueSummaryResponse,
    RetryJobResponse,
    TrainRequest,
    TrainResponse,
)
from api.jobs.service import JobService


async def enqueue_job(
    payload: EnqueueRequest,
    _: User = Depends(require_admin),
) -> EnqueueResponse:
    job_id = await JobService.enqueue(payload.function_name, payload.job_data)
    return EnqueueResponse(job_id=job_id)


async def enqueue_train_job(
    payload: TrainRequest,
    _: User = Depends(require_admin),
) -> TrainResponse:
    job_id = await JobService.enqueue_train(
        payload.model_type,
        payload.epochs,
        payload.batch_size,
        payload.start_time,
    )
    return TrainResponse(job_id=job_id, scheduled_at=payload.start_time)


async def get_job_status(
    job_id: str,
    _: User = Depends(require_admin),
) -> JobStatusResponse:
    result = await JobService.get_status(job_id)
    return JobStatusResponse(**result)


async def get_all_queues_summary(
    _: User = Depends(require_admin),
) -> list[QueueSummaryResponse]:
    """สรุปภาพรวมของทุกคิวใน Redis (จำนวนงานที่รอ, กำลังรัน, พัง)"""
    summaries = await JobService.get_all_queues_summary()
    return [QueueSummaryResponse(**s) for s in summaries]


async def get_queue_jobs(
    name: str,
    _: User = Depends(require_admin),
) -> QueueJobsResponse:
    """ดูรายการ Job ทั้งหมดที่ค้างอยู่ในคิวที่เลือก"""
    result = await JobService.get_queue_jobs(name)
    return QueueJobsResponse(**result)


async def cancel_job(
    job_id: str,
    _: User = Depends(require_admin),
) -> CancelJobResponse:
    """ยกเลิก / ลบ Job ออกจากคิวทันท่วงที (Cancel Job)"""
    result = await JobService.cancel_job(job_id)
    return CancelJobResponse(**result)


async def retry_job(
    job_id: str,
    _: User = Depends(require_admin),
) -> RetryJobResponse:
    """สั่งให้ Job ที่เคย Failed รันใหม่อีกครั้ง"""
    result = await JobService.retry_job(job_id)
    return RetryJobResponse(**result)


async def clear_queue(
    name: str,
    _: User = Depends(require_admin),
) -> ClearQueueResponse:
    """ล้างคิวงานทั้งหมด (Flush Pending Jobs)"""
    result = await JobService.clear_queue(name)
    return ClearQueueResponse(**result)
