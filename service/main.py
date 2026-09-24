import os

from arq.connections import RedisSettings

from service.workers.simple_worker import simple_work
from service.workers.train_worker import train_model
from service.workers.inference_worker import run_inference


class WorkerSettings:
    """Settings สำหรับ Trainer Worker (ทำงานทั้ง train และ simple)"""
    queue_name = "train_queue"  # แยกคิว
    functions = [simple_work, train_model]
    redis_settings = RedisSettings(
        host=os.environ.get("REDIS_HOST", "localhost"),
        port=int(os.environ.get("REDIS_PORT", "6379")),
    )


class InferenceWorkerSettings:
    """Settings สำหรับ Inference Worker (แยก Container)"""
    queue_name = "inference_queue"  # แยกคิว
    functions = [run_inference]
    redis_settings = RedisSettings(
        host=os.environ.get("REDIS_HOST", "localhost"),
        port=int(os.environ.get("REDIS_PORT", "6379")),
    )
