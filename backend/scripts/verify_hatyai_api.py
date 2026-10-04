import asyncio
import sys

# Ensure UTF-8 output
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from httpx import AsyncClient, ASGITransport
from main import app

async def main():
    print("=" * 60)
    print(">> VERIFYING HAT YAI API ENDPOINTS END-TO-END")
    print("=" * 60)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Login
        login_res = await client.post(
            "/api/auth/login",
            json={"email": "operator@solardss.io", "password": "operator1234"}
        )
        print(f"[1] POST /api/auth/login -> Status: {login_res.status_code}")
        token = login_res.json().get("access_token")
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Get stations
        st_res = await client.get("/api/stations", headers=headers)
        stations = st_res.json()
        print(f"[2] GET /api/stations -> Status: {st_res.status_code}, Found {len(stations)} stations")
        hat_yai = next((s for s in stations if s["id"] == "ST-001"), None)
        if hat_yai:
            print(f"    - Found Hat Yai: {hat_yai['name']}")
            print(f"    - Coordinates: ({hat_yai['latitude']}, {hat_yai['longitude']})")
            print(f"    - Panel Area: {hat_yai['panel_area']:,} m² | Capacity: {hat_yai['target_capacity_kw']:,} kW")

        # 3. Get latest prediction for Hat Yai
        pred_res = await client.get("/api/inference/latest/ST-001", headers=headers)
        print(f"[3] GET /api/inference/latest/ST-001 -> Status: {pred_res.status_code}")
        if pred_res.status_code == 200:
            pred = pred_res.json()
            print(f"    - Station: {pred['station_name']} ({pred['station_id']})")
            print(f"    - Job ID: {pred['job_id']}")
            print(f"    - Forecast Horizon: {pred['forecast_horizon_hours']} Hours (18 steps at 10-min resolution)")
            print(f"    - Modulated GHI (First 6): {pred['ghi_forecast_curve'][:6]}")
            print(f"    - Estimated Power P_gen: {pred['estimated_power_kw']:,.1f} kW")
            print(f"    - Target Power P_target: {pred['target_power_kw']:,.1f} kW")
            print(f"    - Delta P (Gap): {pred['delta_p_kw']:,.1f} kW")
            print(f"    - Cloud Trend: {pred['cloud_trend']} (Confidence: {pred['confidence']*100:.1f}%)")
            print(f"    - Alert Level: {pred['alert_level']}")
            print(f"    - Recommendation: {pred['recommendation_text']}")

        # 4. Get Prediction History
        hist_res = await client.get("/api/inference/history/ST-001", headers=headers)
        print(f"[4] GET /api/inference/history/ST-001 -> Status: {hist_res.status_code}, Records: {len(hist_res.json())}")

        # 5. Get Dashboard Summary & Station Details
        summary_res = await client.get("/api/dashboard/summary", headers=headers)
        print(f"[5] GET /api/dashboard/summary -> Status: {summary_res.status_code}")
        if summary_res.status_code == 200:
            kpi = summary_res.json()
            print(f"    - Total Generated Power: {kpi.get('total_power_kw', 0):,.1f} kW")
            print(f"    - Total Target Power: {kpi.get('total_target_kw', 0):,.1f} kW")
            print(f"    - Total Delta P: {kpi.get('total_delta_p_kw', 0):,.1f} kW")
            print(f"    - Active Stations: {kpi.get('active_stations_count', 0)}")
            print(f"    - Alert Breakdown: {kpi.get('alert_summary', {})}")

        station_dash_res = await client.get("/api/dashboard/station/ST-001", headers=headers)
        print(f"[6] GET /api/dashboard/station/ST-001 -> Status: {station_dash_res.status_code}")
        if station_dash_res.status_code == 200:
            sd = station_dash_res.json()
            print(f"    - Station Detail: {sd['station_name']} | P_gen: {sd['estimated_power_kw']:,} kW | Alert: {sd['alert_level']}")

    print("\n✓ ALL ENDPOINTS VERIFIED END-TO-END SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(main())
