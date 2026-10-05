"""ตรวจ flow label (Label Studio จำลองในหน่วยความจำ) + อัปโหลดไฟล์ + predictions-by-date + นัด retrain.

รันจากโฟลเดอร์ backend:  python scripts/check_ground_truth_flow.py
ต้องมี aiosqlite, httpx, python-multipart, openpyxl  (ใช้ SQLite แทน Postgres เฉพาะ SELECT/INSERT ธรรมดา)
"""

import asyncio
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
for k, v in {
    "database_url": "sqlite+aiosqlite:///:memory:", "label_studio_url": "http://x", "label_studio_api_key": "k",
    "minio_endpoint": "x:9000", "minio_access_key": "a", "minio_secret_key": "b", "jwt_secret_key": "s",
    "jwt_algorithm": "HS256", "access_token_expire_minutes": "60",
}.items():
    os.environ.setdefault(k, v)

import httpx  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from api.auth.service import get_current_user  # noqa: E402
from api.inference.model import Prediction  # noqa: E402
from api.inference.router import router as inference_router  # noqa: E402
from api.ingestion.model import WeatherHistory  # noqa: E402
from api.label_studio import ground_truth as gt  # noqa: E402
from api.label_studio import file_import  # noqa: E402
from api.label_studio import service as ls_service  # noqa: E402
from api.label_studio.router import router as ls_router  # noqa: E402
from api.stations.model import Station  # noqa: E402
from core.config import settings  # noqa: E402
from db.database import Base, get_db_session  # noqa: E402

SAMPLES = Path(__file__).resolve().parent / "samples"
UTC = timezone.utc


class FakeLS:
    """Label Studio จำลอง (ข้อมูลอยู่ที่ระดับคลาส ใช้ร่วมกันทุก instance)."""

    projects: list = []
    tasks: dict = {}
    anns: dict = {}
    calls: list = []

    @classmethod
    def reset(cls):
        cls.projects, cls.tasks, cls.anns, cls.calls = [], {}, {}, []

    def get_or_create_project(self, title, label_config):
        for p in self.projects:
            if p.title == title:
                return p
        p = SimpleNamespace(id=len(self.projects) + 1, title=title, config=label_config)
        self.projects.append(p)
        return p

    def list_tasks_with_annotations(self, pid):
        return [
            SimpleNamespace(id=tid, data=t["data"], annotations=list(self.anns.get(tid, [])))
            for tid, t in self.tasks.items() if t["project"] == pid
        ]

    def create_task(self, pid, data):
        tid = len(self.tasks) + 1
        self.tasks[tid] = {"project": pid, "data": dict(data)}
        self.calls.append(("create_task", tid))
        return SimpleNamespace(id=tid)

    def create_annotation(self, task_id, result, ground_truth=True):
        aid = sum(len(v) for v in self.anns.values()) + 1
        self.anns.setdefault(task_id, []).append({"id": aid, "result": result, "was_cancelled": False, "ground_truth": ground_truth})
        self.calls.append(("create_annotation", task_id))
        return SimpleNamespace(id=aid)

    def update_task(self, task_id, data):
        self.tasks[task_id]["data"] = dict(data)
        self.calls.append(("update_task", task_id))

    def update_annotation(self, annotation_id, result, ground_truth=True):
        for anns in self.anns.values():
            for a in anns:
                if a["id"] == annotation_id:
                    a["result"] = result
        self.calls.append(("update_annotation", annotation_id))

    def list_annotations(self, task_id):
        return [SimpleNamespace(**a) for a in self.anns.get(task_id, [])]


ls_service.LabelStudioService = FakeLS  # GroundTruthStore import แบบ lazy จึงใช้ตัวจำลองนี้


class FakePool:
    def __init__(self):
        self.keys, self.jobs = {}, []

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.keys:
            return None
        self.keys[key] = value
        return True

    async def delete(self, key):
        self.keys.pop(key, None)

    async def exists(self, key):
        return 1 if key in self.keys else 0

    async def enqueue_job(self, name, *args, **kwargs):
        self.jobs.append((name, args, kwargs))

    async def close(self):
        pass


