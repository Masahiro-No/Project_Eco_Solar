"""Inference Worker — Solar Power Forecasting & Decision Support System

Flow:
  1. Receive station_id, target_power_kw, model_version from Redis Queue (inference_queue).
  2. Attempt to load trained LSTM / ConvLSTM from MLflow Model Registry (cached in ARQ ctx).
  3. If model not yet registered (pre-training stage), use realistic Sun Elevation Physics simulation.
  4. Evaluate Rule-based Decision Engine:
     P_gen = (Area * Efficiency * GHI) / 1000
     Delta_P = Target_Power - P_gen
     Cross-referenced with Cloud Motion (Clear, Inward, Outward, Overcast).
  5. Return forecast horizon (3h at 30-min intervals) + decision support advisory.
  6. Record OpenTelemetry traces & Prometheus metrics.
"""

import logging
import math
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

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
    """
    Hybrid model loader:
    1. Check MinIO: if accessible and has a newer version, sync to project 'model/time-series/'.
    2. Load model & scalers directly from project 'model/time-series/'.
       Allows teammates to run inference completely offline without MinIO!
    3. Return (session, feature_scaler, target_scaler).
    """
    try:
        import joblib
        import onnxruntime as ort

        model_dir = _get_local_model_dir()

        # Step 1: Check and sync with MinIO if reachable
        _sync_best_model_from_minio(model_dir)

        # Step 2: Load directly from project directory
        onnx_file = model_dir / "solar_ghi_lstm.onnx"
        fs_file = model_dir / "feature_scaler.joblib"
        ts_file = model_dir / "target_scaler.joblib"

        if not (onnx_file.exists() and fs_file.exists() and ts_file.exists()):
            print(f"[Model Warning] Model files not found in '{model_dir}'")
            return None, None, None

        session = ort.InferenceSession(str(onnx_file))
        feature_scaler = joblib.load(str(fs_file))
        target_scaler = joblib.load(str(ts_file))

        print(f"[Model Loader] Successfully loaded Solar GHI LSTM from project '{model_dir}'")
        return session, feature_scaler, target_scaler
    except Exception as e:
        print(f"[Model Loader Error] Failed to load local project model: {e}")
        return None, None, None


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


def _run_convlstm_nowcasting(session, sat_sequence_12: Any, roi_size: int = 5) -> tuple[Any, list[float]]:
    """Execute ConvLSTM inference on 12-frame satellite sequence and extract 18-step Cloud Index (CI).

    Returns:
        tuple of (frames_18: np.ndarray of shape (18, 64, 64), ci_array: list of 18 floats in [0.0, 1.0])
    """
    import numpy as np

    input_name = session.get_inputs()[0].name
    out = session.run(None, {input_name: sat_sequence_12})[0]
    frames_18 = out[0, :, 0, :, :]

    cy, cx = frames_18.shape[1] // 2, frames_18.shape[2] // 2
    r = roi_size // 2
    roi = frames_18[:, cy - r : cy + r + 1, cx - r : cx + r + 1]
    ci_values = np.clip(np.mean(roi, axis=(1, 2)), 0.0, 1.0)
    ci_list = [round(float(x), 3) for x in ci_values]
    return frames_18, ci_list


def _classify_cloud_motion_and_advisory(ci_array: list[float], frames_18: Any) -> tuple[str, float, str]:
    """Classify cloud dynamics into Clear, Inward, Outward, Overcast and provide specific BESS advisory."""
    import numpy as np

    ci_mean = float(np.mean(ci_array))
    ci_delta = float(ci_array[-1] - ci_array[0])
    ci_first_half = float(np.mean(ci_array[:9]))
    ci_second_half = float(np.mean(ci_array[9:]))

    if ci_mean < 0.20:
        trend = "Clear"
        advisory = "คงการชาร์จแบตเตอรี่ปกติ ไม่จำเป็นต้องสำรองไฟฉุกเฉิน (Clear Sky, high irradiance steady)"
    elif ci_mean > 0.70:
        trend = "Overcast"
        advisory = "เตรียมจ่ายไฟจาก BESS เสริมความเสถียร แดดตกต่ำต่อเนื่องยาวนาน 3 ชม. (Persistent overcast cloud layer)"
    elif ci_delta > 0.15 or (ci_second_half - ci_first_half > 0.12):
        trend = "Inward"
        advisory = "แจ้งเตือนแดดดรอปเฉียบพลัน! สั่งเตรียมปล่อยกำลังไฟ BESS Ramp-up รองรับ (Dense cloud front moving in)"
    elif ci_delta < -0.10 or (ci_first_half - ci_second_half > 0.10):
        trend = "Outward"
        advisory = "กลุ่มเมฆกำลังพ้นสถานี แดดจะฟื้นตัวกลับมา เตรียมลดการจ่ายไฟ BESS (Cloud cover clearing out)"
    else:
        if ci_mean < 0.40:
            trend = "Clear"
            advisory = "คงการชาร์จแบตเตอรี่ปกติ แดดส่องสม่ำเสมอเป็นส่วนใหญ่ (Scattered light clouds)"
        else:
            trend = "Overcast"
            advisory = "เตรียมจ่ายไฟจาก BESS เสริมความเสถียร รองรับความผันผวนของเมฆ (Moderate cloud shading)"

    variance = float(np.var(ci_array))
    confidence = round(float(np.clip(0.95 - (variance * 0.4), 0.82, 0.97)), 2)

    return trend, confidence, advisory


