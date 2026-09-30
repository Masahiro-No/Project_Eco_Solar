"""Seed Weather History Table in PostgreSQL

Loads historical NSRDB 10-minute records into PostgreSQL 'weather_history' table
so the API endpoints and Dashboard have operational data to query.
"""

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Add backend directory to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from api.ingestion.model import WeatherHistory
from api.stations.model import Station
from db.database import SessionLocal, create_database_schema, seed_default_stations

MINIO_ENDPOINT = "localhost:9000"
MINIO_ACCESS_KEY = "admin"
MINIO_SECRET_KEY = "password"


def _load_data_from_minio_or_local() -> pd.DataFrame:
    """Stream test_10min.csv from MinIO or fallback to local disk."""
    import io
    from minio import Minio

    local_path = BASE_DIR.parent / "data" / "timeseries" / "test_10min.csv"
    if local_path.exists():
        print(f"[1/3] Reading NSRDB data from local disk: {local_path.name}")
        return pd.read_csv(local_path)

    print("[1/3] Streaming NSRDB test_10min.csv directly from MinIO (datasets/timeseries/test_10min.csv)...")
    client = Minio(MINIO_ENDPOINT, access_key=MINIO_ACCESS_KEY, secret_key=MINIO_SECRET_KEY, secure=False)
    resp = client.get_object("datasets", "timeseries/test_10min.csv")
    df = pd.read_csv(io.BytesIO(resp.read()))
    resp.close()
    resp.release_conn()
    return df


async def seed_weather_data(days: int = 30, station_id: str = "ST-001"):
    print("=" * 60)
    print(f">> SEEDING WEATHER HISTORY INTO POSTGRESQL (Station: {station_id})")
    print("=" * 60)

    # 1. Initialize DB schema and seed default station
    await create_database_schema()
    await seed_default_stations()

    # 2. Read recent rows from MinIO or local
    df = _load_data_from_minio_or_local()
    df["Datetime"] = pd.to_datetime(df["Datetime"])

    # Filter to requested number of days (10 min = 144 steps/day)
    total_steps = days * 144
    df_subset = df.tail(total_steps).copy()
    print(f"  - Loaded {len(df_subset):,} rows (~{days} days from {df_subset['Datetime'].min()} to {df_subset['Datetime'].max()})")


    # 3. Insert into PostgreSQL
    print("[2/3] Writing records to PostgreSQL...")
    async with SessionLocal() as session:
        # Check existing count
        existing_stmt = select(WeatherHistory).where(WeatherHistory.station_id == station_id).limit(1)
        res = await session.execute(existing_stmt)
        if res.scalar_one_or_none():
            print(f"  [Info] Station {station_id} already has weather records in DB.")

        records = []
        for _, row in df_subset.iterrows():
            dt = row["Datetime"]
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            record = WeatherHistory(
                station_id=station_id,
                timestamp=dt,
                ghi=float(row["GHI"]),
                dni=float(row["DNI"]),
                dhi=float(row["DHI"]),
                clearsky_ghi=float(row["Clearsky GHI"]),
                clearsky_index=float(row["clearsky_ratio"]),
                solar_zenith_angle=float(row["Solar Zenith Angle"]),
                temperature=float(row["Temperature"]),
                relative_humidity=float(row["Relative Humidity"]),
                wind_speed=float(row["Wind Speed"]),
                cloud_cover=float(round((1.0 - min(row["clearsky_ratio"], 1.0)) * 100.0, 2)),
                surface_pressure=float(row["Pressure"]),
                source="nsrdb_2020",
            )
            records.append(record)

        session.add_all(records)
        await session.commit()
        print(f"[3/3] Successfully inserted {len(records):,} weather records into 'weather_history' table!")


def main():
    parser = argparse.ArgumentParser(description="Seed weather history in PostgreSQL")
    parser.add_argument("--days", type=int, default=30, help="Number of recent days to seed (default: 30)")
    parser.add_argument("--station", type=str, default="ST-001", help="Station ID (default: ST-001)")
    args = parser.parse_args()

    asyncio.run(seed_weather_data(days=args.days, station_id=args.station))


if __name__ == "__main__":
    main()
