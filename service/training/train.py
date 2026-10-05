"""Solar LSTM Model Training, ONNX Export & MLflow Tracking Pipeline

1. Streams 10-minute NSRDB splits (2016-2020) directly from MinIO (bucket: 'datasets').
2. Trains a 2-layer LSTM on GPU (RTX 3050 Ti) with Early Stopping.
3. Evaluates on 2020 unseen test data (18-step horizon = 3 hours ahead), overall and daylight-only.
4. Exports directly to self-contained ONNX format (embedded weights, no external .data file).
5. Verifies ONNX inference using ONNX Runtime.
6. Logs metrics and ONNX model artifacts to Docker MLflow (http://localhost:5000).
7. Writes the artifacts to an output directory. They replace the deployed model (MinIO
   'models/solar_lstm/' + project 'model/time-series/') only with --deploy / --deploy-from.

Usage (from the project root, in the environment with CUDA PyTorch):
    python -m service.training.train --lookback 144 --deploy          # train and deploy, as before
    python -m service.training.train --ablation 36 48 72 144          # lookback experiment, nothing deployed
    python -m service.training.train --deploy-from artifacts/lookback_ablation/lb72
"""

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, Optional, Sequence

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    pass

import mlflow
import numpy as np
import onnx
import onnxruntime as ort
import torch
import torch.nn as nn
from minio import Minio
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from torch.utils.data import DataLoader

# Add project root to sys.path so 'service' package can be resolved
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from service.models.solar_lstm import SolarLSTMForecaster
from service.training.dataset import (
    ALIGNED_FEATURE_COLS,
    FORECAST_STEPS,
    LOOKBACK_STEPS,
    SolarTimeWindowDataset,
    load_and_scale_splits,
)

# MinIO & MLflow Configuration
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "admin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "password")
MLFLOW_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")

# Training Hyperparameters
BATCH_SIZE = 128
LEARNING_RATE = 1e-3
WEIGHT_DECAY = 1e-4
MAX_EPOCHS = 12
EARLY_STOPPING_PATIENCE = 3
HIDDEN_DIM = 128
NUM_LAYERS = 2
DROPOUT = 0.2

MODEL_FILES = ["solar_ghi_lstm.onnx", "feature_scaler.joblib", "target_scaler.joblib", "model_meta.json"]
PROJECT_MODEL_DIR = BASE_DIR / "model" / "time-series"
ABLATION_DIR = BASE_DIR / "artifacts" / "lookback_ablation"
REPORT_STEPS = [0, 2, 5, 11, 17]  # +10m, +30m, +60m, +120m, +180m
DAYLIGHT_CLEARSKY_GHI = 10.0     # W/m2: a target step counts as daytime when clear-sky GHI exceeds this
CLEARSKY_FEATURE = ALIGNED_FEATURE_COLS.index("Clearsky GHI")


def calculate_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    """Calculate MAE, RMSE, R2, and daylight nRMSE."""
    mae = mean_absolute_error(y_true, y_pred)
    mse = mean_squared_error(y_true, y_pred)
    rmse = np.sqrt(mse)
    r2 = r2_score(y_true.flatten(), y_pred.flatten())

    # Daylight normalized RMSE (mean of daylight GHI > 10 W/m2)
    daylight_mask = y_true > 10.0
    if daylight_mask.sum() > 0:
        daylight_mean = y_true[daylight_mask].mean()
        nrmse = (rmse / daylight_mean) * 100.0
    else:
        nrmse = 0.0

    return {
        "mae": round(float(mae), 3),
        "rmse": round(float(rmse), 3),
        "r2": round(float(r2), 4),
        "nrmse_pct": round(float(nrmse), 2),
    }


