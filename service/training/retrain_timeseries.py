"""Solar Time-Series LSTM retraining (ข้อมูลจริง + ground truth, ตรวจสอบก่อน deploy).

ลำดับงาน:
  1. ตรวจ ENABLE_RETRAIN + ล็อกกันรันซ้อน (Redis) + ล้างคิว debounce
  2. ดึงโมเดลที่ใช้งานอยู่ (ONNX + scalers + meta) จาก MinIO (สำรอง: model/time-series/) — ONNX คือแหล่งความจริงเดียว ไม่ต้องมี .pth
  3. อ่าน weather_history จาก PostgreSQL + label ทั้งหมดจาก Label Studio -> สร้างฟีเจอร์ 16 ตัว/window (ground truth ทับค่า GHI)
  4. โหลดน้ำหนัก ONNX เข้า PyTorch -> fine-tune (แบ่ง validation ตามวัน ไม่ให้ target รั่ว)
  5. deploy เมื่อ MAE บน validation ไม่แย่กว่าโมเดลเดิมเกินเกณฑ์ -> export ONNX, ตรวจเทียบ onnxruntime,
     สำรองของเดิม (เก็บ 3 เวอร์ชัน), เขียนไฟล์ local, อัปโหลด MinIO (meta ขึ้นทีหลังสุด)

หมายเหตุ: ทุกครั้งที่รัน label "ทั้งหมด" ในช่วงข้อมูลจะถูกนำไปทับ GHI (ไม่ใช่เฉพาะ label ใหม่) เพื่อให้โมเดลเห็นข้อมูลเดิมด้วย.
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
    """อ่าน weather_history จาก Postgres + ใช้ label จาก Label Studio -> {station_id: feature frame}."""
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
        lab_df = labels_df[labels_df["station_id"] == station_id]
        lab_series = (
            pd.Series(lab_df["ghi_actual"].values, index=pd.to_datetime(lab_df["timestamp"], utc=True))
            if len(lab_df)
            else None
        )
        frames[station_id] = build_station_frame(wdf.drop(columns=["station_id"]), labels=lab_series)
    return frames


# ----------------------------------------------------------------------------- model math
def evaluate_mae(model, X_scaled: np.ndarray, Y_raw: np.ndarray, target_scaler, device, batch_size: int = 256) -> float:
    """MAE (W/m²) บนข้อมูลที่ scale แล้ว; แปลงผลกลับเป็น W/m² ด้วย target_scaler และ clamp >= 0 เหมือนตอน inference."""
    import torch

    model.eval()
    preds = []
    with torch.no_grad():
        for i in range(0, len(X_scaled), batch_size):
            xb = torch.from_numpy(X_scaled[i:i + batch_size]).to(device)
            preds.append(model(xb).cpu().numpy())
    p = np.concatenate(preds)
    p_raw = np.clip(target_scaler.inverse_transform(p.reshape(-1, 1)).reshape(p.shape), 0.0, None)
    return float(np.mean(np.abs(p_raw - Y_raw)))


def fine_tune(
    model,
    X_tr: np.ndarray,
    Y_tr_scaled: np.ndarray,
    X_va: np.ndarray,
    Y_va_raw: np.ndarray,
    target_scaler,
    device,
    epochs: int,
    lr: float,
    batch_size: int = 64,
    patience: int = 3,
    seed: int = 42,
) -> dict[str, Any]:
    """fine-tune แบบ warm-start; เก็บสถานะที่ val MAE ต่ำสุด (epoch 0 = โมเดลเดิม). คืนสรุปผล และโหลด best state ใส่ model."""
    import copy

    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset

    torch.manual_seed(seed)
    loader = DataLoader(
        TensorDataset(torch.from_numpy(X_tr), torch.from_numpy(Y_tr_scaled)),
        batch_size=batch_size,
        shuffle=True,
    )
    criterion = nn.HuberLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)

    baseline_mae = evaluate_mae(model, X_va, Y_va_raw, target_scaler, device)
    best_mae, best_epoch = baseline_mae, 0
    best_state = copy.deepcopy(model.state_dict())
    history = []
    bad = 0
    for epoch in range(1, epochs + 1):
        model.train()
        total, count = 0.0, 0
        for xb, yb in loader:
            xb, yb = xb.to(device), yb.to(device)
            optimizer.zero_grad()
            loss = criterion(model(xb), yb)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            total += float(loss.item()) * len(xb)
            count += len(xb)
        val_mae = evaluate_mae(model, X_va, Y_va_raw, target_scaler, device)
        history.append({"epoch": epoch, "train_loss": round(total / max(count, 1), 6), "val_mae": round(val_mae, 3)})
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

        # 4. ข้อมูลจริง -> window
        from service.training.features import make_windows, split_by_day

        frames = load_training_frames(engine, lookback_days, labels_df)
        stride = _env_int("RETRAIN_WINDOW_STRIDE", 2)
        Xs, Ys, starts, has_label = [], [], [], []
        for station_id, frame in frames.items():
            X, Y, st, hl = make_windows(frame, lookback=lookback, stride=stride)
            logger.info(f"  {station_id}: {len(frame)} ช่องเวลา -> {len(X)} windows")
            if len(X):
                Xs.append(X), Ys.append(Y), starts.append(st), has_label.append(hl)
        if not Xs:
            return {"status": "skipped", "reason": "no_complete_windows", "message": f"weather_history ไม่พอสำหรับ window {(lookback + FORECAST_STEPS) / 6:g} ชม."}
        X_all, Y_all = np.concatenate(Xs), np.concatenate(Ys)
        starts_all, has_label_all = np.concatenate(starts), np.concatenate(has_label)

        train_idx, val_idx = split_by_day(starts_all, has_label_all, lookback=lookback)
        min_val = _env_int("RETRAIN_MIN_VAL_WINDOWS", 50)
        if len(val_idx) < min_val or len(train_idx) == 0:
            return {
                "status": "skipped",
                "reason": "insufficient_validation_data",
                "train_windows": int(len(train_idx)),
                "val_windows": int(len(val_idx)),
                "min_val_windows": min_val,
            }

        def scale_x(X: np.ndarray) -> np.ndarray:
            n = len(X)
            return feature_scaler.transform(X.reshape(-1, X.shape[-1])).reshape(n, lookback, -1).astype(np.float32)

        X_va, Y_va_raw = scale_x(X_all[val_idx]), Y_all[val_idx]
        oversample = max(1, _env_int("RETRAIN_LABEL_OVERSAMPLE", 5))
        repeat = np.where(has_label_all[train_idx], oversample, 1)
        train_rep = np.repeat(train_idx, repeat)
        X_tr = scale_x(X_all[train_rep])
        Y_tr = target_scaler.transform(Y_all[train_rep].reshape(-1, 1)).reshape(len(train_rep), FORECAST_STEPS).astype(np.float32)
        logger.info(f"train windows={len(train_idx)} (+label oversample => {len(train_rep)}), val windows={len(val_idx)}")

        # 5. โหลดน้ำหนัก ONNX -> PyTorch -> fine-tune
        import torch

        from service.models.solar_lstm import SolarLSTMForecaster
        from service.training.onnx_weights import load_onnx_into_model

        dev = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        model = SolarLSTMForecaster(
            input_dim=len(ALIGNED_FEATURE_COLS), hidden_dim=128, num_layers=2, forecast_steps=FORECAST_STEPS
        )
        load_onnx_into_model(model, str(model_dir / "solar_ghi_lstm.onnx"))
        model.to(dev)
        result = fine_tune(
            model, X_tr, Y_tr, X_va, Y_va_raw, target_scaler, dev,
            epochs=int(payload.get("epochs", epochs)),
            lr=float(payload.get("learning_rate", learning_rate)),
        )

        old_mae, new_mae = result["baseline_val_mae"], result["best_val_mae"]
        ratio = _env_float("RETRAIN_MAX_REGRESSION_RATIO", 1.0)
        summary = {
            "val_mae_before": round(old_mae, 3),
            "val_mae_after": round(new_mae, 3),
            "best_epoch": result["best_epoch"],
            "train_windows": int(len(train_idx)),
            "val_windows": int(len(val_idx)),
            "label_count": int(len(labels_df)),
            "history": result["history"],
        }

        if result["best_epoch"] == 0 or new_mae > old_mae * ratio:
            _log_mlflow(summary, deployed=False)
            return {"status": "rejected", "reason": "no_improvement_on_validation", **summary}

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
                    "val_mae_before": summary["val_mae_before"],
                    "val_mae_after": summary["val_mae_after"],
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

        _log_mlflow(summary, deployed=True)
        logger.info(f">> DEPLOYED v{new_meta['version']} val_mae {old_mae:.2f} -> {new_mae:.2f}")
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


def _log_mlflow(summary: dict[str, Any], deployed: bool) -> None:
    """บันทึกผลลง MLflow แบบ best-effort (ล้มเหลวไม่กระทบการ retrain)."""
    try:
        import mlflow

        mlflow.set_experiment("solar_lstm_retrain")
        with mlflow.start_run():
            mlflow.log_params({k: summary[k] for k in ("train_windows", "val_windows", "label_count", "best_epoch")})
            mlflow.log_metrics({"val_mae_before": summary["val_mae_before"], "val_mae_after": summary["val_mae_after"]})
            mlflow.set_tag("deployed", str(deployed))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"MLflow logging skipped: {e}")
