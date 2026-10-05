from fastapi import APIRouter, status

from api.retrain.controller import get_retrain_status
from api.retrain.schema import RetrainStatusResponse

router = APIRouter(prefix="/retrain", tags=["retrain"])

router.add_api_route(
    "/status",
    get_retrain_status,
    methods=["GET"],
    response_model=RetrainStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Deployed models, pending retrains and the retrain history of both models",
)
