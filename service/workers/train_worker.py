"""Trainer Worker — Token Classification (NER) บน conll2003

Flow:
  1. ตรวจสอบ MinIO ว่ามี Dataset อยู่ไหม
     - มี  → download จาก MinIO
     - ไม่มี → load_dataset("conll2003") จาก HuggingFace แล้ว cache ขึ้น MinIO
  2. Tokenize ด้วย bert-base-cased
  3. Train ด้วย HuggingFace Trainer API + log ทุก step
  4. Zip โมเดล → upload ขึ้น MinIO bucket "models" พร้อมเปิด Versioning
"""

import logging
import os
import time
from datetime import datetime
from pathlib import Path

from minio import Minio
from minio.error import S3Error
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# ─── Config จาก Environment Variables ──────────────────────────────────────
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "admin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "password")
DATASETS_BUCKET = "datasets"
MODELS_BUCKET = "models"
LOG_DIR = Path(os.environ.get("LOG_DIR", "/app/logs"))

DATASET_HUB_MAPPING: dict[str, str] = {
    "conll2003": "eriktks/conll2003",
}

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
train_checkpoints_counter = meter.create_counter(
    "train_checkpoints_saved_total",
    description="Total number of checkpoints synced to MinIO",
)
# ─────────────────────────────────────────────────────────────────────────────


# ─── Helpers ────────────────────────────────────────────────────────────────

def get_minio_client() -> Minio:
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False,
    )


def ensure_bucket(client: Minio, bucket_name: str) -> None:
    """สร้าง bucket ถ้ายังไม่มี."""
    if not client.bucket_exists(bucket_name):
        client.make_bucket(bucket_name)


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


def _get_or_download_dataset(client: Minio, dataset_name: str, logger: logging.Logger):
    """โหลด Dataset — ตรวจ MinIO ก่อน ถ้าไม่มีค่อย HuggingFace แล้ว cache ขึ้น MinIO."""
    from datasets import load_dataset as hf_load

    train_key = f"{dataset_name}/train.parquet"
    valid_key = f"{dataset_name}/validation.parquet"

    tmp_dir = Path(f"/tmp/{dataset_name}")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    train_path = tmp_dir / "train.parquet"
    valid_path = tmp_dir / "validation.parquet"

    try:
        # ── ตรวจสอบว่า cache อยู่ใน MinIO แล้วหรือยัง ──
        client.stat_object(DATASETS_BUCKET, train_key)
        logger.info(f"[Dataset] พบ cache ใน MinIO — กำลัง download...")

        client.fget_object(DATASETS_BUCKET, train_key, str(train_path))
        client.fget_object(DATASETS_BUCKET, valid_key, str(valid_path))

        dataset = hf_load(
            "parquet",
            data_files={"train": str(train_path), "validation": str(valid_path)},
        )
        logger.info("[Dataset] โหลดจาก MinIO cache สำเร็จ")

    except S3Error:
        # ── ยังไม่มี → โหลดจาก HuggingFace แล้ว cache ขึ้น MinIO ──
        logger.info(f"[Dataset] ไม่พบ cache — กำลัง download '{dataset_name}' จาก HuggingFace...")
        # ใช้ชื่อที่ map แล้ว (เช่น conll2003 → eriktks/conll2003)
        hub_name = DATASET_HUB_MAPPING.get(dataset_name, dataset_name)
        if hub_name != dataset_name:
            logger.info(f"[Dataset] Mapped '{dataset_name}' → '{hub_name}' (community version)")
        dataset = hf_load(hub_name, trust_remote_code=True)
        logger.info(f"[Dataset] Download สำเร็จ — กำลัง cache ขึ้น MinIO...")

        ensure_bucket(client, DATASETS_BUCKET)
        for split in ["train", "validation"]:
            parquet_path = tmp_dir / f"{split}.parquet"
            dataset[split].to_parquet(str(parquet_path))

            file_size = parquet_path.stat().st_size
            with open(parquet_path, "rb") as f:
                client.put_object(
                    DATASETS_BUCKET,
                    f"{dataset_name}/{split}.parquet",
                    f,
                    length=file_size,
                    content_type="application/octet-stream",
                )
            logger.info(f"[Dataset] Cached '{split}.parquet' → MinIO bucket '{DATASETS_BUCKET}'")

    return dataset


