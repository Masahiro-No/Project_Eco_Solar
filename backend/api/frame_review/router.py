from fastapi import APIRouter, status

from api.frame_review.controller import convlstm_status, list_frames, submit_reviews
from api.frame_review.schema import ConvLstmStatusResponse, FrameListResponse, SubmitReviewsResponse

router = APIRouter(prefix="/frame-review", tags=["frame-review"])
router.add_api_route("/frames", list_frames, methods=["GET"], response_model=FrameListResponse, status_code=status.HTTP_200_OK)
router.add_api_route("/frames", submit_reviews, methods=["POST"], response_model=SubmitReviewsResponse, status_code=status.HTTP_200_OK)
router.add_api_route("/status", convlstm_status, methods=["GET"], response_model=ConvLstmStatusResponse, status_code=status.HTTP_200_OK)
