import bisect
import json
import logging
import math
import os
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from arq import create_pool
from arq.connections import RedisSettings
from arq.jobs import Job, JobStatus
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.inference.model import Prediction
from api.inference.persistence import MODEL_SOURCE, parse_dt, save_model_prediction
from api.inference.schema import PredictionResultData
from api.ingestion.model import WeatherHistory
from api.stations.model import Station
from core.config import settings

logger = logging.getLogger("inference_service")

INFERENCE_QUEUE = "inference_queue"
STEP_MINUTES = 10
MAX_DATA_AGE_MINUTES = 20       # newest weather row older than this => do not predict
PENDING_KEY = "solar:inference:pending"
META_PREFIX = "solar:inference:meta:"
PENDING_TTL_SECONDS = 2 * 3600
GIVE_UP_AFTER = timedelta(minutes=30)


@dataclass
class ModelInput:
    features: Optional[list[list[float]]]
    data_time: Optional[datetime]
    reason: Optional[str] = None   # set when the input is not usable

    @property
    def ok(self) -> bool:
        return self.features is not None and self.reason is None


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _to_schema(pred: Prediction, station_name: str) -> PredictionResultData:
    level = pred.cloud_trend if pred.cloud_trend in ("low", "medium", "high") else None
    return PredictionResultData(
        job_id=pred.job_id,
        station_id=pred.station_id,
        station_name=station_name,
        predicted_at=pred.predicted_at,
        forecast_horizon_hours=pred.forecast_horizon_hours,
        ghi_forecast_curve=pred.ghi_forecast_curve,
        ghi_forecast_lstm_raw=pred.ghi_forecast_lstm_raw,
        blend_weight=pred.blend_weight,
        cloud_coverage_pct=pred.cloud_coverage_pct,
        cloud_coverage_now_pct=pred.cloud_coverage_now_pct,
        sat_ghi_loss_pct=pred.sat_ghi_loss_pct,
        sat_ghi_loss_now_pct=pred.sat_ghi_loss_now_pct,
        target_profile_kw=pred.target_profile_kw,
        cloud_impact_level=level,
        satellite_status=pred.satellite_status,
        satellite_lag_minutes=pred.satellite_lag_minutes,
        is_night=pred.is_night,
        estimated_power_kw=pred.estimated_power_kw,
        target_power_kw=pred.target_power_kw,
        delta_p_kw=pred.delta_p_kw,
        reserve_kw=pred.reserve_kw,
        cloud_trend=pred.cloud_trend,
        alert_level=pred.alert_level,
        recommendation_text=pred.recommendation_text,
        satellite_image_url=pred.satellite_frame_url,
        model_version=pred.model_version,
        data_time=pred.data_time,
    )


def deployed_lookback_steps() -> Optional[int]:
    """Input length of the deployed LSTM, read from its model_meta.json (the single source of truth).

    Returns None when the metadata cannot be read; callers then skip the run instead of guessing.
    """
    candidates = [
        os.environ.get("SOLAR_MODEL_DIR"),
        "/app/model/time-series",
        "/workspace/model/time-series",
        str(Path(__file__).resolve().parents[3] / "model" / "time-series"),
    ]
    for d in candidates:
        if not d:
            continue
        meta_path = Path(d) / "model_meta.json"
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return int(json.load(f)["lookback_steps"])
        except (OSError, KeyError, ValueError):
            continue
    return None


