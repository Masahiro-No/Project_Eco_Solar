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
                              delta_p_kw=0, cloud_trend="Clear", confidence=0.9, alert_level="Normal", recommendation_text="x"))
        await db.commit()

    app = FastAPI()
    app.include_router(ls_router, prefix="/api")
    app.include_router(inference_router, prefix="/api")

    async def _db():
        async with Session() as s:
            yield s

    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
    pool = FakePool()
    from api.jobs.service import JobService

    async def _pool():
        return pool

    JobService.get_pool = staticmethod(_pool)

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
        assert len(pool.jobs) == 1 and pool.jobs[0][0] == "train_timeseries_lstm"
        assert pool.jobs[0][2]["_queue_name"] == "train_queue" and pool.jobs[0][2]["_defer_by"] == timedelta(seconds=settings.retrain_debounce_seconds)
        settings.enable_retrain = False

        # --- Label Studio ล่ม: ยังต้องดูค่าพยากรณ์ได้ แต่บันทึก label ได้ 502 พร้อมเหตุผล
        class Broken(FakeLS):
            def get_or_create_project(self, *a, **k):
                raise RuntimeError("401 token expired")

        ls_service.LabelStudioService = Broken
        r = await c.get("/api/inference/predictions-by-date", params={"station_id": "ST-001", "date": "2026-10-02"})
        assert r.status_code == 200 and "token expired" in r.json()["label_error"] and r.json()["points"]
        r = await c.post("/api/label-studio/ground-truth/batch-submit", json={"station_id": "ST-001", "items": [{"timestamp": "2026-10-02T13:30:00", "ghi_actual": 1.0}]})
        assert r.status_code == 502 and "token expired" in r.json()["detail"]
        ls_service.LabelStudioService = FakeLS
    print("PASS http flow (predictions-by-date, batch-submit, upload, debounce retrain, LS down)")
    await engine.dispose()


if __name__ == "__main__":
    check_time_rules()
    check_sample_files()
    check_store_upsert()
    asyncio.run(check_http_flow())
