import os

from arq import cron
from arq.connections import RedisSettings

from service.workers.inference_worker import run_inference
from service.workers.simple_worker import simple_work
from service.workers.train_worker import train_model


class WorkerSettings:
    """Settings สำหรับ Trainer Worker (GPU Dedicated สำหรับเทรนโมเดลล้วนๆ)"""
    queue_name = "train_queue"
    functions = [simple_work, train_model]
    redis_settings = RedisSettings(
        host=os.environ.get("REDIS_HOST", "localhost"),
        port=int(os.environ.get("REDIS_PORT", "6379")),
    )


class InferenceWorkerSettings:
    """Settings สำหรับ Solar Forecast Inference Worker (แยกคิว/Container)"""
    queue_name = "inference_queue"
    functions = [run_inference]
    redis_settings = RedisSettings(
        host=os.environ.get("REDIS_HOST", "localhost"),
        port=int(os.environ.get("REDIS_PORT", "6379")),
    )


try:
    from service.workers.ingestion_worker import (
        ingest_single_station,
        scheduled_ingest_pipeline,
        shutdown as ingestion_shutdown,
        startup as ingestion_startup,
    )
except ImportError:
    ingest_single_station = None
    scheduled_ingest_pipeline = None
    ingestion_shutdown = None
    ingestion_startup = None


if scheduled_ingest_pipeline is not None:
    class IngestionWorkerSettings:
        """Settings สำหรับ Ingestion Worker (ดึงภาพดาวเทียม & สภาพอากาศทุก 10 นาที)"""
        queue_name = "ingest_queue"
        functions = [scheduled_ingest_pipeline, ingest_single_station]
        cron_jobs = [
            # Himawari satellite imagery updates every 10 minutes (:08, :18, :28, :38, :48, :58)
            cron(scheduled_ingest_pipeline, minute={8, 18, 28, 38, 48, 58})
        ]
        redis_settings = RedisSettings(
            host=os.environ.get("REDIS_HOST", os.environ.get("redis_host", "localhost")),
            port=int(os.environ.get("REDIS_PORT", os.environ.get("redis_port", 6379))),
        )
        on_startup = ingestion_startup
        on_shutdown = ingestion_shutdown
