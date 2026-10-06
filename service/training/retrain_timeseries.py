"""Solar Time-Series LSTM retraining (เรียนจากค่าที่วัดจริง ในเงื่อนไขเดียวกับตอนใช้งาน, ตรวจสอบก่อน deploy).

ลำดับงาน:
  1. ตรวจ ENABLE_RETRAIN + ล็อกกันรันซ้อน (Redis) + ล้างคิว debounce
  2. ดึงโมเดลที่ใช้งานอยู่ (ONNX + scalers + meta) จาก MinIO (สำรอง: model/time-series/) — ONNX คือแหล่งความจริงเดียว ไม่ต้องมี .pth
  3. อ่าน weather_history จาก PostgreSQL + label ทั้งหมดจาก Label Studio -> window ที่ข้อมูลป้อนมาจากสภาพอากาศอย่างเดียว
     (แบบที่โมเดลได้รับตอนพยากรณ์จริง) และเป้าหมายคือ GHI ที่วัดจริงของช่วงพยากรณ์
  4. นับวันที่มีค่าวัดจริงที่รอบก่อนยังไม่เคยใช้: ยังไม่ครบ RETRAIN_MIN_NEW_DAYS -> บันทึกจำนวนไว้ให้หน้าเว็บแล้วจบรอบ
  5. cross-validation ตามวัน บนวันที่โมเดลที่ใช้งานอยู่ยังไม่เคยเทรน (model_meta.json: retrain.trained_days):
     กันวันเหล่านั้นไว้ตรวจทีละกลุ่มจนครบ แต่ละกลุ่มเริ่มจากโมเดลที่ใช้งานอยู่ แล้ว fine-tune จากวันที่เหลือทั้งหมด
     รวมวันที่เคยเทรนแล้ว (loss เฉพาะช่องที่มีค่าวัดจริง) ได้ MAE รวมทุกวันที่ตรวจของแต่ละ epoch
     วันที่โมเดลเคยเทรนแล้วไม่ใช้ตรวจ: โมเดลเดิมจะดูดีกว่าความจริงบนวันที่เคยเห็นคำตอบ
  6. deploy เมื่อ MAE รวมที่ epoch ที่ดีที่สุดลดลงอย่างน้อย RETRAIN_MIN_IMPROVEMENT -> เทรนจากทุกวันด้วยจำนวน epoch นั้น,
     export ONNX, ตรวจเทียบ onnxruntime, สำรองของเดิม (เก็บ 3 เวอร์ชัน), เขียนไฟล์ local, อัปโหลด MinIO (meta ขึ้นทีหลังสุด)
     และจดวันที่โมเดลใหม่เทรนไปแล้วลง retrain.trained_days

หมายเหตุ: ทุกครั้งที่รัน label "ทั้งหมด" ในช่วงข้อมูลจะถูกนำมาใช้ (ไม่ใช่เฉพาะ label ใหม่) และเริ่มจากโมเดลที่ใช้งานอยู่เสมอ.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np

from service.training.dataset import ALIGNED_FEATURE_COLS, FORECAST_STEPS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RetrainTimeSeries")

MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "model" / "time-series"
MINIO_BUCKET = "models"
MINIO_PREFIX = "solar_lstm"
MODEL_FILES = ["solar_ghi_lstm.onnx", "feature_scaler.joblib", "target_scaler.joblib", "model_meta.json"]
LOCK_KEY = "retrain:timeseries:lock"
SCHEDULED_KEY = "retrain:timeseries:scheduled"  # backend ตั้งไว้ตอน debounce; trainer ลบตอนเริ่มรัน
STATUS_KEY = "retrain:timeseries:status"        # JSON: จำนวนวันใหม่ที่นับได้ครั้งล่าสุด (หน้าสถานะ retrain อ่าน)
USED_DAYS_KEY = "retrain:timeseries:used_days"  # JSON list ของ 'สถานี|YYYY-MM-DD' ที่รอบ retrain ล่าสุดใช้ไปแล้ว
LS_PROJECT_TITLE = "Solar GHI Ground Truth Verification"
LOCK_TTL_SECONDS = 3600
KEEP_BACKUPS = 3


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).lower() == "true"


def _env_float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _sync_db_url() -> str:
    url = os.environ.get("RETRAIN_DATABASE_URL") or os.environ.get("DATABASE_URL") or os.environ.get("database_url", "")
    if not url:
        raise RuntimeError("DATABASE_URL (หรือ RETRAIN_DATABASE_URL) ไม่ได้ตั้งค่าใน trainer-worker")
    return url.replace("+asyncpg", "+psycopg2")


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")  # รูปแบบเดียวกับ model_meta.json เดิม


def _minio_client():
    from minio import Minio

    return Minio(
        os.environ.get("MINIO_ENDPOINT", "localhost:9000"),
        access_key=os.environ.get("MINIO_ACCESS_KEY", "admin"),
        secret_key=os.environ.get("MINIO_SECRET_KEY", "password"),
        secure=False,
    )


# ----------------------------------------------------------------------------- deployed model I/O
def fetch_deployed_model(workdir: Path) -> tuple[Path, str]:
    """ดึงไฟล์โมเดลที่ใช้งานอยู่มาไว้ใน workdir. คืน (โฟลเดอร์, แหล่งที่มา 'minio'|'local')."""
    workdir.mkdir(parents=True, exist_ok=True)
    try:
        client = _minio_client()
        for name in MODEL_FILES:
            client.fget_object(MINIO_BUCKET, f"{MINIO_PREFIX}/{name}", str(workdir / name))
        return workdir, "minio"
    except Exception as e:  # noqa: BLE001
        logger.warning(f"โหลดโมเดลจาก MinIO ไม่ได้ ({e}) — ใช้ไฟล์ใน {MODELS_DIR}")
    for name in MODEL_FILES:
        shutil.copy2(MODELS_DIR / name, workdir / name)
    return workdir, "local"


def backup_local_model(trained_at: str) -> Optional[Path]:
    """สำรองไฟล์โมเดล local เดิมไว้ model/time-series/backups/<trained_at>/ และเก็บแค่ KEEP_BACKUPS เวอร์ชันล่าสุด."""
    if not (MODELS_DIR / "solar_ghi_lstm.onnx").exists():
        return None
    slug = re.sub(r"[^0-9A-Za-z]+", "_", trained_at).strip("_") or "unknown"
    dest = MODELS_DIR / "backups" / slug
    dest.mkdir(parents=True, exist_ok=True)
    for name in MODEL_FILES:
        if (MODELS_DIR / name).exists():
            shutil.copy2(MODELS_DIR / name, dest / name)
    backups = sorted(p for p in (MODELS_DIR / "backups").iterdir() if p.is_dir())
    for old in backups[:-KEEP_BACKUPS]:
        shutil.rmtree(old, ignore_errors=True)
    return dest


def _bump_patch(version: str) -> str:
    parts = (version or "1.0.0").split(".")
    try:
        parts[-1] = str(int(parts[-1]) + 1)
    except ValueError:
        parts.append("1")
    return ".".join(parts)


# ----------------------------------------------------------------------------- labels (Label Studio)
def _ls_headers(base: str, key: str) -> dict[str, str]:
    """legacy token -> 'Token', JWT (refresh token ของ Label Studio 1.2x+) -> แลกเป็น access token ก่อน."""
    import requests

    if key.count(".") == 2 and key.startswith("eyJ"):
        r = requests.post(f"{base}/api/token/refresh", json={"refresh": key}, timeout=30)
        if r.status_code != 200:
            raise RuntimeError(
                f"Label Studio ปฏิเสธ API key (HTTP {r.status_code}). key ที่ใส่เป็น refresh token ที่อาจหมดอายุ — "
                "สร้าง Legacy/Personal Access Token ใหม่จากหน้า Account & Settings แล้วตั้ง LABEL_STUDIO_API_KEY"
            )
        return {"Authorization": f"Bearer {r.json()['access']}"}
    return {"Authorization": f"Token {key}"}


def _annotation_ghi(task: dict) -> Optional[float]:
    """ค่า GHI จาก annotation ล่าสุดของ task (แก้ใน Label Studio แล้วต้องถือตามนั้น); สำรอง = data.ghi_actual."""
    for ann in reversed(task.get("annotations") or []):
        if ann.get("was_cancelled"):
            continue
        for item in ann.get("result") or []:
            if item.get("from_name") == "ghi":
                v = (item.get("value") or {}).get("number")
                if v is not None:
                    return float(v)
    v = (task.get("data") or {}).get("ghi_actual")
    return float(v) if v is not None else None


def parse_label_tasks(tasks: list[dict], since):
    """แปลง tasks (export JSON ของ Label Studio) -> DataFrame[station_id, timestamp(UTC), ghi_actual]."""
    import pandas as pd

    rows = []
    for t in tasks:
        d = t.get("data") or {}
        ghi = _annotation_ghi(t)
        if ghi is None or not d.get("station_id") or not d.get("timestamp"):
            continue
        ts = pd.to_datetime(d["timestamp"], utc=True)
        if ts < since:
            continue
        rows.append({"station_id": d["station_id"], "timestamp": ts, "ghi_actual": ghi})
    df = pd.DataFrame(rows, columns=["station_id", "timestamp", "ghi_actual"])
    if not df.empty:
        df["timestamp"] = df["timestamp"].dt.floor("10min")
        df = df.drop_duplicates(["station_id", "timestamp"], keep="last")
    return df


def fetch_labels_from_label_studio(lookback_days: int):
    """ดึง label ทั้งหมดของ project GHI จาก Label Studio (REST) ในช่วง lookback_days."""
    import pandas as pd
    import requests

    base = os.environ.get("LABEL_STUDIO_URL", "http://label-studio:8080").rstrip("/")
    key = os.environ.get("LABEL_STUDIO_API_KEY") or os.environ.get("label_studio_api_key", "")
    if not key:
        raise RuntimeError("LABEL_STUDIO_API_KEY ไม่ได้ตั้งค่าใน trainer-worker")
    headers = _ls_headers(base, key)

    r = requests.get(f"{base}/api/projects", params={"title": LS_PROJECT_TITLE}, headers=headers, timeout=30)
    r.raise_for_status()
    body = r.json()
    projects = body.get("results", []) if isinstance(body, dict) else body
    project = next((p for p in projects if p.get("title") == LS_PROJECT_TITLE), None)
    if project is None:
        return pd.DataFrame(columns=["station_id", "timestamp", "ghi_actual"])

    r = requests.get(
        f"{base}/api/projects/{project['id']}/export",
        params={"exportType": "JSON", "download_all_tasks": "false"},
        headers=headers,
        timeout=300,
    )
    r.raise_for_status()
    since = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=lookback_days)
    return parse_label_tasks(r.json(), since)


# ----------------------------------------------------------------------------- data
def load_training_frames(engine, lookback_days: int, labels_df):
    """อ่าน weather_history จาก Postgres และ label จาก Label Studio -> {station_id: {"inputs", "measured"}}

    inputs    ตารางฟีเจอร์จากสภาพอากาศอย่างเดียว แบบเดียวกับที่โมเดลได้รับตอนพยากรณ์จริง
    measured  Series ของ GHI ที่วัดจริงบนช่องเวลาเดียวกัน (NaN = ไม่มีค่าวัด) หรือ None เมื่อสถานีไม่มี label
    ค่าที่วัดจริงไม่ถูกเขียนลงในข้อมูลป้อน: ตอนใช้งานจริงค่านั้นยังมาไม่ถึง
    """
    import pandas as pd
    from sqlalchemy import text

    from service.training.features import build_station_frame

    since = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=lookback_days)
    weather = pd.read_sql(
        text(
            "SELECT station_id, timestamp, ghi, dni, dhi, clearsky_ghi, solar_zenith_angle, temperature, "
            "relative_humidity, surface_pressure, wind_speed FROM weather_history "
            "WHERE timestamp >= :since ORDER BY station_id, timestamp"
        ),
        engine,
        params={"since": since.to_pydatetime()},
    )
    frames = {}
    for station_id, wdf in weather.groupby("station_id"):
        wdf = wdf.drop(columns=["station_id"])
        lab_df = labels_df[labels_df["station_id"] == station_id]
        measured = None
        if len(lab_df):
            lab_series = pd.Series(lab_df["ghi_actual"].values, index=pd.to_datetime(lab_df["timestamp"], utc=True))
            with_labels = build_station_frame(wdf, labels=lab_series)   # ใช้กติกาคัด label ของ build_station_frame
            measured = with_labels["GHI"].where(with_labels["is_label"])
        frames[station_id] = {"inputs": build_station_frame(wdf), "measured": measured}
    return frames


def days_with_new_values(current: set[str], used: set[str]) -> list[str]:
    """วันที่มีค่าวัดจริงซึ่งรอบ retrain ก่อนหน้ายังไม่เคยใช้ (สมาชิก = 'สถานี|YYYY-MM-DD')

    หลายสถานีในวันเดียวกันนับเป็นวันเดียว; ค่าของสถานีใหม่ในวันที่เคยใช้แล้วก็นับวันนั้นเป็นวันใหม่
    """
    return sorted({key.split("|", 1)[1] for key in current - used})


def accepts(mae_before: float, mae_after: float, min_improvement: float) -> bool:
    """รับโมเดลใหม่เมื่อ MAE เทียบค่าที่วัดจริงของวันที่กันไว้ตรวจลดลงอย่างน้อย min_improvement (สัดส่วนของค่าเดิม)

    ผลต่างที่เล็กกว่านั้นอยู่ในระดับความแกว่งของการเทรนแต่ละครั้ง ไม่นับว่าดีขึ้น
    """
    return mae_after <= mae_before * (1.0 - min_improvement)


# ----------------------------------------------------------------------------- model math
def evaluate_mae(
    model, X_scaled: np.ndarray, Y_raw: np.ndarray, target_scaler, device, batch_size: int = 256, mask: Optional[np.ndarray] = None
) -> float:
    """MAE (W/m²) บนข้อมูลที่ scale แล้ว; แปลงผลกลับเป็น W/m² ด้วย target_scaler และ clamp >= 0 เหมือนตอน inference.

    mask (n, horizon) bool: วัดเฉพาะช่องที่เป็น True (ใช้กับช่องที่มีค่า GHI วัดจริง)
    """
    import torch

    model.eval()
    preds = []
    with torch.no_grad():
        for i in range(0, len(X_scaled), batch_size):
            xb = torch.from_numpy(X_scaled[i:i + batch_size]).to(device)
            preds.append(model(xb).cpu().numpy())
    p = np.concatenate(preds)
    p_raw = np.clip(target_scaler.inverse_transform(p.reshape(-1, 1)).reshape(p.shape), 0.0, None)
    err = np.abs(p_raw - Y_raw)
    return float(err[mask].mean()) if mask is not None else float(err.mean())


def fine_tune(
    model,
    X_tr: np.ndarray,
    Y_tr_scaled: np.ndarray,
    X_va: Optional[np.ndarray],
    Y_va_raw: Optional[np.ndarray],
    target_scaler,
    device,
    epochs: int,
    lr: float,
    batch_size: int = 64,
    patience: int = 3,
    seed: int = 42,
    val_mask: Optional[np.ndarray] = None,
    train_mask: Optional[np.ndarray] = None,
) -> dict[str, Any]:
    """fine-tune แบบ warm-start; เก็บสถานะที่ val MAE ต่ำสุด (epoch 0 = โมเดลเดิม). คืนสรุปผล และโหลด best state ใส่ model.

    train_mask (n, horizon) bool: คิด loss เฉพาะช่องที่เป็น True (ช่องที่มีค่าวัดจริง); None = ทุกช่อง
    X_va = None: ไม่มีชุดตรวจ จึงเทรนครบทุก epoch แล้วใช้สถานะสุดท้าย (ใช้เทรนโมเดลที่จะนำไปใช้ หลัง cross-validation เลือกจำนวน epoch แล้ว)
    """
    import copy

    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset

    torch.manual_seed(seed)
    weights = np.ones(Y_tr_scaled.shape, np.float32) if train_mask is None else train_mask.astype(np.float32)
    loader = DataLoader(
        TensorDataset(torch.from_numpy(X_tr), torch.from_numpy(Y_tr_scaled), torch.from_numpy(weights)),
        batch_size=batch_size,
        shuffle=True,
    )
    criterion = nn.HuberLoss(reduction="none")
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)

    select = X_va is not None
    baseline_mae = evaluate_mae(model, X_va, Y_va_raw, target_scaler, device, mask=val_mask) if select else float("nan")
    best_mae, best_epoch = baseline_mae, 0
    best_state = copy.deepcopy(model.state_dict())
    # epoch 0 = the deployed model, before any update
    history = [{"epoch": 0, "val_mae": round(baseline_mae, 3)}] if select else [{"epoch": 0}]
    bad = 0
    for epoch in range(1, epochs + 1):
        model.train()
        total, count = 0.0, 0
        for xb, yb, wb in loader:
            xb, yb, wb = xb.to(device), yb.to(device), wb.to(device)
            optimizer.zero_grad()
            loss = (criterion(model(xb), yb) * wb).sum() / wb.sum().clamp(min=1.0)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            total += float(loss.item()) * len(xb)
            count += len(xb)
        if not select:
            history.append({"epoch": epoch, "train_loss": round(total / max(count, 1), 6), "lr": optimizer.param_groups[0]["lr"]})
            logger.info(f"epoch {epoch}/{epochs} train_loss={total / max(count, 1):.6f}")
            best_epoch, best_state = epoch, copy.deepcopy(model.state_dict())
            continue
        val_mae = evaluate_mae(model, X_va, Y_va_raw, target_scaler, device, mask=val_mask)
        history.append({
            "epoch": epoch, "train_loss": round(total / max(count, 1), 6), "val_mae": round(val_mae, 3),
            "lr": optimizer.param_groups[0]["lr"],
        })
        logger.info(f"epoch {epoch}/{epochs} train_loss={total / max(count, 1):.6f} val_mae={val_mae:.2f} (best {best_mae:.2f})")
        if val_mae < best_mae - 1e-6:
            best_mae, best_epoch, bad = val_mae, epoch, 0
            best_state = copy.deepcopy(model.state_dict())
        else:
            bad += 1
            if bad >= patience:
                break
    model.load_state_dict(best_state)
    return {"baseline_val_mae": baseline_mae, "best_val_mae": best_mae, "best_epoch": best_epoch, "history": history}


def export_onnx(model, path: Path, lookback: int) -> None:
    """export ด้วยชื่อ input/output เดียวกับ train.py เพื่อให้ inference worker ใช้ต่อได้ทันที."""
    import torch

    model.eval().to("cpu")
    torch.onnx.export(
        model,
        torch.randn(1, lookback, len(ALIGNED_FEATURE_COLS)),
        str(path),
        input_names=["weather_sequence"],
        output_names=["ghi_forecast_18steps"],
        dynamic_axes={"weather_sequence": {0: "batch_size"}, "ghi_forecast_18steps": {0: "batch_size"}},
        opset_version=17,
        dynamo=False,
    )


def verify_onnx_matches(model, path: Path, lookback: int, tol: float = 1e-4) -> float:
    """เทียบ onnxruntime กับ PyTorch บน input สุ่ม; ถ้าต่างเกิน tol ให้ raise."""
    import onnxruntime as ort
    import torch

    x = np.random.default_rng(0).random((4, lookback, len(ALIGNED_FEATURE_COLS)), dtype=np.float32)
    sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    onnx_out = sess.run(None, {sess.get_inputs()[0].name: x})[0]
    with torch.no_grad():
        torch_out = model.eval().to("cpu")(torch.from_numpy(x)).numpy()
    diff = float(np.abs(onnx_out - torch_out).max())
    if diff > tol:
        raise RuntimeError(f"ONNX ที่ export ไม่ตรงกับ PyTorch (max diff {diff:.2e} > {tol:.0e})")
    return diff


# ----------------------------------------------------------------------------- orchestration
def execute_timeseries_retrain(
    payload: dict[str, Any],
    epochs: int = 8,
    learning_rate: float = 1e-4,
    device: Optional[str] = None,
) -> dict[str, Any]:
    """รัน retrain LSTM หนึ่งรอบ. คืน dict ที่มี status = skipped | rejected | deployed | failed."""
    logger.info(f">> [TIMESERIES RETRAIN] payload={payload}")

    # 1. Safety gate
    if not _env_bool("ENABLE_RETRAIN", False):
        logger.info("[STANDBY] ENABLE_RETRAIN=false — ข้ามการ retrain")
        return {
            "status": "skipped",
            "reason": "retrain_disabled",
            "message": "ตั้ง ENABLE_RETRAIN=true เพื่อเปิดใช้งาน",
            "received_payload": payload,
        }

    import joblib
    import redis
    from sqlalchemy import create_engine

    token = uuid.uuid4().hex
    try:
        lock = redis.Redis(host=os.environ.get("REDIS_HOST", "localhost"), port=_env_int("REDIS_PORT", 6379))
        lock.delete(SCHEDULED_KEY)  # เริ่มรันแล้ว: label ที่ส่งมาหลังจากนี้จะนัดรอบใหม่
        if not lock.set(LOCK_KEY, token, nx=True, ex=LOCK_TTL_SECONDS):
            return {"status": "skipped", "reason": "another_retrain_running"}
    except Exception as e:  # noqa: BLE001
        return {"status": "failed", "error": f"redis unavailable: {e}"}

    workdir = Path(tempfile.mkdtemp(prefix="retrain_ts_"))
    engine = None
    try:
        engine = create_engine(_sync_db_url(), pool_pre_ping=True)

        # 2. label ทั้งหมดจาก Label Studio (ทุก label ในช่วง lookback ถูกนำมาใช้ทุกครั้ง)
        lookback_days = _env_int("RETRAIN_LOOKBACK_DAYS", 45)
        labels_df = fetch_labels_from_label_studio(lookback_days)
        if labels_df.empty:
            return {"status": "skipped", "reason": "no_labels", "message": "ยังไม่มี label ใน Label Studio ช่วง lookback"}
        logger.info(f"label จาก Label Studio: {len(labels_df)} ค่า / {labels_df['station_id'].nunique()} สถานี")

        # 3. โมเดลที่ใช้งานอยู่ (ONNX = แหล่งความจริง)
        model_dir, source = fetch_deployed_model(workdir / "deployed")
        meta = json.loads((model_dir / "model_meta.json").read_text(encoding="utf-8"))
        feature_scaler = joblib.load(model_dir / "feature_scaler.joblib")
        target_scaler = joblib.load(model_dir / "target_scaler.joblib")
        lookback = int(meta["lookback_steps"])  # ความยาว input ของโมเดลที่ใช้งานอยู่ (ไม่กำหนดตายตัวในโค้ด)
        logger.info(f"โมเดลปัจจุบัน v{meta.get('version')} trained_at={meta.get('trained_at')} (จาก {source})")

        # 4. window แบบเดียวกับตอนใช้งาน: ข้อมูลป้อนจากสภาพอากาศอย่างเดียว เป้าหมายคือค่าที่วัดจริง
        from service.training.features import day_folds, forecast_days, make_live_windows, make_windows, measured_slots_per_day

        frames = load_training_frames(engine, lookback_days, labels_df)
        min_slots = _env_int("RETRAIN_MIN_DAY_SLOTS", 6)   # วันที่มีค่าวัดจริงน้อยกว่านี้ (1 ชั่วโมง) ยังไม่นับเป็นวันใหม่
        trained = set((meta.get("retrain") or {}).get("trained_days") or [])   # 'สถานี|วัน' ที่โมเดลที่ใช้งานอยู่เคยเทรนแล้ว
        Xs, Ys, Ms, starts, seen, station_days, all_days = [], [], [], [], [], set(), set()
        for station_id, frame in frames.items():
            if frame["measured"] is None:
                continue
            X, Y, M, st = make_live_windows(frame["inputs"], frame["measured"], lookback=lookback)
            logger.info(f"  {station_id}: {len(frame['inputs'])} ช่องเวลา -> {len(X)} windows ที่มีค่าวัดจริง")
            if len(X):
                Xs.append(X), Ys.append(Y), Ms.append(M), starts.append(st)
                slots = measured_slots_per_day(st, M, lookback)
                station_days |= {f"{station_id}|{day}" for day, n in slots.items() if n >= min_slots}
                all_days |= {f"{station_id}|{day}" for day in slots}
                seen_days = np.array([day for day in slots if f"{station_id}|{day}" in trained], dtype="datetime64[D]")
                seen.append(np.isin(forecast_days(st, lookback), seen_days))
        if not Xs:
            return {"status": "skipped", "reason": "no_complete_windows", "message": f"weather_history ไม่พอสำหรับ window {(lookback + FORECAST_STEPS) / 6:g} ชม. ที่มีค่าวัดจริง"}

        # สะสมค่าวัดจริงของวันใหม่ให้ครบก่อน: รอบที่ได้ข้อมูลเพิ่มวันเดียวให้ผลตามสภาพอากาศของวันนั้น ไม่ใช่ตามโมเดล
        days_needed = _env_int("RETRAIN_MIN_NEW_DAYS", 7)
        used = lock.get(USED_DAYS_KEY)   # ไม่มีบันทึก (เช่น Redis ถูกล้าง): ถือว่าใช้ไปแล้วเท่าที่โมเดลเคยเทรน
        new_days = days_with_new_values(station_days, set(json.loads(used)) if used else trained)

        def save_counter(count: int) -> None:
            lock.set(STATUS_KEY, json.dumps({
                "new_days": count,
                "days_needed": days_needed,
                "measured_days": len({key.split("|", 1)[1] for key in station_days}),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }))

        def mark_days_used() -> None:
            lock.set(USED_DAYS_KEY, json.dumps(sorted(station_days)))
            save_counter(0)

        save_counter(len(new_days))
        if len(new_days) < days_needed:
            logger.info(f"ค่าวัดจริงของวันใหม่ {len(new_days)}/{days_needed} วัน — ยังไม่ retrain")
            return {
                "status": "skipped",
                "reason": "waiting_for_more_days",
                "new_days": len(new_days),
                "days_needed": days_needed,
                "message": f"มีค่าวัดจริงของวันใหม่ {len(new_days)} วัน จะ retrain เมื่อครบ {days_needed} วัน",
            }

        # 5. cross-validation ตามวัน: ตรวจเฉพาะวันที่โมเดลที่ใช้งานอยู่ยังไม่เคยเทรน โมเดลที่ถูกวัดก็ไม่เคยเห็นวันนั้น
        X_all, Y_all, M_all, starts_all = np.concatenate(Xs), np.concatenate(Ys), np.concatenate(Ms), np.concatenate(starts)
        days = forecast_days(starts_all, lookback)
        unseen = M_all & ~np.concatenate(seen)
        if not unseen.any():
            return {
                "status": "skipped",
                "reason": "no_unseen_days",
                "label_count": int(len(labels_df)),
                "message": "โมเดลที่ใช้งานอยู่เคยเทรนกับค่าวัดจริงทุกวันที่มีแล้ว ไม่มีวันให้ตรวจ",
            }
        folds = day_folds(days, M_all, max_folds=_env_int("RETRAIN_CV_FOLDS", 7), test_on=unseen)
        if not folds:
            return {
                "status": "skipped",
                "reason": "needs_two_days_of_measured_ghi",
                "label_count": int(len(labels_df)),
                "message": "ต้องมีค่าวัดจริงอย่างน้อย 2 วัน: กันไว้ตรวจหนึ่งวัน ใช้เทรนหนึ่งวัน",
            }
        min_train = _env_int("RETRAIN_MIN_TRAIN_WINDOWS", 50)
        fewest = min(len(fold["train_idx"]) for fold in folds)
        if fewest < min_train:
            return {"status": "skipped", "reason": "insufficient_training_data", "train_windows": int(fewest), "min_train_windows": min_train}
        test_days = sorted(day for fold in folds for day in fold["days"])
        measured_days = len(np.unique(days[M_all]))
        logger.info(f"ค่าวัดจริง {measured_days} วัน: ตรวจ {len(test_days)} วันที่โมเดลยังไม่เคยเทรน แบ่ง {len(folds)} กลุ่ม, windows={len(X_all)}")

        def scale_x(X: np.ndarray) -> np.ndarray:
            n = len(X)
            return feature_scaler.transform(X.reshape(-1, X.shape[-1])).reshape(n, lookback, -1).astype(np.float32)

        X_scaled = scale_x(X_all)
        Y_scaled = target_scaler.transform(Y_all.reshape(-1, 1)).reshape(Y_all.shape).astype(np.float32)

        # window ที่เป้าหมายเป็นค่าของ Open-Meteo (ทุกสถานี): ไม่ใช้ตัดสิน บันทึกไว้ให้เห็นว่าโมเดลขยับจากแหล่งข้อมูลป้อนไปเท่าไร
        Xp, Yp = [], []
        for frame in frames.values():
            X, Y, _, _ = make_windows(frame["inputs"], lookback=lookback, stride=_env_int("RETRAIN_WINDOW_STRIDE", 2))
            if len(X):
                Xp.append(X), Yp.append(Y)
        X_plain, Y_plain = scale_x(np.concatenate(Xp)), np.concatenate(Yp)

        import torch

        from service.models.solar_lstm import SolarLSTMForecaster
        from service.training.onnx_weights import load_onnx_into_model

        dev = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))

        def deployed_model():
            m = SolarLSTMForecaster(input_dim=len(ALIGNED_FEATURE_COLS), hidden_dim=128, num_layers=2, forecast_steps=FORECAST_STEPS)
            load_onnx_into_model(m, str(model_dir / "solar_ghi_lstm.onnx"))
            return m.to(dev)

        n_epochs = int(payload.get("epochs", epochs))
        lr = float(payload.get("learning_rate", learning_rate))
        mae_sum, loss_sum, points = np.zeros(n_epochs + 1), np.zeros(n_epochs + 1), 0
        for i, fold in enumerate(folds, 1):
            tr, te = fold["train_idx"], fold["test_idx"]
            run = fine_tune(
                deployed_model(), X_scaled[tr], Y_scaled[tr], X_scaled[te], Y_all[te], target_scaler, dev,
                epochs=n_epochs, lr=lr, patience=n_epochs + 1,   # ไม่หยุดก่อน: ต้องได้ค่าของทุก epoch จากทุกกลุ่ม
                val_mask=fold["test_mask"], train_mask=M_all[tr],
            )
            n = int(fold["test_mask"].sum())
            mae_sum += n * np.array([row["val_mae"] for row in run["history"]])
            loss_sum[1:] += np.array([row["train_loss"] for row in run["history"][1:]])
            points += n
            logger.info(f"กลุ่ม {i}/{len(folds)} กัน {', '.join(fold['days'])} ({n} จุด): MAE {run['history'][0]['val_mae']:.1f} -> {run['history'][-1]['val_mae']:.1f}")
        mae_by_epoch = mae_sum / points                  # MAE รวมทุกวันของแต่ละ epoch; epoch 0 = โมเดลที่ใช้งานอยู่
        best_epoch = int(np.argmin(mae_by_epoch))
        real_before, real_after = float(mae_by_epoch[0]), float(mae_by_epoch[best_epoch])
        history = [{"epoch": 0, "val_mae": round(real_before, 3)}] + [
            {"epoch": e, "train_loss": round(float(loss_sum[e] / len(folds)), 6), "val_mae": round(float(mae_by_epoch[e]), 3), "lr": lr}
            for e in range(1, n_epochs + 1)
        ]

        # โมเดลที่จะนำไปใช้: เทรนจากทุกวันด้วยจำนวน epoch ที่ cross-validation เลือก
        model = deployed_model()
        plain_before = evaluate_mae(model, X_plain, Y_plain, target_scaler, dev)
        if best_epoch > 0:
            fine_tune(model, X_scaled, Y_scaled, None, None, target_scaler, dev, epochs=best_epoch, lr=lr, train_mask=M_all)
        plain_after = evaluate_mae(model, X_plain, Y_plain, target_scaler, dev)

        min_improvement = _env_float("RETRAIN_MIN_IMPROVEMENT", 0.03)
        summary = {
            "gate": "measured_ghi",
            "val_mae_before": round(plain_before, 3),   # เทียบกับค่าของ Open-Meteo: ข้อมูลประกอบ ไม่ใช้ตัดสิน
            "val_mae_after": round(plain_after, 3),
            "best_epoch": best_epoch,
            "train_windows": int(len(X_all)),
            "val_windows": int(len(X_all)),
            "label_count": int(len(labels_df)),
            "history": history,
            "holdout_day": f"{test_days[0]} – {test_days[-1]}",
            "test_days": len(test_days),
            "measured_days": measured_days,
            "new_days": len(new_days),
            "cv_folds": len(folds),
            "real_val_points": points,
            "real_mae_before": round(real_before, 3),
            "real_mae_after": round(real_after, 3),
            "min_improvement": min_improvement,
        }
        improved = best_epoch > 0 and accepts(real_before, real_after, min_improvement)
        reason = None if improved else "no_improvement_on_measured_ghi"
        old_mae, new_mae = real_before, real_after

        if reason is not None:
            mark_days_used()
            _log_mlflow(summary, deployed=False, reason=reason)
            return {"status": "rejected", "reason": reason, **summary}

        # 6. export + ตรวจ + สำรอง + deploy
        new_onnx = workdir / "new_model.onnx"
        export_onnx(model, new_onnx, lookback)
        diff = verify_onnx_matches(model, new_onnx, lookback)

        backup_dir = backup_local_model(meta.get("trained_at", "unknown"))
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        new_meta = dict(meta)
        new_meta.update(
            {
                "version": _bump_patch(meta.get("version", "1.0.0")),
                "trained_at": _utc_stamp(),
                "size_bytes": new_onnx.stat().st_size,
                "retrain": {
                    "previous_version": meta.get("version"),
                    "previous_trained_at": meta.get("trained_at"),
                    "gate": summary["gate"],
                    "val_mae_before": summary["val_mae_before"],
                    "val_mae_after": summary["val_mae_after"],
                    "real_mae_before": summary.get("real_mae_before"),
                    "real_mae_after": summary.get("real_mae_after"),
                    "holdout_day": summary.get("holdout_day"),
                    "test_days": summary.get("test_days"),
                    "measured_days": summary.get("measured_days"),
                    "cv_folds": summary.get("cv_folds"),
                    # ทุกวันที่โมเดลนี้และโมเดลก่อนหน้าในสายเดียวกันเคยเทรน: รอบถัดไปไม่ใช้วันเหล่านี้ตรวจ
                    "trained_days": sorted(trained | all_days),
                    "min_improvement": summary.get("min_improvement"),
                    "train_windows": summary["train_windows"],
                    "val_windows": summary["val_windows"],
                    "lookback_days": lookback_days,
                    "stations": sorted(frames.keys()),
                    "onnx_max_diff": diff,
                },
            }
        )
        shutil.copy2(new_onnx, MODELS_DIR / "solar_ghi_lstm.onnx")
        for name in ("feature_scaler.joblib", "target_scaler.joblib"):  # scalers ไม่เปลี่ยน (ใช้ชุดเดิมของโมเดล)
            if not (MODELS_DIR / name).exists():
                shutil.copy2(model_dir / name, MODELS_DIR / name)
        (MODELS_DIR / "model_meta.json").write_text(json.dumps(new_meta, indent=2, ensure_ascii=False), encoding="utf-8")

        client = _minio_client()
        if not client.bucket_exists(MINIO_BUCKET):
            client.make_bucket(MINIO_BUCKET)
        client.fput_object(MINIO_BUCKET, f"{MINIO_PREFIX}/solar_ghi_lstm.onnx", str(MODELS_DIR / "solar_ghi_lstm.onnx"))
        client.fput_object(MINIO_BUCKET, f"{MINIO_PREFIX}/model_meta.json", str(MODELS_DIR / "model_meta.json"))  # meta ขึ้นทีหลังสุด

        mark_days_used()
        _log_mlflow(summary, deployed=True, version=new_meta["version"])
        logger.info(f">> DEPLOYED v{new_meta['version']} MAE เทียบค่าวัดจริง {old_mae:.2f} -> {new_mae:.2f}")
        return {
            "status": "deployed",
            "version": new_meta["version"],
            "trained_at": new_meta["trained_at"],
            "backup_dir": str(backup_dir) if backup_dir else None,
            "onnx_model_path": str(MODELS_DIR / "solar_ghi_lstm.onnx"),
            **summary,
        }
    except Exception as e:  # noqa: BLE001
        logger.exception("retrain failed")
        return {"status": "failed", "error": str(e)}
    finally:
        try:
            if lock.get(LOCK_KEY) == token.encode():
                lock.delete(LOCK_KEY)
        except Exception:  # noqa: BLE001
            pass
        if engine is not None:
            engine.dispose()
        shutil.rmtree(workdir, ignore_errors=True)


def _log_mlflow(summary: dict[str, Any], deployed: bool, reason: Optional[str] = None, version: Optional[str] = None) -> None:
    """บันทึกผลลง MLflow แบบ best-effort (ล้มเหลวไม่กระทบการ retrain)."""
    try:
        import mlflow

        from service.training.curves import log_history

        mlflow.set_experiment("solar_lstm_retrain")
        with mlflow.start_run():
            mlflow.log_params({k: summary[k] for k in ("train_windows", "val_windows", "label_count", "best_epoch")})
            mlflow.log_metrics({"val_mae_before": summary["val_mae_before"], "val_mae_after": summary["val_mae_after"]})
            if "real_mae_before" in summary:
                mlflow.log_metrics({"real_mae_before": summary["real_mae_before"], "real_mae_after": summary["real_mae_after"]})
                mlflow.set_tag("holdout_day", summary["holdout_day"])
            for name in ("min_improvement", "test_days", "measured_days", "new_days", "cv_folds"):
                if name in summary:
                    mlflow.log_param(name, summary[name])
            mlflow.set_tag("gate", summary["gate"])
            log_history(mlflow, summary.get("history"))  # learning curve: one point per epoch
            mlflow.set_tag("deployed", str(deployed))
            mlflow.set_tag("status", "deployed" if deployed else "rejected")
            if reason:
                mlflow.set_tag("reason", reason)
            if version:
                mlflow.set_tag("version", str(version))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"MLflow logging skipped: {e}")
