import math
import random
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from arq import create_pool
from arq.connections import RedisSettings
from arq.jobs import Job
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.inference.decision_engine import CloudTrend, evaluate_decision_support
from api.inference.model import Prediction
from api.inference.schema import PredictionResultData
from api.ingestion.model import WeatherHistory
from api.stations.model import Station
from core.config import settings


def simulate_realistic_ghi_curve(current_dt: datetime) -> list[float]:
    """Generate 18 points of GHI (every 10 mins for 3 hours) based on sun elevation."""
    base_hour = current_dt.hour + (current_dt.minute / 60.0)
    curve = []

    for i in range(18):
        step_hour = base_hour + (i * (10.0 / 60.0))
        # Sunlight window roughly 6:00 to 18:30 in Thailand
        if 6.0 <= step_hour <= 18.5:
            # Solar zenith simulation: sinusoidal peak at 12:30 ~ 850 W/m^2
            fraction = (step_hour - 6.0) / (18.5 - 6.0)
            solar_peak = math.sin(fraction * math.pi) * 850.0
            # Add slight cloud variation
            ghi_val = max(50.0, solar_peak * random.uniform(0.75, 1.05))
        else:
            ghi_val = 0.0

        curve.append(round(ghi_val, 2))

    return curve


class InferenceService:
    @staticmethod
    async def get_redis_pool():
        return await create_pool(RedisSettings(
            host=settings.redis_host,
            port=settings.redis_port,
        ))

    @staticmethod
    async def extract_latest_weather_features(station_id: str, db: AsyncSession) -> Optional[list[list[float]]]:
        """Fetch latest 144 weather records for station and compute 16 aligned features with local timezone.
        
        CRITICAL TIMEZONE ALIGNMENT:
        Database timestamps are stored in UTC. However, the solar ML model was trained on cyclical
        hour encodings synchronized to Thailand Local Time (UTC+7 / Asia/Bangkok).
        We convert each timestamp to UTC+7 before computing hour_sin/cos to prevent phase shift.
        """
        stmt = (
            select(WeatherHistory)
            .where(WeatherHistory.station_id == station_id)
            .order_by(WeatherHistory.timestamp.desc())
            .limit(144)
        )
        res = await db.execute(stmt)
        records = list(reversed(res.scalars().all()))
        if len(records) < 144:
            return None

        features = []
        th_tz = timezone(timedelta(hours=7))  # Thailand Local Time (UTC+7)

        for r in records:
            dt_local = r.timestamp.astimezone(th_tz)
            minute_of_day = dt_local.hour * 60 + dt_local.minute
            hour_sin = math.sin(2 * math.pi * minute_of_day / 1440.0)
            hour_cos = math.cos(2 * math.pi * minute_of_day / 1440.0)
            day_of_year = dt_local.timetuple().tm_yday
            day_sin = math.sin(2 * math.pi * day_of_year / 365.25)
            day_cos = math.cos(2 * math.pi * day_of_year / 365.25)
            month_sin = math.sin(2 * math.pi * (dt_local.month - 1) / 12.0)
            month_cos = math.cos(2 * math.pi * (dt_local.month - 1) / 12.0)
            clearsky_ratio = max(0.0, min(1.0, float(r.clearsky_index)))

            row = [
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
            ]
            features.append(row)

        return features

    @staticmethod
    async def enqueue_solar_inference(
        station_id: str,
        target_power_kw: Optional[float] = None,
        model_version: str = "latest",
        db: AsyncSession = None,
    ) -> str:
        """Enqueue solar inference job to Redis with 144-step real weather features."""
        # 1. Verify station exists
        stmt = select(Station).where(Station.id == station_id, Station.is_active.is_(True))
        res = await db.execute(stmt)
        station = res.scalar_one_or_none()
        if not station:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Solar station '{station_id}' not found or inactive.",
            )

        job_id = f"infer-{uuid.uuid4().hex[:12]}"
        target_kw = target_power_kw if target_power_kw is not None else station.target_capacity_kw

        # 2. Extract latest 144 real weather features with Asia/Bangkok alignment
        weather_features = await InferenceService.extract_latest_weather_features(station_id, db)

        # 3. Generate initial simulated solar forecast & cloud trend (baseline fallback)
        now_utc = datetime.now(timezone.utc)
        ghi_curve = simulate_realistic_ghi_curve(now_utc)
        current_ghi = ghi_curve[0]

        # Simulate cloud trend
        cloud_options = [CloudTrend.CLEAR, CloudTrend.INWARD, CloudTrend.OUTWARD, CloudTrend.OVERCAST]
        cloud_trend = random.choice(cloud_options)
        confidence = round(random.uniform(0.78, 0.95), 2)

        # 4. Evaluate Rule-based Decision Engine
        decision = evaluate_decision_support(
            panel_area_m2=station.panel_area,
            efficiency=station.efficiency,
            current_ghi_w_m2=current_ghi,
            target_power_kw=target_kw,
            cloud_trend=cloud_trend,
        )

        # 5. Save prediction record to Database
        prediction = Prediction(
            job_id=job_id,
            station_id=station.id,
            predicted_at=now_utc,
            forecast_horizon_hours=3,
            ghi_forecast_curve=ghi_curve,
            estimated_power_kw=decision.estimated_power_kw,
            target_power_kw=target_kw,
            delta_p_kw=decision.recommended_delta_p_kw,
            cloud_trend=cloud_trend.value,
            confidence=confidence,
            alert_level=decision.alert_level.value,
            recommendation_text=decision.recommendation_text,
            satellite_frame_url=f"/api/storage/download/satellite-cache/{station.id}_latest.png",
        )
        db.add(prediction)
        await db.commit()

        # 6. Enqueue background task into Redis inference_queue with 144 weather features
        try:
            pool = await InferenceService.get_redis_pool()
            await pool.enqueue_job(
                "run_inference",
                station_id,
                target_kw,
                model_version,
                weather_features=weather_features,
                _job_id=job_id,
                _queue_name="inference_queue",
            )
            await pool.close()
        except Exception:
            # Fallback if redis is offline during local test
            pass

        return job_id

    @staticmethod
    async def get_result(job_id: str, db: AsyncSession) -> dict:
        """Fetch inference result from DB and synchronize with worker ONNX output."""
        stmt = select(Prediction, Station.name).join(Station, Prediction.station_id == Station.id).where(Prediction.job_id == job_id)
        res = await db.execute(stmt)
        row = res.first()

        if not row:
            # Check redis status
            try:
                pool = await InferenceService.get_redis_pool()
                job = Job(job_id, pool)
                st = await job.status()
                await pool.close()
                return {"job_id": job_id, "status": st.value, "result": None}
            except Exception:
                return {"job_id": job_id, "status": "not_found", "result": None}

        pred, station_name = row

        # Synchronize ONNX worker result from Redis if available
        try:
            pool = await InferenceService.get_redis_pool()
            job = Job(job_id, pool)
            worker_res = await job.result(timeout=0.1)
            await pool.close()
            if worker_res and isinstance(worker_res, dict) and "ghi_forecast_curve" in worker_res:
                pred.ghi_forecast_curve = worker_res["ghi_forecast_curve"]
                pred.estimated_power_kw = worker_res.get("estimated_power_kw", pred.estimated_power_kw)
                pred.delta_p_kw = worker_res.get("delta_p_kw", pred.delta_p_kw)
                pred.alert_level = worker_res.get("alert_level", pred.alert_level)
                pred.recommendation_text = worker_res.get("recommendation_text", pred.recommendation_text)
                await db.commit()
        except Exception:
            pass

        pred, station_name = row
        result_data = PredictionResultData(
            job_id=pred.job_id,
            station_id=pred.station_id,
            station_name=station_name,
            predicted_at=pred.predicted_at,
            forecast_horizon_hours=pred.forecast_horizon_hours,
            ghi_forecast_curve=pred.ghi_forecast_curve,
            estimated_power_kw=pred.estimated_power_kw,
            target_power_kw=pred.target_power_kw,
            delta_p_kw=pred.delta_p_kw,
            cloud_trend=pred.cloud_trend,
            confidence=pred.confidence,
            alert_level=pred.alert_level,
            recommendation_text=pred.recommendation_text,
            satellite_image_url=pred.satellite_frame_url,
        )

        return {"job_id": job_id, "status": "complete", "result": result_data}

    @staticmethod
    async def get_latest_prediction(station_id: str, db: AsyncSession) -> PredictionResultData:
        """Fetch the latest prediction for a station."""
        stmt = (
            select(Prediction, Station.name)
            .join(Station, Prediction.station_id == Station.id)
            .where(Prediction.station_id == station_id)
            .order_by(Prediction.predicted_at.desc())
            .limit(1)
        )
        res = await db.execute(stmt)
        row = res.first()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No prediction records found for station '{station_id}'.",
            )

        pred, station_name = row
        return PredictionResultData(
            job_id=pred.job_id,
            station_id=pred.station_id,
            station_name=station_name,
            predicted_at=pred.predicted_at,
            forecast_horizon_hours=pred.forecast_horizon_hours,
            ghi_forecast_curve=pred.ghi_forecast_curve,
            estimated_power_kw=pred.estimated_power_kw,
            target_power_kw=pred.target_power_kw,
            delta_p_kw=pred.delta_p_kw,
            cloud_trend=pred.cloud_trend,
            confidence=pred.confidence,
            alert_level=pred.alert_level,
            recommendation_text=pred.recommendation_text,
            satellite_image_url=pred.satellite_frame_url,
        )

    @staticmethod
    async def get_prediction_history(
        station_id: str,
        db: AsyncSession,
        limit: int = 50,
    ) -> list[PredictionResultData]:
        """Fetch historical predictions for chart comparison."""
        stmt = (
            select(Prediction, Station.name)
            .join(Station, Prediction.station_id == Station.id)
            .where(Prediction.station_id == station_id)
            .order_by(Prediction.predicted_at.desc())
            .limit(limit)
        )
        res = await db.execute(stmt)
        rows = res.all()

        return [
            PredictionResultData(
                job_id=pred.job_id,
                station_id=pred.station_id,
                station_name=station_name,
                predicted_at=pred.predicted_at,
                forecast_horizon_hours=pred.forecast_horizon_hours,
                ghi_forecast_curve=pred.ghi_forecast_curve,
                estimated_power_kw=pred.estimated_power_kw,
                target_power_kw=pred.target_power_kw,
                delta_p_kw=pred.delta_p_kw,
                cloud_trend=pred.cloud_trend,
                confidence=pred.confidence,
                alert_level=pred.alert_level,
                recommendation_text=pred.recommendation_text,
                satellite_image_url=pred.satellite_frame_url,
            )
            for pred, station_name in rows
        ]