def daylight_target_mask(features_scaled: np.ndarray, feature_scaler, lookback: int, n_windows: int) -> np.ndarray:
    """(n_windows, FORECAST_STEPS) mask: True where the target step is in daytime (clear-sky GHI > 10 W/m2)."""
    clearsky = feature_scaler.inverse_transform(features_scaled)[:, CLEARSKY_FEATURE]
    windows = np.lib.stride_tricks.sliding_window_view(clearsky[lookback:], FORECAST_STEPS)[:n_windows]
    return windows > DAYLIGHT_CLEARSKY_GHI


def daylight_metrics(y_true: np.ndarray, y_pred: np.ndarray, mask: np.ndarray) -> Dict[str, float]:
    """MAE / RMSE on daytime target steps only: overall and at the reported lead times."""
    out = {
        "test_day_mae": round(float(np.abs(y_true - y_pred)[mask].mean()), 3),
        "test_day_rmse": round(float(np.sqrt(((y_true - y_pred) ** 2)[mask].mean())), 3),
        "test_day_share_pct": round(float(mask.mean() * 100.0), 2),
    }
    for s_idx in REPORT_STEPS:
        m = mask[:, s_idx]
        err = (y_true[:, s_idx] - y_pred[:, s_idx])[m]
        mins = (s_idx + 1) * 10
        out[f"test_day_mae_plus_{mins}min"] = round(float(np.abs(err).mean()), 2)
        out[f"test_day_rmse_plus_{mins}min"] = round(float(np.sqrt((err**2).mean())), 2)
    return out


def _minio() -> Minio:
    return Minio(MINIO_ENDPOINT, access_key=MINIO_ACCESS_KEY, secret_key=MINIO_SECRET_KEY, secure=False)


