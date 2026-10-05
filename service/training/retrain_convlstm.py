"""ConvLSTM cloud nowcaster: batch retraining on real satellite frames.

Flow (started by the trainer worker when a batch of new daytime scans is complete):
  1. ENABLE_RETRAIN gate + Redis lock (one run at a time)
  2. Dataset: real Himawari Band 03 crops from the MinIO cache, cut into runs of 30 consecutive
     10-minute daytime frames (12 in -> 18 out) per station
  3. Chronological split: the newest part of the period is held out for validation
  4. Fine-tune from the weights of the deployed ONNX model
  5. Gate: the fine-tuned model must not be worse than the deployed one on the held-out sequences
  6. Deploy: back up the current files, export ONNX (checked against PyTorch), update the metadata,
     upload to MinIO, log the run in MLflow. The inference worker loads the file on its next job.

The network below is the architecture of the deployed 'cloud_seq2seq_12to18.onnx' (read back from its
graph), so the ONNX weights load by name and the export keeps the same input and output tensors.

CLI (trainer container, /workspace):
    python -m service.training.retrain_convlstm --status
    python -m service.training.retrain_convlstm --backfill-days 3
    python -m service.training.retrain_convlstm --run [--force]
"""

import argparse
import io
import json
import logging
import os
import re
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    _TORCH_AVAILABLE = True
except ImportError:  # the module is imported by code that only needs the constants
    torch = None
    F = None
    _TORCH_AVAILABLE = False

    class _DummyModule:
        def __init__(self, *args, **kwargs):
            pass

    nn = type("nn", (), {"Module": _DummyModule})()

from service.workers import convlstm_batch as batch
from service.workers.cloud_coverage import aoi_cloud_fraction
from service.workers.solar_geometry import cos_zenith_at

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RetrainConvLSTM")

MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "model" / "convlstm"
ONNX_NAME = "cloud_seq2seq_12to18.onnx"
META_NAME = "cloud_seq2seq_metadata.json"
MODEL_FILES = (ONNX_NAME, META_NAME)
MINIO_BUCKET = "models"
MINIO_PREFIX = "cloud_convlstm"  # the inference worker syncs from here
KEEP_BACKUPS = 5

IN_FRAMES = 12
OUT_FRAMES = 18
SEQ_FRAMES = IN_FRAMES + OUT_FRAMES
IMAGE_SIZE = 64
HIDDEN_DIM = 64
INPUT_NAME = "satellite_sequence_12"
OUTPUT_NAME = "future_satellite_sequence_18"


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


# ----------------------------------------------------------------------------- model
class ConvLSTMCell(nn.Module):
    """ConvLSTM cell; gate order along the channel axis is input, forget, cell, output."""

    def __init__(self, in_dim: int, hidden_dim: int):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.conv = nn.Conv2d(in_dim + hidden_dim, 4 * hidden_dim, kernel_size=3, padding=1)

    def forward(self, x, h, c):
        i, f, g, o = torch.split(self.conv(torch.cat([x, h], dim=1)), self.hidden_dim, dim=1)
        c = torch.sigmoid(f) * c + torch.sigmoid(i) * torch.tanh(g)
        h = torch.sigmoid(o) * torch.tanh(c)
        return h, c


class SpatialEncoder(nn.Module):
    """Frame (1, 64, 64) -> features (64, 32, 32)."""

    def __init__(self, hidden_dim: int = HIDDEN_DIM):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(1, 32, kernel_size=3, padding=1),
            nn.LeakyReLU(0.1),
            nn.Conv2d(32, hidden_dim, kernel_size=3, stride=2, padding=1),
            nn.LeakyReLU(0.1),
        )

    def forward(self, x):
        return self.net(x)


class SpatialDecoder(nn.Module):
    """Hidden state (64, 32, 32) -> frame (1, 64, 64) in [0, 1]."""

    def __init__(self, hidden_dim: int = HIDDEN_DIM):
        super().__init__()
        self.net = nn.Sequential(
            nn.ConvTranspose2d(hidden_dim, 32, kernel_size=4, stride=2, padding=1),
            nn.LeakyReLU(0.1),
            nn.Conv2d(32, 16, kernel_size=3, padding=1),
            nn.LeakyReLU(0.1),
            nn.Conv2d(16, 1, kernel_size=3, padding=1),
            nn.Sigmoid(),
        )

    def forward(self, x):
        return self.net(x)


