"""Mock Hat Yai Station, Weather History, and Execute AI Inference Pipeline

This script:
1. Creates the database schema (stations, weather_history, predictions, etc.)
2. Seeds Hat Yai Solar Farm (ST-001) and neighboring southern stations in PostgreSQL / SQLite.
3. Mocks 144 steps (24 hours at 10-minute intervals) of realistic solar weather history
   geocoded precisely for PSU Hat Yai (Lat: 7.0086, Lon: 100.4988).
4. Connects Hat Yai data to the AI Models:
   - Solar GHI LSTM (solar_ghi_lstm.onnx) -> 18-step GHI forecast
   - ConvLSTM Satellite Nowcasting (cloud_seq2seq_12to18.onnx) -> 18-step Cloud Index & Trend
   - Model Fusion -> Modulated GHI curve
   - Physics-based Power Equation -> P_gen (kW)
   - Decision Engine & BESS Advisory -> Alert & Delta P
5. Saves the final Prediction record into the database for immediate display on Dashboard.
"""

import asyncio
import math
import os
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Ensure UTF-8 output on Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root and backend directory to path
BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

import joblib
import numpy as np
import onnxruntime as ort
from sqlalchemy import select, func, delete

from api.auth.model import User
from api.stations.model import Station
from api.ingestion.model import WeatherHistory
from api.ingestion.solar_calculator import SolarCalculator
from api.inference.model import Prediction
from api.inference.decision_engine import evaluate_decision_support, CloudTrend
from db.database import SessionLocal, create_database_schema, engine
from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()


HAT_YAI_STATION = {
    "id": "ST-001",
    "name": "PSU Hat Yai Solar Farm (ม.อ. หาดใหญ่)",
    "latitude": 7.0086,
    "longitude": 100.4988,
    "panel_area": 30000.0,      # 30,000 m^2
    "efficiency": 0.185,        # 18.5%
    "target_capacity_kw": 5000.0, # 5,000 kW (5 MW)
}

OTHER_STATIONS = [
    {
        "id": "ST-002",
        "name": "Songkhla Solar Farm (พพ. สงขลา)",
        "latitude": 7.1982,
        "longitude": 100.5954,
        "panel_area": 24000.0,
        "efficiency": 0.185,
        "target_capacity_kw": 4000.0,
    },
    {
        "id": "ST-003",
        "name": "Nakhon Si Thammarat Solar Farm",
        "latitude": 8.4304,
        "longitude": 99.9631,
        "panel_area": 18000.0,
        "efficiency": 0.190,
        "target_capacity_kw": 3000.0,
    },
    {
        "id": "ST-004",
        "name": "Pattani Solar Farm",
        "latitude": 6.8696,
        "longitude": 101.2501,
        "panel_area": 15000.0,
        "efficiency": 0.180,
        "target_capacity_kw": 2500.0,
    },
    {
        "id": "ST-005",
        "name": "Trang Solar Farm",
        "latitude": 7.5563,
        "longitude": 99.6114,
        "panel_area": 16500.0,
        "efficiency": 0.185,
        "target_capacity_kw": 2750.0,
    },
]


async def seed_stations(session):
    """Seed Hat Yai and regional stations."""
    print("\n[Step 1/5] Seeding Solar Stations into Database...")
    all_stations = [HAT_YAI_STATION] + OTHER_STATIONS

    for st_data in all_stations:
        stmt = select(Station).where(Station.id == st_data["id"])
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing:
            existing.name = st_data["name"]
            existing.latitude = st_data["latitude"]
            existing.longitude = st_data["longitude"]
            existing.panel_area = st_data["panel_area"]
            existing.efficiency = st_data["efficiency"]
            existing.target_capacity_kw = st_data["target_capacity_kw"]
            existing.is_active = True
            print(f"  - Updated station: {st_data['id']} ({st_data['name']})")
        else:
            station = Station(
                id=st_data["id"],
                name=st_data["name"],
                latitude=st_data["latitude"],
                longitude=st_data["longitude"],
                panel_area=st_data["panel_area"],
                efficiency=st_data["efficiency"],
                target_capacity_kw=st_data["target_capacity_kw"],
                is_active=True,
            )
            session.add(station)
            print(f"  + Added station: {st_data['id']} ({st_data['name']})")

    await session.commit()
    print("  ✓ Stations seeded successfully.")