def check_time_rules():
    # ไม่มี tz = เวลาไทย; ปัดลงเป็นช่อง 10 นาที
    assert gt.parse_label_timestamp("2026-10-04 14:45") == datetime(2026, 10, 4, 7, 40, tzinfo=UTC)
    assert gt.parse_label_timestamp("2026-10-04 14:45:02") == datetime(2026, 10, 4, 7, 40, tzinfo=UTC)
    assert gt.parse_label_timestamp("2026-10-04 14:49:59") == datetime(2026, 10, 4, 7, 40, tzinfo=UTC)
    assert gt.parse_label_timestamp("2026-10-04 14:50:00") == datetime(2026, 10, 4, 7, 50, tzinfo=UTC)
    assert gt.parse_label_timestamp("2026-10-04T07:45:00Z") == datetime(2026, 10, 4, 7, 40, tzinfo=UTC)
    now = datetime.now(UTC)
    ok = gt.floor_slot(now - timedelta(days=1))
    assert gt.validate_value(500, ok) is None
    assert gt.validate_value(-1, ok).startswith("ghi_out_of_range") and gt.validate_value(2000, ok).startswith("ghi_out_of_range")
    assert gt.validate_value("x", ok) == "invalid_ghi"
    assert gt.validate_value(1, now + timedelta(days=1)) == "timestamp_in_future"
    s, e = gt.th_day_bounds(date(2026, 10, 4))
    assert s == datetime(2026, 10, 3, 17, 0, tzinfo=UTC) and e == datetime(2026, 10, 4, 17, 0, tzinfo=UTC)
    print("PASS time rules (ปัดลง, naive=เวลาไทย)")


def check_sample_files():
    results, preview = {}, {}
    for name in ("sample_solar_intensity.csv", "sample_solar_intensity.xlsx"):
        content = (SAMPLES / name).read_bytes()
        preview[name] = file_import.preview(name, content)
        p = file_import.parse_ground_truth_file(name, content, day=date(2026, 10, 4))
        assert not p.invalid, p.invalid
        results[name] = (p, {gt.parse_label_timestamp(i["timestamp"]): i["ghi_actual"] for i in p.items})
        assert p.total_rows == 59 and p.clamped_negative == 6
        assert all(gt.parse_label_timestamp(i["timestamp"]).minute % 10 == 0 for i in p.items)
        assert p.duplicates_collapsed + len(p.items) == 59 - p.outside_day
        # 12:15 เวลาไทย ซ้ำ 7 แถว -> ปัดลงเป็น 12:10 = 05:10 UTC เก็บค่าของ ID สูงสุด
        assert results[name][1][datetime(2026, 10, 4, 5, 10, tzinfo=UTC)] == 1032.89
    for pv in preview.values():
        assert pv["guessed_timestamp"] == "Date/Time" and pv["guessed_ghi"] == "Solar Intensity Value", pv
        assert len(pv["sample_rows"]) == 5 and pv["total_rows"] == 59
    csv_p, csv_d = results["sample_solar_intensity.csv"]
    xl_p, xl_d = results["sample_solar_intensity.xlsx"]
    assert csv_d == xl_d, "CSV (xx:x5) กับ XLSX (xx:x5:02) ต้องได้ช่องเวลาและค่าเหมือนกัน"
    assert (csv_p.duplicates_collapsed, csv_p.outside_day) == (xl_p.duplicates_collapsed, xl_p.outside_day)
    # วันอื่น -> ไม่มีแถวในวันนั้นเลย
    other = file_import.parse_ground_truth_file("x.csv", (SAMPLES / "sample_solar_intensity.csv").read_bytes(), day=date(2026, 10, 5))
    assert other.items == [] and other.outside_day == 59
    # เลือกคอลัมน์เอง / เลือกผิด
    c = (SAMPLES / "sample_solar_intensity.csv").read_bytes()
    assert len(file_import.parse_ground_truth_file("a.csv", c, timestamp_col="date/time", ghi_col="solar intensity value").items) == len(csv_p.items)
    for bad in ({"ghi_col": "nope"}, {"timestamp_col": "ID", "ghi_col": "ID"}):
        try:
            file_import.parse_ground_truth_file("a.csv", c, **bad)
            raise AssertionError("ควรเกิด FileImportError")
        except file_import.FileImportError:
            pass
    for fname, data in (("a.pdf", b"x"), ("a.csv", b"only,header\n")):
        try:
            file_import.read_table(fname, data)
            raise AssertionError("ควรเกิด FileImportError")
        except file_import.FileImportError:
            pass
    print(f"PASS sample files (csv == xlsx, {len(csv_p.items)} slots, {csv_p.duplicates_collapsed} dup, {csv_p.clamped_negative} clamped)")


