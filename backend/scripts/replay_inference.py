"""Replay the real inference worker for a past moment (real weather rows + real satellite frames).

Used to check the forecast pipeline in daytime conditions and to compare forecasts with measured GHI.
Nothing is written to the database: the job result is only read back from Redis and printed.

Usage (api container):
    PYTHONPATH=/app uv run python scripts/replay_inference.py ST-002 2026-10-04T07:00:00+00:00
"""
import asyncio
import json
import math
import sys
from datetime import datetime, timedelta, timezone

from arq import create_pool
from arq.connections import RedisSettings
from arq.jobs import Job
from sqlalchemy import select

from api.inference.service import INFERENCE_QUEUE, deployed_lookback_steps
from api.ingestion.model import WeatherHistory
from api.stations.model import Station
from core.config import settings
from db.database import SessionLocal


async def main(station_id: str, at_iso: str) -> None:
    at = datetime.fromisoformat(at_iso)
    lookback = deployed_lookback_steps()
    async with SessionLocal() as db:
        station = (await db.execute(select(Station).where(Station.id == station_id))).scalar_one()
        rows = (await db.execute(
            select(WeatherHistory).where(WeatherHistory.station_id == station_id, WeatherHistory.timestamp <= at)
            .order_by(WeatherHistory.timestamp.desc()).limit(lookback)
        )).scalars().all()
    rows = list(reversed(rows))
    assert len(rows) == lookback, f"only {len(rows)} rows"
    th = timezone(timedelta(hours=7))
    feats = []
    for r in rows:
        t = r.timestamp.astimezone(th)
        m = t.hour * 60 + t.minute
        doy = t.timetuple().tm_yday
        feats.append([
            float(r.ghi), float(r.dni), float(r.dhi or 0.0), float(r.clearsky_ghi), float(r.solar_zenith_angle),
            max(0.0, min(1.0, float(r.clearsky_index))), float(r.temperature), float(r.relative_humidity),
            float(r.surface_pressure or 1008.0), float(r.wind_speed),
            math.sin(2 * math.pi * m / 1440), math.cos(2 * math.pi * m / 1440),
            math.sin(2 * math.pi * doy / 365.25), math.cos(2 * math.pi * doy / 365.25),
            math.sin(2 * math.pi * (t.month - 1) / 12), math.cos(2 * math.pi * (t.month - 1) / 12),
        ])
    data_time = rows[-1].timestamp
    pool = await create_pool(RedisSettings(host=settings.redis_host, port=settings.redis_port))
    job_id = f"daytest-{station_id}-{int(datetime.now(timezone.utc).timestamp())}"
    await pool.enqueue_job(
        "run_inference", station.id, station.target_capacity_kw, "latest",
        weather_features=feats, data_time=data_time.isoformat(),
        station_lat=station.latitude, station_lon=station.longitude,
        panel_area=station.panel_area, efficiency=station.efficiency,
        _job_id=job_id, _queue_name=INFERENCE_QUEUE,
    )
    res = await Job(job_id, pool, _queue_name=INFERENCE_QUEUE).result(timeout=120)
    await pool.close()
    keep = ["forecast_origin", "satellite_status", "satellite_reason", "satellite_end_time", "satellite_lag_minutes",
            "cloud_coverage_now_pct", "cloud_impact_level", "is_night", "estimated_power_kw", "target_power_kw",
            "delta_p_kw", "reserve_kw", "alert_level", "recommendation_text", "model_version"]
    print(json.dumps({k: res.get(k) for k in keep}, ensure_ascii=False, indent=1))
    for k in ("ghi_forecast_lstm_raw", "ghi_forecast_curve", "clearsky_ghi", "blend_weight", "cloud_coverage_pct"):
        print(k, res.get(k))
    print("actual GHI rows after data_time are in weather_history for comparison; data_time =", data_time.isoformat())


asyncio.run(main(sys.argv[1], sys.argv[2]))
