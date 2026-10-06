"""State and history of the retraining of both models, for the admin page.

Nothing here starts a retrain. The numbers come from three places:

  deployed model     model/time-series/model_meta.json and model/convlstm/cloud_seq2seq_metadata.json
  what is pending    Redis keys written by the label API, the ingestion worker and the trainer
  history            MLflow experiments solar_lstm_retrain and solar_convlstm_retrain (one run per retrain)
"""

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from core.config import settings

LSTM_META = Path("/app/model/time-series/model_meta.json")
CONVLSTM_META = Path("/app/model/convlstm/cloud_seq2seq_metadata.json")
EXPERIMENTS = {"lstm": "solar_lstm_retrain", "convlstm": "solar_convlstm_retrain"}

# Redis keys (service/training/retrain_timeseries.py and service/workers/convlstm_batch.py)
LSTM_SCHEDULED_KEY = "retrain:timeseries:scheduled"
LSTM_LOCK_KEY = "retrain:timeseries:lock"
CONVLSTM_SCHEDULED_KEY = "convlstm:retrain:scheduled"
CONVLSTM_RUNNING_KEY = "convlstm:retrain:running"
CONVLSTM_STATUS_KEY = "convlstm:retrain:status"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def deployed_lstm() -> dict[str, Any]:
    meta = _read_json(LSTM_META)
    return {
        "model_version": str(meta["version"]) if meta.get("version") is not None else None,
        "trained_at": meta.get("trained_at"),
        "lookback_steps": meta.get("lookback_steps"),
        "previous_version": (meta.get("retrain") or {}).get("previous_version"),
    }


def deployed_convlstm() -> dict[str, Any]:
    meta = _read_json(CONVLSTM_META)
    return {
        "model_version": str(meta["version"]) if meta.get("version") is not None else None,
        "retrained_at": meta.get("retrained_at"),
    }


CURVE_PREFIX = "epoch_"   # service/training/curves.py logs one point per epoch under this prefix
RUN_ID = re.compile(r"^[0-9a-f]{32}$")


def _mlflow_get(path: str, params: dict[str, str]) -> dict[str, Any]:
    url = settings.mlflow_tracking_uri.rstrip("/") + path + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=8) as resp:
        return json.load(resp)


def read_curves(run_id: str) -> dict[str, list[dict[str, Any]]]:
    """Per-epoch values of every `epoch_*` metric of a run (blocking: call in a thread)."""
    run = _mlflow_get("/api/2.0/mlflow/runs/get", {"run_id": run_id}).get("run", {})
    keys = sorted(m["key"] for m in run.get("data", {}).get("metrics", []) if m["key"].startswith(CURVE_PREFIX))
    curves: dict[str, list[dict[str, Any]]] = {}
    for key in keys:
        points = _mlflow_get("/api/2.0/mlflow/metrics/get-history", {"run_id": run_id, "metric_key": key}).get("metrics", [])
        by_epoch = {int(p.get("step", 0)): float(p["value"]) for p in points}   # a re-logged epoch keeps its last value
        curves[key[len(CURVE_PREFIX):]] = [{"epoch": e, "value": v} for e, v in sorted(by_epoch.items())]
    return curves


def _has_curves(metrics: dict[str, Any]) -> bool:
    return any(k.startswith(CURVE_PREFIX) for k in metrics)


