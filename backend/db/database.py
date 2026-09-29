from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from core.config import Settings

settings = Settings()

class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def create_database_schema() -> None:
    # Import models before metadata is created so SQLAlchemy knows every table.
    from api.auth import model as auth_model  # noqa: F401
    from api.stations import model as station_model  # noqa: F401
    from api.inference import model as inference_model  # noqa: F401
    from api.ingestion import model as ingestion_model  # noqa: F401

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def seed_default_stations() -> None:
    """Seed initial reference station (ม.อ. หาดใหญ่) if not present."""
    from sqlalchemy import select
    from api.stations.model import Station

    async with SessionLocal() as session:
        stmt = select(Station).where(Station.id == "ST-001")
        existing = await session.execute(stmt)
        if not existing.scalar_one_or_none():
            station = Station(
                id="ST-001",
                name="PSU Hat Yai Solar Farm (ม.อ. หาดใหญ่)",
                latitude=7.0086,
                longitude=100.4988,
                panel_area=30000.0,
                efficiency=0.185,
                target_capacity_kw=5000.0,
                is_active=True,
            )
            session.add(station)
            await session.commit()