class CloudSeq2SeqConvLSTM(nn.Module):
    """Encoder-decoder ConvLSTM: 12 observed frames -> 18 future frames (10-minute steps)."""

    def __init__(self, out_frames: int = OUT_FRAMES, hidden_dim: int = HIDDEN_DIM):
        super().__init__()
        self.out_frames = out_frames
        self.hidden_dim = hidden_dim
        self.spatial_encoder = SpatialEncoder(hidden_dim)
        self.encoder_cell = ConvLSTMCell(hidden_dim, hidden_dim)
        self.decoder_cell = ConvLSTMCell(hidden_dim, hidden_dim)
        self.spatial_decoder = SpatialDecoder(hidden_dim)

    def forward(self, in_seq, targets=None, teacher_forcing_ratio: float = 0.0):
        """in_seq (B, 12, 1, H, W) -> (B, 18, 1, H, W). `targets` is only used for teacher forcing."""
        b, t_in, _, height, width = in_seq.shape
        h = torch.zeros(b, self.hidden_dim, height // 2, width // 2, device=in_seq.device, dtype=in_seq.dtype)
        c = torch.zeros_like(h)

        feat = None
        for t in range(t_in):
            feat = self.spatial_encoder(in_seq[:, t])
            h, c = self.encoder_cell(feat, h, c)

        preds = []
        dec_in = feat  # the decoder starts from the newest observed frame
        for t in range(self.out_frames):
            h, c = self.decoder_cell(dec_in, h, c)
            pred = self.spatial_decoder(h)
            preds.append(pred)
            use_truth = targets is not None and teacher_forcing_ratio > 0.0 and torch.rand(1).item() < teacher_forcing_ratio
            dec_in = self.spatial_encoder(targets[:, t] if use_truth else pred)
        return torch.stack(preds, dim=1)


def load_onnx_weights(model: "CloudSeq2SeqConvLSTM", onnx_path: Path) -> None:
    """Copy the weights of the deployed ONNX file into the PyTorch model (same parameter names)."""
    import onnx
    from onnx import numpy_helper

    initializers = {i.name: numpy_helper.to_array(i) for i in onnx.load(str(onnx_path)).graph.initializer}
    state = model.state_dict()
    missing = [k for k in state if k not in initializers]
    if missing:
        raise RuntimeError(f"ONNX file '{onnx_path.name}' has no weights for {missing}: architecture mismatch")
    for name, tensor in state.items():
        arr = initializers[name]
        if tuple(arr.shape) != tuple(tensor.shape):
            raise RuntimeError(f"shape mismatch for '{name}': onnx {arr.shape} vs model {tuple(tensor.shape)}")
        state[name] = torch.from_numpy(np.array(arr))
    model.load_state_dict(state)


def export_onnx(model: "CloudSeq2SeqConvLSTM", path: Path) -> None:
    model = model.to("cpu").eval()
    dummy = torch.zeros(1, IN_FRAMES, 1, IMAGE_SIZE, IMAGE_SIZE)
    torch.onnx.export(
        model,
        (dummy,),
        str(path),
        input_names=[INPUT_NAME],
        output_names=[OUTPUT_NAME],
        dynamic_axes={INPUT_NAME: {0: "batch_size"}, OUTPUT_NAME: {0: "batch_size"}},
        opset_version=14,
        dynamo=False,
    )


def onnx_max_deviation(model: "CloudSeq2SeqConvLSTM", onnx_path: Path, sample: np.ndarray) -> float:
    """Largest absolute difference between ONNX Runtime and PyTorch on `sample` (B, 12, 1, H, W)."""
    import onnxruntime as ort

    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    onnx_out = session.run(None, {session.get_inputs()[0].name: sample.astype(np.float32)})[0]
    model = model.to("cpu").eval()
    with torch.no_grad():
        torch_out = model(torch.from_numpy(sample.astype(np.float32))).numpy()
    return float(np.max(np.abs(onnx_out - torch_out)))


# ----------------------------------------------------------------------------- loss / metrics
def ssim(pred, target, window_size: int = 11):
    """Mean structural similarity over 2D frames (B, C, H, W)."""
    c1, c2 = 0.01**2, 0.03**2
    pad = window_size // 2
    mu1 = F.avg_pool2d(pred, window_size, stride=1, padding=pad)
    mu2 = F.avg_pool2d(target, window_size, stride=1, padding=pad)
    sigma1_sq = F.avg_pool2d(pred * pred, window_size, stride=1, padding=pad) - mu1.pow(2)
    sigma2_sq = F.avg_pool2d(target * target, window_size, stride=1, padding=pad) - mu2.pow(2)
    sigma12 = F.avg_pool2d(pred * target, window_size, stride=1, padding=pad) - mu1 * mu2
    ssim_map = ((2 * mu1 * mu2 + c1) * (2 * sigma12 + c2)) / ((mu1.pow(2) + mu2.pow(2) + c1) * (sigma1_sq + sigma2_sq + c2))
    return ssim_map.mean()


class CompositeNowcastingLoss(nn.Module):
    """MSE + L1 + (1 - SSIM) + spatial gradient difference, the loss the model was first trained with."""

    def __init__(self, w_mse: float = 1.0, w_l1: float = 0.5, w_ssim: float = 0.4, w_grad: float = 0.2):
        super().__init__()
        self.w_mse, self.w_l1, self.w_ssim, self.w_grad = w_mse, w_l1, w_ssim, w_grad

    def forward(self, pred, target):
        b, t, ch, height, width = pred.shape
        ssim_loss = 1.0 - ssim(pred.reshape(b * t, ch, height, width), target.reshape(b * t, ch, height, width))
        grad_loss = F.l1_loss(pred[..., 1:] - pred[..., :-1], target[..., 1:] - target[..., :-1]) + F.l1_loss(
            pred[..., 1:, :] - pred[..., :-1, :], target[..., 1:, :] - target[..., :-1, :]
        )
        return (
            self.w_mse * F.mse_loss(pred, target)
            + self.w_l1 * F.l1_loss(pred, target)
            + self.w_ssim * ssim_loss
            + self.w_grad * grad_loss
        )


# ----------------------------------------------------------------------------- real data
def _minio_client():
    import urllib3
    from minio import Minio

    return Minio(
        os.environ.get("MINIO_ENDPOINT", "localhost:9000"),
        access_key=os.environ.get("MINIO_ACCESS_KEY", "admin"),
        secret_key=os.environ.get("MINIO_SECRET_KEY", "password"),
        secure=False,
        http_client=urllib3.PoolManager(timeout=urllib3.Timeout(connect=5, read=120)),
    )


def station_coordinates() -> dict[str, tuple[float, float]]:
    """Latitude/longitude of every station, read from the stations table."""
    from sqlalchemy import create_engine, text

    url = os.environ.get("RETRAIN_DATABASE_URL") or os.environ.get("DATABASE_URL") or os.environ.get("database_url", "")
    if not url:
        raise RuntimeError("DATABASE_URL is not set in the trainer worker")
    engine = create_engine(url.replace("+asyncpg", "+psycopg2"))
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT id, latitude, longitude FROM stations")).fetchall()
    finally:
        engine.dispose()
    return {r[0]: (float(r[1]), float(r[2])) for r in rows}


def rejected_frames() -> set[tuple[str, datetime]]:
    """Frames a reviewer marked as not usable (frame review page). They never enter a training sequence."""
    from sqlalchemy import create_engine, text

    url = os.environ.get("RETRAIN_DATABASE_URL") or os.environ.get("DATABASE_URL") or os.environ.get("database_url", "")
    if not url:
        return set()
    engine = create_engine(url.replace("+asyncpg", "+psycopg2"))
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT station_id, frame_timestamp FROM satellite_frame_reviews WHERE status = 'rejected'")).fetchall()
    except Exception as e:  # noqa: BLE001  the table does not exist before the first review
        logger.info(f"No frame reviews read ({type(e).__name__})")
        return set()
    finally:
        engine.dispose()
    return {(r[0], r[1].astimezone(timezone.utc).replace(second=0, microsecond=0)) for r in rows}


def load_frame(minio_client, station_id: str, ts: datetime) -> np.ndarray:
    """One cached real frame as float32 (64, 64) in [0, 1], decoded exactly as the inference worker does."""
    from service.workers.satellite_preprocessor import CACHE_BUCKET, frame_object_name, load_and_preprocess_single_frame

    resp = minio_client.get_object(CACHE_BUCKET, frame_object_name(station_id, ts))
    try:
        return load_and_preprocess_single_frame(resp.read())
    finally:
        resp.close()
        resp.release_conn()


def build_dataset(minio_client, coords: dict[str, tuple[float, float]], stride: int, lookback_days: Optional[int] = None) -> dict[str, Any]:
    """Sequences of 30 consecutive real daytime frames per station, from the last `lookback_days` days of the cache.

    Returns {"x": (N, 12, 1, 64, 64), "y": (N, 18, 1, 64, 64), "starts": [...], "stations": [...],
             "cos_out": (N, 18) cos(solar zenith) of the target frames, "newest_scan": datetime | None}.
    """
    day = batch.daytime_scans(batch.list_cached_scans(minio_client), coords)
    newest = max((times[-1] for times in day.values()), default=None)
    if newest is not None and lookback_days:
        oldest = newest - timedelta(days=lookback_days)
        day = {station_id: [ts for ts in times if ts >= oldest] for station_id, times in day.items()}

    # every candidate frame is a daytime scan, so an all-black one is NICT's "no image" tile, not an observation
    frames: dict[tuple[str, datetime], np.ndarray] = {}
    blank = 0
    rejected = rejected_frames()
    skipped_by_review = 0
    items: list[tuple[datetime, str]] = []
    for station_id, times in day.items():
        real_times = []
        for ts in times:
            if (station_id, ts) in rejected:
                skipped_by_review += 1
                continue
            frame = load_frame(minio_client, station_id, ts)
            if float(frame.max()) == 0.0:
                blank += 1
                continue
            frames[(station_id, ts)] = frame
            real_times.append(ts)
        items.extend((start, station_id) for start in batch.find_sequences(real_times, SEQ_FRAMES, stride))
    items.sort()

    xs, ys, cos_out = [], [], []
    for start, station_id in items:
        lat, lon = coords[station_id]
        seq = [frames[(station_id, start + k * batch.FRAME_INTERVAL)] for k in range(SEQ_FRAMES)]
        arr = np.stack(seq)[:, np.newaxis, :, :]
        xs.append(arr[:IN_FRAMES])
        ys.append(arr[IN_FRAMES:])
        cos_out.append([cos_zenith_at(lat, lon, start + k * batch.FRAME_INTERVAL) for k in range(IN_FRAMES, SEQ_FRAMES)])

    shape = (0, 0, 1, IMAGE_SIZE, IMAGE_SIZE)
    return {
        "x": np.stack(xs).astype(np.float32) if xs else np.zeros(shape, dtype=np.float32),
        "y": np.stack(ys).astype(np.float32) if ys else np.zeros(shape, dtype=np.float32),
        "cos_out": np.asarray(cos_out, dtype=np.float64),
        "starts": [s for s, _ in items],
        "stations": [st for _, st in items],
        "newest_scan": newest,
        "frames_used": len(frames),
        "blank_frames_skipped": blank,
        "frames_rejected_by_review": skipped_by_review,
    }


def split_by_time(starts: list[datetime], val_fraction: float) -> tuple[list[int], list[int], Optional[datetime]]:
    """Chronological split shared by all stations (they see the same cloud field).

    Validation = sequences that start in the newest `val_fraction` of the period. Training keeps only
    sequences that end before the first validation frame, so no frame is in both sets.
    """
    if not starts:
        return [], [], None
    order = sorted(set(starts))
    cut = order[min(len(order) - 1, int(len(order) * (1.0 - val_fraction)))]
    span = SEQ_FRAMES * batch.FRAME_INTERVAL
    train = [i for i, s in enumerate(starts) if s + span <= cut]
    val = [i for i, s in enumerate(starts) if s >= cut]
    return train, val, cut


def evaluate(model: "CloudSeq2SeqConvLSTM", x: np.ndarray, y: np.ndarray, cos_out: np.ndarray, device, batch_size: int = 8) -> dict[str, float]:
    """Frame metrics and the metric the system uses: error of the cloud cover in the station's AOI."""
    model = model.to(device).eval()
    preds = []
    with torch.no_grad():
        for i in range(0, len(x), batch_size):
            preds.append(model(torch.from_numpy(x[i : i + batch_size]).to(device)).cpu())
    pred = torch.cat(preds)
    target = torch.from_numpy(y)

    n, t = pred.shape[:2]
    ssim_val = float(ssim(pred.reshape(n * t, 1, IMAGE_SIZE, IMAGE_SIZE), target.reshape(n * t, 1, IMAGE_SIZE, IMAGE_SIZE)))
    errors = []
    for k in range(n):
        got = aoi_cloud_fraction(pred[k].numpy(), cos_zenith=cos_out[k])
        want = aoi_cloud_fraction(y[k], cos_zenith=cos_out[k])
        errors.extend(abs(g - w) for g, w in zip(got, want) if g is not None and w is not None)
    return {
        "mse": float(F.mse_loss(pred, target)),
        "mae": float(F.l1_loss(pred, target)),
        "ssim": ssim_val,
        "aoi_cloud_mae_pct": round(100.0 * float(np.mean(errors)), 2) if errors else float("nan"),
        "aoi_frames": len(errors),
    }


def fine_tune(
    model: "CloudSeq2SeqConvLSTM",
    train: tuple[np.ndarray, np.ndarray],
    val: tuple[np.ndarray, np.ndarray, np.ndarray],
    device,
    epochs: int,
    learning_rate: float,
    batch_size: int,
    seed: int = 42,
) -> tuple[dict, int, list[dict]]:
    """Fine-tune and return (best state dict, best epoch, history). Best = lowest validation MSE."""
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    x_train, y_train = train
    criterion = CompositeNowcastingLoss().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs, eta_min=learning_rate * 0.05)

    best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
    best_mse, best_epoch, history = float("inf"), 0, []
    tf_ratio = 0.3
    for epoch in range(1, epochs + 1):
        model.to(device).train()
        order = rng.permutation(len(x_train))
        total, steps = 0.0, 0
        for i in range(0, len(order), batch_size):
            idx = order[i : i + batch_size]
            xb = torch.from_numpy(x_train[idx]).to(device)
            yb = torch.from_numpy(y_train[idx]).to(device)
            optimizer.zero_grad()
            loss = criterion(model(xb, targets=yb, teacher_forcing_ratio=tf_ratio), yb)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            optimizer.step()
            total, steps = total + float(loss.item()), steps + 1
        lr_used = optimizer.param_groups[0]["lr"]
        scheduler.step()
        tf_ratio *= 0.6

        metrics = evaluate(model, val[0], val[1], val[2], device, batch_size)
        history.append({"epoch": epoch, "train_loss": round(total / max(1, steps), 5), "lr": lr_used, **{k: round(v, 5) for k, v in metrics.items()}})
        logger.info(
            f"[epoch {epoch}/{epochs}] train loss {total / max(1, steps):.4f}  val MSE {metrics['mse']:.5f}  "
            f"SSIM {metrics['ssim']:.4f}  AOI cloud MAE {metrics['aoi_cloud_mae_pct']}%"
        )
        if metrics["mse"] < best_mse:
            best_mse, best_epoch = metrics["mse"], epoch
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
    return best_state, best_epoch, history


