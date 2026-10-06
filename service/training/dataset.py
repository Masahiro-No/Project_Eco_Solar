"""Solar Time-Series Dataset & Sliding Window Data Preparation

Ensures strict 16-feature alignment between NSRDB training data and real-time Open-Meteo inference.
"""

from pathlib import Path
from typing import Any, Optional, Tuple
import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
import torch
from torch.utils.data import Dataset

# 16 Guaranteed Aligned Features (Present in both NSRDB and Open-Meteo + SolarCalculator)
ALIGNED_FEATURE_COLS = [
    "GHI",
    "DNI",
    "DHI",
    "Clearsky GHI",
    "Solar Zenith Angle",
    "clearsky_ratio",
    "Temperature",
    "Relative Humidity",
    "Pressure",
    "Wind Speed",
    "hour_sin",
    "hour_cos",
    "day_sin",
    "day_cos",
    "month_sin",
    "month_cos",
]

TARGET_COL = "GHI"
LOOKBACK_STEPS = 144   # 24 hours at 10-minute resolution
FORECAST_STEPS = 18    # 3 hours at 10-minute resolution


class SolarTimeWindowDataset(Dataset):
    """PyTorch Dataset that extracts sliding windows from continuous time-series arrays."""

    def __init__(
        self,
        features: np.ndarray,
        targets: np.ndarray,
        lookback_steps: int = LOOKBACK_STEPS,
        forecast_steps: int = FORECAST_STEPS,
        step_stride: int = 1,
    ):
        """
        Args:
            features: 2D array of shape (N, num_features=16)
            targets: 1D array of shape (N,) containing GHI values
            lookback_steps: Input sequence length (144 = 24h)
            forecast_steps: Target forecast horizon (18 = 3h)
            step_stride: Step between sample windows (1 = sliding by 10 min)
        """
        self.features = torch.tensor(features, dtype=torch.float32)
        self.targets = torch.tensor(targets, dtype=torch.float32)
        self.lookback_steps = lookback_steps
        self.forecast_steps = forecast_steps
        self.step_stride = step_stride

        # Total number of valid sliding windows
        total_len = len(features)
        self.num_samples = (total_len - lookback_steps - forecast_steps) // step_stride + 1

    def __len__(self) -> int:
        return max(0, self.num_samples)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        start_idx = idx * self.step_stride
        mid_idx = start_idx + self.lookback_steps
        end_idx = mid_idx + self.forecast_steps

        x = self.features[start_idx:mid_idx]  # Shape: (144, 16)
        y = self.targets[mid_idx:end_idx]     # Shape: (18,)
        return x, y


def load_splits_from_minio(
    minio_client: Optional[Any] = None,
    bucket: str = "datasets",
    prefix: str = "timeseries",
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Stream dataset splits directly from MinIO into pandas without writing to disk."""
    import io
    from minio import Minio

    if minio_client is None:
        from service.training.retrain_timeseries import _minio_client  # the storage settings every trainer uses

        minio_client = _minio_client()

    dfs = {}
    for name in ["train_10min.csv", "val_10min.csv", "test_10min.csv"]:
        object_name = f"{prefix}/{name}"
        resp = minio_client.get_object(bucket, object_name)
        dfs[name] = pd.read_csv(io.BytesIO(resp.read()))
        resp.close()
        resp.release_conn()
        print(f"  [MinIO Stream] Loaded {name} ({len(dfs[name]):,} rows) from bucket '{bucket}'")

    return dfs["train_10min.csv"], dfs["val_10min.csv"], dfs["test_10min.csv"]


def load_and_scale_splits(
    data_dir: Optional[Path] = None,
    save_scalers_dir: Optional[Path] = None,
    minio_client: Optional[Any] = None,
) -> Tuple[
    Tuple[np.ndarray, np.ndarray],
    Tuple[np.ndarray, np.ndarray],
    Tuple[np.ndarray, np.ndarray],
    MinMaxScaler,
    MinMaxScaler,
]:
    """Load train/val/test CSVs from MinIO or local disk, apply strict feature selection and scale.

    Returns:
        (X_train, y_train), (X_val, y_val), (X_test, y_test), feature_scaler, target_scaler
    """
    if data_dir and (data_dir / "train_10min.csv").exists():
        print(f"  [Storage] Loading dataset splits from local disk: {data_dir}")
        df_train = pd.read_csv(data_dir / "train_10min.csv")
        df_val = pd.read_csv(data_dir / "val_10min.csv")
        df_test = pd.read_csv(data_dir / "test_10min.csv")
    else:
        print("  [Storage] Streaming dataset splits directly from MinIO (bucket: 'datasets')...")
        df_train, df_val, df_test = load_splits_from_minio(minio_client=minio_client)

    # 1. Extract exactly the 16 aligned features
    X_train_raw = df_train[ALIGNED_FEATURE_COLS].values.astype(np.float32)
    y_train_raw = df_train[TARGET_COL].values.astype(np.float32)

    X_val_raw = df_val[ALIGNED_FEATURE_COLS].values.astype(np.float32)
    y_val_raw = df_val[TARGET_COL].values.astype(np.float32)

    X_test_raw = df_test[ALIGNED_FEATURE_COLS].values.astype(np.float32)
    y_test_raw = df_test[TARGET_COL].values.astype(np.float32)

    # 2. Fit Scalers on TRAIN SET ONLY to avoid data leakage
    feature_scaler = MinMaxScaler(feature_range=(0.0, 1.0))
    feature_scaler.fit(X_train_raw)

    target_scaler = MinMaxScaler(feature_range=(0.0, 1.0))
    target_scaler.fit(y_train_raw.reshape(-1, 1))

    # 3. Transform all splits
    X_train = feature_scaler.transform(X_train_raw)
    y_train = target_scaler.transform(y_train_raw.reshape(-1, 1)).flatten()

    X_val = feature_scaler.transform(X_val_raw)
    y_val = target_scaler.transform(y_val_raw.reshape(-1, 1)).flatten()

    X_test = feature_scaler.transform(X_test_raw)
    y_test = target_scaler.transform(y_test_raw.reshape(-1, 1)).flatten()

    # Save scalers for production inference if directory provided
    if save_scalers_dir:
        save_scalers_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump(feature_scaler, save_scalers_dir / "feature_scaler.joblib")
        joblib.dump(target_scaler, save_scalers_dir / "target_scaler.joblib")
        joblib.dump(ALIGNED_FEATURE_COLS, save_scalers_dir / "feature_names.joblib")
        print(f"[Dataset] Scalers saved to {save_scalers_dir}")

    return (X_train, y_train), (X_val, y_val), (X_test, y_test), feature_scaler, target_scaler

