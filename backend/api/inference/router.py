from fastapi import APIRouter

from api.inference.controller import get_result, predict
from api.inference.schema import InferenceResponse, InferenceResultResponse

router = APIRouter(prefix="/inference", tags=["inference"])

router.add_api_route(
    "/predict",
    predict,
    methods=["POST"],
    response_model=InferenceResponse,
    summary="ส่งข้อความไปให้ Inference Worker วิเคราะห์ NER",
    description="Enqueue งาน Inference ไปที่ Worker แล้วรับ job_id กลับมาทันที",
)

router.add_api_route(
    "/result/{job_id}",
    get_result,
    methods=["GET"],
    response_model=InferenceResultResponse,
    summary="ดูผลการ Inference ด้วย job_id",
    description="ดึงผล NER Entities จาก Redis Job Result ด้วย job_id ที่ได้รับจาก /predict",
)