# ----------------------------------------------------------------------------- deploy
def _bump_patch(version: str) -> str:
    parts = (version or "1.0.0").split(".")
    try:
        parts[-1] = str(int(parts[-1]) + 1)
    except ValueError:
        parts.append("1")
    return ".".join(parts)


def backup_model(label: str) -> Optional[Path]:
    """Copy the deployed files to model/convlstm/backups/<label>/ and keep the newest KEEP_BACKUPS."""
    if not (MODELS_DIR / ONNX_NAME).exists():
        return None
    dest = MODELS_DIR / "backups" / (re.sub(r"[^0-9A-Za-z]+", "_", label).strip("_") or "unknown")
    dest.mkdir(parents=True, exist_ok=True)
    for name in MODEL_FILES:
        if (MODELS_DIR / name).exists():
            shutil.copy2(MODELS_DIR / name, dest / name)
    backups = sorted((p for p in (MODELS_DIR / "backups").iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime)
    for old in backups[:-KEEP_BACKUPS]:
        shutil.rmtree(old, ignore_errors=True)
    return dest


def deploy(model: "CloudSeq2SeqConvLSTM", summary: dict[str, Any], sample: np.ndarray) -> dict[str, Any]:
    """Replace the deployed ONNX with the fine-tuned model. Raises when the export does not match PyTorch."""
    meta_path = MODELS_DIR / META_NAME
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    old_version = str(meta.get("version", "1.0.0"))

    candidate = MODELS_DIR / (ONNX_NAME + ".candidate")
    export_onnx(model, candidate)
    deviation = onnx_max_deviation(model, candidate, sample)
    if deviation > 1e-4:
        candidate.unlink(missing_ok=True)
        raise RuntimeError(f"exported ONNX differs from PyTorch by {deviation:.2e}")

    backup_dir = backup_model(f"v{old_version}_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}")
    os.replace(candidate, MODELS_DIR / ONNX_NAME)

    new_version = _bump_patch(old_version)
    meta["version"] = new_version
    meta["retrained_at"] = _utc_stamp()
    benchmarks = meta.setdefault("performance_benchmarks", {})
    benchmarks.update(
        {
            "file_size_mb": round((MODELS_DIR / ONNX_NAME).stat().st_size / 1e6, 2),
            "pytorch_onnx_max_deviation": deviation,
            "validation_mse": round(summary["candidate"]["mse"], 5),
            "validation_ssim": round(summary["candidate"]["ssim"], 4),
        }
    )
    meta["retrain"] = {
        "base_version": old_version,
        "data": "real Himawari Band 03 crops from the MinIO cache (daytime, 10-minute steps)",
        "frames_from": summary["frames_from"],
        "frames_to": summary["frames_to"],
        "train_sequences": summary["train_sequences"],
        "val_sequences": summary["val_sequences"],
        "best_epoch": summary["best_epoch"],
        "baseline": summary["baseline"],
        "candidate": summary["candidate"],
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    uploaded = False
    try:
        client = _minio_client()
        if not client.bucket_exists(MINIO_BUCKET):
            client.make_bucket(MINIO_BUCKET)
        for name in MODEL_FILES:
            client.fput_object(MINIO_BUCKET, f"{MINIO_PREFIX}/{name}", str(MODELS_DIR / name))
        uploaded = True
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Could not upload the model to MinIO ({e}); the local file is deployed")

    return {
        "version": new_version,
        "previous_version": old_version,
        "backup_dir": str(backup_dir) if backup_dir else None,
        "onnx_max_deviation": deviation,
        "uploaded_to_minio": uploaded,
    }


def _log_mlflow(summary: dict[str, Any]) -> None:
    try:
        import mlflow

        from service.training.curves import log_history

        mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000"))
        mlflow.set_experiment("solar_convlstm_retrain")
        with mlflow.start_run(run_name=f"convlstm_retrain_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}"):
            mlflow.log_params(
                {k: summary[k] for k in ("train_sequences", "val_sequences", "frames_used", "epochs", "best_epoch", "learning_rate", "device")}
            )
            for side in ("baseline", "candidate"):
                mlflow.log_metrics({f"val_{k}_{side}": v for k, v in summary[side].items() if isinstance(v, float) and v == v})
            mlflow.set_tags({"status": summary["status"], "data": "real_himawari_b03", "version": str(summary.get("version", ""))})
            # learning curve: epoch 0 = the deployed model on the validation data, then one point per epoch
            log_history(mlflow, [{"epoch": 0, **summary["baseline"]}] + list(summary.get("history") or []), skip=("aoi_frames",))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"MLflow logging skipped: {e}")


def _publish_result(redis_client, summary: dict[str, Any]) -> None:
    """Keep a short summary of the run in Redis for the frame review page."""
    keep = ("status", "reason", "version", "previous_version", "sequences", "train_sequences", "val_sequences", "frames_used",
            "blank_frames_skipped", "frames_rejected_by_review", "best_epoch", "baseline", "candidate", "duration_seconds")
    short = {k: summary[k] for k in keep if k in summary}
    short["finished_at"] = _utc_stamp()
    try:
        redis_client.set(batch.LAST_RESULT_KEY, json.dumps(short, default=str))
    except Exception:  # noqa: BLE001
        pass


# ----------------------------------------------------------------------------- entry points
def retrain_status(batch_size: Optional[int] = None) -> dict[str, Any]:
    """New daytime scans since the last retrain attempt (what the trigger looks at)."""
    import redis

    batch_size = batch_size or _env_int("CONVLSTM_RETRAIN_THRESHOLD", 50)
    r = redis.Redis(host=os.environ.get("REDIS_HOST", "localhost"), port=_env_int("REDIS_PORT", 6379))
    since = batch.parse_time(r.get(batch.LAST_FRAME_KEY))
    return batch.batch_status(batch.list_cached_scans(_minio_client()), station_coordinates(), since, batch_size)


def backfill_frames(days: int) -> dict[str, int]:
    """Download the real frames of the last `days` days that are missing in the cache (daytime only).

    Nothing is generated: a scan that NICT does not publish stays missing.
    """
    from service.workers.satellite_preprocessor import _FrameSource, floor_10min

    client = _minio_client()
    coords = station_coordinates()
    have = batch.list_cached_scans(client)
    end = floor_10min(datetime.now(timezone.utc)) - timedelta(minutes=30)
    sources = {sid: _FrameSource(sid, lat, lon, client) for sid, (lat, lon) in coords.items()}
    added = {sid: 0 for sid in coords}
    ts = end - timedelta(days=days)
    while ts <= end:
        for sid, (lat, lon) in coords.items():
            if ts in set(have.get(sid, ())) or not batch.is_daytime(ts, lat, lon):
                continue
            sources[sid].network_errors = 0  # one failed scan must not stop the whole backfill
            if sources[sid].get(ts) is not None:
                added[sid] += 1
        ts += batch.FRAME_INTERVAL
    return added


def execute_convlstm_retrain(payload: dict[str, Any], force: bool = False) -> dict[str, Any]:
    """Fine-tune the ConvLSTM on the real frames in the cache and deploy it when it is not worse.

    Returns a summary with status: skipped | insufficient_data | rejected | deployed | failed.
    """
    logger.info(f">> [ConvLSTM retrain] payload: {payload}")
    if not _TORCH_AVAILABLE:
        return {"status": "skipped", "reason": "torch_not_installed"}
    if not force and not _env_bool("ENABLE_RETRAIN", False):
        logger.info("[STANDBY] ENABLE_RETRAIN=false: retrain skipped")
        return {"status": "skipped", "reason": "retrain_disabled", "message": "Set ENABLE_RETRAIN=true to activate"}

    import redis

    r = redis.Redis(host=os.environ.get("REDIS_HOST", "localhost"), port=_env_int("REDIS_PORT", 6379))
    try:
        if not r.set(batch.RUNNING_KEY, "1", nx=True, ex=3 * 3600):
            return {"status": "skipped", "reason": "already_running"}
    except Exception as e:  # noqa: BLE001
        return {"status": "failed", "error": f"redis unavailable: {e}"}

    started = time.time()
    newest_scan: Optional[datetime] = None
    try:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        client = _minio_client()
        coords = station_coordinates()
        data = build_dataset(
            client, coords,
            stride=_env_int("CONVLSTM_SEQUENCE_STRIDE", 2),
            lookback_days=_env_int("CONVLSTM_LOOKBACK_DAYS", 5),
        )
        newest_scan = data["newest_scan"]

        train_idx, val_idx, cut = split_by_time(data["starts"], _env_float("CONVLSTM_VAL_FRACTION", 0.2))
        min_train, min_val = _env_int("CONVLSTM_MIN_TRAIN_SEQUENCES", 20), _env_int("CONVLSTM_MIN_VAL_SEQUENCES", 5)
        counts = {"sequences": len(data["starts"]), "train_sequences": len(train_idx), "val_sequences": len(val_idx), "frames_used": data["frames_used"], "blank_frames_skipped": data["blank_frames_skipped"], "frames_rejected_by_review": data["frames_rejected_by_review"]}
        if len(train_idx) < min_train or len(val_idx) < min_val:
            logger.info(f"Not enough real sequences yet: {counts} (need {min_train} train / {min_val} val)")
            result = {"status": "insufficient_data", **counts, "min_train": min_train, "min_val": min_val}
            _publish_result(r, result)
            return result

        # keep the run bounded as the cache grows: fine-tune on the newest sequences
        train_idx = train_idx[-_env_int("CONVLSTM_MAX_TRAIN_SEQUENCES", 300):]
        counts["train_sequences"] = len(train_idx)
        logger.info(f"Real sequences: {counts}; validation from {cut:%Y-%m-%d %H:%M} UTC; device {device}")

        x_train, y_train = data["x"][train_idx], data["y"][train_idx]
        x_val, y_val, cos_val = data["x"][val_idx], data["y"][val_idx], data["cos_out"][val_idx]

        onnx_path = MODELS_DIR / ONNX_NAME
        model = CloudSeq2SeqConvLSTM()
        load_onnx_weights(model, onnx_path)
        load_deviation = onnx_max_deviation(model, onnx_path, x_val[:2])
        if load_deviation > 1e-4:
            raise RuntimeError(f"PyTorch model does not reproduce the deployed ONNX (max deviation {load_deviation:.2e})")

        baseline = evaluate(model, x_val, y_val, cos_val, device)
        logger.info(
            f"Deployed model on the held-out sequences: MSE {baseline['mse']:.5f}  SSIM {baseline['ssim']:.4f}  "
            f"AOI cloud MAE {baseline['aoi_cloud_mae_pct']}% ({baseline['aoi_frames']} frames)"
        )
        epochs = _env_int("CONVLSTM_RETRAIN_EPOCHS", 6)
        learning_rate = _env_float("CONVLSTM_RETRAIN_LR", 1e-4)
        best_state, best_epoch, history = fine_tune(
            model, (x_train, y_train), (x_val, y_val, cos_val), device,
            epochs=epochs, learning_rate=learning_rate, batch_size=_env_int("CONVLSTM_RETRAIN_BATCH_SIZE", 8),
        )
        model.load_state_dict(best_state)
        candidate = evaluate(model, x_val, y_val, cos_val, device)

        summary: dict[str, Any] = {
            **counts,
            "frames_from": min(data["starts"]).isoformat(),
            "frames_to": (max(data["starts"]) + (SEQ_FRAMES - 1) * batch.FRAME_INTERVAL).isoformat(),
            "val_from": cut.isoformat() if cut else None,
            "epochs": epochs,
            "best_epoch": best_epoch,
            "learning_rate": learning_rate,
            "device": str(device),
            "baseline": baseline,
            "candidate": candidate,
            "history": history,
            "accumulated_count": payload.get("new_scans"),
            "threshold": payload.get("batch_size"),
        }

        ratio = _env_float("CONVLSTM_MAX_REGRESSION_RATIO", 1.0)
        if best_epoch == 0 or candidate["mse"] > baseline["mse"] * ratio:
            summary["status"] = "rejected"
            summary["reason"] = f"validation MSE {candidate['mse']:.5f} is not better than the deployed model's {baseline['mse']:.5f}"
            logger.info(f">> ConvLSTM retrain rejected: {summary['reason']}")
        else:
            summary.update(deploy(model, summary, x_val[:2]))
            summary["status"] = "deployed"
            logger.info(f">> ConvLSTM v{summary['version']} deployed: val MSE {baseline['mse']:.5f} -> {candidate['mse']:.5f}")
        summary["duration_seconds"] = round(time.time() - started, 1)
        _log_mlflow(summary)
        _publish_result(r, summary)
        return summary
    except Exception as e:  # noqa: BLE001
        logger.exception("ConvLSTM retrain failed")
        newest_scan = None  # a failed run does not consume the batch
        return {"status": "failed", "error": str(e)}
    finally:
        try:
            if newest_scan is not None:
                r.set(batch.LAST_FRAME_KEY, newest_scan.isoformat())
            r.delete(batch.RUNNING_KEY, batch.SCHEDULED_KEY)
        except Exception:  # noqa: BLE001
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="ConvLSTM retraining on real satellite frames")
    parser.add_argument("--status", action="store_true", help="show the batch counter")
    parser.add_argument("--backfill-days", type=int, help="download missing real daytime frames of the last N days")
    parser.add_argument("--run", action="store_true", help="run a retrain now")
    parser.add_argument("--force", action="store_true", help="with --run: ignore ENABLE_RETRAIN")
    args = parser.parse_args()

    if args.backfill_days:
        print(json.dumps({"backfilled": backfill_frames(args.backfill_days)}, indent=2))
    if args.status:
        print(json.dumps(retrain_status(), indent=2))
    if args.run:
        result = execute_convlstm_retrain({"reason": "manual"}, force=args.force)
        result.pop("history", None)
        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
