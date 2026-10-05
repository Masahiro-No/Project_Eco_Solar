"""Trainer worker jobs (queue: train_queue)

  train_timeseries_lstm      fine-tune LSTM จากค่า GHI ที่ผู้ใช้ label   -> service/training/retrain_timeseries.py
  train_convlstm_nowcaster   retrain ConvLSTM จากภาพดาวเทียมจริงเป็นรอบ  -> service/training/retrain_convlstm.py

ทั้งสองงานรันงานหนักใน thread แยก (ไม่ให้ event loop ของ worker ค้าง) เขียน log ลงไฟล์ต่อ job
และบันทึก span กับ metric ของรอบ (train_runs_total, train_duration_seconds)
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# ─── Config จาก Environment Variables ──────────────────────────────────────
LOG_DIR = Path(os.environ.get("LOG_DIR", "/app/logs"))

# ── OTel Setup ────────────────────────────────────────────────────────────────
_otel_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
_resource = Resource.create({"service.name": os.environ.get("OTEL_SERVICE_NAME", "trainer-worker")})

# Tracing
_provider = TracerProvider(resource=_resource)
_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=_otel_endpoint, insecure=True)))
trace.set_tracer_provider(_provider)
tracer = trace.get_tracer(__name__)

# Metrics
_metric_reader = PeriodicExportingMetricReader(
    OTLPMetricExporter(endpoint=_otel_endpoint, insecure=True),
    export_interval_millis=5000,
)
_meter_provider = MeterProvider(resource=_resource, metric_readers=[_metric_reader])
metrics.set_meter_provider(_meter_provider)
meter = metrics.get_meter(__name__)

train_runs_counter = meter.create_counter(
    "train_runs_total",
    description="Total number of training runs completed",
)
train_duration_histogram = meter.create_histogram(
    "train_duration_seconds",
    description="Duration of training execution in seconds",
    unit="s",
)
# ─────────────────────────────────────────────────────────────────────────────


# ─── Helpers ────────────────────────────────────────────────────────────────

def setup_logger(job_id: str) -> logging.Logger:
    """สร้าง Logger ที่เขียนลงทั้งไฟล์และ stdout."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"train_{job_id}.log"

    logger = logging.getLogger(f"trainer.{job_id}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()  # ป้องกัน duplicate handlers

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    # File handler — เก็บ Log ถาวร
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Stream handler — แสดงผลบน terminal
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    return logger


async def _run_retrain(ctx: dict, job_name: str, model: str, job_payload_json, load: Callable[[], Callable[[dict], dict]]) -> str:
    """Shared body of the two retrain jobs. `load` imports and returns the function that does the work."""
    job_id: str = ctx.get("job_id", datetime.now().strftime("%Y%m%d%H%M%S"))
    logger = setup_logger(job_id)
    logger.info(f">> [ARQ Job] {job_name} started  job_id={job_id}")

    try:
        execute = load()
    except ImportError as e:
        logger.warning(f"Could not import the training module of {job_name} ({e})")
        return '{"status": "skipped", "reason": "missing_dependencies"}'

    try:
        payload = json.loads(job_payload_json) if isinstance(job_payload_json, str) else job_payload_json
    except Exception:
        payload = {}

    started = time.time()
    with tracer.start_as_current_span(f"train.{model}", attributes={"job.id": job_id}) as span:
        result = await asyncio.to_thread(execute, payload)  # งานหนัก/บล็อก: ไม่ให้ค้าง event loop ของ worker
        result.pop("history", None)
        span.set_attribute("train.status", str(result.get("status")))

    try:
        train_runs_counter.add(1, {"model": model, "status": str(result.get("status", "unknown"))})
        train_duration_histogram.record(time.time() - started, {"model": model})
        _metric_reader.force_flush()
    except Exception as e:
        logger.warning(f"[Metrics] Failed to record training metrics: {e}")

    logger.info(f"[ARQ Job] {job_name} result: {result}")
    return json.dumps(result, default=str)


# ─── Jobs ───────────────────────────────────────────────────────────────────

async def train_timeseries_lstm(ctx: dict, job_payload_json: str = "{}") -> str:
    """ARQ Worker Job: Incremental fine-tuning for Time-Series LSTM (Safe Standby)."""
    def load():
        from service.training.retrain_timeseries import execute_timeseries_retrain
        return execute_timeseries_retrain

    return await _run_retrain(ctx, "train_timeseries_lstm", "lstm", job_payload_json, load)


async def train_convlstm_nowcaster(ctx: dict, job_payload_json: str = "{}") -> str:
    """ARQ Worker Job: batch retraining of the ConvLSTM cloud nowcaster on real satellite frames."""
    def load():
        from service.training.retrain_convlstm import execute_convlstm_retrain
        return execute_convlstm_retrain

    return await _run_retrain(ctx, "train_convlstm_nowcaster", "convlstm", job_payload_json, load)
