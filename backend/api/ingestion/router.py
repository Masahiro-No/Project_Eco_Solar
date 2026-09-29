from fastapi import APIRouter, status

from api.ingestion.controller import (
    get_ingestion_status,
    get_recent_satellite_frames,
    get_recent_weather,
    trigger_ingestion,
)
from api.ingestion.schema import (
    IngestTriggerResponse,
    IngestionStatusResponse,
    SatelliteFrameItem,
    WeatherRecentItem,
)

router = APIRouter(prefix="/ingestion", tags=["ingestion"])

router.add_api_route(
    "/trigger",
    trigger_ingestion,
    methods=["POST"],
    response_model=IngestTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger Real-time Weather & Satellite Ingestion",
)

router.add_api_route(
    "/weather/{station_id}/recent",
    get_recent_weather,
    methods=["GET"],
    response_model=list[WeatherRecentItem],
    status_code=status.HTTP_200_OK,
    summary="Get Normalized Weather Time-series for Station",
)

router.add_api_route(
    "/satellite/{station_id}/frames",
    get_recent_satellite_frames,
    methods=["GET"],
    response_model=list[SatelliteFrameItem],
    status_code=status.HTTP_200_OK,
    summary="Get Recent Satellite Frame Sequences",
)

router.add_api_route(
    "/status",
    get_ingestion_status,
    methods=["GET"],
    response_model=IngestionStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Ingestion Health & Metrics",
)
