"""Ingestion Worker — Automated Satellite & Real-time Weather Fetcher

Scheduled via ARQ Cron (every 10 minutes, matching Himawari satellite scan interval).

Flow:
  1. Fetch real-time weather & solar irradiance (GHI, DNI, Temp, Humidity, Wind) from Open-Meteo.
  2. Fetch latest full-disk Himawari satellite imagery from NICT Japan.
  3. Upload satellite image to MinIO bucket 'satellite-cache'.
  4. Record OpenTelemetry traces & Prometheus metrics.
"""

import io
import json
import logging
import os
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from minio import Minio
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# ── Environment & Config ──────────────────────────────────────────────────────
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "admin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "password")
SATELLITE_BUCKET = "satellite-cache"
LOG_DIR = Path(os.environ.get("LOG_DIR", "/app/logs"))

NICT_LATEST_JSON = "https://himawari8-dl.nict.go.jp/himawari8/img/D531106/latest.json"
NICT_BASE_IMG_URL = "https://himawari8-dl.nict.go.jp/himawari8/img/D531106"

# ── OTel Setup ────────────────────────────────────────────────────────────────
_otel_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
_resource = Resource.create({"service.name": os.environ.get("OTEL_SERVICE_NAME", "ingestion-worker")})

_provider = TracerProvider(resource=_resource)
_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=_otel_endpoint, insecure=True)))
trace.set_tracer_provider(_provider)
tracer = trace.get_tracer(__name__)

_metric_reader = PeriodicExportingMetricReader(
    OTLPMetricExporter(endpoint=_otel_endpoint, insecure=True),
    export_interval_millis=5000,
)
_meter_provider = MeterProvider(resource=_resource, metric_readers=[_metric_reader])
metrics.set_meter_provider(_meter_provider)
meter = metrics.get_meter(__name__)

ingestion_runs_counter = meter.create_counter(
    "ingestion_runs_total",
    description="Total number of scheduled ingestion runs completed",
)
ingestion_duration_histogram = meter.create_histogram(
    "ingestion_duration_seconds",
    description="Duration of weather and satellite ingestion pipeline in seconds",
    unit="s",
)


def setup_logger(job_id: str) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"ingest_{job_id}.log"
    logger = logging.getLogger(f"ingest.{job_id}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger


def _get_minio_client() -> Minio:
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False,
    )


def fetch_open_meteo(lat: float, lon: float) -> dict[str, Any]:
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}&timezone=Asia%2FBangkok"
        f"&current=temperature_2m,relative_humidity_2m,surface_pressure,wind_speed_10m,cloud_cover,direct_normal_irradiance,shortwave_radiation"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "SolarForecastDSS/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def fetch_nict_himawari_image() -> tuple[Optional[bytes], datetime, str]:
    req = urllib.request.Request(NICT_LATEST_JSON, headers={"User-Agent": "SolarForecastDSS/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        latest_info = json.loads(resp.read().decode())

    date_str = latest_info.get("date")  # e.g. "2026-09-29 07:50:00"
    dt_utc = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)

    yyyy = dt_utc.strftime("%Y")
    mm = dt_utc.strftime("%m")
    dd = dt_utc.strftime("%d")
    hhmmss = dt_utc.strftime("%H%M%S")

    img_url = f"{NICT_BASE_IMG_URL}/1d/550/{yyyy}/{mm}/{dd}/{hhmmss}_0_0.png"
    img_req = urllib.request.Request(img_url, headers={"User-Agent": "SolarForecastDSS/1.0"})
    with urllib.request.urlopen(img_req, timeout=20) as img_resp:
        content = img_resp.read()

    filename = f"nict_{yyyy}{mm}{dd}_{hhmmss}.png"
    return content, dt_utc, filename


async def scheduled_ingest_pipeline(
    ctx: dict,
    station_id: str = "ST-001",
    lat: float = 7.0086,
    lon: float = 100.4988,
) -> dict[str, Any]:
    """ARQ Cron Task — Ingest Open-Meteo & NICT Himawari imagery every 10 mins."""
    job_id = ctx.get("job_id", f"cron-ingest-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}")
    logger = setup_logger(job_id)
    start_time = time.time()

    with tracer.start_as_current_span(
        "ingestion.pipeline",
        attributes={"station.id": station_id, "job.id": job_id},
    ) as span:
        logger.info(f"[Ingest Worker] Starting data pipeline for station: {station_id}")

        # 1. Fetch live Open-Meteo weather
        weather_data = {}
        try:
            weather_data = fetch_open_meteo(lat, lon)
            current = weather_data.get("current", {})
            logger.info(
                f"[Weather Ingested] Temp: {current.get('temperature_2m')} C, "
                f"GHI: {current.get('shortwave_radiation')} W/m2, "
                f"Cloud: {current.get('cloud_cover')}%"
            )
            span.set_attribute("weather.ghi", float(current.get("shortwave_radiation") or 0.0))
        except Exception as e:
            logger.warning(f"[Weather Warning] Failed to fetch Open-Meteo: {e}")

        # 2. Fetch NICT Himawari satellite image & upload to MinIO
        image_meta = {}
        try:
            img_bytes, dt_frame, filename = fetch_nict_himawari_image()
            if img_bytes:
                minio_client = _get_minio_client()
                if not minio_client.bucket_exists(SATELLITE_BUCKET):
                    minio_client.make_bucket(SATELLITE_BUCKET)

                object_name = f"{station_id}/{filename}"
                minio_client.put_object(
                    bucket_name=SATELLITE_BUCKET,
                    object_name=object_name,
                    data=io.BytesIO(img_bytes),
                    length=len(img_bytes),
                    content_type="image/png",
                )
                image_meta = {
                    "object_name": object_name,
                    "frame_time": dt_frame.isoformat(),
                    "size_bytes": len(img_bytes),
                }
                logger.info(f"[Satellite Stored] Saved to MinIO: {SATELLITE_BUCKET}/{object_name}")
                span.set_attribute("satellite.frame_stored", object_name)
        except Exception as e:
            logger.warning(f"[Satellite Warning] Failed to fetch NICT image: {e}")

        duration = time.time() - start_time
        try:
            ingestion_runs_counter.add(1, {"station_id": station_id})
            ingestion_duration_histogram.record(duration, {"station_id": station_id})
            _metric_reader.force_flush()
        except Exception as e:
            logger.warning(f"[Metrics Warning] Failed to flush metrics: {e}")

        logger.info(f"[Ingest Complete] Pipeline finished in {duration:.2f}s")
        return {
            "job_id": job_id,
            "station_id": station_id,
            "weather": weather_data.get("current", {}),
            "satellite": image_meta,
            "duration_seconds": duration,
        }
