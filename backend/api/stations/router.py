from fastapi import APIRouter, status

from api.stations.controller import (
    create_station,
    find_nearest_station,
    get_all_stations,
    get_archived_stations,
    get_station_by_id,
    patch_station,
    restore_station,
    soft_delete_station,
    update_station,
)
from api.stations.schema import NearestStationResponse, StationResponse

router = APIRouter(prefix="/stations", tags=["stations"])

# Static sub-routes must be registered before dynamic /{station_id} route
router.add_api_route(
    "",
    get_all_stations,
    methods=["GET"],
    response_model=list[StationResponse],
    status_code=status.HTTP_200_OK,
    summary="List Active Solar Stations",
)
router.add_api_route(
    "",
    create_station,
    methods=["POST"],
    response_model=StationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create New Solar Station",
)
router.add_api_route(
    "/archived",
    get_archived_stations,
    methods=["GET"],
    response_model=list[StationResponse],
    status_code=status.HTTP_200_OK,
    summary="List Archived / Soft-Deleted Stations",
)
router.add_api_route(
    "/nearest",
    find_nearest_station,
    methods=["GET"],
    response_model=NearestStationResponse,
    status_code=status.HTTP_200_OK,
    summary="Find Nearest Solar Station by Coordinates",
)
router.add_api_route(
    "/{station_id}",
    get_station_by_id,
    methods=["GET"],
    response_model=StationResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Station Detail by ID",
)
router.add_api_route(
    "/{station_id}",
    update_station,
    methods=["PUT"],
    response_model=StationResponse,
    status_code=status.HTTP_200_OK,
    summary="Full Update Station Spec",
)
router.add_api_route(
    "/{station_id}",
    patch_station,
    methods=["PATCH"],
    response_model=StationResponse,
    status_code=status.HTTP_200_OK,
    summary="Partial Update Station Spec",
)
router.add_api_route(
    "/{station_id}",
    soft_delete_station,
    methods=["DELETE"],
    response_model=StationResponse,
    status_code=status.HTTP_200_OK,
    summary="Soft-Delete / Deactivate Station",
)
router.add_api_route(
    "/{station_id}/restore",
    restore_station,
    methods=["PATCH"],
    response_model=StationResponse,
    status_code=status.HTTP_200_OK,
    summary="Restore Soft-Deleted Station",
)
