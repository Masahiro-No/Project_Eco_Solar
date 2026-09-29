import os

from arq import cron
from arq.connections import RedisSettings

from service.workers.inference_worker import run_inference
from service.workers.ingestion_worker import scheduled_ingest_pipeline
from service.workers.simple_worker import simple_work
from service.workers.train_worker import train_model


class WorkerSettings:
    """Settings สำหรับ Trainer & Data Ingestion Worker"""
    queue_name = "train_queue"
    functions = [simple_work, train_model, scheduled_ingest_pipeline]
    cron_jobs = [
        # Himawari satellite imagery updates every 10 minutes (:08, :18, :28, :38, :48, :58)
        cron(scheduled_ingest_pipeline, minute={8, 18, 28, 38, 48, 58})
    ]
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