class InferenceService:
    @staticmethod
    async def get_redis_pool():
        return await create_pool(RedisSettings(
            host=settings.redis_host,
            port=settings.redis_port,
        ))

    # ------------------------------------------------------------------
    # Model input
    # ------------------------------------------------------------------
    @staticmethod
    async def prepare_model_input(station_id: str, db: AsyncSession) -> ModelInput:
        """Fetch the newest weather window the deployed LSTM needs and compute the 16 aligned features.

        Returns a ModelInput whose `reason` explains why the data is NOT usable
        (model metadata unreadable, too little history, or the newest observation is stale),
        so callers skip the run instead of predicting from old or made-up data.

        CRITICAL TIMEZONE ALIGNMENT:
        Database timestamps are stored in UTC. The model was trained on cyclical hour
        encodings in Thailand local time (UTC+7), so each timestamp is converted first.
        """
        lookback = deployed_lookback_steps()
        if lookback is None:
            return ModelInput(None, None, "model_meta_unavailable (cannot read lookback_steps of the deployed LSTM)")

        stmt = (
            select(WeatherHistory)
            .where(WeatherHistory.station_id == station_id)
            .order_by(WeatherHistory.timestamp.desc())
            .limit(lookback)
        )
        res = await db.execute(stmt)
        records = list(reversed(res.scalars().all()))
        if len(records) < lookback:
            return ModelInput(None, None, f"insufficient_history ({len(records)}/{lookback} rows)")

        data_time = _as_utc(records[-1].timestamp)
        age = datetime.now(timezone.utc) - data_time
        if age > timedelta(minutes=MAX_DATA_AGE_MINUTES):
            return ModelInput(None, data_time, f"stale_data (newest observation is {int(age.total_seconds() // 60)} min old)")

        span_min = (data_time - _as_utc(records[0].timestamp)).total_seconds() / 60.0
        expected = (lookback - 1) * STEP_MINUTES
        if abs(span_min - expected) > expected * 0.25:
            # Not blocking, but the model expects a 10-minute grid: make the drift visible.
            logger.warning(
                "[%s] weather history spans %.0f min, expected ~%d min for %d steps of %d min",
                station_id, span_min, expected, lookback, STEP_MINUTES,
            )

        features: list[list[float]] = []
        th_tz = timezone(timedelta(hours=7))  # Thailand Local Time (UTC+7)

        for r in records:
            dt_local = _as_utc(r.timestamp).astimezone(th_tz)
            minute_of_day = dt_local.hour * 60 + dt_local.minute
            hour_sin = math.sin(2 * math.pi * minute_of_day / 1440.0)
            hour_cos = math.cos(2 * math.pi * minute_of_day / 1440.0)
            day_of_year = dt_local.timetuple().tm_yday
            day_sin = math.sin(2 * math.pi * day_of_year / 365.25)
            day_cos = math.cos(2 * math.pi * day_of_year / 365.25)
            month_sin = math.sin(2 * math.pi * (dt_local.month - 1) / 12.0)
            month_cos = math.cos(2 * math.pi * (dt_local.month - 1) / 12.0)
            clearsky_ratio = max(0.0, min(1.0, float(r.clearsky_index)))

            features.append([
                float(r.ghi),
                float(r.dni),
                float(r.dhi or 0.0),
                float(r.clearsky_ghi),
                float(r.solar_zenith_angle),
                clearsky_ratio,
                float(r.temperature),
                float(r.relative_humidity),
                float(r.surface_pressure or 1008.0),
                float(r.wind_speed),
                round(hour_sin, 6),
                round(hour_cos, 6),
                round(day_sin, 6),
                round(day_cos, 6),
                round(month_sin, 6),
                round(month_cos, 6),
            ])

        return ModelInput(features, data_time)

    # ------------------------------------------------------------------
    # Enqueue (shared by POST /inference/predict and the ingestion worker)
    # ------------------------------------------------------------------
    @staticmethod
    async def enqueue_for_station(
        station: Station,
        db: AsyncSession,
        pool: Any,
        job_id: str,
        target_power_kw: Optional[float] = None,
        model_version: str = "latest",
    ) -> tuple[Optional[str], Optional[str]]:
        """Build the model input and enqueue `run_inference`.

        Returns (job_id, None) when queued, or (None, reason) when the run was skipped
        (unusable input, or a job with this id already exists).
        """
        model_input = await InferenceService.prepare_model_input(station.id, db)
        if not model_input.ok:
            return None, model_input.reason

        target_kw = target_power_kw if target_power_kw is not None else station.target_capacity_kw
        job = await pool.enqueue_job(
            "run_inference",
            station.id,
            target_kw,
            model_version,
            weather_features=model_input.features,
            data_time=model_input.data_time.isoformat(),
            station_lat=station.latitude,
            station_lon=station.longitude,
            panel_area=station.panel_area,
            efficiency=station.efficiency,
            _job_id=job_id,
            _queue_name=INFERENCE_QUEUE,
        )
        if job is None:
            return None, "duplicate_job"

        meta = {
            "station_id": station.id,
            "data_time": model_input.data_time.isoformat() if model_input.data_time else None,
            "queued_at": datetime.now(timezone.utc).isoformat(),
        }
        await pool.set(f"{META_PREFIX}{job_id}", json.dumps(meta), ex=PENDING_TTL_SECONDS)
        await pool.sadd(PENDING_KEY, job_id)
        return job_id, None

    @staticmethod
    async def enqueue_solar_inference(
        station_id: str,
        target_power_kw: Optional[float] = None,
        model_version: str = "latest",
        db: AsyncSession = None,
    ) -> str:
        """Manually enqueue a solar inference job (the real result is saved once the worker finishes)."""
        stmt = select(Station).where(Station.id == station_id, Station.is_active.is_(True))
        station = (await db.execute(stmt)).scalar_one_or_none()
        if not station:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Solar station '{station_id}' not found or inactive.",
            )

        job_id = f"infer-{uuid.uuid4().hex[:12]}"
        try:
            pool = await InferenceService.get_redis_pool()
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Job queue unavailable: {exc}")
        try:
            queued_id, reason = await InferenceService.enqueue_for_station(
                station, db, pool, job_id, target_power_kw=target_power_kw, model_version=model_version
            )
        finally:
            await pool.close()

        if queued_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot run forecast for '{station_id}': {reason}",
            )
        return queued_id

    # ------------------------------------------------------------------
    # Collect finished jobs (called every minute by the ingestion worker cron)
    # ------------------------------------------------------------------
    @staticmethod
    async def collect_finished_jobs(pool: Any, db: AsyncSession) -> dict[str, int]:
        """Persist results of finished inference jobs and drop dead ones from the pending set."""
        stats = {"saved": 0, "pending": 0, "dropped": 0}
        now = datetime.now(timezone.utc)

        for raw_id in await pool.smembers(PENDING_KEY):
            job_id = raw_id.decode() if isinstance(raw_id, bytes) else str(raw_id)
            raw_meta = await pool.get(f"{META_PREFIX}{job_id}")
            meta: dict = json.loads(raw_meta) if raw_meta else {}
            queued_at = parse_dt(meta.get("queued_at"))
            expired = queued_at is None or (now - queued_at) > GIVE_UP_AFTER

            job = Job(job_id, pool, _queue_name=INFERENCE_QUEUE)
            job_status = await job.status()

            if job_status == JobStatus.complete:
                try:
                    result = await job.result(timeout=2)
                    saved = await save_model_prediction(
                        db, job_id, result, data_time=parse_dt(meta.get("data_time"))
                    )
                    if saved is not None:
                        stats["saved"] += 1
                    else:
                        logger.warning("Result of %s could not be saved (unknown station / empty curve)", job_id)
                except Exception as exc:  # the job itself raised, or the result is unreadable
                    logger.error("Inference job %s failed: %s", job_id, exc)
                    stats["dropped"] += 1
                await pool.srem(PENDING_KEY, job_id)
            elif job_status == JobStatus.not_found or expired:
                logger.warning("Dropping inference job %s (status=%s, expired=%s)", job_id, job_status.value, expired)
                await pool.srem(PENDING_KEY, job_id)
                stats["dropped"] += 1
            else:
                stats["pending"] += 1

        return stats

    # ------------------------------------------------------------------
    # Read APIs
    # ------------------------------------------------------------------
    @staticmethod
    async def get_result(job_id: str, db: AsyncSession) -> dict:
        """Fetch a job result: from the DB if already saved, otherwise from the worker's Redis result."""
        stmt = (
            select(Prediction, Station.name)
            .join(Station, Prediction.station_id == Station.id)
            .where(Prediction.job_id == job_id)
        )
        row = (await db.execute(stmt)).first()

        worker_res: Optional[dict] = None
        job_status_value = "not_found"
        pool = None
        try:
            pool = await InferenceService.get_redis_pool()
            job = Job(job_id, pool, _queue_name=INFERENCE_QUEUE)
            job_status = await job.status()
            job_status_value = job_status.value
            if job_status == JobStatus.complete:
                try:
                    worker_res = await job.result(timeout=0.5)
                except Exception:
                    worker_res = None
                if row is None and isinstance(worker_res, dict):
                    raw_meta = await pool.get(f"{META_PREFIX}{job_id}")
                    meta = json.loads(raw_meta) if raw_meta else {}
                    saved = await save_model_prediction(
                        db, job_id, worker_res, data_time=parse_dt(meta.get("data_time"))
                    )
                    if saved is not None:
                        await pool.srem(PENDING_KEY, job_id)
                        name = (await db.execute(select(Station.name).where(Station.id == saved.station_id))).scalar_one()
                        row = (saved, name)
        except Exception:
            pass
        finally:
            if pool is not None:
                await pool.close()

        if row is None:
            return {"job_id": job_id, "status": job_status_value, "result": None}

        pred, station_name = row
        return {"job_id": job_id, "status": "complete", "result": _to_schema(pred, station_name)}

    @staticmethod
    async def get_latest_prediction(station_id: str, db: AsyncSession) -> PredictionResultData:
        """Latest REAL model prediction for a station (404 if none has been produced yet)."""
        stmt = (
            select(Prediction, Station.name)
            .join(Station, Prediction.station_id == Station.id)
            .where(Prediction.station_id == station_id, Prediction.source == MODEL_SOURCE)
            .order_by(Prediction.predicted_at.desc())
            .limit(1)
        )
        row = (await db.execute(stmt)).first()

        if not row:
            station = (await db.execute(select(Station).where(Station.id == station_id))).scalar_one_or_none()
            if not station:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Station '{station_id}' not found.",
                )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No model prediction available yet for station '{station_id}'.",
            )

        pred, station_name = row
        return _to_schema(pred, station_name)

    @staticmethod
    async def get_prediction_history(
        station_id: str,
        db: AsyncSession,
        limit: int = 50,
    ) -> list[PredictionResultData]:
        """Fetch historical real predictions for chart comparison."""
        stmt = (
            select(Prediction, Station.name)
            .join(Station, Prediction.station_id == Station.id)
            .where(Prediction.station_id == station_id, Prediction.source == MODEL_SOURCE)
            .order_by(Prediction.predicted_at.desc())
            .limit(limit)
        )
        rows = (await db.execute(stmt)).all()
        return [_to_schema(pred, station_name) for pred, station_name in rows]

    @staticmethod
    async def get_aligned_predictions(station_id: str, day: date, db: AsyncSession) -> dict:
        """ค่าที่โมเดลพยากรณ์ไว้ จัดเรียงตามเวลาจริงของวัน (เวลาไทย) ที่เลือก — ใช้เฉพาะผลจากโมเดลจริง (source='model').

        เวลาของจุดที่ i ในเส้นพยากรณ์ = data_time (เวลาของข้อมูลล่าสุดที่ป้อนโมเดล) + (i+1)*ระยะห่างของจุด
        แถวที่ไม่มี data_time ใช้ช่องข้อมูลล่าสุดใน weather_history ที่ไม่เกิน predicted_at แทน
        ช่องเวลาเดียวกันที่ถูกพยากรณ์หลายรอบ ใช้รอบที่ origin ใหม่ที่สุด.
        pred = เส้นพยากรณ์สุดท้าย (LSTM รวมกับภาพดาวเทียม), pred_lstm = LSTM อย่างเดียวของรอบเดียวกัน
        Returns: {"pred": {slot: ghi}, "pred_lstm": {slot: ghi}, "weather": {slot: ghi}, "runs": n}
        """
        from api.label_studio.ground_truth import floor_slot, th_day_bounds

        step = timedelta(minutes=STEP_MINUTES)
        start, end = th_day_bounds(day)
        lead = step * 18

        def nearest_slot(dt: datetime) -> datetime:  # ข้อมูล weather: ใกล้สุด (กึ่งกลางปัดขึ้น)
            return floor_slot(_as_utc(dt) + step / 2)

        w_res = await db.execute(
            select(WeatherHistory.timestamp, WeatherHistory.ghi)
            .where(WeatherHistory.station_id == station_id, WeatherHistory.timestamp >= start - lead, WeatherHistory.timestamp < end)
            .order_by(WeatherHistory.timestamp)
        )
        weather: dict[datetime, float] = {}
        for ts, ghi in w_res.all():
            if ghi is not None:
                weather[nearest_slot(ts)] = float(ghi)
        w_slots = sorted(weather)

        p_res = await db.execute(
            select(
                Prediction.predicted_at, Prediction.data_time, Prediction.ghi_forecast_curve,
                Prediction.forecast_horizon_hours, Prediction.ghi_forecast_lstm_raw,
            )
            .where(
                Prediction.station_id == station_id,
                Prediction.source == MODEL_SOURCE,
                Prediction.predicted_at >= start - lead,
                Prediction.predicted_at < end,
            )
            .order_by(Prediction.predicted_at)
        )
        pred: dict[datetime, tuple[datetime, float, Optional[float]]] = {}
        runs = 0
        for predicted_at, data_time, curve, horizon_hours, lstm_curve in p_res.all():
            curve = curve or []
            lstm_curve = lstm_curve or []
            if not curve:
                continue
            if data_time is not None:
                origin = nearest_slot(data_time)
            else:
                pa = _as_utc(predicted_at)
                i = bisect.bisect_right(w_slots, pa)
                origin = w_slots[i - 1] if i else floor_slot(pa)
            gap = step * max(1, round((horizon_hours or 3) * 6 / len(curve)))
            used = False
            for k, value in enumerate(curve):
                slot = origin + gap * (k + 1)
                if start <= slot < end and (slot not in pred or origin >= pred[slot][0]):
                    lstm_value = lstm_curve[k] if k < len(lstm_curve) and lstm_curve[k] is not None else None
                    pred[slot] = (origin, float(value), None if lstm_value is None else float(lstm_value))
                    used = True
            runs += 1 if used else 0

        return {
            "pred": {s: v for s, (_, v, _l) in pred.items()},
            "pred_lstm": {s: lv for s, (_, _v, lv) in pred.items() if lv is not None},
            "weather": {s: g for s, g in weather.items() if start <= s < end},
            "runs": runs,
        }
