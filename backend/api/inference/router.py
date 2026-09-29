from fastapi import APIRouter, status

from api.inference.controller import (
    get_latest_prediction,
    get_prediction_history,
    get_result,
    predict,
)
from api.inference.schema import (
    InferenceResponse,
    InferenceResultResponse,
    PredictionResultData,
)

router = APIRouter(prefix="/inference", tags=["inference"])

router.add_api_route(
    "/predict",
    predict,
    methods=["POST"],
    response_model=InferenceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enqueue 3-Hour Solar Forecast Request",
)
router.add_api_route(
    "/result/{job_id}",
    get_result,
    methods=["GET"],
    response_model=InferenceResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Forecast Result by Job ID",
)
router.add_api_route(
    "/latest/{station_id}",
    get_latest_prediction,
    methods=["GET"],
    response_model=PredictionResultData,
    status_code=status.HTTP_200_OK,
    summary="Get Latest Pre-computed Forecast for Station Dashboard",
)
router.add_api_route(
    "/history/{station_id}",
    get_prediction_history,
    methods=["GET"],
    response_model=list[PredictionResultData],
    status_code=status.HTTP_200_OK,
    summary="Get Historical Forecasts for Comparison",
)
