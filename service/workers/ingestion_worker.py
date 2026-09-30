"""Ingestion Worker — Automated Satellite & Real-time Weather Fetcher

Scheduled via ARQ Cron (every 10 minutes, matching Himawari satellite scan interval).

Flow:
  1. Fetch the latest Himawari satellite imagery from NICT Japan (once per round).
  2. Upload satellite imagery to MinIO 'satellite-cache' bucket.
  3. Register metadata in PostgreSQL 'satellite_frames' table.
  4. Ensure past 12 consecutive frames (2 hours) are present via auto_catchup_satellite.
  5. Backfill/heal any missing weather intervals (auto_catchup_weather).
  6. Query live weather (GHI, DHI, DNI, Clearsky, Temperature, etc.) from Open-Meteo.
  7. Record OpenTelemetry traces & Prometheus metrics.
"""

import io
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Ensure backend is in sys.path for local dev and docker containers
BASE_DIR = Path(__file__).resolve().parent.parent.parent
for p in [str(BASE_DIR / "backend"), "/workspace/backend"]:
    if p not in sys.path and Path(p).exists():
        sys.path.insert(0, p)

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from sqlalchemy import select

from api.ingestion.model import SatelliteFrameMetadata, WeatherHistory
from api.ingestion.normalizer import WeatherDataNormalizer
from api.ingestion.service import IngestionService, SATELLITE_BUCKET
from api.stations.model import Station
from api.storage.service import StorageService
from core.config import settings
from db.database import SessionLocal

# ── Logging Configuration ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Ingestion Worker] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ingestion_worker")

# ── OpenTelemetry Telemetry Setup ───────────────────────────────────────────
_otel_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
_service_name = os.environ.get("OTEL_SERVICE_NAME", "ingestion-worker")
resource = Resource.create({"service.name": _service_name, "service.version": "0.2.0"})

_tracer_provider = TracerProvider(resource=resource)
_tracer_provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint=_otel_endpoint, insecure=True))
)
trace.set_tracer_provider(_tracer_provider)
tracer = trace.get_tracer("ingestion_worker")

_metric_reader = PeriodicExportingMetricReader(
    OTLPMetricExporter(endpoint=_otel_endpoint, insecure=True),
    export_interval_millis=15000,
)
_meter_provider = MeterProvider(resource=resource, metric_readers=[_metric_reader])
metrics.set_meter_provider(_meter_provider)
meter = metrics.get_meter("ingestion_worker")

runs_counter = meter.create_counter(
    name="ingestion_pipeline_runs_total",
    description="Total executions of scheduled ingestion pipeline",
    unit="1",
)
duration_histogram = meter.create_histogram(
    name="ingestion_pipeline_duration_seconds",
    description="Execution duration of ingestion pipeline in seconds",
    unit="s",
)


# ── Core Worker Functions ───────────────────────────────────────────────────

