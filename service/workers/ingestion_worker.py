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
  8. Chain real-model inference: enqueue `run_inference` for every station whose input data is
     fresh (skipped otherwise), then `collect_inference_results` (cron, every minute) saves the
     finished results into the `predictions` table.
"""

import asyncio
import io
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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

from api.inference.service import InferenceService
from api.ingestion.model import SatelliteFrameMetadata, WeatherHistory, insert_once
from api.ingestion.normalizer import WeatherDataNormalizer
from api.ingestion.service import IngestionService, NICT_LATEST_JSON, SATELLITE_BUCKET, fetch_json
from api.stations.model import Station
from api.storage.service import StorageService
from service.workers.round_lock import clear_round_lock, run_one_at_a_time
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
    """ARQ Cron Task — every 10 minutes and once at worker start. A round that fires while another runs is skipped."""
    ran, result = await run_one_at_a_time(ctx.get("redis"), lambda: _ingest_round(ctx))
    if not ran:
        logger.info("Ingestion round skipped: another round is still running.")
        return {"skipped": "another_round_running"}
    return result


async def _ingest_round(ctx: dict) -> dict[str, Any]:
    """Ingest weather and satellite for ALL active stations, then queue the forecast of each station."""
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
        # 1. Determine latest Himawari observation timestamp from NICT Japan
        dt_frame = None
        try:
            # downloads and uploads of the round run in threads: the worker's other jobs (collecting finished
            # forecasts every minute) and its Redis connection are not held while it waits for the network
            latest_info = await asyncio.to_thread(fetch_json, NICT_LATEST_JSON, 10)
            date_str = latest_info.get("date")
            dt_frame = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            results["satellite_frame"] = {
                "observation_time": dt_frame.isoformat(),
            }
            logger.info(f"Latest Himawari satellite observation timestamp: {dt_frame.isoformat()}")
            span.set_attribute("satellite.frame_time", dt_frame.isoformat())
        except Exception as e:
            logger.warning(f"Could not check NICT observation time: {e}")
            span.record_exception(e)
            now = datetime.now(timezone.utc)
            dt_frame = now.replace(minute=(now.minute // 10) * 10, second=0, microsecond=0)

        storage = StorageService()
        try:
            await asyncio.to_thread(storage.create_bucket, SATELLITE_BUCKET)
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

                # A. Save localized satellite frame metadata & upload to station folder
                st_img_bytes, st_dt_frame, st_filename = await asyncio.to_thread(
                    IngestionService.fetch_station_b03_crop, dt_frame or datetime.now(timezone.utc), st.latitude, st.longitude
                )

                if st_img_bytes and st_dt_frame and st_filename:
                    try:
                        object_name = f"{st.id}/{st_filename}"
                        await asyncio.to_thread(
                            storage.upload_file,
                            bucket_name=SATELLITE_BUCKET,
                            object_name=object_name,
                            data=io.BytesIO(st_img_bytes),
                            length=len(st_img_bytes),
                            content_type="image/png",
                        )
                        # Also upload latest cropped preview for dashboard
                        await asyncio.to_thread(
                            storage.upload_file,
                            bucket_name=SATELLITE_BUCKET,
                            object_name=f"{st.id}_latest.png",
                            data=io.BytesIO(st_img_bytes),
                            length=len(st_img_bytes),
                            content_type="image/png",
                        )

                        # Idempotent DB insert: check if (station_id, frame_timestamp) already exists
                        exist_stmt = select(SatelliteFrameMetadata).where(
                            SatelliteFrameMetadata.station_id == st.id,
                            SatelliteFrameMetadata.frame_timestamp == st_dt_frame,
                        )
                        existing_frame = (await db.execute(exist_stmt)).scalar_one_or_none()
                        if not existing_frame:
                            frame_record = SatelliteFrameMetadata(
                                station_id=st.id,
                                frame_timestamp=st_dt_frame,
                                image_url=f"/api/storage/download/{SATELLITE_BUCKET}/{object_name}",
                            )
                            await db.execute(insert_once(db, [frame_record]))
                        st_info["satellite_recorded"] = True
                    except Exception as se:
                        logger.warning(f"Failed to store satellite frame for station {st.id}: {se}")

                # B. Auto Catch-up (heal missing weather and satellite gaps)
                try:
                    catchup_res = await IngestionService.auto_catchup_weather(db, station_id=st.id)
                    st_info["catchup_records"] = catchup_res.get("records_inserted", 0)
                    if catchup_res.get("status") == "failed":
                        logger.warning(f"[{st.id}] Weather catch-up stored nothing: {catchup_res.get('message')}")
                    if catchup_res.get("records_skipped"):
                        logger.warning(f"[{st.id}] {catchup_res['records_skipped']} weather slots not stored: no complete Open-Meteo values for them.")
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
                    raw_weather = await asyncio.to_thread(IngestionService.fetch_open_meteo_live, st.latitude, st.longitude)
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
                        await db.execute(insert_once(db, [weather_rec]))
                    st_info["weather_recorded"] = True
                    st_info["ghi"] = canonical.ghi
                except Exception as we:
                    logger.warning(f"[{st.id}] Live weather fetch error: {we}")

                results["stations"][st.id] = st_info

            await db.commit()

            # D. Chain: run the real forecast model on the data that was just ingested
            round_started = datetime.fromtimestamp(start_time, tz=timezone.utc)
            results["inference"] = await _trigger_inference(ctx, db, active_stations, round_started)

            # E. ConvLSTM retrain: start one when a batch of new real daytime scans is complete
            results["convlstm_retrain"] = await _trigger_convlstm_retrain(ctx, active_stations)

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


async def _trigger_inference(ctx: dict, db, stations, round_started: datetime) -> dict[str, Any]:
    """Enqueue `run_inference` for each station. Stations with stale/insufficient data are skipped."""
    summary: dict[str, Any] = {"queued": [], "skipped": {}}
    pool = ctx.get("redis")
    if pool is None:
        logger.warning("No Redis connection in ARQ context; inference not triggered.")
        return summary

    # One forecast per station per 10-minute round, keyed by the time the round started (rounds take
    # 2-4 minutes, so the time of this call can already be in the next 10-minute slot). The satellite scan
    # time is not used: NICT's newest scan can stay the same for two rounds (it does every day around the
    # 02:40 UTC gap), and the weather input is newer by then.
    slot = round_started.replace(minute=(round_started.minute // 10) * 10, second=0, microsecond=0).strftime("%Y%m%d%H%M")
    for st in stations:
        job_id = f"infer-{st.id}-{slot}"  # deterministic: a round that is triggered twice runs once
        try:
            queued_id, reason = await InferenceService.enqueue_for_station(st, db, pool, job_id)
        except Exception as exc:
            logger.error(f"[{st.id}] Failed to enqueue inference: {exc}")
            summary["skipped"][st.id] = f"error: {exc}"
            continue
        if queued_id:
            summary["queued"].append(queued_id)
            logger.info(f"[{st.id}] Inference queued: {queued_id}")
        else:
            summary["skipped"][st.id] = reason
            logger.warning(f"[{st.id}] Inference skipped: {reason}")
    return summary


async def _trigger_convlstm_retrain(ctx: dict, stations) -> dict[str, Any]:
    """Enqueue the ConvLSTM retrain when enough new real daytime scans are in the frame cache.

    The batch counter is published every round (also while retraining is switched off), so the
    frame review page can show it.
    """
    pool = ctx.get("redis")
    if pool is None:
        return {"status": "no_redis"}
    try:
        from service.workers import convlstm_batch
        from service.workers.satellite_preprocessor import connect_minio

        client = connect_minio(read_timeout=60)
        if client is None:
            return {"status": "minio_unavailable"}
        coords = {st.id: (st.latitude, st.longitude) for st in stations}
        since = convlstm_batch.parse_time(await pool.get(convlstm_batch.LAST_FRAME_KEY))
        scans = await asyncio.to_thread(convlstm_batch.list_cached_scans, client)
        status = convlstm_batch.batch_status(scans, coords, since, settings.convlstm_retrain_threshold)
        published = {k: status[k] for k in ("new_scans", "batch_size", "newest_scan", "since")}
        published.update(retrain_enabled=settings.enable_retrain, checked_at=datetime.now(timezone.utc).isoformat())
        await pool.set(convlstm_batch.STATUS_KEY, json.dumps(published))
        if not settings.enable_retrain:
            return {"status": "retrain_disabled", "new_scans": status["new_scans"], "batch_size": status["batch_size"]}
        if not status["due"]:
            return {"status": "accumulating", "new_scans": status["new_scans"], "batch_size": status["batch_size"]}

        # one job per batch: the key is cleared by the trainer when the run ends
        if not await pool.set(convlstm_batch.SCHEDULED_KEY, "1", nx=True, ex=3 * 3600):
            return {"status": "already_scheduled", "new_scans": status["new_scans"]}
        payload = {"new_scans": status["new_scans"], "batch_size": status["batch_size"], "newest_scan": status["newest_scan"]}
        try:
            await pool.enqueue_job("train_convlstm_nowcaster", json.dumps(payload), _queue_name="train_queue")
        except Exception:
            await pool.delete(convlstm_batch.SCHEDULED_KEY)
            raise
        logger.info(f"ConvLSTM retrain queued: {payload}")
        return {"status": "queued", **payload}
    except Exception as exc:
        logger.warning(f"ConvLSTM retrain trigger failed: {exc}")
        return {"status": f"error: {exc}"}


async def collect_inference_results(ctx: dict) -> dict[str, int]:
    """ARQ Cron Task — every minute: save finished inference results into the predictions table."""
    pool = ctx.get("redis")
    if pool is None:
        return {"saved": 0, "pending": 0, "dropped": 0}
    async with SessionLocal() as db:
        stats = await InferenceService.collect_finished_jobs(pool, db)
    if stats["saved"] or stats["dropped"]:
        logger.info(f"Inference results collected: {stats}")
    return stats


async def startup(ctx: dict) -> None:
    await clear_round_lock(ctx.get("redis"))
    logger.info("Ingestion Worker started up successfully. Listening on 'ingest_queue'.")


async def shutdown(ctx: dict) -> None:
    logger.info("Ingestion Worker shutting down...")
