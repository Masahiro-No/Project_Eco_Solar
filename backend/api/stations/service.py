from typing import Sequence
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.stations.model import Station
from api.stations.repository import StationRepository
from api.stations.schema import (
    NearestStationResponse,
    StationCreateRequest,
    StationPatchRequest,
    StationUpdateRequest,
)


class StationService:
    @staticmethod
    async def get_all_stations(
        db: AsyncSession,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Station]:
        repo = StationRepository(db)
        return await repo.get_all(include_archived=include_archived, limit=limit, offset=offset)

    @staticmethod
    async def get_archived_stations(db: AsyncSession) -> Sequence[Station]:
        repo = StationRepository(db)
        return await repo.get_archived()

    @staticmethod
    async def get_station_by_id(db: AsyncSession, station_id: str, include_archived: bool = False) -> Station:
        repo = StationRepository(db)
        station = await repo.get_by_id(station_id, include_archived=include_archived)
        if not station:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Station with ID '{station_id}' not found.",
            )
        return station

    @staticmethod
    async def create_station(db: AsyncSession, payload: StationCreateRequest) -> Station:
        repo = StationRepository(db)
        if payload.id:
            existing = await repo.get_by_id(payload.id, include_archived=True)
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Station with ID '{payload.id}' already exists.",
                )
        return await repo.create(payload)

    @staticmethod
    async def update_station(db: AsyncSession, station_id: str, payload: StationUpdateRequest) -> Station:
        repo = StationRepository(db)
        station = await StationService.get_station_by_id(db, station_id, include_archived=False)
        return await repo.update(station, payload)

    @staticmethod
    async def patch_station(db: AsyncSession, station_id: str, payload: StationPatchRequest) -> Station:
        repo = StationRepository(db)
        station = await StationService.get_station_by_id(db, station_id, include_archived=False)
        return await repo.patch(station, payload)

    @staticmethod
    async def soft_delete_station(db: AsyncSession, station_id: str) -> Station:
        repo = StationRepository(db)
        station = await StationService.get_station_by_id(db, station_id, include_archived=False)
        return await repo.soft_delete(station)

    @staticmethod
    async def restore_station(db: AsyncSession, station_id: str) -> Station:
        repo = StationRepository(db)
        station = await StationService.get_station_by_id(db, station_id, include_archived=True)
        if station.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Station '{station_id}' is already active.",
            )
        return await repo.restore(station)

    @staticmethod
    async def find_nearest_station(db: AsyncSession, lat: float, lon: float) -> NearestStationResponse:
        repo = StationRepository(db)
        match = await repo.find_nearest(lat, lon)
        if not match:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active solar stations found in database.",
            )
        station, distance = match
        return NearestStationResponse(
            station_id=station.id,
            name=station.name,
            latitude=station.latitude,
            longitude=station.longitude,
            target_capacity_kw=station.target_capacity_kw,
            distance_km=distance,
        )
