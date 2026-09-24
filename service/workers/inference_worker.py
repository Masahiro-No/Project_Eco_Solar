"""Inference Worker — Token Classification NER Inference

Flow:
  1. โหลดโมเดลจาก MLflow Model Registry (Cache ไว้ใน ARQ ctx)
  2. รับ text input จาก Redis Queue
  3. รัน NER Inference
  4. คืนผลลัพธ์ entities กลับผ่าน ARQ Job Result
"""

import logging
import os
from datetime import datetime
from pathlib import Path

import time

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")
LOG_DIR = Path(os.environ.get("LOG_DIR", "/app/logs"))

# ── OTel Setup ────────────────────────────────────────────────────────────────
_otel_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
_resource = Resource.create({"service.name": os.environ.get("OTEL_SERVICE_NAME", "inference-worker")})

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

inference_requests_counter = meter.create_counter(
    "inference_requests_total",
    description="Total number of inference requests processed",
)
inference_entities_counter = meter.create_counter(
    "inference_entities_total",
    description="Total number of entities detected",
)
inference_duration_histogram = meter.create_histogram(
    "inference_duration_seconds",
    description="Duration of inference execution in seconds",
    unit="s",
)
# ─────────────────────────────────────────────────────────────────────────────


def setup_logger(job_id: str) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"inference_{job_id}.log"
    logger = logging.getLogger(f"inference.{job_id}")
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


def _load_model_from_mlflow(model_name: str, version: str, logger: logging.Logger):
    """โหลดโมเดลจาก MLflow Model Registry

    Args:
        model_name: ชื่อ Registered Model เช่น "bert-base-cased_conll2003"
        version: "latest" หรือ version number เช่น "1", "2"
    """
    import mlflow
    import mlflow.transformers

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)

    if version == "latest":
        model_uri = f"models:/{model_name}/latest"
    else:
        model_uri = f"models:/{model_name}/{version}"

    logger.info(f"[Model] Loading from MLflow: {model_uri}")
    pipeline = mlflow.transformers.load_model(model_uri)
    logger.info(f"[Model] Loaded successfully!")
    return pipeline


async def run_inference(
    ctx: dict,
    text: str,
    model_name: str = "bert-base-cased_conll2003",
    version: str = "latest",
) -> dict:
    """ARQ Worker Function — รัน NER Inference ด้วยโมเดลจาก MLflow

    Args:
        ctx: ARQ context (มี job_id และ model_cache)
        text: ข้อความที่ต้องการวิเคราะห์
        model_name: ชื่อ Registered Model ใน MLflow
        version: version ของโมเดล ("latest" หรือ "1", "2", ...)

    Returns:
        dict ที่มี entities ที่พบและ text ต้นฉบับ
    """
    job_id: str = ctx.get("job_id", datetime.now().strftime("%Y%m%d%H%M%S"))
    logger = setup_logger(job_id)
    start_time = time.time()

    with tracer.start_as_current_span(
        "inference.run",
        attributes={
            "job.id": job_id,
            "model.name": model_name,
            "model.version": version,
        },
    ) as span:
        logger.info("=" * 60)
        logger.info(f"[Job] Inference Started  job_id={job_id}")
        logger.info(f"[Job] Model: {model_name} (version={version})")
        logger.info(f"[Job] Input text: {text[:100]}")
        logger.info("=" * 60)

        # ── Cache โมเดลไว้ใน ARQ ctx ──────────────────────────────
        if "model_cache" not in ctx:
            ctx["model_cache"] = {}

        cache_key = f"{model_name}@{version}"

        if cache_key not in ctx["model_cache"]:
            logger.info(f"[Cache] Miss — กำลังโหลดโมเดล '{cache_key}' จาก MLflow...")
            with tracer.start_as_current_span("inference.model_load"):
                pipeline = _load_model_from_mlflow(model_name, version, logger)
            ctx["model_cache"][cache_key] = pipeline
            logger.info(f"[Cache] โมเดลถูก Cache แล้ว key='{cache_key}'")
            span.set_attribute("model.cache_hit", False)
        else:
            logger.info(f"[Cache] Hit — ใช้โมเดลที่ Cache ไว้แล้ว key='{cache_key}'")
            pipeline = ctx["model_cache"][cache_key]
            span.set_attribute("model.cache_hit", True)

        # ── รัน Inference ──────────────────────────────────────────
        logger.info("[Inference] Running prediction...")
        with tracer.start_as_current_span("inference.predict"):
            raw_results = pipeline(text)

        # ── แปลงผลลัพธ์ รวม Sub-tokens ───────────────────────────
        entities = []
        current_entity = None

        for token_result in raw_results:
            label = token_result["entity"]
            word = token_result["word"]
            score = round(float(token_result["score"]), 4)

            if label == "O":
                if current_entity:
                    entities.append(current_entity)
                    current_entity = None
                continue

            bio_prefix = label[:2]
            entity_type = label[2:]

            if bio_prefix == "B-":
                if current_entity:
                    entities.append(current_entity)
                current_entity = {
                    "entity_type": entity_type,
                    "word": word,
                    "score": score,
                    "start": token_result.get("start"),
                    "end": token_result.get("end"),
                }
            elif bio_prefix == "I-" and current_entity and current_entity["entity_type"] == entity_type:
                if word.startswith("##"):
                    current_entity["word"] += word[2:]
                else:
                    current_entity["word"] += f" {word}"
                current_entity["end"] = token_result.get("end")
                current_entity["score"] = round((current_entity["score"] + score) / 2, 4)

        if current_entity:
            entities.append(current_entity)

        result = {
            "text": text,
            "model_name": model_name,
            "version": version,
            "entities": entities,
            "entity_count": len(entities),
        }

        span.set_attribute("inference.entity_count", len(entities))
        logger.info(f"[Inference] Complete! Found {len(entities)} entities: {[e['word'] for e in entities]}")
        logger.info("=" * 60)

        # ── Record Metrics to Prometheus ─────────────────────────
        try:
            duration = time.time() - start_time
            inference_requests_counter.add(1, {"model_name": model_name, "version": version})
            inference_entities_counter.add(len(entities), {"model_name": model_name})
            inference_duration_histogram.record(duration, {"model_name": model_name})
            _metric_reader.force_flush()
        except Exception as e:
            logger.warning(f"[Metrics] Failed to record metrics: {e}")

    return result
