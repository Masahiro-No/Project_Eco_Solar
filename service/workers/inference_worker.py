"""Inference Worker — Solar Power Forecasting & Decision Support System

Flow of one job (queue: inference_queue):
  1. LSTM (ONNX) forecasts GHI for the next 18 steps of 10 minutes from the real weather window.
  2. The newest 12 real Himawari Band 03 frames around the station go through the ConvLSTM (ONNX),
     which predicts the next 18 frames; the cloud fraction in the AOI is measured on each frame.
  3. Both are blended with a weight that favours the satellite at short lead times (ghi_blend.py).
  4. The decision rules run on the blended GHI (decision.py).
  5. OpenTelemetry traces and metrics are recorded.

Nothing is simulated: if the LSTM or its input is unavailable the job fails, and if the satellite
branch is unavailable its weight is 0 and the result says so in `satellite_status`.
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from service.workers import decision
from service.workers.cloud_coverage import (
    MIN_COS_ZENITH,
    OBSERVED_HOLD_MAX_MIN,
    aoi_brightness,
    aoi_cloud_fraction,
    ghi_loss,
    held_observation_weight,
    load_calibration,
    observed_then_forecast,
)
from service.workers.ghi_blend import BLEND_TAU_MIN, BLEND_W0, blend_ghi
from service.workers.satellite_preprocessor import load_satellite_window
from service.workers.solar_geometry import NIGHT_CLEARSKY_GHI, clearsky_ghi_at, cos_zenith_at

STEP_MINUTES = 10

MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")
LOG_DIR = Path(os.environ.get("LOG_DIR", "/app/logs"))

# ── OTel Setup ────────────────────────────────────────────────────────────────
_otel_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
_resource = Resource.create({"service.name": os.environ.get("OTEL_SERVICE_NAME", "solar-inference-worker")})

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

solar_inference_requests_counter = meter.create_counter(
    "solar_inference_requests_total",
    description="Total number of solar forecast inference requests processed",
)
solar_forecast_power_kw_histogram = meter.create_histogram(
    "solar_forecast_power_kw",
    description="Forecasted solar power generation in kW",
    unit="kW",
)
solar_inference_duration_histogram = meter.create_histogram(
    "solar_inference_duration_seconds",
    description="Duration of solar inference execution in seconds",
    unit="s",
)
solar_satellite_status_counter = meter.create_counter(
    "solar_satellite_status_total",
    description="Inference runs by state of the satellite branch (ok, shifted, missing, night, model_unavailable)",
)
# ─────────────────────────────────────────────────────────────────────────────


def setup_logger(job_id: str) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"inference_{job_id}.log"
    logger = logging.getLogger(f"inference.{job_id}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger


def _get_local_model_dir() -> Path:
    """Find local project model/time-series directory across container and host environments."""
    env_dir = os.environ.get("SOLAR_MODEL_DIR")
    if env_dir and Path(env_dir).exists():
        return Path(env_dir)

    # 1. Project root / model / time-series (relative to this file: service/workers/inference_worker.py)
    root_candidate = Path(__file__).resolve().parent.parent.parent / "model" / "time-series"
    if root_candidate.exists():
        return root_candidate

    # 2. Container standard path /workspace/model/time-series
    container_candidate = Path("/workspace/model/time-series")
    if container_candidate.exists():
        return container_candidate

    # 3. Current working directory
    cwd_candidate = Path.cwd() / "model" / "time-series"
    if cwd_candidate.exists():
        return cwd_candidate

    # Default to container candidate if in container, else root candidate
    return container_candidate if Path("/workspace").exists() else root_candidate


def _sync_best_model_from_minio(target_dir: Path) -> bool:
    """
    Attempt to check MinIO 'models/solar_lstm/' for the best/latest model.
    If MinIO has a newer model or local model is missing, pull artifacts to target_dir.
    Returns True if local model was updated or verified, False if MinIO was unreachable.
    """
    try:
        import json
        import urllib3
        from minio import Minio

        minio_endpoint = os.environ.get("MINIO_ENDPOINT", "minio:9000")
        http_client = urllib3.PoolManager(
            timeout=urllib3.Timeout(connect=1.5, read=3.0),
            retries=urllib3.Retry(total=1, connect=1, read=1),
        )
        minio_client = Minio(
            minio_endpoint,
            access_key=os.environ.get("MINIO_ACCESS_KEY", "admin"),
            secret_key=os.environ.get("MINIO_SECRET_KEY", "password"),
            secure=False,
            http_client=http_client,
        )

        # Check if MinIO has the model metadata
        minio_meta_resp = minio_client.get_object("models", "solar_lstm/model_meta.json")
        remote_meta = json.loads(minio_meta_resp.read().decode("utf-8"))
        minio_meta_resp.close()
        minio_meta_resp.release_conn()

        local_meta_path = target_dir / "model_meta.json"
        needs_pull = False

        required_files = ["solar_ghi_lstm.onnx", "feature_scaler.joblib", "target_scaler.joblib", "model_meta.json"]
        for f in required_files:
            if not (target_dir / f).exists():
                needs_pull = True
                break

        if not needs_pull and local_meta_path.exists():
            try:
                with open(local_meta_path, "r", encoding="utf-8") as f:
                    local_meta = json.load(f)
                if remote_meta.get("trained_at", "") > local_meta.get("trained_at", ""):
                    needs_pull = True
            except Exception:
                needs_pull = True

        if needs_pull:
            target_dir.mkdir(parents=True, exist_ok=True)
            for f in required_files:
                minio_client.fget_object("models", f"solar_lstm/{f}", str(target_dir / f))
            print(f"[Model Sync] Pulled updated model (v{remote_meta.get('version', '1.0.0')}) from MinIO into '{target_dir}'")
        else:
            print(f"[Model Sync] Local project model in '{target_dir}' is already up-to-date")

        return True
    except Exception as e:
        print(f"[Model Sync Notice] MinIO not reachable or skipped ({e}). Loading local project model directly.")
        return False


def _load_trained_solar_onnx():
    """Load the deployed LSTM: sync from MinIO when it has a newer version, then read the project
    'model/time-series/' directory. Returns (session, feature_scaler, target_scaler, meta).

    Raises RuntimeError when the model cannot be loaded: there is no simulated substitute.
    """
    import joblib
    import onnxruntime as ort

    model_dir = _get_local_model_dir()
    _sync_best_model_from_minio(model_dir)

    names = ("solar_ghi_lstm.onnx", "feature_scaler.joblib", "target_scaler.joblib", "model_meta.json")
    files = {n: model_dir / n for n in names}
    missing = [n for n, f in files.items() if not f.exists()]
    if missing:
        raise RuntimeError(f"lstm_model_unavailable: missing {missing} in '{model_dir}'")

    session = ort.InferenceSession(str(files["solar_ghi_lstm.onnx"]))
    feature_scaler = joblib.load(str(files["feature_scaler.joblib"]))
    target_scaler = joblib.load(str(files["target_scaler.joblib"]))
    with open(files["model_meta.json"], "r", encoding="utf-8") as f:
        meta = json.load(f)
    return session, feature_scaler, target_scaler, meta


def _get_convlstm_model_dir() -> Path:
    """Locate ConvLSTM model directory across container, host, or fallback paths."""
    env_dir = os.environ.get("CONVLSTM_MODEL_DIR")
    if env_dir and Path(env_dir).exists():
        return Path(env_dir)

    # 1. Project root / model / convlstm
    root_candidate = Path(__file__).resolve().parent.parent.parent / "model" / "convlstm"
    if root_candidate.exists():
        return root_candidate

    # 2. Container standard path /workspace/model/convlstm
    container_candidate = Path("/workspace/model/convlstm")
    if container_candidate.exists():
        return container_candidate

    # 3. Fallback to Non_time_series directory
    non_ts_candidate = Path(__file__).resolve().parent.parent.parent / "Non_time_series"
    if non_ts_candidate.exists():
        return non_ts_candidate

    container_non_ts = Path("/workspace/Non_time_series")
    if container_non_ts.exists():
        return container_non_ts

    return container_candidate if Path("/workspace").exists() else root_candidate


def _sync_convlstm_from_minio(target_dir: Path) -> bool:
    """Sync ConvLSTM ONNX model from MinIO 'models/cloud_convlstm/' if reachable."""
    try:
        import urllib3
        from minio import Minio
        minio_endpoint = os.environ.get("MINIO_ENDPOINT", "minio:9000")
        http_client = urllib3.PoolManager(
            timeout=urllib3.Timeout(connect=1.5, read=3.0),
            retries=urllib3.Retry(total=1, connect=1, read=1),
        )
        minio_client = Minio(
            minio_endpoint,
            access_key=os.environ.get("MINIO_ACCESS_KEY", "admin"),
            secret_key=os.environ.get("MINIO_SECRET_KEY", "password"),
            secure=False,
            http_client=http_client,
        )

        required = ["cloud_seq2seq_12to18.onnx", "cloud_seq2seq_metadata.json"]
        needs_pull = any(not (target_dir / f).exists() for f in required)
        if needs_pull:
            target_dir.mkdir(parents=True, exist_ok=True)
            for f in required:
                minio_client.fget_object("models", f"cloud_convlstm/{f}", str(target_dir / f))
            print(f"[ConvLSTM Sync] Pulled ConvLSTM model from MinIO into '{target_dir}'")
        return True
    except Exception:
        return False


def _load_trained_convlstm_onnx():
    """Hybrid ConvLSTM model loader with project-first strategy and MinIO sync fallback."""
    try:
        import onnxruntime as ort

        model_dir = _get_convlstm_model_dir()
        _sync_convlstm_from_minio(model_dir)

        onnx_file = model_dir / "cloud_seq2seq_12to18.onnx"
        if not onnx_file.exists():
            for fallback in [
                Path("/workspace/Non_time_series/cloud_seq2seq_12to18.onnx"),
                Path(__file__).resolve().parent.parent.parent / "Non_time_series" / "cloud_seq2seq_12to18.onnx",
            ]:
                if fallback.exists():
                    onnx_file = fallback
                    break

        if not onnx_file.exists():
            print(f"[ConvLSTM Warning] Model file not found in '{model_dir}'")
            return None

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        session = ort.InferenceSession(str(onnx_file), opts, providers=["CPUExecutionProvider"])
        print(f"[ConvLSTM Loader] Successfully loaded ConvLSTM from '{onnx_file}'")
        return session
    except Exception as e:
        print(f"[ConvLSTM Loader Error] Failed to load ConvLSTM model: {e}")
        return None


def _run_lstm(session, feat_scaler, tgt_scaler, features: Any, meta: dict) -> list[float]:
    """Run the LSTM on the real weather window and return GHI in W/m2 for each forecast step."""
    lookback = int(meta["lookback_steps"])
    n_features = len(meta["input_features"])
    arr = np.asarray(features, dtype=np.float32) if features is not None else None
    if arr is None or arr.shape != (lookback, n_features):
        got = None if arr is None else arr.shape
        raise ValueError(f"invalid_weather_features: expected ({lookback}, {n_features}), got {got}")

    scaled = feat_scaler.transform(arr).astype(np.float32)[np.newaxis, :, :]
    raw_pred = session.run(None, {session.get_inputs()[0].name: scaled})[0]
    unscaled = tgt_scaler.inverse_transform(raw_pred.reshape(-1, 1)).flatten()
    return [round(float(max(0.0, v)), 2) for v in unscaled]


def _forecast_origin(data_time: Any) -> datetime:
    """10-minute slot of the newest weather observation; forecast step i is origin + (i + 1) * 10 min."""
    if data_time is None:
        raise ValueError("missing_data_time: the job must say which observation time the features end at")
    dt = data_time if isinstance(data_time, datetime) else datetime.fromisoformat(str(data_time).replace("Z", "+00:00"))
    dt = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    half = timedelta(minutes=STEP_MINUTES / 2)
    epoch = int((dt + half).timestamp() // (STEP_MINUTES * 60)) * STEP_MINUTES * 60
    return datetime.fromtimestamp(epoch, tz=timezone.utc)


def _no_satellite(n_steps: int, reason: str) -> dict[str, Any]:
    return {
        "status": "missing", "reason": reason, "end_time": None, "lag_minutes": None, "shift_minutes": 0,
        "cloud_now": None, "cloud": [None] * n_steps, "k_now": None, "k": [None] * n_steps, "lead_min": [None] * n_steps,
        "weight_scale": [1.0] * n_steps,
    }


def _satellite_branch(
    station_id: str, lat: float, lon: float, origin: datetime, n_steps: int, logger: logging.Logger
) -> dict[str, Any]:
    """Satellite values per forecast step, aligned to the forecast origin.

    Per step: the cloud fraction in the AOI (for display) and the clear-sky index k from the AOI brightness
    (for the blend). The newest satellite frame is usually 20-30 minutes older than the weather data, so
    ConvLSTM frame j (sat_end + (j + 1) * 10 min) maps to forecast step i = j - lag_steps. Near lead times
    use what the newest real frame shows, later ones the ConvLSTM forecast. Without a complete 12-frame
    window the value of the newest real frame is held for at most OBSERVED_HOLD_MAX_MIN. Steps without a
    value keep None and get a satellite weight of 0.
    """
    window = load_satellite_window(station_id, lat, lon, origin)
    out = _no_satellite(n_steps, window.reason)
    if window.last_frame is None:
        return out
    calibration = load_calibration()
    if calibration is None:
        out["reason"] = "satellite_calibration_missing"
        return out

    out["end_time"] = window.end_time
    out["shift_minutes"] = window.shift_minutes
    out["lag_minutes"] = int((origin - window.end_time).total_seconds() // 60)
    cos_end = cos_zenith_at(lat, lon, window.end_time)
    if cos_end < MIN_COS_ZENITH:
        # Band 03 is visible light: frames taken with the sun down or very low do not show the clouds
        out["status"] = "night" if cos_end <= 0.015 else "low_sun"
        out["reason"] = "sun_too_low_at_last_frame"
        return out

    rho_now = aoi_brightness(window.last_frame, [cos_end])[0]
    out["cloud_now"] = aoi_cloud_fraction(window.last_frame, cos_zenith=[cos_end])[0]
    out["k_now"] = calibration.clear_sky_index(rho_now)

    rho_pred: list = []
    frac_pred: list = []
    session = _load_trained_convlstm_onnx() if window.frames is not None else None
    if session is not None:
        predicted = session.run(None, {session.get_inputs()[0].name: window.frames})[0]
        cos_pred = [cos_zenith_at(lat, lon, window.end_time + timedelta(minutes=STEP_MINUTES * (j + 1))) for j in range(predicted.shape[1])]
        rho_pred = aoi_brightness(predicted, cos_pred)
        frac_pred = aoi_cloud_fraction(predicted, cos_zenith=cos_pred)

    lag_steps = out["lag_minutes"] // STEP_MINUTES
    for i in range(n_steps):
        j = i + lag_steps
        lead = float((j + 1) * STEP_MINUTES)   # minutes after the newest real frame
        if 0 <= j < len(rho_pred):
            rho = observed_then_forecast(rho_now, rho_pred[j], lead)
            cover = observed_then_forecast(out["cloud_now"], frac_pred[j], lead)
        elif not rho_pred and lead <= OBSERVED_HOLD_MAX_MIN:
            rho, cover = rho_now, out["cloud_now"]   # no ConvLSTM forecast: hold the real observation
            out["weight_scale"][i] = held_observation_weight(lead, STEP_MINUTES)
        else:
            rho = cover = None
        if rho is not None:
            out["k"][i] = calibration.clear_sky_index(rho)
            out["cloud"][i] = cover
            out["lead_min"][i] = lead

    out["status"] = window.status if rho_pred else "observed_only"
    if not rho_pred and window.frames is not None:
        out["reason"] = "convlstm_model_not_loaded"
    known = [k for k in out["k"] if k is not None]
    span = f"k {min(known):.2f}-{max(known):.2f} on {len(known)} steps" if known else "no usable step"
    logger.info(
        f"[Satellite] {out['status']}: newest frame {window.end_time:%H:%M} UTC, lag {out['lag_minutes']} min, "
        f"shift {window.shift_minutes} min; now cloud {out['cloud_now'] * 100:.0f}% k {out['k_now']:.2f}; forecast {span}"
    )
    return out


def _require(kwargs: dict, name: str) -> Any:
    value = kwargs.get(name)
    if value is None:
        raise ValueError(f"missing_{name}: the job must be enqueued with the station's real {name}")
    return value


def _pct(fraction: Any) -> Any:
    return None if fraction is None else round(fraction * 100.0, 1)


async def run_inference(
    ctx: dict,
    station_id: str,
    target_power_kw: float,
    model_version: str = "latest",
    **kwargs,
) -> dict[str, Any]:
    """ARQ Worker Function — Run Solar GHI & Power Forecast Inference.

    Args:
        ctx: ARQ context (job_id, redis, etc.)
        station_id: ID of the solar station (e.g. ST-001)
        target_power_kw: Dispatch power obligation target
        model_version: Requested model version (the deployed one is used and reported)
        kwargs: weather_features, data_time, station_lat, station_lon, panel_area, efficiency (all required)
    """
    job_id: str = ctx.get("job_id", f"infer-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}")
    logger = setup_logger(job_id)
    start_time = time.time()

    with tracer.start_as_current_span(
        "solar_forecast.inference",
        attributes={"job.id": job_id, "station.id": station_id, "target.kw": target_power_kw},
    ) as span:
        lat = float(_require(kwargs, "station_lat"))
        lon = float(_require(kwargs, "station_lon"))
        panel_area = float(_require(kwargs, "panel_area"))
        efficiency = float(_require(kwargs, "efficiency"))
        origin = _forecast_origin(kwargs.get("data_time"))
        logger.info(
            f"[Job] {job_id}: station {station_id}, target {target_power_kw} kW, "
            f"forecast origin {origin:%Y-%m-%d %H:%M} UTC"
        )

        # ── 1. Time-series LSTM on the real weather window ──────────────
        session, feat_scaler, tgt_scaler, meta = _load_trained_solar_onnx()
        ghi_lstm = _run_lstm(session, feat_scaler, tgt_scaler, kwargs.get("weather_features"), meta)
        n_steps = len(ghi_lstm)
        step_times = [origin + timedelta(minutes=STEP_MINUTES * (i + 1)) for i in range(n_steps)]
        clearsky = [round(clearsky_ghi_at(lat, lon, t), 2) for t in step_times]
        logger.info(
            f"[Model LSTM] v{meta.get('version')} lookback {meta.get('lookback_steps')}: "
            f"GHI {min(ghi_lstm):.1f}-{max(ghi_lstm):.1f} W/m2"
        )

        # ── 2. Satellite branch: real frames -> ConvLSTM -> cloud fraction in the AOI ──
        try:
            sat = _satellite_branch(station_id, lat, lon, origin, n_steps, logger)
        except Exception as e:  # the LSTM forecast is still real: continue without the satellite
            logger.warning(f"[Satellite] branch failed ({e}); using the LSTM alone")
            sat = _no_satellite(n_steps, f"error: {e}")

        # ── 3. Blend and decide ──────────────────────────────────────────
        ghi_blend, weights = blend_ghi(ghi_lstm, clearsky, sat["k"], sat["lead_min"], weight_scale=sat["weight_scale"])
        sat_loss = [None if k is None else ghi_loss(k) for k in sat["k"]]
        sat_loss_now = None if sat["k_now"] is None else ghi_loss(sat["k_now"])
        ghi_blend = [round(v, 2) for v in ghi_blend]
        # the night rule applies to the raw LSTM curve as well, so both lines agree after sunset
        ghi_lstm = [0.0 if cs < NIGHT_CLEARSKY_GHI else v for v, cs in zip(ghi_lstm, clearsky)]
        d = decision.evaluate(
            ghi_blend, clearsky, panel_area, efficiency, target_power_kw,
            sat_loss=sat_loss, sat_loss_now=sat_loss_now,
            step_metrics=meta.get("step_metrics"), step_minutes=STEP_MINUTES,
        )
        if d.is_night and sat["status"] in ("ok", "shifted", "observed_only"):
            sat["status"] = "night"
        logger.info(
            f"[Blend] w0={BLEND_W0} tau={BLEND_TAU_MIN} min; satellite {sat['status']}; "
            f"GHI {min(ghi_blend):.1f}-{max(ghi_blend):.1f} W/m2"
        )
        logger.info(f"[Decision] {d.alert_level}: {d.recommendation_text}")

        result = {
            "job_id": job_id,
            "station_id": station_id,
            "model_version": str(meta.get("version", model_version)),
            "predicted_at": datetime.now(timezone.utc).isoformat(),
            "forecast_origin": origin.isoformat(),
            "forecast_horizon_hours": n_steps * STEP_MINUTES // 60,
            "ghi_forecast_curve": ghi_blend,
            "ghi_forecast_lstm_raw": ghi_lstm,
            "clearsky_ghi": clearsky,
            "blend_weight": [round(w, 3) for w in weights],
            "cloud_coverage_pct": [_pct(c) for c in sat["cloud"]],
            "cloud_coverage_now_pct": _pct(sat["cloud_now"]),
            "sat_ghi_loss_pct": [_pct(x) for x in sat_loss],
            "sat_ghi_loss_now_pct": _pct(sat_loss_now),
            "cloud_impact_level": d.cloud_impact_level,
            "satellite_status": sat["status"],
            "satellite_reason": sat["reason"],
            "satellite_end_time": sat["end_time"].isoformat() if sat["end_time"] else None,
            "satellite_lag_minutes": sat["lag_minutes"],
            "is_night": d.is_night,
            "estimated_power_kw": d.estimated_power_kw,
            "power_forecast_kw": d.power_forecast_kw,
            "target_power_kw": target_power_kw,
            "target_profile_kw": d.target_profile_kw,
            "delta_p_kw": d.delta_p_kw,
            "reserve_kw": d.reserve_kw,
            "alert_level": d.alert_level,
            "recommendation_text": d.recommendation_text,
            # provenance: every value above comes from the deployed models and real inputs
            "lstm_source": "onnx",
            "input_source": "weather_features",
            "cloud_source": {"ok": "convlstm", "shifted": "convlstm", "observed_only": "observed"}.get(sat["status"], "none"),
        }

        try:
            duration = time.time() - start_time
            solar_inference_requests_counter.add(1, {"station_id": station_id, "model_version": result["model_version"]})
            solar_forecast_power_kw_histogram.record(d.estimated_power_kw, {"station_id": station_id})
            solar_inference_duration_histogram.record(duration, {"station_id": station_id})
            solar_satellite_status_counter.add(1, {"station_id": station_id, "status": sat["status"]})
            span.set_attribute("forecast.power_kw", d.estimated_power_kw)
            span.set_attribute("forecast.delta_p_kw", d.delta_p_kw)
            span.set_attribute("forecast.alert_level", d.alert_level)
            span.set_attribute("satellite.status", sat["status"])
            _metric_reader.force_flush()
        except Exception as e:
            logger.warning(f"[Metrics Warning] Failed to flush metrics: {e}")

        logger.info(f"[Job Complete] Elapsed time: {time.time() - start_time:.3f}s")
        return result