def train_solar_model(
    lookback_steps: int = LOOKBACK_STEPS,
    out_dir: Optional[Path] = None,
    experiment: str = "solar_ghi_lstm_forecasting",
    seed: int = 42,
    version: str = "1.0.0",
) -> Dict:
    """Train one LSTM with the given lookback and write its artifacts to out_dir. Returns the metadata."""
    print("=" * 70)
    print(f">> STARTING SOLAR GHI LSTM TRAINING PIPELINE (lookback {lookback_steps} steps = {lookback_steps / 6:g} h)")
    print("=" * 70)

    torch.manual_seed(seed)
    np.random.seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[Device] Using: {device} ({torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'})")

    minio_client = _minio()
    for b in ("datasets", "models", "mlflow"):
        if not minio_client.bucket_exists(b):
            minio_client.make_bucket(b)
            print(f"[MinIO] Created bucket '{b}'")

    out_dir = Path(out_dir) if out_dir else ABLATION_DIR / f"lb{lookback_steps}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("\n[1/5] Streaming and scaling dataset directly from MinIO (bucket: 'datasets')...")
    (X_train, y_train), (X_val, y_val), (X_test, y_test), feature_scaler, target_scaler = load_and_scale_splits(
        data_dir=None,
        save_scalers_dir=out_dir,
        minio_client=minio_client,
    )

    train_ds = SolarTimeWindowDataset(X_train, y_train, lookback_steps, FORECAST_STEPS)
    val_ds = SolarTimeWindowDataset(X_val, y_val, lookback_steps, FORECAST_STEPS)
    test_ds = SolarTimeWindowDataset(X_test, y_test, lookback_steps, FORECAST_STEPS)
    print(f"  - Train windows: {len(train_ds):,} (2016-2018)")
    print(f"  - Val windows:   {len(val_ds):,} (2019)")
    print(f"  - Test windows:  {len(test_ds):,} (2020)")

    generator = torch.Generator().manual_seed(seed)
    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, pin_memory=torch.cuda.is_available(), generator=generator)
    val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE * 2, shuffle=False)
    test_loader = DataLoader(test_ds, batch_size=BATCH_SIZE * 2, shuffle=False)

    model = SolarLSTMForecaster(
        input_dim=len(ALIGNED_FEATURE_COLS),
        hidden_dim=HIDDEN_DIM,
        num_layers=NUM_LAYERS,
        forecast_steps=FORECAST_STEPS,
        dropout=DROPOUT,
    ).to(device)

    criterion = nn.HuberLoss(delta=1.0)
    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE, weight_decay=WEIGHT_DECAY)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="min", factor=0.5, patience=1)

    os.environ["AWS_ACCESS_KEY_ID"] = MINIO_ACCESS_KEY
    os.environ["AWS_SECRET_ACCESS_KEY"] = MINIO_SECRET_KEY
    os.environ["MLFLOW_S3_ENDPOINT_URL"] = f"http://{MINIO_ENDPOINT}"
    mlflow.set_tracking_uri(MLFLOW_URI)
    mlflow.set_experiment(experiment)

    print("\n[2/5] Training LSTM Model...")
    best_val_loss = float("inf")
    best_checkpoint_path = out_dir / "best_solar_lstm.pt"
    epochs_no_improve = 0
    train_started = time.time()

    with mlflow.start_run(run_name=f"lstm_lb{lookback_steps}_{time.strftime('%Y%m%d_%H%M%S')}"):
        mlflow.log_params({
            "model_type": "LSTM",
            "format": "ONNX",
            "input_dim": len(ALIGNED_FEATURE_COLS),
            "hidden_dim": HIDDEN_DIM,
            "num_layers": NUM_LAYERS,
            "dropout": DROPOUT,
            "lookback_steps": lookback_steps,
            "lookback_hours": lookback_steps / 6.0,
            "forecast_steps": FORECAST_STEPS,
            "forecast_horizon_hours": 3.0,
            "resolution_mins": 10,
            "batch_size": BATCH_SIZE,
            "learning_rate": LEARNING_RATE,
            "loss_function": "HuberLoss",
            "seed": seed,
            "features": ALIGNED_FEATURE_COLS,
        })

        for epoch in range(1, MAX_EPOCHS + 1):
            epoch_start = time.time()

            model.train()
            train_loss = 0.0
            for batch_x, batch_y in train_loader:
                batch_x, batch_y = batch_x.to(device), batch_y.to(device)
                optimizer.zero_grad()
                preds = model(batch_x)
                loss = criterion(preds, batch_y)
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
                optimizer.step()
                train_loss += loss.item() * len(batch_y)
            train_loss /= len(train_ds)

            model.eval()
            val_loss = 0.0
            val_preds_list, val_true_list = [], []
            with torch.no_grad():
                for batch_x, batch_y in val_loader:
                    batch_x, batch_y = batch_x.to(device), batch_y.to(device)
                    preds = model(batch_x)
                    val_loss += criterion(preds, batch_y).item() * len(batch_y)
                    val_preds_list.append(preds.cpu().numpy())
                    val_true_list.append(batch_y.cpu().numpy())
            val_loss /= len(val_ds)
            scheduler.step(val_loss)

            # Invert validation predictions back to physical W/m^2
            val_preds_arr = np.concatenate(val_preds_list, axis=0)
            val_true_arr = np.concatenate(val_true_list, axis=0)
            val_preds_watts = target_scaler.inverse_transform(val_preds_arr.reshape(-1, 1)).reshape(val_preds_arr.shape)
            val_true_watts = target_scaler.inverse_transform(val_true_arr.reshape(-1, 1)).reshape(val_true_arr.shape)
            val_metrics = calculate_metrics(val_true_watts, val_preds_watts)

            print(
                f"Epoch [{epoch:02d}/{MAX_EPOCHS:02d}] ({time.time() - epoch_start:.1f}s) | "
                f"Train Loss: {train_loss:.5f} | Val Loss: {val_loss:.5f} | "
                f"Val RMSE: {val_metrics['rmse']:.2f} W/m2 | Val MAE: {val_metrics['mae']:.2f} W/m2 | "
                f"Val R2: {val_metrics['r2']:.4f}"
            )
            mlflow.log_metrics({
                "train_loss": train_loss,
                "val_loss": val_loss,
                "val_rmse": val_metrics["rmse"],
                "val_mae": val_metrics["mae"],
                "val_r2": val_metrics["r2"],
                "val_nrmse_pct": val_metrics["nrmse_pct"],
                "lr": optimizer.param_groups[0]["lr"],
            }, step=epoch)

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                epochs_no_improve = 0
                torch.save({
                    "epoch": epoch,
                    "model_state_dict": model.state_dict(),
                    "val_loss": val_loss,
                    "val_metrics": val_metrics,
                }, best_checkpoint_path)
                print(f"  --> Saved new best checkpoint (Val Loss: {val_loss:.5f})")
            else:
                epochs_no_improve += 1
                if epochs_no_improve >= EARLY_STOPPING_PATIENCE:
                    print(f"\n[Early Stopping] No improvement for {EARLY_STOPPING_PATIENCE} epochs. Stopping.")
                    break

        train_minutes = (time.time() - train_started) / 60.0

        print("\n[3/5] Evaluating Best Model on 2020 Test Set...")
        checkpoint = torch.load(best_checkpoint_path, map_location=device)
        model.load_state_dict(checkpoint["model_state_dict"])
        model.eval()

        test_preds_list, test_true_list = [], []
        with torch.no_grad():
            for batch_x, batch_y in test_loader:
                preds = model(batch_x.to(device))
                test_preds_list.append(preds.cpu().numpy())
                test_true_list.append(batch_y.numpy())
        test_preds_arr = np.concatenate(test_preds_list, axis=0)
        test_true_arr = np.concatenate(test_true_list, axis=0)
        test_preds_watts = target_scaler.inverse_transform(test_preds_arr.reshape(-1, 1)).reshape(test_preds_arr.shape)
        test_true_watts = target_scaler.inverse_transform(test_true_arr.reshape(-1, 1)).reshape(test_true_arr.shape)

        test_metrics = calculate_metrics(test_true_watts, test_preds_watts)
        step_metrics = {}
        for s_idx in REPORT_STEPS:
            m_mins = (s_idx + 1) * 10
            s_rmse = float(np.sqrt(mean_squared_error(test_true_watts[:, s_idx], test_preds_watts[:, s_idx])))
            s_mae = float(mean_absolute_error(test_true_watts[:, s_idx], test_preds_watts[:, s_idx]))
            step_metrics[f"test_rmse_plus_{m_mins}min"] = round(s_rmse, 2)
            step_metrics[f"test_mae_plus_{m_mins}min"] = round(s_mae, 2)

        day_mask = daylight_target_mask(X_test, feature_scaler, lookback_steps, len(test_true_watts))
        day_metrics = daylight_metrics(test_true_watts, test_preds_watts, day_mask)

        print("\n" + "=" * 70)
        print(f">> 2020 UNSEEN TEST SET, lookback {lookback_steps}:")
        print(f"All hours:      RMSE {test_metrics['rmse']:.2f}  MAE {test_metrics['mae']:.2f}  R2 {test_metrics['r2']:.4f}")
        print(f"Daylight only:  RMSE {day_metrics['test_day_rmse']:.2f}  MAE {day_metrics['test_day_mae']:.2f}"
              f"  ({day_metrics['test_day_share_pct']:.1f}% of target steps)")
        for s_idx in REPORT_STEPS:
            mins = (s_idx + 1) * 10
            print(f"  +{mins:>3} min  day RMSE {day_metrics[f'test_day_rmse_plus_{mins}min']:>7.2f}"
                  f"  day MAE {day_metrics[f'test_day_mae_plus_{mins}min']:>7.2f}")
        print("=" * 70)

        mlflow.log_metrics({
            "test_overall_rmse": test_metrics["rmse"],
            "test_overall_mae": test_metrics["mae"],
            "test_overall_r2": test_metrics["r2"],
            "test_daylight_nrmse_pct": test_metrics["nrmse_pct"],
            "train_minutes": round(train_minutes, 2),
            "best_epoch": checkpoint["epoch"],
            **step_metrics,
            **day_metrics,
        })

        print("\n[4/5] Exporting Model to Self-Contained ONNX Format (.onnx)...")
        export_model = SolarLSTMForecaster(
            input_dim=len(ALIGNED_FEATURE_COLS),
            hidden_dim=HIDDEN_DIM,
            num_layers=NUM_LAYERS,
            forecast_steps=FORECAST_STEPS,
            dropout=0.0,
        ).to(torch.device("cpu"))
        export_model.load_state_dict(checkpoint["model_state_dict"])
        export_model.eval()

        onnx_path = out_dir / "solar_ghi_lstm.onnx"
        dummy_input = torch.randn(1, lookback_steps, len(ALIGNED_FEATURE_COLS), dtype=torch.float32)
        # dynamo=False guarantees the entire model and all weights are embedded in a single .onnx file
        torch.onnx.export(
            export_model,
            dummy_input,
            str(onnx_path),
            export_params=True,
            dynamo=False,
            input_names=["weather_sequence"],
            output_names=["ghi_forecast_18steps"],
            dynamic_axes={
                "weather_sequence": {0: "batch_size"},
                "ghi_forecast_18steps": {0: "batch_size"},
            },
        )
        onnx.checker.check_model(onnx.load(str(onnx_path)))
        with torch.no_grad():
            torch_out = export_model(dummy_input).numpy()
        ort_out = ort.InferenceSession(str(onnx_path)).run(None, {"weather_sequence": dummy_input.numpy()})[0]
        max_diff = float(np.abs(torch_out - ort_out).max())
        print(f"  [ONNX] {onnx_path.stat().st_size / 1024:.1f} KB, ONNX Runtime matches PyTorch within {max_diff:.2e}")

        meta = {
            "model_name": "solar_ghi_lstm",
            "format": "ONNX",
            "file_name": "solar_ghi_lstm.onnx",
            "size_bytes": onnx_path.stat().st_size,
            "version": version,
            "trained_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "input_features": ALIGNED_FEATURE_COLS,
            "lookback_steps": lookback_steps,
            "forecast_steps": FORECAST_STEPS,
            "resolution_minutes": 10,
            "test_metrics": test_metrics,
            "step_metrics": step_metrics,
            "daylight_metrics": day_metrics,
            "best_epoch": checkpoint["epoch"],
            "train_minutes": round(train_minutes, 2),
            "seed": seed,
            "device_trained": str(device),
        }
        with open(out_dir / "model_meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        print("\n[5/5] Logging artifacts to MLflow...")
        mlflow.log_artifact(str(onnx_path), artifact_path="model")
        for name in ("feature_scaler.joblib", "target_scaler.joblib", "model_meta.json"):
            mlflow.log_artifact(str(out_dir / name))
        print(f"  [MLflow] Logged to {MLFLOW_URI}; artifacts in '{out_dir}'")

    return meta


def deploy(artifacts_dir: Path, version: Optional[str] = None) -> None:
    """Make the artifacts in artifacts_dir the deployed model: MinIO 'models/solar_lstm/' and 'model/time-series/'."""
    artifacts_dir = Path(artifacts_dir)
    missing = [n for n in MODEL_FILES if not (artifacts_dir / n).exists()]
    if missing:
        raise FileNotFoundError(f"{artifacts_dir} is missing {missing}")

    if version:
        meta_path = artifacts_dir / "model_meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["version"] = version
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    client = _minio()
    # model_meta.json last: workers compare its trained_at to decide whether to pull the other files
    for name in sorted(MODEL_FILES, key=lambda n: n == "model_meta.json"):
        client.fput_object("models", f"solar_lstm/{name}", str(artifacts_dir / name))
    print("  [MinIO] Uploaded model + scalers to bucket 'models/solar_lstm/'")

    PROJECT_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for name in MODEL_FILES:
        shutil.copy2(artifacts_dir / name, PROJECT_MODEL_DIR / name)
    print(f"  [Project] Deployed to '{PROJECT_MODEL_DIR}'")


def run_ablation(lookbacks: Sequence[int], tolerance: float = 0.02) -> Dict:
    """Train one model per lookback with everything else fixed and pick the shortest one whose
    daylight RMSE is within `tolerance` of the best. Nothing is deployed."""
    results = []
    for lb in lookbacks:
        meta = train_solar_model(lookback_steps=lb, out_dir=ABLATION_DIR / f"lb{lb}", experiment="solar_ghi_lstm_lookback_ablation")
        results.append({
            "lookback_steps": lb,
            "lookback_hours": lb / 6.0,
            "best_epoch": meta["best_epoch"],
            "train_minutes": meta["train_minutes"],
            **{k: meta["test_metrics"][k] for k in ("mae", "rmse", "r2")},
            **meta["daylight_metrics"],
        })
        with open(ABLATION_DIR / "results.json", "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

    best = min(r["test_day_rmse"] for r in results)
    chosen = min((r for r in results if r["test_day_rmse"] <= best * (1.0 + tolerance)), key=lambda r: r["lookback_steps"])
    summary = {"tolerance": tolerance, "best_day_rmse": best, "chosen_lookback_steps": chosen["lookback_steps"], "results": results}
    with open(ABLATION_DIR / "results.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 70)
    print(">> LOOKBACK ABLATION (2020 test set, daylight target steps only)")
    print("lookback  hours | day RMSE  day MAE | +10m   +60m  +180m (day RMSE) | all-hours RMSE | epochs  minutes")
    for r in results:
        mark = "  <-- chosen" if r is chosen else ""
        print(f"{r['lookback_steps']:>8} {r['lookback_hours']:>6g} | {r['test_day_rmse']:>8.2f} {r['test_day_mae']:>8.2f} |"
              f" {r['test_day_rmse_plus_10min']:>6.2f} {r['test_day_rmse_plus_60min']:>6.2f} {r['test_day_rmse_plus_180min']:>6.2f}"
              f"            | {r['rmse']:>14.2f} | {r['best_epoch']:>6} {r['train_minutes']:>8.1f}{mark}")
    print(f"Chosen: shortest lookback within {tolerance:.0%} of the best daylight RMSE ({best:.2f}) = {chosen['lookback_steps']} steps")
    print(f"Deploy it with: python -m service.training.train --deploy-from {ABLATION_DIR / ('lb' + str(chosen['lookback_steps']))}")
    print("=" * 70)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Train / compare / deploy the solar GHI LSTM")
    parser.add_argument("--lookback", type=int, default=LOOKBACK_STEPS, help="input length in 10-minute steps")
    parser.add_argument("--ablation", type=int, nargs="+", metavar="STEPS", help="train one model per lookback and compare")
    parser.add_argument("--deploy", action="store_true", help="deploy the model trained by this run")
    parser.add_argument("--deploy-from", type=Path, help="deploy existing artifacts without training")
    parser.add_argument("--out", type=Path, help="output directory of a single run")
    parser.add_argument("--version", help="version string written to model_meta.json (default 1.0.0 when training)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if args.deploy_from:
        deploy(args.deploy_from, version=args.version)
    elif args.ablation:
        run_ablation(args.ablation)
    else:
        out = args.out or ABLATION_DIR / f"lb{args.lookback}"
        train_solar_model(lookback_steps=args.lookback, out_dir=out, seed=args.seed, version=args.version or "1.0.0")
        if args.deploy:
            deploy(out)


if __name__ == "__main__":
    main()