def _mlflow(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(
        settings.mlflow_tracking_uri.rstrip("/") + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.load(resp)


def _parse_time(value: Any) -> Optional[datetime]:
    """'2026-10-05 01:31:52 UTC' or ISO text -> aware datetime."""
    if not value:
        return None
    text = str(value).replace(" UTC", "+00:00").replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def lstm_run(run: dict[str, Any], deployed: dict[str, Any]) -> dict[str, Any]:
    """One MLflow run of solar_lstm_retrain as a row of the history table."""
    data = run.get("data", {})
    metrics = {m["key"]: m["value"] for m in data.get("metrics", [])}
    params = {p["key"]: p["value"] for p in data.get("params", [])}
    tags = {t["key"]: t["value"] for t in data.get("tags", [])}
    started = datetime.fromtimestamp(run["info"]["start_time"] / 1000, tz=timezone.utc)
    ended = datetime.fromtimestamp(run["info"]["end_time"] / 1000, tz=timezone.utc) if run["info"].get("end_time") else started

    gate = tags.get("gate") or "weather_only"
    measured = gate == "measured_ghi" and "real_mae_before" in metrics
    before = metrics.get("real_mae_before" if measured else "val_mae_before")
    after = metrics.get("real_mae_after" if measured else "val_mae_after")
    outcome = tags.get("status") or ("deployed" if tags.get("deployed") == "True" else "rejected")
    reason = tags.get("reason")
    if reason is None and outcome == "rejected":  # runs logged before the reason was recorded
        if not measured:
            reason = "no_improvement_on_validation"
        else:
            reason = "no_improvement_on_measured_ghi" if (after is None or before is None or after >= before) else "worse_on_weather_only_validation"

    version = tags.get("version")
    trained_at = _parse_time(deployed.get("trained_at"))
    if version is None and outcome == "deployed" and trained_at is not None and abs(ended - trained_at) < timedelta(minutes=10):
        version = deployed.get("model_version")   # the run that produced the model in use
    return {
        "run_id": run["info"]["run_id"],
        "has_curves": _has_curves(metrics),
        "started_at": started,
        "outcome": outcome,
        "reason": reason,
        "version": version,
        "gate": "measured_ghi" if measured else "weather_only",
        "metric": "real_mae" if measured else "val_mae",
        "before": before,
        "after": after,
        "details": {
            "val_mae_before": metrics.get("val_mae_before"),
            "val_mae_after": metrics.get("val_mae_after"),
            "holdout_day": tags.get("holdout_day"),
            "select_day": tags.get("select_day"),
            # set since the run feeds the model weather only, as in a live forecast; absent = the older check,
            # which had measured GHI in the model input, so its real_mae is lower than in real use
            "min_improvement": params.get("min_improvement"),
            "label_count": params.get("label_count"),
            "train_windows": params.get("train_windows"),
            "val_windows": params.get("val_windows"),
            "best_epoch": params.get("best_epoch"),
        },
    }


def convlstm_run(run: dict[str, Any]) -> dict[str, Any]:
    """One MLflow run of solar_convlstm_retrain as a row of the history table."""
    data = run.get("data", {})
    metrics = {m["key"]: m["value"] for m in data.get("metrics", [])}
    params = {p["key"]: p["value"] for p in data.get("params", [])}
    tags = {t["key"]: t["value"] for t in data.get("tags", [])}
    return {
        "run_id": run["info"]["run_id"],
        "has_curves": _has_curves(metrics),
        "started_at": datetime.fromtimestamp(run["info"]["start_time"] / 1000, tz=timezone.utc),
        "outcome": tags.get("status") or "unknown",
        "reason": tags.get("reason"),
        "version": tags.get("version"),
        "gate": "val_mse",
        "metric": "val_mse",
        "before": metrics.get("val_mse_baseline"),
        "after": metrics.get("val_mse_candidate"),
        "details": {
            "ssim_before": metrics.get("val_ssim_baseline"),
            "ssim_after": metrics.get("val_ssim_candidate"),
            "aoi_cloud_mae_before": metrics.get("val_aoi_cloud_mae_pct_baseline"),
            "aoi_cloud_mae_after": metrics.get("val_aoi_cloud_mae_pct_candidate"),
            "frames_used": params.get("frames_used"),
            "train_sequences": params.get("train_sequences"),
            "val_sequences": params.get("val_sequences"),
            "device": params.get("device"),
        },
    }


def read_history(limit: int = 30) -> tuple[dict[str, list[dict[str, Any]]], Optional[str]]:
    """Retrain runs of both models, newest first (blocking: call in a thread). Returns (history, error text)."""
    history: dict[str, list[dict[str, Any]]] = {"lstm": [], "convlstm": []}
    try:
        experiments = _mlflow("/api/2.0/mlflow/experiments/search", {"max_results": 100}).get("experiments", [])
        ids = {e["name"]: e["experiment_id"] for e in experiments}
        deployed = deployed_lstm()
        for model, name in EXPERIMENTS.items():
            if name not in ids:
                continue
            runs = _mlflow(
                "/api/2.0/mlflow/runs/search",
                {"experiment_ids": [ids[name]], "max_results": limit, "order_by": ["attributes.start_time DESC"]},
            ).get("runs", [])
            history[model] = [lstm_run(r, deployed) if model == "lstm" else convlstm_run(r) for r in runs]
        return history, None
    except Exception as e:  # noqa: BLE001  the deployed models and the counters are still worth showing
        return history, f"MLflow: {e}"