def _run_onnx_inference(session, feat_scaler, tgt_scaler, input_features: Optional[Any] = None) -> list[float]:
    """Execute ONNX inference on a 144-step sequence and return 18 unscaled GHI predictions."""
    import numpy as np

    seq_144 = None
    if input_features is not None:
        try:
            arr = np.array(input_features, dtype=np.float32)
            if arr.shape == (144, 16):
                seq_144 = arr
        except Exception:
            seq_144 = None

    if seq_144 is None:
        # Baseline nominal sequence (144 steps, 16 features) for realistic daytime inference
        seq_144 = np.zeros((144, 16), dtype=np.float32)
        seq_144[:, 0] = 550.0   # GHI
        seq_144[:, 1] = 620.0   # DNI
        seq_144[:, 2] = 160.0   # DHI
        seq_144[:, 3] = 700.0   # Clearsky GHI
        seq_144[:, 4] = 40.0    # Zenith
        seq_144[:, 5] = 0.85    # clearsky_ratio
        seq_144[:, 6] = 31.0    # Temp
        seq_144[:, 7] = 68.0    # Humidity
        seq_144[:, 8] = 1011.0  # Pressure
        seq_144[:, 9] = 2.8     # Wind Speed

    scaled_seq = feat_scaler.transform(seq_144).astype(np.float32)
    scaled_batch = np.expand_dims(scaled_seq, axis=0)  # (1, 144, 16)
    ort_inputs = {session.get_inputs()[0].name: scaled_batch}
    raw_pred = session.run(None, ort_inputs)[0]        # (1, 18)
    unscaled = tgt_scaler.inverse_transform(raw_pred.reshape(-1, 1)).flatten()
    return [round(float(max(0.0, val)), 2) for val in unscaled]


def simulate_realistic_ghi_curve(current_dt: datetime) -> list[float]:
    """Generate 18 points of GHI (every 10 mins for 3 hours) based on sun elevation."""
    base_hour = current_dt.hour + (current_dt.minute / 60.0)
    curve = []
    for i in range(18):
        step_hour = base_hour + (i * (10.0 / 60.0))
        # Sunlight window roughly 6:00 to 18:30 in Thailand
        if 6.0 <= step_hour <= 18.5:
            fraction = (step_hour - 6.0) / (18.5 - 6.0)
            solar_peak = math.sin(fraction * math.pi) * 850.0
            ghi_val = max(50.0, solar_peak * random.uniform(0.85, 1.05))
        else:
            ghi_val = 0.0
        curve.append(round(ghi_val, 2))
    return curve



def _evaluate_rule_based_advisory(
    panel_area: float,
    efficiency: float,
    forecast_ghi: float,
    target_power_kw: float,
    cloud_trend: str,
) -> tuple[float, float, str, str]:
    """Calculate P_gen = (A * eta * GHI)/1000 and Delta_P = Target - P_gen, with decision logic."""
    estimated_power_kw = round((panel_area * efficiency * forecast_ghi) / 1000.0, 2)
    delta_p = round(target_power_kw - estimated_power_kw, 2)

    # 4-case decision support matrix
    if delta_p > 0:  # Deficit: Generation < Target
        if cloud_trend in ("Inward", "Overcast"):
            alert_level = "CRITICAL"
            recommendation = (
                f"Deficit of {delta_p} kW detected with cloud cover advancing ({cloud_trend}). "
                f"Immediately dispatch fast-start spinning reserve +{delta_p} kW to prevent grid drop."
            )
        else:
            alert_level = "WARNING"
            recommendation = (
                f"Deficit of {delta_p} kW detected under {cloud_trend} sky. "
                f"Schedule battery energy storage discharge (BESS) or dispatch reserve +{delta_p} kW."
            )
    else:  # Surplus: Generation >= Target
        surplus = abs(delta_p)
        if cloud_trend in ("Clear", "Outward"):
            alert_level = "NORMAL"
            recommendation = (
                f"Optimal generation with {surplus} kW surplus ({cloud_trend} sky). "
                f"Direct excess power to BESS battery charging or electrolyzer storage."
            )
        else:
            alert_level = "CAUTION"
            recommendation = (
                f"Surplus of {surplus} kW currently, but cloud trend is {cloud_trend}. "
                f"Prepare ramp-down buffer in anticipation of irradiance drop."
            )

    return estimated_power_kw, delta_p, alert_level, recommendation