async def seed_default_user(session):
    """Seed default grid operator user for authentication."""
    stmt = select(User).where(User.email == "operator@solardss.io")
    user = (await session.execute(stmt)).scalar_one_or_none()
    if not user:
        user = User(
            email="operator@solardss.io",
            password_hash=password_hash.hash("operator1234"),
        )
        session.add(user)
        await session.commit()
        print("  ✓ Seeded operator user (operator@solardss.io / operator1234)")
    else:
        print("  ✓ Operator user already exists (operator@solardss.io)")



async def mock_hatyai_weather_history(session, total_steps: int = 144):
    """Mock 144 consecutive 10-minute weather records (24h lookback) for Hat Yai."""
    print(f"\n[Step 2/5] Generating {total_steps} Weather History Records for Hat Yai (Lat 7.0086, Lon 100.4988)...")
    station_id = HAT_YAI_STATION["id"]
    lat = HAT_YAI_STATION["latitude"]
    lon = HAT_YAI_STATION["longitude"]

    # Clear previous weather history for clean state
    await session.execute(delete(WeatherHistory).where(WeatherHistory.station_id == station_id))
    await session.commit()

    now_utc = datetime.now(timezone.utc)
    # Align to nearest 10-minute block
    aligned_min = (now_utc.minute // 10) * 10
    end_dt = now_utc.replace(minute=aligned_min, second=0, microsecond=0)
    start_dt = end_dt - timedelta(minutes=10 * (total_steps - 1))

    records = []
    th_tz = timezone(timedelta(hours=7))

    for i in range(total_steps):
        dt = start_dt + timedelta(minutes=10 * i)
        dt_local = dt.astimezone(th_tz)
        local_hour = dt_local.hour + (dt_local.minute / 60.0)

        zenith, elevation = SolarCalculator.calculate_solar_position(lat, lon, dt)
        clearsky_ghi = SolarCalculator.calculate_clearsky_ghi(zenith)
        zenith = round(zenith, 2)

        # Realistic diurnal solar curve for Southern Thailand (Tropical Hat Yai climate)
        if 6.0 <= local_hour <= 18.5:
            # Solar peak at 12:30 PM (up to 850-920 W/m²)
            fraction = (local_hour - 6.0) / (18.5 - 6.0)
            ideal_ghi = math.sin(fraction * math.pi) * 880.0
            # Realistic cloud variation factor
            cloud_factor = 0.85 + 0.15 * math.sin(i * 0.4)
            ghi = round(max(0.0, ideal_ghi * cloud_factor), 2)
            dni = round(max(0.0, ghi * 1.15 if ghi > 150 else 0.0), 2)
            dhi = round(max(0.0, ghi * 0.28), 2)
            clearsky_ratio = round(min(1.0, max(0.0, ghi / max(1.0, clearsky_ghi))), 3)
            cloud_cover = round(max(10.0, min(95.0, (1.0 - clearsky_ratio) * 100.0)), 1)
        else:
            ghi = 0.0
            dni = 0.0
            dhi = 0.0
            clearsky_ratio = 0.0
            cloud_cover = 40.0

        # Temperature variation (25°C at night to 33.5°C afternoon)
        temp_cycle = math.sin((local_hour - 8.0) * math.pi / 12.0)
        temp = round(29.0 + (temp_cycle * 4.5), 1)

        # Humidity (inversely correlated with temperature)
        humidity = round(78.0 - (temp_cycle * 18.0), 1)

        # Surface pressure (sea level ~1010-1013 hPa)
        pressure = round(1011.5 + (0.8 * math.cos(local_hour * math.pi / 12.0)), 1)

        # Tropical wind speed (2.0 to 5.0 m/s)
        wind_speed = round(2.5 + (1.5 * abs(math.sin(i * 0.2))), 1)

        record = WeatherHistory(
            station_id=station_id,
            timestamp=dt,
            ghi=ghi,
            dni=dni,
            dhi=dhi,
            clearsky_ghi=clearsky_ghi,
            clearsky_index=clearsky_ratio,
            solar_zenith_angle=zenith,
            temperature=temp,
            relative_humidity=humidity,
            wind_speed=wind_speed,
            cloud_cover=cloud_cover,
            surface_pressure=pressure,
            source="hatyai_ground_truth_mock",
        )
        records.append(record)

    session.add_all(records)
    await session.commit()
    print(f"  ✓ Successfully inserted {len(records)} weather records for '{station_id}'")
    print(f"    - Time window: {start_dt.strftime('%Y-%m-%d %H:%M')} to {end_dt.strftime('%Y-%m-%d %H:%M')} UTC")
    return records


def extract_16_features_from_records(records: list[WeatherHistory]) -> np.ndarray:
    """Extract 16 time-series features aligned with Asia/Bangkok UTC+7 encodings."""
    th_tz = timezone(timedelta(hours=7))
    features = []

    for r in records[-144:]:
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
            float(r.surface_pressure or 1010.0),
            float(r.wind_speed),
            round(hour_sin, 6),
            round(hour_cos, 6),
            round(day_sin, 6),
            round(day_cos, 6),
            round(month_sin, 6),
            round(month_cos, 6),
        ]
        features.append(row)

    return np.array(features, dtype=np.float32)


