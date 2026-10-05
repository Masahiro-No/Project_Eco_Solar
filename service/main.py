import os

from arq import cron
from arq.connections import RedisSettings

try:
    from service.workers.inference_worker import run_inference
except ImportError:
    run_inference = None

try:
    from service.workers.train_worker import check_satellite_calibration, train_convlstm_nowcaster, train_timeseries_lstm
except ImportError:
    check_satellite_calibration = None
    train_timeseries_lstm = None
    train_convlstm_nowcaster = None


def _redis_settings() -> RedisSettings:
    """Redis connection of the workers.

    A job keeps the worker's event loop busy for seconds at a time (model inference, satellite downloads).
    With arq's default 1-second connect timeout a new connection opened in that moment failed and took the
    whole worker down (seen on 5 Oct 2026). Be patient and retry instead.
    """
    return RedisSettings(
        host=os.environ.get("REDIS_HOST", os.environ.get("redis_host", "localhost")),
        port=int(os.environ.get("REDIS_PORT", os.environ.get("redis_port", 6379))),
        conn_timeout=20,
        conn_retries=10,
        conn_retry_delay=2,
        retry_on_timeout=True,
    )


class WorkerSettings:
    """Settings สำหรับ Trainer Worker (retrain LSTM และ ConvLSTM)"""
    queue_name = "train_queue"
    job_timeout = 3600  # retrain LSTM อาจนานเกิน default 300 วินาที
    max_tries = 1  # ไม่ retry อัตโนมัติ (retrain ซ้ำทำให้เปลืองและอาจชนล็อก)
    functions = [f for f in [train_timeseries_lstm, train_convlstm_nowcaster, check_satellite_calibration] if f is not None]
    redis_settings = _redis_settings()


class InferenceWorkerSettings:
    """Settings สำหรับ Solar Forecast Inference Worker (แยกคิว/Container)"""
    queue_name = "inference_queue"
    functions = [f for f in [run_inference] if f is not None]
    redis_settings = _redis_settings()


try:
    from service.workers.ingestion_worker import (
        ingest_single_station,
        collect_inference_results,
        scheduled_ingest_pipeline,
        shutdown as ingestion_shutdown,
        startup as ingestion_startup,
    )
except ImportError:
    collect_inference_results = None
    ingest_single_station = None
    scheduled_ingest_pipeline = None
    ingestion_shutdown = None
    ingestion_startup = None


if scheduled_ingest_pipeline is not None:
    class IngestionWorkerSettings:
        """Settings สำหรับ Ingestion Worker (ดึงภาพดาวเทียม & สภาพอากาศทุก 10 นาที)"""
        queue_name = "ingest_queue"
        functions = [scheduled_ingest_pipeline, ingest_single_station, collect_inference_results]
        cron_jobs = [
            # Himawari satellite imagery updates every 10 minutes (:08, :18, :28, :38, :48, :58);
            # the pipeline also enqueues the real-model inference for every station afterwards
            cron(scheduled_ingest_pipeline, minute={8, 18, 28, 38, 48, 58}),
            # Save finished inference results to the DB (every minute)
            cron(collect_inference_results, minute=set(range(60)), timeout=60),
        ]
        redis_settings = _redis_settings()
        on_startup = ingestion_startup
        on_shutdown = ingestion_shutdown