def check_store_upsert():
    FakeLS.reset()
    store = gt.GroundTruthStore(FakeLS())
    slot = datetime(2026, 10, 2, 5, 0, tzinfo=UTC)
    row = lambda i, g: (i, slot, g, {"source": "manual"})  # noqa: E731
    s1 = store.upsert("ST-001", [row(0, 100.0)])
    assert [i.status for i in s1.items] == ["created"] and s1.changed == 1
    s2 = store.upsert("ST-001", [row(0, 100.0)])
    assert [i.status for i in s2.items] == ["unchanged"] and s2.changed == 0
    s3 = store.upsert("ST-001", [row(0, 120.0)])
    assert [i.status for i in s3.items] == ["updated"] and len(FakeLS.tasks) == 1, "ต้องอัปเดตของเดิม ไม่สร้าง task ซ้ำ"
    pid = store.project_id()
    day_s, day_e = slot - timedelta(hours=1), slot + timedelta(hours=1)
    assert store.index(pid, "ST-001", day_s, day_e)[slot].ghi == 120.0
    assert store.index(pid, "ST-002", day_s, day_e) == {}, "สถานีอื่นต้องไม่ปนกัน"
    # ผู้ใช้แก้ค่าใน Label Studio โดยตรง -> annotation ชนะ data
    FakeLS.anns[1][0]["result"] = gt.make_annotation_result(333.0)
    assert store.index(pid, "ST-001", day_s, day_e)[slot].ghi == 333.0
    print("PASS store upsert (created/unchanged/updated, annotation ชนะ data)")