async def scheduled_ingest_pipeline(ctx: dict) -> dict[str, Any]:
    """ARQ Cron Task — Runs every 10 minutes to ingest weather and satellite for ALL active stations."""
    start_time = time.time()
    job_id = ctx.get("job_id", f"cron-ingest-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}")
    logger.info(f"Starting scheduled ingestion pipeline (Job: {job_id})")

    results = {
        "job_id": job_id,
        "satellite_frame": None,
        "stations_processed": 0,
        "stations": {},
    }

    with tracer.start_as_current_span("ingestion.scheduled_pipeline", attributes={"job.id": job_id}) as span:
        # 1. Fetch latest NICT Himawari satellite frame ONCE per round
        img_bytes, dt_frame, filename = None, None, None
        try:
            img_bytes, dt_frame, filename = IngestionService.fetch_nict_realtime_image()
            if img_bytes and dt_frame:
                results["satellite_frame"] = {
                    "filename": filename,
                    "timestamp": dt_frame.isoformat(),
                    "size_bytes": len(img_bytes),
                }
                logger.info(f"Fetched latest NICT satellite frame: {filename} ({len(img_bytes):,} bytes)")
                span.set_attribute("satellite.filename", filename)
                span.set_attribute("satellite.frame_time", dt_frame.isoformat())
        except Exception as e:
            logger.warning(f"Could not fetch NICT satellite image: {e}")
            span.record_exception(e)

        storage = StorageService()
        try:
            storage.create_bucket(SATELLITE_BUCKET)
        except Exception:
            pass

        # 2. Iterate through all active stations in Database
        async with SessionLocal() as db:
            station_stmt = select(Station).where(Station.is_active == True)
            res = await db.execute(station_stmt)
            active_stations = res.scalars().all()
            results["stations_processed"] = len(active_stations)
            logger.info(f"Processing ingestion for {len(active_stations)} active stations.")

            for st in active_stations:
                st_info = {
                    "weather_recorded": False,
                    "satellite_recorded": False,
                    "catchup_records": 0,
                    "sat_backfilled": 0,
                }

                # A. Save satellite frame metadata & upload to station folder
                if img_bytes and dt_frame and filename:
                    try:
                        object_name = f"{st.id}/{filename}"
                        storage.upload_file(
                            bucket_name=SATELLITE_BUCKET,
                            object_name=object_name,
                            data=io.BytesIO(img_bytes),
                            length=len(img_bytes),
                            content_type="image/png",
                        )

                        # Idempotent DB insert: check if (station_id, frame_timestamp) already exists
                        exist_stmt = select(SatelliteFrameMetadata).where(
                            SatelliteFrameMetadata.station_id == st.id,
                            SatelliteFrameMetadata.frame_timestamp == dt_frame,
                        )
                        existing_frame = (await db.execute(exist_stmt)).scalar_one_or_none()
                        if not existing_frame:
                            frame_record = SatelliteFrameMetadata(
                                station_id=st.id,
                                frame_timestamp=dt_frame,
                                image_url=f"/api/storage/download/{SATELLITE_BUCKET}/{object_name}",
                            )
                            db.add(frame_record)
                        st_info["satellite_recorded"] = True
                    except Exception as se:
                        logger.warning(f"Failed to store satellite frame for station {st.id}: {se}")

                # B. Auto Catch-up (heal missing weather and satellite gaps)
                try:
                    catchup_res = await IngestionService.auto_catchup_weather(db, station_id=st.id)
                    st_info["catchup_records"] = catchup_res.get("records_inserted", 0)
                    if st_info["catchup_records"] > 0:
                        logger.info(f"[{st.id}] Healed {st_info['catchup_records']} missing weather intervals.")
                except Exception as ce:
                    logger.warning(f"[{st.id}] Auto catch-up weather error: {ce}")

                try:
                    sat_catchup_res = await IngestionService.auto_catchup_satellite(db, station_id=st.id, count=12)
                    st_info["sat_backfilled"] = sat_catchup_res.get("frames_backfilled", 0)
                    if st_info["sat_backfilled"] > 0:
                        logger.info(f"[{st.id}] Backfilled {st_info['sat_backfilled']} missing satellite frames.")
                except Exception as se:
                    logger.warning(f"[{st.id}] Satellite catch-up error: {se}")

                # C. Live Open-Meteo Ingestion
                try:
                    raw_weather = IngestionService.fetch_open_meteo_live(st.latitude, st.longitude)
                    canonical = WeatherDataNormalizer.normalize_open_meteo(
                        raw_weather, st.id, lat=st.latitude, lon=st.longitude
                    )

                    # Idempotent DB check for exact timestamp
                    w_exist_stmt = select(WeatherHistory).where(
                        WeatherHistory.station_id == st.id,
                        WeatherHistory.timestamp == canonical.timestamp,
                    )
                    existing_weather = (await db.execute(w_exist_stmt)).scalar_one_or_none()
                    if not existing_weather:
                        weather_rec = WeatherHistory(
                            station_id=st.id,
                            timestamp=canonical.timestamp,
                            ghi=canonical.ghi,
                            dni=canonical.dni,
                            dhi=canonical.dhi,
                            clearsky_ghi=canonical.clearsky_ghi,
                            clearsky_index=canonical.clearsky_index,
                            solar_zenith_angle=canonical.solar_zenith_angle,
                            temperature=canonical.temperature,
                            relative_humidity=canonical.relative_humidity,
                            wind_speed=canonical.wind_speed,
                            cloud_cover=canonical.cloud_cover,
                            surface_pressure=canonical.surface_pressure,
                            source=canonical.source,
                        )
                        db.add(weather_rec)
                    st_info["weather_recorded"] = True
                    st_info["ghi"] = canonical.ghi
                except Exception as we:
                    logger.warning(f"[{st.id}] Live weather fetch error: {we}")

                results["stations"][st.id] = st_info

            await db.commit()

        duration = time.time() - start_time
        results["duration_seconds"] = round(duration, 2)
        runs_counter.add(1)
        duration_histogram.record(duration)
        try:
            _metric_reader.force_flush()
        except Exception:
            pass

        logger.info(f"Ingestion pipeline completed for all stations in {duration:.2f}s")
        return results


async def ingest_single_station(ctx: dict, station_id: str) -> dict[str, Any]:
    """On-demand task to immediately trigger ingestion for a single station."""
    logger.info(f"Manual ingestion triggered for station: {station_id}")
    async with SessionLocal() as db:
        res = await IngestionService.trigger_ingest(station_id, db)
        return {"station_id": station_id, "status": res.status, "message": res.message}


async def startup(ctx: dict) -> None:
    logger.info("Ingestion Worker started up successfully. Listening on 'ingest_queue'.")


async def shutdown(ctx: dict) -> None:
    logger.info("Ingestion Worker shutting down...")
