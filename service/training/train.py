"""Solar LSTM Model Training, ONNX Export & MLflow Tracking Pipeline

1. Streams 10-minute NSRDB splits (2016-2020) directly from MinIO (bucket: 'datasets').
2. Trains a 2-layer LSTM on GPU (RTX 3050 Ti) with Early Stopping.
3. Evaluates on 2020 unseen test data (18-step horizon = 3 hours ahead).
4. Exports directly to self-contained ONNX format (embedded weights, ~872 KB, no external .data file).
5. Verifies ONNX inference using ONNX Runtime.
6. Logs metrics and ONNX model artifacts to Docker MLflow (http://localhost:5000).
7. Uploads ONNX model & scalers to MinIO (bucket: 'models/solar_lstm/').
8. Leaves ZERO files in the local repository workspace.
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, Tuple

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    pass

import joblib
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


def train_solar_model():
    print("=" * 70)
    print(">> STARTING SOLAR GHI LSTM TRAINING PIPELINE (MINIO & ONNX)")
    print("=" * 70)

    # 1. Device Selection (RTX 3050 Ti GPU if available)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[Device] Using: {device} ({torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'})")

    # 2. MinIO Client Connection
    minio_client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False,
    )

    # Ensure required buckets exist
    for b in ("datasets", "models", "mlflow"):
        if not minio_client.bucket_exists(b):
            minio_client.make_bucket(b)
            print(f"[MinIO] Created bucket '{b}'")

    # Use a secure isolated temporary directory for staging artifacts during training
    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)

        # 3. Load and Scale Dataset Splits directly from MinIO
        print("\n[1/5] Streaming and scaling dataset directly from MinIO (bucket: 'datasets')...")
        (X_train, y_train), (X_val, y_val), (X_test, y_test), feature_scaler, target_scaler = load_and_scale_splits(
            data_dir=None,
            save_scalers_dir=temp_dir,
            minio_client=minio_client,
        )

        train_ds = SolarTimeWindowDataset(X_train, y_train, LOOKBACK_STEPS, FORECAST_STEPS)
        val_ds = SolarTimeWindowDataset(X_val, y_val, LOOKBACK_STEPS, FORECAST_STEPS)
        test_ds = SolarTimeWindowDataset(X_test, y_test, LOOKBACK_STEPS, FORECAST_STEPS)

        print(f"  - Train windows: {len(train_ds):,} (2016-2018)")
        print(f"  - Val windows:   {len(val_ds):,} (2019)")
        print(f"  - Test windows:  {len(test_ds):,} (2020)")

        train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, pin_memory=torch.cuda.is_available())
        val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE * 2, shuffle=False)
        test_loader = DataLoader(test_ds, batch_size=BATCH_SIZE * 2, shuffle=False)

        # 4. Model Architecture
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

        # 5. Setup MLflow Tracking with S3 MinIO backend
        os.environ["AWS_ACCESS_KEY_ID"] = MINIO_ACCESS_KEY
        os.environ["AWS_SECRET_ACCESS_KEY"] = MINIO_SECRET_KEY
        os.environ["MLFLOW_S3_ENDPOINT_URL"] = f"http://{MINIO_ENDPOINT}"

        mlflow.set_tracking_uri(MLFLOW_URI)
        mlflow.set_experiment("solar_ghi_lstm_forecasting")

        # 6. Training Loop
        print("\n[2/5] Training LSTM Model on GPU...")
        best_val_loss = float("inf")
        best_checkpoint_path = temp_dir / "best_solar_lstm.pt"
        epochs_no_improve = 0

        with mlflow.start_run(run_name=f"onnx_solar_lstm_{time.strftime('%Y%m%d_%H%M%S')}"):
            mlflow.log_params({
                "model_type": "LSTM",
                "format": "ONNX",
                "input_dim": len(ALIGNED_FEATURE_COLS),
                "hidden_dim": HIDDEN_DIM,
                "num_layers": NUM_LAYERS,
                "dropout": DROPOUT,
                "lookback_steps": LOOKBACK_STEPS,
                "forecast_steps": FORECAST_STEPS,
                "forecast_horizon_hours": 3.0,
                "resolution_mins": 10,
                "batch_size": BATCH_SIZE,
                "learning_rate": LEARNING_RATE,
                "loss_function": "HuberLoss",
                "features": ALIGNED_FEATURE_COLS,
            })

            for epoch in range(1, MAX_EPOCHS + 1):
                epoch_start = time.time()

                # Train Phase
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

                # Validation Phase
                model.eval()
                val_loss = 0.0
                val_preds_list = []
                val_true_list = []

                with torch.no_grad():
                    for batch_x, batch_y in val_loader:
                        batch_x, batch_y = batch_x.to(device), batch_y.to(device)
                        preds = model(batch_x)
                        loss = criterion(preds, batch_y)
                        val_loss += loss.item() * len(batch_y)
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
                epoch_time = time.time() - epoch_start

                print(
                    f"Epoch [{epoch:02d}/{MAX_EPOCHS:02d}] ({epoch_time:.1f}s) | "
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

                # Checkpoint Best Model
                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                    epochs_no_improve = 0
                    torch.save({
                        "epoch": epoch,
                        "model_state_dict": model.state_dict(),
                        "optimizer_state_dict": optimizer.state_dict(),
                        "val_loss": val_loss,
                        "val_metrics": val_metrics,
                    }, best_checkpoint_path)
                    print(f"  --> Saved new best checkpoint (Val Loss: {val_loss:.5f})")
                else:
                    epochs_no_improve += 1
                    if epochs_no_improve >= EARLY_STOPPING_PATIENCE:
                        print(f"\n[Early Stopping] No improvement for {EARLY_STOPPING_PATIENCE} epochs. Stopping.")
                        break

            # 7. Evaluate Best Model on 2020 Test Set
            print("\n[3/5] Evaluating Best Model on 2020 Test Set...")
            checkpoint = torch.load(best_checkpoint_path, map_location=device)
            model.load_state_dict(checkpoint["model_state_dict"])
            model.eval()

            test_preds_list = []
            test_true_list = []

            with torch.no_grad():
                for batch_x, batch_y in test_loader:
                    batch_x, batch_y = batch_x.to(device), batch_y.to(device)
                    preds = model(batch_x)
                    test_preds_list.append(preds.cpu().numpy())
                    test_true_list.append(batch_y.cpu().numpy())

            test_preds_arr = np.concatenate(test_preds_list, axis=0)
            test_true_arr = np.concatenate(test_true_list, axis=0)

            test_preds_watts = target_scaler.inverse_transform(test_preds_arr.reshape(-1, 1)).reshape(test_preds_arr.shape)
            test_true_watts = target_scaler.inverse_transform(test_true_arr.reshape(-1, 1)).reshape(test_true_arr.shape)

            test_metrics = calculate_metrics(test_true_watts, test_preds_watts)

            step_metrics = {}
            target_steps = [0, 2, 5, 11, 17]  # +10m, +30m, +60m, +120m, +180m
            for s_idx in target_steps:
                m_mins = (s_idx + 1) * 10
                s_rmse = float(np.sqrt(mean_squared_error(test_true_watts[:, s_idx], test_preds_watts[:, s_idx])))
                s_mae = float(mean_absolute_error(test_true_watts[:, s_idx], test_preds_watts[:, s_idx]))
                step_metrics[f"test_rmse_plus_{m_mins}min"] = round(s_rmse, 2)
                step_metrics[f"test_mae_plus_{m_mins}min"] = round(s_mae, 2)

            print("\n" + "=" * 70)
            print(">> 2020 UNSEEN TEST SET EVALUATION RESULTS:")
            print("=" * 70)
            print(f"Overall Test RMSE:  {test_metrics['rmse']:.2f} W/m2")
            print(f"Overall Test MAE:   {test_metrics['mae']:.2f} W/m2")
            print(f"Overall Test R2:    {test_metrics['r2']:.4f}")
            print(f"Daylight nRMSE:     {test_metrics['nrmse_pct']:.2f} %")
            print("-" * 70)
            print("Step-by-step Performance:")
            for k, v in step_metrics.items():
                print(f"  {k}: {v} W/m2")
            print("=" * 70)

            mlflow.log_metrics({
                "test_overall_rmse": test_metrics["rmse"],
                "test_overall_mae": test_metrics["mae"],
                "test_overall_r2": test_metrics["r2"],
                "test_daylight_nrmse_pct": test_metrics["nrmse_pct"],
                **step_metrics,
            })

            # 8. Export directly to Self-Contained ONNX Format (embedded weights)
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

            onnx_path = temp_dir / "solar_ghi_lstm.onnx"
            dummy_input = torch.randn(1, LOOKBACK_STEPS, len(ALIGNED_FEATURE_COLS), dtype=torch.float32)

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
            onnx_size_kb = onnx_path.stat().st_size / 1024
            print(f"  [ONNX] Successfully exported single self-contained model: {onnx_size_kb:.1f} KB")

            # Verify ONNX model validity & in-memory inference
            onnx_model = onnx.load(str(onnx_path))
            onnx.checker.check_model(onnx_model)
            with open(onnx_path, "rb") as f:
                raw_onnx_bytes = f.read()
            ort_session = ort.InferenceSession(raw_onnx_bytes)
            ort_inputs = {ort_session.get_inputs()[0].name: dummy_input.numpy()}
            ort_out = ort_session.run(None, ort_inputs)
            print(f"  [ONNX Runtime] In-memory verification passed! Output shape: {ort_out[0].shape}")

            # 9. Save Metadata & Scalers to Docker MLflow & MinIO
            print("\n[5/5] Logging Artifacts to Docker MLflow & MinIO (Bucket: 'models')...")
            meta = {
                "model_name": "solar_ghi_lstm",
                "format": "ONNX",
                "file_name": "solar_ghi_lstm.onnx",
                "size_bytes": onnx_path.stat().st_size,
                "version": "1.0.0",
                "trained_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                "input_features": ALIGNED_FEATURE_COLS,
                "lookback_steps": LOOKBACK_STEPS,
                "forecast_steps": FORECAST_STEPS,
                "resolution_minutes": 10,
                "test_metrics": test_metrics,
                "step_metrics": step_metrics,
                "device_trained": str(device),
            }
            meta_path = temp_dir / "model_meta.json"
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)

            # Log to Docker MLflow
            mlflow.log_artifact(str(onnx_path), artifact_path="model")
            mlflow.log_artifact(str(temp_dir / "feature_scaler.joblib"))
            mlflow.log_artifact(str(temp_dir / "target_scaler.joblib"))
            mlflow.log_artifact(str(meta_path))
            print(f"  [MLflow] Successfully logged ONNX model and scalers to MLflow ({MLFLOW_URI})")

            # Upload directly to MinIO 'models/solar_lstm/'
            minio_client.fput_object("models", "solar_lstm/solar_ghi_lstm.onnx", str(onnx_path))
            minio_client.fput_object("models", "solar_lstm/feature_scaler.joblib", str(temp_dir / "feature_scaler.joblib"))
            minio_client.fput_object("models", "solar_lstm/target_scaler.joblib", str(temp_dir / "target_scaler.joblib"))
            minio_client.fput_object("models", "solar_lstm/model_meta.json", str(meta_path))
            print("  [MinIO] Uploaded self-contained 'solar_ghi_lstm.onnx' and scalers to bucket 'models/solar_lstm/'")

    print("\n" + "=" * 70)
    print(">> PIPELINE COMPLETE! Local repository is 100% clean.")
    print("=" * 70)


if __name__ == "__main__":
    train_solar_model()