def run_timeseries_lstm_inference(seq_144x16: np.ndarray) -> list[float]:
    """Execute Solar GHI LSTM ONNX model on the 144-step sequence."""
    model_dir = PROJECT_ROOT / "model" / "time-series"
    onnx_path = model_dir / "solar_ghi_lstm.onnx"
    fs_path = model_dir / "feature_scaler.joblib"
    ts_path = model_dir / "target_scaler.joblib"

    print(f"\n[Step 3/5] Running Solar LSTM AI Model ({onnx_path.name})...")
    session = ort.InferenceSession(str(onnx_path))
    feat_scaler = joblib.load(str(fs_path))
    tgt_scaler = joblib.load(str(ts_path))

    scaled_seq = feat_scaler.transform(seq_144x16).astype(np.float32)
    batch = np.expand_dims(scaled_seq, axis=0) # (1, 144, 16)
    inp_name = session.get_inputs()[0].name
    raw_pred = session.run(None, {inp_name: batch})[0] # (1, 18)
    unscaled = tgt_scaler.inverse_transform(raw_pred.reshape(-1, 1)).flatten()

    ghi_pred_18 = [round(float(max(0.0, v)), 2) for v in unscaled]
    print(f"  ✓ Solar LSTM 18-step GHI forecast: min={min(ghi_pred_18):.1f}, max={max(ghi_pred_18):.1f} W/m²")
    return ghi_pred_18


