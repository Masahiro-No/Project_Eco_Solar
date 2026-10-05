from fastapi import Depends

from api.auth.model import User
from api.auth.service import require_admin
from api.jobs.schema import (
    CancelJobResponse,
    ClearQueueResponse,
    JobStatusResponse,
    QueueJobsResponse,
    QueueSummaryResponse,
    RetryJobResponse,
)
from api.jobs.service import JobService


async def get_job_status(
    job_id: str,
    _: User = Depends(require_admin),
) -> JobStatusResponse:
    result = await JobService.get_status(job_id)
    return JobStatusResponse(**result)


async def get_all_queues_summary(
    _: User = Depends(require_admin),
) -> list[QueueSummaryResponse]:
    """สรุปจำนวนงานที่รอในแต่ละคิวของ Redis"""
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