# ─── Main Worker Function ────────────────────────────────────────────────────

async def train_model(ctx: dict, dataset_name: str = "conll2003", model_name: str = "bert-base-cased") -> str:
    """ARQ Worker Function — เทรน Token Classification Model.

    Args:
        ctx: ARQ context (มี job_id)
        dataset_name: ชื่อ Dataset ใน HuggingFace / MinIO (default: conll2003)
        model_name: ชื่อโมเดลเริ่มต้นบน HuggingFace (default: bert-base-cased)

    Returns:
        ชื่อโฟลเดอร์โมเดลที่ upload ขึ้น MinIO สำเร็จ
    """
    job_id: str = ctx.get("job_id", datetime.now().strftime("%Y%m%d%H%M%S"))
    logger = setup_logger(job_id)
    start_time = time.time()

    with tracer.start_as_current_span(
        "train.run",
        attributes={
            "job.id": job_id,
            "train.dataset": dataset_name,
            "train.model": model_name,
        },
    ):
        logger.info("=" * 60)
        logger.info(f"[Job] Training Started   job_id={job_id}")
        logger.info(f"[Job] Dataset: {dataset_name}")
        logger.info(f"[Job] Base Model: {model_name}")
        logger.info("=" * 60)

        client = get_minio_client()

        # ── Step 1: Load Dataset ─────────────────────────────────────
        logger.info("[Step 1/4] Loading dataset...")
        with tracer.start_as_current_span("train.load_dataset"):
            raw_datasets = _get_or_download_dataset(client, dataset_name, logger)

    # ── Step 2: Tokenize ─────────────────────────────────────────
    logger.info("[Step 2/4] Tokenizing dataset...")
    from transformers import AutoTokenizer

    model_checkpoint = model_name
    tokenizer = AutoTokenizer.from_pretrained(model_checkpoint)

    label_names = raw_datasets["train"].features["ner_tags"].feature.names
    id2label = dict(enumerate(label_names))
    label2id = {v: k for k, v in id2label.items()}
    logger.info(f"[Step 2/4] Labels ({len(label_names)}): {label_names}")

    def tokenize_and_align_labels(examples):
        tokenized = tokenizer(
            examples["tokens"],
            truncation=True,
            is_split_into_words=True,
        )
        all_labels = []
        for i, label in enumerate(examples["ner_tags"]):
            word_ids = tokenized.word_ids(batch_index=i)
            prev = None
            label_ids = []
            for wid in word_ids:
                if wid is None:
                    label_ids.append(-100)
                elif wid != prev:
                    label_ids.append(label[wid])
                else:
                    label_ids.append(-100)
                prev = wid
            all_labels.append(label_ids)
        tokenized["labels"] = all_labels
        return tokenized

    tokenized = raw_datasets.map(tokenize_and_align_labels, batched=True)
    logger.info("[Step 2/4] Tokenization complete.")

    # ── Step 3: Train ────────────────────────────────────────────
    logger.info("[Step 3/4] Training model...")
    from transformers import (
        AutoModelForTokenClassification,
        DataCollatorForTokenClassification,
        Trainer,
        TrainerCallback,
        TrainingArguments,
    )
    import mlflow
    import mlflow.transformers

    # ── ตั้งค่า MLflow ───────────────────────────────────────────
    MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(dataset_name)  # จัดกลุ่ม Run ตาม Dataset

    model = AutoModelForTokenClassification.from_pretrained(
        model_checkpoint,
        id2label=id2label,
        label2id=label2id,
    )

    output_dir = f"/tmp/model_output_{job_id}"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_identifier = f"{model_name}_{dataset_name}"
    base_minio_path = f"{model_identifier}"

    # เปิด Versioning บน bucket models (เผื่อยังไม่เปิด)
    ensure_bucket(client, MODELS_BUCKET)
    from minio.versioningconfig import ENABLED, VersioningConfig
    client.set_bucket_versioning(MODELS_BUCKET, VersioningConfig(ENABLED))

    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=3,
        per_device_train_batch_size=16,
        per_device_eval_batch_size=16,
        logging_steps=50,
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=2,  # บนดิสก์เก็บแค่ 2 ตัว (Best & Latest)
        load_best_model_at_end=True,
    )

    class TrainLogCallback(TrainerCallback):
        def on_log(self, args, state, control, logs=None, **kwargs):
            if logs:
                logger.info(f"[Training] step={state.global_step} | {logs}")
                # บันทึก Metrics ลง MLflow ทุกครั้งที่มี log
                try:
                    filtered = {k: v for k, v in logs.items() if isinstance(v, (int, float))}
                    if filtered:
                        mlflow.log_metrics(filtered, step=state.global_step)
                except Exception:
                    pass

    class MinIOCheckpointCallback(TrainerCallback):
        """Callback สำหรับ Sync Checkpoint ขึ้น MinIO และลบของเก่าทิ้งให้เหลือ 2 ตัว"""
        def on_save(self, args, state, control, **kwargs):
            logger.info("[Checkpoint] Syncing checkpoints to MinIO...")
            local_ckpt_dirs = [d for d in Path(args.output_dir).glob("checkpoint-*") if d.is_dir()]
            local_ckpt_names = [d.name for d in local_ckpt_dirs]

            # 1. อัปโหลด Checkpoint ทั้งหมดที่มีในดิสก์ขึ้น MinIO
            ckpt_base_path = f"{base_minio_path}/checkpoints/{timestamp}"
            for ckpt_dir in local_ckpt_dirs:
                for fp in ckpt_dir.rglob("*"):
                    if fp.is_file():
                        minio_key = f"{ckpt_base_path}/{ckpt_dir.name}/{fp.relative_to(ckpt_dir)}"
                        file_size = fp.stat().st_size
                        with open(fp, "rb") as f:
                            client.put_object(MODELS_BUCKET, minio_key, f, length=file_size)

            # 2. ค้นหาและลบ Checkpoint เก่าใน MinIO ที่ถูกลบออกจากดิสก์ไปแล้ว
            from minio.deleteobjects import DeleteObject
            objects_to_delete = []
            objects = client.list_objects(MODELS_BUCKET, prefix=f"{ckpt_base_path}/", recursive=True)
            for obj in objects:
                parts = obj.object_name.split("/")
                ckpt_name = next((p for p in parts if p.startswith("checkpoint-")), None)
                if ckpt_name and ckpt_name not in local_ckpt_names:
                    objects_to_delete.append(DeleteObject(obj.object_name))

            if objects_to_delete:
                errors = client.remove_objects(MODELS_BUCKET, objects_to_delete)
                for error in errors:
                    logger.error(f"[Checkpoint] ลบไฟล์เก่าไม่สำเร็จ: {error}")

            logger.info(f"[Checkpoint] Sync สำเร็จ! ปัจจุบันเก็บ: {local_ckpt_names}")
            try:
                train_checkpoints_counter.add(len(local_ckpt_dirs), {"dataset_name": dataset_name, "model_name": model_name})
            except Exception:
                pass

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized["train"],
        eval_dataset=tokenized["validation"],
        data_collator=DataCollatorForTokenClassification(tokenizer=tokenizer),
        tokenizer=tokenizer,
        callbacks=[TrainLogCallback(), MinIOCheckpointCallback()],
    )

    # ── เริ่ม MLflow Run ─────────────────────────────────────────
    with mlflow.start_run(run_name=f"{model_identifier}_{job_id[:8]}") as run:
        mlflow_run_id = run.info.run_id
        logger.info(f"[MLflow] Run ID: {mlflow_run_id}")

        # บันทึก Hyperparameters
        mlflow.log_params({
            "model_name": model_name,
            "dataset_name": dataset_name,
            "num_train_epochs": training_args.num_train_epochs,
            "per_device_train_batch_size": training_args.per_device_train_batch_size,
            "job_id": job_id,
        })

        trainer.train()

        # ── Step 4: Upload Final Model ────────────────────────────
        logger.info("[Step 4/4] Uploading FINAL model to MinIO & MLflow...")
        final_output_dir = f"/tmp/final_model_{job_id}"
        trainer.save_model(final_output_dir)
        tokenizer.save_pretrained(final_output_dir)

        # 4a. อัปโหลดไปยัง MinIO (ทับที่เดิมเพื่อให้ Versioning ทำงาน)
        final_minio_path = f"{base_minio_path}/final"
        for fp in Path(final_output_dir).rglob("*"):
            if fp.is_file():
                minio_key = f"{final_minio_path}/{fp.relative_to(final_output_dir)}"
                file_size = fp.stat().st_size
                with open(fp, "rb") as f:
                    client.put_object(MODELS_BUCKET, minio_key, f, length=file_size)

        # 4b. Register โมเดลเข้า MLflow Model Registry
        pipeline_components = {
            "model": trainer.model,
            "tokenizer": tokenizer,
        }
        registered_model_name = model_identifier  # เช่น "bert-base-cased_conll2003"
        mlflow.transformers.log_model(
            transformers_model=pipeline_components,
            artifact_path="model",
            task="token-classification",
            registered_model_name=registered_model_name,
        )
        logger.info(f"[MLflow] Model registered as '{registered_model_name}'")

        # 4c. บันทึกไฟล์ Log เข้า MLflow ด้วย
        log_file = LOG_DIR / f"train_{job_id}.log"
        if log_file.exists():
            mlflow.log_artifact(str(log_file), artifact_path="logs")

    logger.info(f"[Step 4/4] Final Model uploaded → MinIO bucket '{MODELS_BUCKET}/{final_minio_path}'")
    logger.info("=" * 60)
    logger.info(f"[Job] Training Completed  job_id={job_id}")
    logger.info(f"[Job] Model Path (MinIO): {final_minio_path}")
    logger.info(f"[Job] MLflow Run ID: {mlflow_run_id}")
    logger.info(f"[Job] MLflow Model: {registered_model_name}")
    logger.info("=" * 60)

    # ── Record Metrics to Prometheus ─────────────────────────
    try:
        duration = time.time() - start_time
        train_runs_counter.add(1, {"dataset_name": dataset_name, "model_name": model_name, "status": "success"})
        train_duration_histogram.record(duration, {"dataset_name": dataset_name, "model_name": model_name})
        _metric_reader.force_flush()
    except Exception as e:
        logger.warning(f"[Metrics] Failed to record training metrics: {e}")

    return {
        "minio_path": final_minio_path,
        "mlflow_run_id": mlflow_run_id,
        "registered_model_name": registered_model_name,
    }