def run_convlstm_satellite_nowcasting() -> tuple[list[float], str, float, str]:
    """Execute ConvLSTM satellite nowcasting model for Cloud Index & Motion tracking."""
    conv_path = PROJECT_ROOT / "model" / "convlstm" / "cloud_seq2seq_12to18.onnx"
    print(f"\n[Step 4/5] Running ConvLSTM Satellite Nowcasting ({conv_path.name})...")

    # Generate 12-frame lookback geocoded for Hat Yai
    base_cloud = np.random.uniform(0.12, 0.28, size=(64, 64)).astype(np.float32)
    frames = []
    for step in range(12):
        noise = np.random.normal(0.0, 0.012, size=(64, 64)).astype(np.float32)
        frame = np.clip(base_cloud + (step * 0.005) + noise, 0.0, 1.0)
        frames.append(frame)

    sat_input = np.stack(frames, axis=0)[np.newaxis, :, np.newaxis, :, :] # (1, 12, 1, 64, 64)

    session = ort.InferenceSession(str(conv_path))
    inp_name = session.get_inputs()[0].name
    out = session.run(None, {inp_name: sat_input})[0] # (1, 18, 1, 64, 64)

    frames_18 = out[0, :, 0, :, :]
    cy, cx = frames_18.shape[1] // 2, frames_18.shape[2] // 2
    r = 2
    roi = frames_18[:, cy - r : cy + r + 1, cx - r : cx + r + 1]
    ci_values = np.clip(np.mean(roi, axis=(1, 2)), 0.0, 1.0)
    ci_list = [round(float(x), 3) for x in ci_values]

    ci_mean = float(np.mean(ci_list))
    ci_delta = float(ci_list[-1] - ci_list[0])

    if ci_mean < 0.20:
        cloud_trend = CloudTrend.CLEAR
        bess_action = "คงการชาร์จแบตเตอรี่ปกติ ไม่จำเป็นต้องสำรองไฟฉุกเฉิน (Clear Sky, high irradiance steady)"
    elif ci_mean > 0.70:
        cloud_trend = CloudTrend.OVERCAST
        bess_action = "เตรียมจ่ายไฟจาก BESS เสริมความเสถียร แดดตกต่ำต่อเนื่องยาวนาน 3 ชม. (Persistent overcast cloud layer)"
    elif ci_delta > 0.08:
        cloud_trend = CloudTrend.INWARD
        bess_action = "แจ้งเตือนแดดดรอปเฉียบพลัน! สั่งเตรียมปล่อยกำลังไฟ BESS Ramp-up รองรับ (Cloud front moving in)"
    else:
        cloud_trend = CloudTrend.OUTWARD
        bess_action = "กลุ่มเมฆกำลังพ้นสถานี แดดจะฟื้นตัวกลับมา เตรียมลดการจ่ายไฟ BESS (Cloud clearing)"

    confidence = 0.91
    print(f"  ✓ ConvLSTM 18-step Cloud Index (CI): min={min(ci_list):.3f}, max={max(ci_list):.3f}, mean={ci_mean:.3f}")
    print(f"  ✓ Cloud Motion Trend: {cloud_trend.value} | Confidence: {confidence*100:.1f}%")
    return ci_list, cloud_trend.value, confidence, bess_action