async def check_http_flow():
    FakeLS.reset()
    gt.clear_label_cache()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    base = datetime(2026, 10, 2, 5, 0, tzinfo=UTC)  # 12:00 เวลาไทย
    async with Session() as db:
        db.add(Station(id="ST-001", name="t", latitude=7.0, longitude=100.5, panel_area=1000.0, efficiency=0.18, target_capacity_kw=100.0, is_active=True))
        await db.commit()
        for i in range(36):
            db.add(WeatherHistory(station_id="ST-001", timestamp=base + timedelta(minutes=10 * i), ghi=500.0 + i, dni=0, clearsky_ghi=900, clearsky_index=0.5,
                                  solar_zenith_angle=30, temperature=30, relative_humidity=60, wind_speed=1, cloud_cover=10, source="test"))
        # รอบเก่า (predicted 12:02 -> origin 12:00) และรอบใหม่ (12:32 -> origin 12:30): ช่องที่ซ้อนกันต้องใช้รอบใหม่
        for jid, at, vals in (("old", base + timedelta(minutes=2), [100.0 + i for i in range(18)]), ("new", base + timedelta(minutes=32), [200.0 + i for i in range(18)])):
            db.add(Prediction(job_id=jid, station_id="ST-001", predicted_at=at, ghi_forecast_curve=vals, estimated_power_kw=1, target_power_kw=1,
                              delta_p_kw=0, cloud_trend="Clear", confidence=0.9, alert_level="Normal", recommendation_text="x",
                              source="model", data_time=at - timedelta(minutes=2)))
        # แถวที่ไม่ได้มาจากโมเดลจริง (source ว่าง) ต้องไม่ถูกนำมาแสดงเป็นค่าทำนาย
        db.add(Prediction(job_id="seed", station_id="ST-001", predicted_at=base + timedelta(minutes=40), ghi_forecast_curve=[999.0] * 18,
                          estimated_power_kw=1, target_power_kw=1, delta_p_kw=0, cloud_trend="Clear", confidence=0.9,
                          alert_level="Normal", recommendation_text="x"))
        await db.commit()

    app = FastAPI()
    app.include_router(ls_router, prefix="/api")
    app.include_router(inference_router, prefix="/api")

    async def _db():
        async with Session() as s:
            yield s

    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1, role="admin")
    pool = FakePool()
    from api.jobs.service import JobService

    async def _pool():
        return pool

    JobService.get_pool = staticmethod(_pool)
    settings.enable_retrain = False  # เริ่มจากสถานะปิด retrain เสมอ ไม่ขึ้นกับค่า ENABLE_RETRAIN ของ container

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        # --- วิธีที่ 1: ดึงค่าพยากรณ์ของวัน
        r = await c.get("/api/inference/predictions-by-date", params={"station_id": "ST-001", "date": "2026-10-02"})
        assert r.status_code == 200, r.text
        body = r.json()
        by = {p["timestamp"]: p for p in body["points"]}
        k = lambda m: (base + timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
        k_ = lambda m: [v for t, v in by.items() if t.startswith((base + timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:%S"))][0]  # noqa: E731
        assert k_(10)["predicted_ghi"] == 100.0, "ช่อง 12:10 มีเฉพาะรอบเก่า"
        assert k_(40)["predicted_ghi"] == 200.0 and k_(40)["weather_ghi"] == 504.0, "ช่อง 12:40 ต้องใช้รอบใหม่"
        assert body["prediction_runs"] == 2 and body["label_count"] == 0 and body["label_error"] is None
        assert all(p["predicted_ghi"] != 999.0 for p in body["points"]), "แถว source ว่างต้องไม่ถูกใช้"

        # --- กราฟทั้งวัน: ช่องเวลาที่ผ่านมาแล้วใช้รอบล่าสุดที่ทำนายล่วงหน้าอย่างน้อยตามระยะที่ขอ (รอบ 12:00 = 100+i, รอบ 12:30 = 200+i)
        day = {"station_id": "ST-001", "date": "2026-10-02"}
        r = await c.get("/api/inference/predictions-by-date", params={**day, "lead_minutes": 60})
        assert r.status_code == 200, r.text
        v = {p["timestamp"][11:16]: p for p in r.json()["points"]}
        assert v["06:00"]["forecast_ghi"] == 105.0 and v["06:00"]["forecast_lead_minutes"] == 60, "13:00 = รอบ 12:00 ล่วงหน้า 60 นาที"
        assert v["06:30"]["forecast_ghi"] == 205.0, "13:30 = รอบ 12:30 ล่วงหน้า 60 นาที"
        assert v["05:40"]["forecast_ghi"] == 103.0 and v["05:40"]["forecast_lead_minutes"] == 40, "12:40 ไม่มีรอบที่ล่วงหน้าถึง 60 นาที ใช้รอบ 12:00 (40 นาที)"
        assert v["05:30"]["forecast_ghi"] is None and v["05:40"]["predicted_ghi"] == 200.0, "12:30 มีแต่รอบที่ล่วงหน้า 30 นาที ห่างจาก 60 เกินไป"
        assert v["06:40"]["forecast_ghi"] == 206.0 and v["06:40"]["forecast_lead_minutes"] == 70, "13:40 = รอบ 12:30 (70 นาที) ไม่ใช่รอบ 12:00 ที่เก่ากว่า"
        assert v["05:40"]["clearsky_ghi"] == 900.0 and r.json()["lead_minutes"] == 60
        r = await c.get("/api/inference/predictions-by-date", params={**day, "lead_minutes": 10})
        v = {p["timestamp"][11:16]: p for p in r.json()["points"]}
        assert (v["05:10"]["forecast_ghi"], v["05:40"]["forecast_ghi"], v["05:20"]["forecast_ghi"]) == (100.0, 200.0, 101.0)
        assert v["05:20"]["forecast_lead_minutes"] == 20, "12:20 ไม่มีรอบที่เริ่ม 12:10 จึงใช้รอบ 12:00 และบอกระยะจริง"
        r = await c.get("/api/inference/predictions-by-date", params={**day, "lead_minutes": 15})
        assert r.status_code == 422, "ระยะพยากรณ์ต้องเป็นทวีคูณของ 10 นาที"

        # --- ส่ง label แบบแก้เอง (เวลาไทย ไม่มี tz; 12:44 -> ปัดลง 12:40)
        pool.keys.clear()
        r = await c.post("/api/label-studio/ground-truth/batch-submit", json={"station_id": "ST-001", "source": "manual", "items": [
            {"timestamp": "2026-10-02T12:44:00", "ghi_actual": 250.0},
            {"timestamp": "2026-10-02T17:30:00", "ghi_actual": 10.0},
            {"timestamp": "2026-10-02T12:50:00", "ghi_actual": 5000.0},
            {"timestamp": "ไม่ใช่เวลา", "ghi_actual": 1.0},
        ]})
        assert r.status_code == 200, r.text
        b = r.json()
        assert (b["created"], b["updated"], b["unchanged"]) == (2, 0, 0) and sorted(x["index"] for x in b["rejected"]) == [2, 3]
        assert b["retrain_enqueued"] is False and b["retrain_status"].startswith("retrain_disabled")

        # --- ส่งซ้ำ: ไม่มีอะไรเปลี่ยน / แก้ค่า -> อัปเดต
        r = await c.post("/api/label-studio/ground-truth/batch-submit", json={"station_id": "ST-001", "items": [{"timestamp": "2026-10-02T12:40:00", "ghi_actual": 250.0}]})
        assert r.json()["unchanged"] == 1 and len(FakeLS.tasks) == 2
        r = await c.post("/api/label-studio/ground-truth/batch-submit", json={"station_id": "ST-001", "items": [{"timestamp": "2026-10-02T12:40:00", "ghi_actual": 260.0}]})
        assert r.json()["updated"] == 1 and len(FakeLS.tasks) == 2
        r = await c.post("/api/label-studio/ground-truth/batch-submit", json={"station_id": "ST-999", "items": [{"timestamp": "2026-10-02T12:40:00", "ghi_actual": 1.0}]})
        assert r.status_code == 404

        r = await c.get("/api/inference/predictions-by-date", params={"station_id": "ST-001", "date": "2026-10-02"})
        body = r.json()
        by = {p["timestamp"]: p for p in body["points"]}
        k40 = [v for t, v in by.items() if t.startswith("2026-10-02T05:40")][0]
        assert k40["label_ghi"] == 260.0 and k40["predicted_ghi"] == 200.0
        assert body["label_count"] == 2 and body["matched_label_count"] == 1 and body["mae_vs_label"] == 60.0
        # ความคลาดเคลื่อนที่ระยะที่ขอ: ช่อง 12:40 มีค่าจริง 260 และค่าที่ทำนายล่วงหน้า 10 นาที = 200 (ไม่มีเส้น LSTM จึงไม่นับ)
        r = await c.get("/api/inference/predictions-by-date", params={**day, "lead_minutes": 10})
        assert r.json()["view_matched_label_count"] == 0 and r.json()["view_mae_vs_label"] is None
        k1730 = [v for t, v in by.items() if t.startswith("2026-10-02T10:30")][0]
        assert k1730["label_ghi"] == 10.0 and k1730["predicted_ghi"] is None

        # --- วิธีที่ 2: อัปโหลดไฟล์ (preview -> เลือกคอลัมน์ -> นำเข้า)
        for name in ("sample_solar_intensity.csv", "sample_solar_intensity.xlsx"):
            content = (SAMPLES / name).read_bytes()
            r = await c.post("/api/label-studio/ground-truth/upload/preview", files={"file": (name, content)})
            assert r.status_code == 200 and r.json()["guessed_ghi"] == "Solar Intensity Value", r.text
            form = {"station_id": "ST-001", "date": "2026-10-04", "timestamp_col": "Date/Time", "ghi_col": "Solar Intensity Value"}
            r = await c.post("/api/label-studio/ground-truth/upload", data=form, files={"file": (name, content)})
            assert r.status_code == 200, r.text
            u = r.json()
            if name.endswith(".csv"):
                first = u
                assert u["created"] == 53 and u["clamped_negative"] == 6 and u["total_rows"] == 59 and u["outside_day"] == 0
            else:  # ไฟล์เดียวกันอีกรูปแบบ -> ช่องเดิมทั้งหมด ไม่มีอะไรเปลี่ยน
                assert u["created"] == 0 and u["unchanged"] == 53 and u["duplicates_collapsed"] == first["duplicates_collapsed"], u
        r = await c.post("/api/label-studio/ground-truth/upload", data={"station_id": "ST-001", "date": "2026-10-05"}, files={"file": ("a.csv", (SAMPLES / "sample_solar_intensity.csv").read_bytes())})
        assert r.status_code == 422 and "2026-10-05" in r.json()["detail"]
        r = await c.post("/api/label-studio/ground-truth/upload", data={"station_id": "ST-001", "date": "2026-10-04", "ghi_col": "nope"}, files={"file": ("a.csv", (SAMPLES / "sample_solar_intensity.csv").read_bytes())})
        assert r.status_code == 422
        r = await c.post("/api/label-studio/ground-truth/upload/preview", files={"file": ("a.pdf", b"x")})
        assert r.status_code == 422

        # --- endpoint เดี่ยวเดิม (/ground-truth/submit)
        r = await c.post("/api/label-studio/ground-truth/submit", json={"station_id": "ST-001", "timestamp": "2026-10-02T13:00:00", "ghi_actual": 400.0})
        assert r.status_code == 200 and r.json()["task_id"] > 0, r.text

        # --- นัด retrain: เปิด ENABLE_RETRAIN -> นัดครั้งเดียว ส่งซ้ำรวมเป็นรอบเดียว
        settings.enable_retrain = True
        pool.keys.clear(); pool.jobs.clear()
        r1 = await c.post("/api/label-studio/ground-truth/batch-submit", json={"station_id": "ST-001", "items": [{"timestamp": "2026-10-02T13:10:00", "ghi_actual": 410.0}]})
        r2 = await c.post("/api/label-studio/ground-truth/batch-submit", json={"station_id": "ST-001", "items": [{"timestamp": "2026-10-02T13:20:00", "ghi_actual": 420.0}]})
        r3 = await c.post("/api/label-studio/ground-truth/batch-submit", json={"station_id": "ST-001", "items": [{"timestamp": "2026-10-02T13:20:00", "ghi_actual": 420.0}]})
        assert r1.json()["retrain_enqueued"] is True and r2.json()["retrain_enqueued"] is False
        assert r2.json()["retrain_status"].startswith("already_scheduled") and r3.json()["retrain_status"] == "no_new_labels"
        retrains = [j for j in pool.jobs if j[0] == "train_timeseries_lstm"]
        assert len(retrains) == 1, "บันทึกสองครั้งติดกัน = retrain รอบเดียว"
        assert retrains[0][2]["_queue_name"] == "train_queue" and retrains[0][2]["_defer_by"] == timedelta(seconds=settings.retrain_debounce_seconds)
        # การตรวจสูตรแสงกับค่าวัดจริง: นัดเองหลังบันทึก รวมการบันทึกที่ติดกันเป็นรอบเดียว และไม่ขึ้นกับ ENABLE_RETRAIN
        checks = [j for j in pool.jobs if j[0] == "check_satellite_calibration"]
        assert len(checks) == 1 and checks[0][2]["_queue_name"] == "train_queue"
        assert checks[0][2]["_defer_by"] == timedelta(seconds=gt.CALIBRATION_CHECK_DELAY_SECONDS)
        settings.enable_retrain = False
        pool.keys.clear(); pool.jobs.clear()
        r = await c.post("/api/label-studio/ground-truth/batch-submit", json={"station_id": "ST-001", "items": [{"timestamp": "2026-10-02T13:40:00", "ghi_actual": 430.0}]})
        assert r.json()["retrain_enqueued"] is False and [j[0] for j in pool.jobs] == ["check_satellite_calibration"]

        # --- สถานะการเทียบสูตรแสงของสถานี (อ่านจากไฟล์ calibration ที่ trainer เขียน)
        import json as _json
        import tempfile

        root = Path(tempfile.mkdtemp())
        (root / "satellite").mkdir()
        os.environ["SOLAR_MODEL_ROOT"] = str(root)
        status_of = lambda sid: c.get("/api/label-studio/ground-truth/calibration-status", params={"station_id": sid})  # noqa: E731
        r = await status_of("ST-001")
        assert r.status_code == 200 and r.json()["state"] == "no_calibration" and r.json()["pending"] is True, r.text
        (root / "satellite" / "ghi_calibration.json").write_text(_json.dumps({
            "intercept": 1.3, "slope": 3.1, "stations": ["ST-002"], "pairs": 93, "mae_leave_one_day_out": 0.2, "min_pairs": 30,
            "checked": {"ST-003": {"fitted": False, "pairs": 84, "mae": 0.2017}}, "insufficient": {"ST-001": {"pairs": 7}},
            "checked_at": "2026-10-05 11:39:08 UTC",
        }), encoding="utf-8")
        pool.keys.clear()
        r = await status_of("ST-001")
        assert (r.json()["state"], r.json()["pairs"], r.json()["min_pairs"], r.json()["pending"]) == ("insufficient", 7, 30, False)
        assert (await status_of("ST-999")).status_code == 404
        async with Session() as db:
            for sid in ("ST-002", "ST-003", "ST-004"):
                db.add(Station(id=sid, name="t", latitude=7.0, longitude=100.5, panel_area=1000.0, efficiency=0.18, target_capacity_kw=100.0, is_active=True))
            await db.commit()
        assert [(await status_of(s)).json()["state"] for s in ("ST-002", "ST-003", "ST-004")] == ["fitted", "checked", "not_checked"]
        assert (await status_of("ST-003")).json()["mae"] == 0.2017
        os.environ.pop("SOLAR_MODEL_ROOT")
        settings.enable_retrain = False

        # --- Label Studio ล่ม: ยังต้องดูค่าพยากรณ์ได้ แต่บันทึก label ได้ 502 พร้อมเหตุผล
        class Broken(FakeLS):
            def get_or_create_project(self, *a, **k):
                raise RuntimeError("401 token expired")

        ls_service.LabelStudioService = Broken
        gt.clear_label_cache()  # ไม่มีสำเนาในหน่วยความจำ (เช่น API เพิ่งเริ่ม): ต้องเห็นข้อผิดพลาดของ Label Studio
        r = await c.get("/api/inference/predictions-by-date", params={"station_id": "ST-001", "date": "2026-10-02"})
        assert r.status_code == 200 and "token expired" in r.json()["label_error"] and r.json()["points"]
        r = await c.post("/api/label-studio/ground-truth/batch-submit", json={"station_id": "ST-001", "items": [{"timestamp": "2026-10-02T13:30:00", "ghi_actual": 1.0}]})
        assert r.status_code == 502 and "token expired" in r.json()["detail"]
        ls_service.LabelStudioService = FakeLS
    print("PASS http flow (predictions-by-date, batch-submit, upload, debounce retrain, LS down)")
    await engine.dispose()


def check_frame_review():
    """Automatic hints of the satellite frame review (pure functions)."""
    import io as _io

    import numpy as np
    from PIL import Image

    from api.frame_review.service import analyse_frame, flag_jumps

    def png(arr):
        buf = _io.BytesIO()
        Image.fromarray((arr * 255).astype("uint8")).save(buf, format="PNG")
        return buf.getvalue()

    lat, lon = 7.0086, 100.4988
    noon = datetime(2026, 10, 4, 5, 0, tzinfo=timezone.utc)      # 12:00 เวลาไทย
    night = datetime(2026, 10, 4, 17, 0, tzinfo=timezone.utc)    # 00:00 เวลาไทย
    assert analyse_frame(png(np.zeros((64, 64))), lat, lon, night) is None            # ภาพกลางคืนไม่นำมาตรวจ
    assert analyse_frame(png(np.zeros((64, 64))), lat, lon, noon)["flags"] == ["blank"]
    half = np.full((64, 64), 0.2)
    half[:, :20] = 0.0
    assert analyse_frame(png(half), lat, lon, noon)["flags"] == ["partial"]
    clear = analyse_frame(png(np.full((64, 64), 0.1)), lat, lon, noon)
    assert clear["flags"] == [] and clear["cloud_pct"] == 0.0
    items = [{"timestamp": noon + timedelta(minutes=10 * i), "rho": r, "flags": []} for i, r in enumerate((0.15, 0.60, 0.16))]
    flag_jumps(items)
    assert [it["flags"] for it in items] == [[], ["jump"], []]
    print("PASS frame review (night skipped, blank / partial / jump hints)")


def check_weather_grid():
    """The LSTM input window is on the 10-minute grid (pure function)."""
    from api.inference.weather_grid import build_feature_window, slot_of

    def row(ts, ghi=500.0, **kw):
        base = dict(timestamp=ts, ghi=ghi, dni=300.0, dhi=None, clearsky_ghi=800.0, solar_zenith_angle=30.0,
                    temperature=30.0, relative_humidity=70.0, surface_pressure=None, wind_speed=2.0)
        base.update(kw)
        return SimpleNamespace(**base)

    t0 = datetime(2026, 10, 5, 3, 0, tzinfo=timezone.utc)
    assert slot_of(t0 + timedelta(minutes=15)) == t0 + timedelta(minutes=20)        # :15 -> :20 (เหมือนตอนเทรน)
    assert slot_of(t0 + timedelta(minutes=14)) == t0 + timedelta(minutes=10)

    # แถวปนกันแบบในฐานข้อมูลจริง: ทุก 10 นาที + แถว :15 และ :45
    stamps = sorted({t0 + timedelta(minutes=m) for h in range(0, 8) for m in (h * 60 + x for x in (0, 10, 15, 20, 30, 40, 45, 50))})
    feats, end, reason = build_feature_window([row(ts, ghi=float(i)) for i, ts in enumerate(stamps)], 36)
    assert reason is None and len(feats) == 36 and len(feats[0]) == 16
    assert end == slot_of(stamps[-1])
    first_slot = end - timedelta(minutes=350)                                       # 36 ช่อง = 350 นาที ไม่ใช่ 260
    i_first = stamps.index(first_slot)
    assert feats[0][0] == float(i_first)
    assert feats[0][2] == 0.0 and feats[0][8] == 1008.0                             # ค่าเริ่มต้นของ DHI และความกดอากาศ
    assert feats[0][5] == min(1.0, feats[0][0] / 800.0)                             # clearsky_ratio คิดใหม่จาก GHI

    # ช่องว่าง 20 นาที: เติมเชิงเส้น; ช่องว่าง 30 นาที: ใช้ไม่ได้
    reg = [t0 + timedelta(minutes=10 * i) for i in range(40)]
    ok, _, reason = build_feature_window([row(ts, ghi=float(i)) for i, ts in enumerate(reg) if i not in (20, 21)], 36)
    assert reason is None and ok[20 - 4][0] == 20.0 and ok[21 - 4][0] == 21.0
    bad, _, reason = build_feature_window([row(ts) for i, ts in enumerate(reg) if i not in (20, 21, 22)], 36)
    assert bad is None and reason.startswith("gap_in_history")
    short, _, reason = build_feature_window([row(ts) for ts in reg[:20]], 36)
    assert short is None and reason.startswith("insufficient_history")
    print("PASS weather grid (10-minute slots, mixed rows, gap rules)")


def check_weather_ingestion():
    """A weather row comes only from values Open-Meteo gave (pure functions)."""
    from api.ingestion.normalizer import MissingWeatherValue, OPEN_METEO_VARIABLES, WeatherDataNormalizer

    def refuses(call, key):
        try:
            call()
        except MissingWeatherValue as e:
            return key in str(e)
        return False

    # รอบสด: ครบทุกค่าจึงได้แถว; ขาดหรือเป็น null แม้ค่าเดียว ไม่มีแถว
    current = {"time": "2026-10-05T03:15", "temperature_2m": 31.2, "relative_humidity_2m": 64, "surface_pressure": 1006.4,
               "wind_speed_10m": 2.1, "cloud_cover": 40, "direct_normal_irradiance": 512.0, "diffuse_radiation": 228.0,
               "shortwave_radiation": 640.0}
    rec = WeatherDataNormalizer.normalize_open_meteo({"current": current}, "ST-TEST-99", lat=7.0, lon=100.5)
    assert (rec.temperature, rec.relative_humidity, rec.surface_pressure, rec.dhi) == (31.2, 64.0, 1006.4, 228.0)   # DHI คือค่าของ Open-Meteo
    assert rec.timestamp == datetime(2026, 10, 5, 3, 15, tzinfo=timezone.utc)
    for key in ("time",) + OPEN_METEO_VARIABLES:
        for broken in ({k: v for k, v in current.items() if k != key}, {**current, key: None}):
            assert refuses(lambda: WeatherDataNormalizer.normalize_open_meteo({"current": broken}, "ST-TEST-99", lat=7.0, lon=100.5), key)

    # ดึงย้อนหลัง: ค่าทุก 15 นาที 03:00-05:00 (ค่า = จำนวนนาทีหลัง 03:00) ลงช่อง 10 นาที
    start = datetime(2026, 10, 5, 3, 0, tzinfo=timezone.utc)

    def minutely(holes=()):
        out = {"time": [(start + timedelta(minutes=15 * i)).strftime("%Y-%m-%dT%H:%M") for i in range(9)]}
        out.update({k: [15.0 * i for i in range(9)] for k in OPEN_METEO_VARIABLES})
        out["temperature_2m"] = [None if i in holes else v for i, v in enumerate(out["temperature_2m"])]
        return out

    def slots(rows):
        return [int((t.to_pydatetime() - start).total_seconds() // 60) for t in rows.index]

    full = WeatherDataNormalizer.open_meteo_ten_minute_rows(minutely())
    assert slots(full) == list(range(0, 121, 10))
    assert all(abs(v - m) < 1e-9 for c in OPEN_METEO_VARIABLES for v, m in zip(full[c], slots(full)))    # เส้นตรงตามเวลา
    # ค่า 03:45 และ 04:00 ขาด: ช่องระหว่าง 03:30 กับ 04:15 ไม่ถูกเติม
    assert slots(WeatherDataNormalizer.open_meteo_ten_minute_rows(minutely(holes=(3, 4)))) == [0, 10, 20, 30, 80, 90, 100, 110, 120]
    # ค่าแรกและค่าสุดท้ายขาด: ไม่ลากค่าข้างเคียงไปเติมที่ปลาย
    assert slots(WeatherDataNormalizer.open_meteo_ten_minute_rows(minutely(holes=(0, 8)))) == list(range(20, 101, 10))
    # คำตอบไม่มีตัวแปรนั้นเลย
    no_pressure = {k: v for k, v in minutely().items() if k != "surface_pressure"}
    assert refuses(lambda: WeatherDataNormalizer.open_meteo_ten_minute_rows(no_pressure), "surface_pressure")
    print("PASS weather ingestion (missing value -> no row, a gap in the source stays a gap)")


if __name__ == "__main__":
    check_weather_grid()
    check_weather_ingestion()
    check_frame_review()
    check_time_rules()
    check_sample_files()
    check_store_upsert()
    asyncio.run(check_http_flow())