async def train_timeseries_lstm(ctx: dict, job_payload_json: str = "{}") -> str:
    """ARQ Worker Job: Incremental fine-tuning for Time-Series LSTM (Safe Standby)."""
    job_id: str = ctx.get("job_id", datetime.now().strftime("%Y%m%d%H%M%S"))
    logger = setup_logger(job_id)
    logger.info(f">> [ARQ Job] train_timeseries_lstm started  job_id={job_id}")

    try:
        from service.training.retrain_timeseries import execute_timeseries_retrain
    except ImportError as e:
        logger.warning(f"Could not import retrain_timeseries ({e})")
        return '{"status": "skipped", "reason": "missing_dependencies"}'

    try:
        import json
        payload = json.loads(job_payload_json) if isinstance(job_payload_json, str) else job_payload_json
    except Exception:
        payload = {}

    result = execute_timeseries_retrain(payload)
    logger.info(f"[ARQ Job] train_timeseries_lstm result: {result}")
    import json
    return json.dumps(result)


async def train_convlstm_nowcaster(ctx: dict, job_payload_json: str = "{}") -> str:
    """ARQ Worker Job: Batch retraining for Spatio-temporal Seq2Seq ConvLSTM (Safe Standby)."""
    job_id: str = ctx.get("job_id", datetime.now().strftime("%Y%m%d%H%M%S"))
    logger = setup_logger(job_id)
    logger.info(f">> [ARQ Job] train_convlstm_nowcaster started  job_id={job_id}")

    try:
        from service.training.retrain_convlstm import execute_convlstm_retrain
    except ImportError as e:
        logger.warning(f"Could not import retrain_convlstm ({e})")
        return '{"status": "skipped", "reason": "missing_dependencies"}'

    try:
        import json
        payload = json.loads(job_payload_json) if isinstance(job_payload_json, str) else job_payload_json
    except Exception:
        payload = {}

    result = execute_convlstm_retrain(payload)
    logger.info(f"[ARQ Job] train_convlstm_nowcaster result: {result}")
    import json
    return json.dumps(result)

