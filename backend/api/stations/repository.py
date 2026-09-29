import math
from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.stations.model import Station
from api.stations.schema import StationCreateRequest, StationPatchRequest, StationUpdateRequest


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in km between two lat/lon points using Haversine formula."""
    r = 6371.0  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


class StationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_all(self, include_archived: bool = False, limit: int = 50, offset: int = 0) -> Sequence[Station]:
        stmt = select(Station)
        if not include_archived:
            stmt = stmt.where(Station.is_active.is_(True))
        stmt = stmt.order_by(Station.id.asc()).limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_archived(self) -> Sequence[Station]:
        stmt = select(Station).where(Station.is_active.is_(False)).order_by(Station.deleted_at.desc())
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_by_id(self, station_id: str, include_archived: bool = False) -> Optional[Station]:
        stmt = select(Station).where(Station.id == station_id)
        if not include_archived:
            stmt = stmt.where(Station.is_active.is_(True))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, payload: StationCreateRequest) -> Station:
        station_id = payload.id
        if not station_id:
            # Generate ID based on current count
            count_stmt = select(Station)
            existing = await self.db.execute(count_stmt)
            count = len(existing.scalars().all()) + 1
            station_id = f"ST-{count:03d}"

        station = Station(
            id=station_id,
            name=payload.name,
            latitude=payload.latitude,
            longitude=payload.longitude,
            panel_area=payload.panel_area,
            efficiency=payload.efficiency,
            target_capacity_kw=payload.target_capacity_kw,
            is_active=True,
        )
        self.db.add(station)
        await self.db.commit()
        await self.db.refresh(station)
        return station

    async def update(self, station: Station, payload: StationUpdateRequest) -> Station:
        station.name = payload.name
        station.latitude = payload.latitude
        station.longitude = payload.longitude
        station.panel_area = payload.panel_area
        station.efficiency = payload.efficiency
        station.target_capacity_kw = payload.target_capacity_kw
        station.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(station)
        return station

    async def patch(self, station: Station, payload: StationPatchRequest) -> Station:
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(station, field, value)
        station.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(station)
        return station

    async def soft_delete(self, station: Station) -> Station:
        station.is_active = False
        station.deleted_at = datetime.now(timezone.utc)
        station.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(station)
        return station

    async def restore(self, station: Station) -> Station:
        station.is_active = True
        station.deleted_at = None
        station.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(station)
        return station

    async def find_nearest(self, lat: float, lon: float) -> Optional[tuple[Station, float]]:
        active_stations = await self.get_all(include_archived=False)
        if not active_stations:
            return None

        best_station = None
        min_distance = float("inf")

        for station in active_stations:
            dist = haversine_distance(lat, lon, station.latitude, station.longitude)
            if dist < min_distance:
                min_distance = dist
                best_station = station

        if best_station is None:
            return None
        return best_station, round(min_distance, 2)