async def run_inference(
    ctx: dict,
    station_id: str = "ST-001",
    target_power_kw: float = 5000.0,
    model_version: str = "latest",
    *args,
    **kwargs,
) -> dict[str, Any]:
    """ARQ Worker Function — Run Solar GHI & Power Forecast Inference.

    Args:
        ctx: ARQ context (job_id, redis, etc.)
        station_id: ID of the solar station (e.g. ST-001)
        target_power_kw: Dispatch power obligation target
        model_version: Registered MLflow model version
    """
    job_id: str = ctx.get("job_id", f"infer-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}")
    logger = setup_logger(job_id)
    start_time = time.time()

    # Fallback if first positional arg was a text string (legacy test calls)
    if isinstance(station_id, str) and not station_id.startswith("ST-") and len(station_id) > 10:
        actual_station_id = "ST-001"
    else:
        actual_station_id = station_id

    with tracer.start_as_current_span(
        "solar_forecast.inference",
        attributes={
            "job.id": job_id,
            "station.id": actual_station_id,
            "model.version": model_version,
            "target.kw": target_power_kw,
        },
    ) as span:
        logger.info("=" * 60)
        logger.info(f"[Job] Solar Forecast Inference Started: job_id={job_id}")
        logger.info(f"[Job] Station ID: {actual_station_id}, Target: {target_power_kw} kW, Model Version: {model_version}")
        logger.info("=" * 60)

        # ── 1. Simulate or Load Model Forecast (Time-Series LSTM) ───────
        now = datetime.now(timezone.utc)
        onnx_session, feat_scaler, tgt_scaler = _load_trained_solar_onnx()
        if onnx_session is not None and feat_scaler is not None and tgt_scaler is not None:
            logger.info("[Model] Successfully loaded ONNX SolarLSTMForecaster from project 'model/time-series/' (solar_ghi_lstm.onnx)")
            raw_ghi_curve = _run_onnx_inference(onnx_session, feat_scaler, tgt_scaler, kwargs.get("weather_features"))
            logger.info(f"[Model LSTM] Produced 18-step Raw GHI forecast: min={min(raw_ghi_curve):.1f}, max={max(raw_ghi_curve):.1f} W/m2")
        else:
            logger.info("[Model] Using simulated astronomical elevation baseline (18 steps)")
            raw_ghi_curve = simulate_realistic_ghi_curve(now)

        # ── 2. Run ConvLSTM Satellite Nowcasting & GHI Cloud Modulation ──
        try:
            from service.workers.satellite_preprocessor import get_satellite_sequence_12, STATION_COORDINATES
            from service.workers.cloud_index_extractor import (
                classify_bess_motion_state,
                extract_center_roi_cloud_indices,
                extract_optical_flow_dynamics,
                modulate_lstm_ghi,
            )

            st_lat = kwargs.get("station_lat")
            st_lon = kwargs.get("station_lon")
            if st_lat is None or st_lon is None:
                coords = STATION_COORDINATES.get(actual_station_id, (7.0086, 100.4988))
                st_lat, st_lon = coords[0], coords[1]

            target_dt_param = kwargs.get("target_dt")
            sat_input = get_satellite_sequence_12(
                station_id=actual_station_id,
                lat=st_lat,
                lon=st_lon,
                target_dt_utc=target_dt_param,
            )
            conv_session = _load_trained_convlstm_onnx()

            if conv_session is not None:
                logger.info(f"[Model ConvLSTM] Running Seq2Seq ConvLSTM Nowcasting for '{actual_station_id}' ({st_lat}, {st_lon})...")
                frames_18, ci_array = _run_convlstm_nowcasting(conv_session, sat_input)

                # Cloud Tracking & Meteorological DSS
                flow_stats = extract_optical_flow_dynamics(frames_18)
                dss_meta = classify_bess_motion_state(ci_array, flow_stats)
                cloud_trend = dss_meta["state"]
                confidence = dss_meta["confidence"]
                bess_advisory = f"{dss_meta['bess_action']} (Speed: {flow_stats['speed_kmh']} km/h, State: {dss_meta['state_th']})"

                # Modulate GHI using formula: GHI_final(t) = GHI_lstm(t) * (1.0 - CI_t)
                ghi_curve = [
                    round(float(v), 1)
                    for v in modulate_lstm_ghi(raw_ghi_curve, ci_array)
                ]
                logger.info(f"[Model ConvLSTM] Extracted 18-step Cloud Index (CI): min={min(ci_array):.3f}, max={max(ci_array):.3f}, mean={float(np.mean(ci_array)):.3f}")
                logger.info(f"[Model Fusion] Modulated GHI curve: min={min(ghi_curve):.1f}, max={max(ghi_curve):.1f} W/m2")
                logger.info(f"[Model Fusion] Meteorological State: {cloud_trend} ({dss_meta['state_th']}) | Wind/Cloud Speed: {flow_stats['speed_kmh']} km/h")
            else:
                logger.warning("[Model ConvLSTM] ConvLSTM not available. Falling back to unmodulated GHI curve.")
                ci_array = [0.0] * 18
                ghi_curve = raw_ghi_curve
                cloud_trend = "Clear"
                confidence = 0.85
                bess_advisory = "คงการชาร์จแบตเตอรี่ปกติ ไม่จำเป็นต้องสำรองไฟฉุกเฉิน (Baseline mode)"
        except Exception as e:
            logger.warning(f"[Model ConvLSTM Error] Nowcasting error ({e}). Using unmodulated GHI.")
            ci_array = [0.0] * 18
            ghi_curve = raw_ghi_curve
            cloud_trend = "Clear"
            confidence = 0.85
            bess_advisory = "คงการชาร์จแบตเตอรี่ปกติ (Fallback mode)"

        avg_forecast_ghi = sum(ghi_curve) / len(ghi_curve) if ghi_curve else 500.0

        panel_area = float(kwargs.get("panel_area") or (20000.0 if actual_station_id == "ST-002" else 30000.0))
        efficiency = float(kwargs.get("efficiency") or 0.185)

        est_kw, delta_p, alert, rec = _evaluate_rule_based_advisory(
            panel_area=panel_area,
            efficiency=efficiency,
            forecast_ghi=avg_forecast_ghi,
            target_power_kw=target_power_kw,
            cloud_trend=cloud_trend,
        )

        logger.info(f"[Inference Result] Avg GHI: {avg_forecast_ghi:.1f} W/m2, P_gen: {est_kw} kW, Delta_P: {delta_p} kW")
        logger.info(f"[Decision Advisory] Alert: {alert} | Trend: {cloud_trend} | BESS: {bess_advisory}")

        result = {
            "job_id": job_id,
            "station_id": actual_station_id,
            "model_version": model_version,
            "predicted_at": now.isoformat(),
            "forecast_horizon_hours": 3,
            "ghi_forecast_curve": ghi_curve,
            "ghi_forecast_lstm_raw": raw_ghi_curve,
            "cloud_indices": ci_array,
            "estimated_power_kw": est_kw,
            "target_power_kw": target_power_kw,
            "delta_p_kw": delta_p,
            "cloud_trend": cloud_trend,
            "confidence": confidence,
            "alert_level": alert,
            "recommendation_text": rec,
            "bess_advisory": bess_advisory,
        }

        # ── 2. OpenTelemetry & Prometheus Metrics ─────────────────────
        try:
            duration = time.time() - start_time
            solar_inference_requests_counter.add(1, {"station_id": actual_station_id, "model_version": model_version})
            solar_forecast_power_kw_histogram.record(est_kw, {"station_id": actual_station_id})
            solar_inference_duration_histogram.record(duration, {"station_id": actual_station_id})
            span.set_attribute("forecast.power_kw", est_kw)
            span.set_attribute("forecast.delta_p_kw", delta_p)
            span.set_attribute("forecast.alert_level", alert)
            _metric_reader.force_flush()
        except Exception as e:
            logger.warning(f"[Metrics Warning] Failed to flush metrics: {e}")

        logger.info(f"[Job Complete] Elapsed time: {time.time() - start_time:.3f}s")
        return result
