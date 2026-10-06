import logging
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
    from api.frame_review import model as frame_review_model  # noqa: F401

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(_ensure_prediction_columns)
        await connection.run_sync(_ensure_user_columns)
        await connection.run_sync(_ensure_unique_rules)


def _ensure_unique_rules(sync_conn) -> None:
    """create_all() adds no rule to a table that already exists: add the unique rules of weather and frames.

    When rows that break a rule are already stored the rule cannot be added: the API starts anyway and says so
    (scripts/cleanup_test_data.py --only leftovers lists such rows).
    """
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    from api.ingestion.model import UNIQUE_RULES

    for model, key, name in UNIQUE_RULES:
        try:
            with sync_conn.begin_nested():
                sync_conn.execute(text(f"CREATE UNIQUE INDEX IF NOT EXISTS {name} ON {model.__tablename__} ({', '.join(key)})"))
        except DBAPIError as e:
            logging.getLogger("solar.api").warning(
                f"[Schema] unique rule {name} not added, rows that break it are stored: {str(e.orig)[:200]}"
            )


def _ensure_prediction_columns(sync_conn) -> None:
    """Lightweight migration: create_all() never ALTERs existing tables, so add the
    nullable columns introduced for real-model predictions when they are missing."""
    from sqlalchemy import inspect, text

    inspector = inspect(sync_conn)
    if "predictions" not in inspector.get_table_names():
        return
    existing = {c["name"]: c for c in inspector.get_columns("predictions")}
    postgres = sync_conn.dialect.name == "postgresql"
    timestamp_type = "TIMESTAMP WITH TIME ZONE" if postgres else "DATETIME"
    new_columns = {
        "source": "VARCHAR(20)",
        "data_time": timestamp_type,
        "ghi_forecast_lstm_raw": "JSON",
        "blend_weight": "JSON",
        "reserve_kw": "FLOAT",
        "cloud_coverage_pct": "JSON",
        "cloud_coverage_now_pct": "FLOAT",
        "sat_ghi_loss_pct": "JSON",
        "sat_ghi_loss_now_pct": "FLOAT",
        "target_profile_kw": "JSON",
        "ghi_forecast_lower": "JSON",
        "ghi_forecast_upper": "JSON",
        "satellite_status": "VARCHAR(30)",
        "satellite_lag_minutes": "INTEGER",
        "is_night": "BOOLEAN",
        "model_version": "VARCHAR(30)",
    }
    for name, sql_type in new_columns.items():
        if name not in existing:
            sync_conn.execute(text(f"ALTER TABLE predictions ADD COLUMN {name} {sql_type}"))
    # 'confidence' is no longer written (it was not a real model output)
    if postgres and "confidence" in existing and not existing["confidence"].get("nullable", True):
        sync_conn.execute(text("ALTER TABLE predictions ALTER COLUMN confidence DROP NOT NULL"))


def _ensure_user_columns(sync_conn) -> None:
    """Add users.role to databases created before roles existed (existing accounts become operators)."""
    from sqlalchemy import inspect, text

    inspector = inspect(sync_conn)
    if "users" not in inspector.get_table_names():
        return
    if "role" not in {c["name"] for c in inspector.get_columns("users")}:
        sync_conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'operator'"))


async def seed_default_stations() -> None:
    """Seed the reference stations and the default operator user if not present."""
    from sqlalchemy import select
    from api.stations.model import Station
    from api.auth.model import User
    from pwdlib import PasswordHash

    default_stations = [
        {
            "id": "ST-001",
            "name": "PSU Hat Yai Solar Farm (ม.อ. หาดใหญ่)",
            "latitude": 7.0086,
            "longitude": 100.4988,
            "panel_area": 30000.0,
            "efficiency": 0.185,
            "target_capacity_kw": 5000.0,
        },
        {
            "id": "ST-002",
            "name": "Songkhla Solar Farm (พพ. สงขลา)",
            "latitude": 7.1982,
            "longitude": 100.5954,
            "panel_area": 24000.0,
            "efficiency": 0.185,
            "target_capacity_kw": 4000.0,
        },
        {
            "id": "ST-003",
            "name": "Nakhon Si Thammarat Solar Farm",
            "latitude": 8.4304,
            "longitude": 99.9631,
            "panel_area": 18000.0,
            "efficiency": 0.190,
            "target_capacity_kw": 3000.0,
        },
        {
            "id": "ST-004",
            "name": "Pattani Solar Farm",
            "latitude": 6.8696,
            "longitude": 101.2501,
            "panel_area": 15000.0,
            "efficiency": 0.180,
            "target_capacity_kw": 2500.0,
        },
        {
            "id": "ST-005",
            "name": "Trang Solar Farm",
            "latitude": 7.5563,
            "longitude": 99.6114,
            "panel_area": 16500.0,
            "efficiency": 0.185,
            "target_capacity_kw": 2750.0,
        },
    ]

    pwd_context = PasswordHash.recommended()

    async with SessionLocal() as session:
        # 1. Seed Stations
        for st_data in default_stations:
            stmt = select(Station).where(Station.id == st_data["id"])
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if not existing:
                station = Station(
                    id=st_data["id"],
                    name=st_data["name"],
                    latitude=st_data["latitude"],
                    longitude=st_data["longitude"],
                    panel_area=st_data["panel_area"],
                    efficiency=st_data["efficiency"],
                    target_capacity_kw=st_data["target_capacity_kw"],
                    is_active=True,
                )
                session.add(station)

        # 2. Operator account, only when a password is configured (never a built-in default)
        if settings.operator_password:
            operator = (await session.execute(select(User).where(User.email == settings.operator_email))).scalar_one_or_none()
            if operator is None:
                session.add(User(email=settings.operator_email, password_hash=pwd_context.hash(settings.operator_password)))
            elif not pwd_context.verify(settings.operator_password, operator.password_hash):
                # OPERATOR_PASSWORD in .env is this account's password: changing it there and restarting the API changes it
                operator.password_hash = pwd_context.hash(settings.operator_password)

        # 3. Admin account, only when a password is configured (never a built-in default)
        if settings.admin_password:
            admin = (await session.execute(select(User).where(User.email == settings.admin_email))).scalar_one_or_none()
            if admin is None:
                session.add(User(
                    email=settings.admin_email,
                    password_hash=pwd_context.hash(settings.admin_password),
                    role="admin",
                ))
            else:
                admin.role = "admin"
                # ADMIN_PASSWORD in .env is the admin's password: changing it there and restarting the API changes it
                if not pwd_context.verify(settings.admin_password, admin.password_hash):
                    admin.password_hash = pwd_context.hash(settings.admin_password)

        await session.commit()