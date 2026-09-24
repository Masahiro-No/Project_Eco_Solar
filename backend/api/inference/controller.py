from fastapi import Depends

from api.auth.model import User
from api.auth.service import get_current_user
from api.inference.schema import InferenceRequest, InferenceResponse, InferenceResultResponse
from api.inference.service import InferenceService


async def predict(
    payload: InferenceRequest,
    _: User = Depends(get_current_user),
) -> InferenceResponse:
    """รับ Text แล้ว Enqueue งาน Inference ไปที่ Worker"""
    job_id = await InferenceService.enqueue_inference(
        payload.text,
        payload.model_name,
        payload.version,
    )
    return InferenceResponse(job_id=job_id, status="queued")


async def get_result(
    job_id: str,
    _: User = Depends(get_current_user),
) -> InferenceResultResponse:
    """ดึงผลลัพธ์ Inference ด้วย job_id"""
    data = await InferenceService.get_result(job_id)
    return InferenceResultResponse(
        job_id=data["job_id"],
        status=data["status"],
        result=data["result"],
    )