async def save_hatyai_prediction(session, ghi_raw_18: list[float], ci_18: list[float], cloud_trend: str, confidence: float, bess_action: str):
    """Fuse model outputs, evaluate physical generation and decision support, and save to DB."""
    print("\n[Step 5/5] Performing Model Fusion, Physics Calculation & Saving Prediction...")
    station_id = HAT_YAI_STATION["id"]
    panel_area = HAT_YAI_STATION["panel_area"]
    efficiency = HAT_YAI_STATION["efficiency"]
    target_kw = HAT_YAI_STATION["target_capacity_kw"]

    # Model Fusion: GHI_final(t) = GHI_lstm(t) * (1.0 - CI_t)
    ghi_modulated_18 = [
        round(max(0.0, raw * (1.0 - ci)), 1)
        for raw, ci in zip(ghi_raw_18, ci_18)
    ]

    current_ghi = ghi_modulated_18[0]
    avg_ghi = sum(ghi_modulated_18) / len(ghi_modulated_18)

    # Evaluate Rule-based Decision Engine
    decision = evaluate_decision_support(
        panel_area_m2=panel_area,
        efficiency=efficiency,
        current_ghi_w_m2=current_ghi,
        target_power_kw=target_kw,
        cloud_trend=cloud_trend,
    )

    now_utc = datetime.now(timezone.utc)
    job_id = f"infer-hatyai-{uuid.uuid4().hex[:8]}"

    prediction = Prediction(
        job_id=job_id,
        station_id=station_id,
        predicted_at=now_utc,
        forecast_horizon_hours=3,
        ghi_forecast_curve=ghi_modulated_18,
        estimated_power_kw=decision.estimated_power_kw,
        target_power_kw=target_kw,
        delta_p_kw=decision.recommended_delta_p_kw,
        cloud_trend=cloud_trend,
        confidence=confidence,
        alert_level=decision.alert_level.value,
        recommendation_text=f"{decision.recommendation_text} | BESS: {bess_action}",
        satellite_frame_url=f"/api/storage/download/satellite-cache/{station_id}_latest.png",
    )
    session.add(prediction)
    await session.commit()

    print(f"\n========================================================")
    print(f">> PREDICTION RECORD SAVED SUCCESSFULLY FOR HAT YAI")
    print(f"========================================================")
    print(f"  Station:          {HAT_YAI_STATION['name']} ({station_id})")
    print(f"  Job ID:           {job_id}")
    print(f"  Predicted At:     {now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"  Current GHI:      {current_ghi:.1f} W/m² (Modulated with ConvLSTM)")
    print(f"  Avg Forecast GHI: {avg_ghi:.1f} W/m²")
    print(f"  P_gen (Generated):{decision.estimated_power_kw:,.1f} kW")
    print(f"  P_target:         {target_kw:,.1f} kW")
    print(f"  Delta P:          {decision.recommended_delta_p_kw:,.1f} kW")
    print(f"  Cloud Trend:      {cloud_trend} (CI mean: {sum(ci_18)/len(ci_18):.3f})")
    print(f"  Alert Level:      {decision.alert_level.value}")
    print(f"  Recommendation:   {decision.recommendation_text}")
    print(f"  BESS Action:      {bess_action}")
    print(f"========================================================")


async def save_regional_station_predictions(session):
    """Seed prediction records for ST-002 to ST-005 so all stations have live backend data."""
    now_utc = datetime.now(timezone.utc)
    for st in OTHER_STATIONS:
        st_id = st["id"]
        target_kw = st["target_capacity_kw"]
        panel_area = st["panel_area"]
        eff = st["efficiency"]

        # Varied realistic weather per station
        if st_id == "ST-002":
            pgen = round(target_kw * 0.855, 1)
            alert = "Normal"
            trend = "Clear"
            recom = "กำลังการผลิตเป็นไปตามเป้าหมาย โครงข่ายเสถียร"
        elif st_id == "ST-003":
            pgen = round(target_kw * 0.883, 1)
            alert = "Normal"
            trend = "Clear"
            recom = "สภาพอากาศแจ่มใส ท้องฟ้าโปร่ง กำลังผลิตสม่ำเสมอ"
        elif st_id == "ST-004":
            pgen = round(target_kw * 0.756, 1)
            alert = "Early Warning"
            trend = "Inward"
            recom = "พบเมฆก่อตัวเล็กน้อยในพื้นที่ ควรเฝ้าระวังกำลังผลิต"
        else: # ST-005
            pgen = round(target_kw * 0.865, 1)
            alert = "Normal"
            trend = "Clear"
            recom = "กำลังผลิตปกติ ไม่มีความเสี่ยงที่ส่งผลกระทบต่อโครงข่าย"

        delta_p = round(max(0.0, target_kw - pgen), 1)
        curve = [round(pgen / (panel_area * eff * 0.001) * (1 - i * 0.015), 1) for i in range(18)]

        pred = Prediction(
            job_id=f"infer-{st_id.lower()}-{uuid.uuid4().hex[:8]}",
            station_id=st_id,
            predicted_at=now_utc,
            forecast_horizon_hours=3,
            ghi_forecast_curve=curve,
            estimated_power_kw=pgen,
            target_power_kw=target_kw,
            delta_p_kw=delta_p,
            cloud_trend=trend,
            confidence=0.88,
            alert_level=alert,
            recommendation_text=recom,
            satellite_frame_url=f"/api/storage/download/satellite-cache/{st_id}_latest.png",
        )
        session.add(pred)
    await session.commit()
    print("  ✓ Seeded live predictions for ST-002 through ST-005 in database.")


async def main():
    print("=" * 60)
    print(">> MOCKING HAT YAI STATION & CONNECTING TO AI MODELS")
    print("=" * 60)

    # 1. Initialize schema
    await create_database_schema()

    async with SessionLocal() as session:
        # Step 1: Seed stations & default operator user
        await seed_stations(session)
        await seed_default_user(session)

        # Step 2: Mock 144 steps weather history for Hat Yai
        records = await mock_hatyai_weather_history(session, total_steps=144)

        # Step 3: Extract 16 features & Run Solar GHI LSTM ONNX
        seq_144 = extract_16_features_from_records(records)
        ghi_pred_18 = run_timeseries_lstm_inference(seq_144)

        # Step 4: Run ConvLSTM Satellite Nowcasting
        ci_18, cloud_trend, confidence, bess_action = run_convlstm_satellite_nowcasting()

        # Step 5: Save prediction to DB
        await save_hatyai_prediction(session, ghi_pred_18, ci_18, cloud_trend, confidence, bess_action)

        # Step 6: Save predictions for remaining stations
        await save_regional_station_predictions(session)


if __name__ == "__main__":
    asyncio.run(main())
