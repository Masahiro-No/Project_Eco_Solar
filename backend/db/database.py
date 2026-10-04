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
    """Seed initial reference stations, default operator user, and initial forecast if not present."""
    from datetime import datetime, timezone
    import uuid
    from sqlalchemy import select
    from api.stations.model import Station
    from api.auth.model import User
    from api.inference.model import Prediction
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

        # 2. Seed Default Operator User
        user_stmt = select(User).where(User.email == "operator@solardss.io")
        existing_user = (await session.execute(user_stmt)).scalar_one_or_none()
        if not existing_user:
            user = User(
                email="operator@solardss.io",
                password_hash=pwd_context.hash("operator1234"),
            )
            session.add(user)

        # 3. Seed Initial Predictions for all 5 stations if none exists
        initial_predictions_data = [
            {
                "station_id": "ST-001",
                "ghi_curve": [685.2, 742.0, 715.4, 620.1, 510.3, 380.0],
                "pgen": 4087.0,
                "target": 5000.0,
                "delta_p": -913.0,
                "cloud": "Inward",
                "conf": 0.88,
                "alert": "Early Warning",
                "rec": "เมฆหนาทึบกำลังเคลื่อนตัวเข้าสู่สถานี ม.อ. หาดใหญ่ — แนะนำเตรียมจ่ายพลังงานสำรองจาก BESS ชดเชย 913 kW",
            },
            {
                "station_id": "ST-002",
                "ghi_curve": [775.0, 810.0, 790.0, 725.0, 580.0, 410.0],
                "pgen": 3441.0,
                "target": 4000.0,
                "delta_p": -559.0,
                "cloud": "Clear",
                "conf": 0.94,
                "alert": "Normal",
                "rec": "สภาพอากาศปลอดโปร่งชายฝั่งสงขลา กำลังผลิตคงที่ ไม่มีสัญญาณก้อนเมฆบดบัง",
            },
            {
                "station_id": "ST-003",
                "ghi_curve": [718.0, 755.0, 730.0, 640.0, 490.0, 340.0],
                "pgen": 2456.0,
                "target": 3000.0,
                "delta_p": -544.0,
                "cloud": "Clear",
                "conf": 0.91,
                "alert": "Normal",
                "rec": "การผลิตพลังงานแสงอาทิตย์นครศรีธรรมราชปกติ สอดคล้องตามแผนจ่ายไฟ",
            },
            {
                "station_id": "ST-004",
                "ghi_curve": [760.0, 785.0, 750.0, 680.0, 520.0, 360.0],
                "pgen": 2052.0,
                "target": 2500.0,
                "delta_p": -448.0,
                "cloud": "Outward",
                "conf": 0.89,
                "alert": "Normal",
                "rec": "ก้อนเมฆกำลังเคลื่อนตัวออกจากพื้นที่ปัตตานี แนวโน้มรังสีอาทิตย์มีเสถียรภาพ",
            },
            {
                "station_id": "ST-005",
                "ghi_curve": [650.0, 680.0, 620.0, 510.0, 390.0, 270.0],
                "pgen": 1984.0,
                "target": 2750.0,
                "delta_p": -766.0,
                "cloud": "Inward",
                "conf": 0.85,
                "alert": "Normal",
                "rec": "มีกลุ่มเมฆฝั่งอันดามันเคลื่อนตัวสู่ตรัง รังสีดวงอาทิตย์ลดลงเล็กน้อย อยู่ในเกณฑ์ปกติ",
            },
        ]

        now_dt = datetime.now(timezone.utc)
        for pdata in initial_predictions_data:
            pred_stmt = select(Prediction).where(Prediction.station_id == pdata["station_id"]).limit(1)
            existing_pred = (await session.execute(pred_stmt)).scalar_one_or_none()
            if not existing_pred:
                initial_pred = Prediction(
                    job_id=str(uuid.uuid4()),
                    station_id=pdata["station_id"],
                    predicted_at=now_dt,
                    forecast_horizon_hours=3,
                    ghi_forecast_curve=pdata["ghi_curve"],
                    estimated_power_kw=pdata["pgen"],
                    target_power_kw=pdata["target"],
                    delta_p_kw=pdata["delta_p"],
                    cloud_trend=pdata["cloud"],
                    confidence=pdata["conf"],
                    alert_level=pdata["alert"],
                    recommendation_text=pdata["rec"],
                    satellite_frame_url=None,
                )
                session.add(initial_pred)

        await session.commit()