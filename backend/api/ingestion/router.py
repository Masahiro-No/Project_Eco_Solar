from fastapi import APIRouter, Response, status

from api.ingestion.controller import (
    get_day_satellite_frames,
    get_ingestion_status,
    get_latest_satellite_crop,
    get_recent_satellite_frames,
    get_recent_weather,
    trigger_auto_catchup,
)
from api.ingestion.schema import (
    DayFramesResponse,
    IngestionStatusResponse,
    SatelliteFrameItem,
    WeatherRecentItem,
)

router = APIRouter(prefix="/ingestion", tags=["ingestion"])

router.add_api_route(
    "/catchup",
    trigger_auto_catchup,
    methods=["POST"],
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Trigger Auto Catch-up / Gap Backfill for Station",
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
router.add_api_route(
    "/satellite/{station_id}/latest.png",
    get_latest_satellite_crop,
    methods=["GET"],
    status_code=status.HTTP_200_OK,
    summary="Newest real satellite crop around a station (PNG)",
    response_class=Response,
)

router.add_api_route(
    "/satellite/{station_id}/day-frames",
    get_day_satellite_frames,
    methods=["GET"],
    response_model=DayFramesResponse,
    status_code=status.HTTP_200_OK,
    summary="Real satellite frames of a day and the newest ConvLSTM forecast frames",
)
