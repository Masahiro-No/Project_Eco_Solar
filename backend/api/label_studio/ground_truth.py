"""Ground-truth GHI labels — เก็บใน Label Studio (project "Solar GHI Ground Truth Verification").

หนึ่ง label = หนึ่ง task (data: station_id, timestamp[UTC, ช่อง 10 นาที], ghi_actual, ...) + หนึ่ง annotation (ground_truth=True,
ค่าอยู่ใน result[from_name="ghi"].value.number). คีย์ไม่ซ้ำ = (station_id, ช่องเวลา) — ส่งซ้ำจะ "อัปเดต" ไม่สร้างใหม่.

กติกาเวลา:
- เวลาที่ไม่มี timezone ถือเป็นเวลาไทย (UTC+7)
- ปัดเวลา "ลง" เป็นช่อง 10 นาที (12:05 -> 12:00, 12:09:59 -> 12:00) เพราะระบบเราบันทึกข้อมูลที่ xx:x0
"""

from __future__ import annotations

import json
import math
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from core.config import settings

SLOT_SECONDS = 600
TH_TZ = timezone(timedelta(hours=7))
GHI_PROJECT_TITLE = "Solar GHI Ground Truth Verification"
MAX_GHI = 1500.0
RETRAIN_SCHEDULED_KEY = "retrain:timeseries:scheduled"  # ต้องตรงกับ service/training/retrain_timeseries.py


# ----------------------------------------------------------------------------- เวลา / validation
def floor_slot(dt: datetime) -> datetime:
    """ปัดลงเป็นช่อง 10 นาที (คืน datetime UTC)."""
    epoch = dt.astimezone(timezone.utc).timestamp()
    return datetime.fromtimestamp(math.floor(epoch / SLOT_SECONDS) * SLOT_SECONDS, tz=timezone.utc)


def parse_label_timestamp(value: str | datetime) -> datetime:
    """ISO string / datetime -> ช่องเวลา 10 นาที (UTC). ไม่มี timezone = เวลาไทย."""
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TH_TZ)
    return floor_slot(dt)


def th_day_bounds(day: date) -> tuple[datetime, datetime]:
    """ขอบเขตของ 'วัน' ตามเวลาไทย เป็น UTC: [00:00, 24:00)."""
    start = datetime(day.year, day.month, day.day, tzinfo=TH_TZ).astimezone(timezone.utc)
    return start, start + timedelta(days=1)


def validate_value(ghi: Any, slot: datetime, now: Optional[datetime] = None) -> Optional[str]:
    """คืนเหตุผลที่ใช้ไม่ได้ หรือ None ถ้าผ่าน."""
    try:
        g = float(ghi)
    except (TypeError, ValueError):
        return "invalid_ghi"
    if not math.isfinite(g) or g < 0 or g > MAX_GHI:
        return f"ghi_out_of_range (0-{int(MAX_GHI)} W/m²)"
    if slot > (now or datetime.now(timezone.utc)) + timedelta(minutes=10):
        return "timestamp_in_future"
    return None


# ----------------------------------------------------------------------------- Label Studio store
@dataclass
class StoredLabel:
    task_id: int
    annotation_id: Optional[int]
    ghi: float


@dataclass
class ItemResult:
    index: int
    status: str  # created | updated | unchanged | rejected
    reason: Optional[str] = None
    task_id: Optional[int] = None
    annotation_id: Optional[int] = None


@dataclass
class UpsertSummary:
    items: list[ItemResult] = field(default_factory=list)

    def count(self, status: str) -> int:
        return sum(1 for i in self.items if i.status == status)

    @property
    def changed(self) -> int:
        return self.count("created") + self.count("updated")

    @property
    def rejected(self) -> list[dict[str, Any]]:
        return [{"index": i.index, "reason": i.reason or "error"} for i in self.items if i.status == "rejected"]


def _get(obj: Any, name: str, default: Any = None) -> Any:
    return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)


def task_ghi(task: Any) -> tuple[Optional[float], Optional[int]]:
    """ค่า GHI + annotation id ของ task (annotation ชนะ data เพราะผู้ใช้อาจแก้ใน Label Studio)."""
    for ann in reversed(list(_get(task, "annotations", None) or [])):
        if _get(ann, "was_cancelled", False):
            continue
        for item in _get(ann, "result", None) or []:
            if _get(item, "from_name") == "ghi":
                v = _get(_get(item, "value", {}) or {}, "number")
                if v is not None:
                    return float(v), _get(ann, "id")
    v = (_get(task, "data", {}) or {}).get("ghi_actual")
    return (float(v) if v is not None else None), None


def make_task_data(station_id: str, slot: datetime, ghi: float, extra: dict[str, Any]) -> dict[str, Any]:
    return {
        "station_id": station_id,
        "timestamp": slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ghi_actual": ghi,
        "temperature": extra.get("temperature"),
        "relative_humidity": extra.get("relative_humidity"),
        "notes": extra.get("notes"),
        "source": extra.get("source"),
    }


def make_annotation_result(ghi: float) -> list[dict[str, Any]]:
    return [{"value": {"number": ghi}, "from_name": "ghi", "to_name": "station", "type": "number"}]


# Reading every label from Label Studio takes 10-30 seconds, so the API keeps what it read:
#   younger than LABEL_CACHE_SECONDS      answered from memory
#   older, up to LABEL_CACHE_MAX_SECONDS  answered from memory while a background thread reads again
#   older than that, or nothing read yet  read before answering (an unreachable Label Studio shows as an error)
# Labels saved through this API go into the memory copy at once. A value edited directly in Label Studio
# shows up after the next read.
LABEL_CACHE_SECONDS = 120
LABEL_CACHE_MAX_SECONDS = 3600
_cache: dict[str, Any] = {"labels": None, "at": 0.0, "project_id": None, "refreshing": False}
_cache_lock = threading.Lock()  # one full read at a time


def clear_label_cache() -> None:
    """Forget what was read from Label Studio (next read goes to Label Studio)."""
    _cache.update(labels=None, at=0.0, project_id=None, refreshing=False)


def warm_label_cache() -> None:
    """Read the labels once at API start so the first page does not wait for it (errors are left for that page)."""
    try:
        store = GroundTruthStore()
        store._all_labels(store.project_id(), fresh=False)
    except Exception:  # noqa: BLE001
        pass


class GroundTruthStore:
    """อ่าน/เขียน label ผ่าน Label Studio API (ใช้ LabelStudioService เดิม)."""

    def __init__(self, svc: Any = None) -> None:
        self._cached = svc is None  # a service passed in by the caller is read every time
        if svc is None:
            from api.label_studio.service import LabelStudioService

            svc = LabelStudioService()
        self.svc = svc

    def project_id(self) -> int:
        if self._cached and _cache["project_id"] is not None and _cache["labels"] is not None:
            return _cache["project_id"]
        from api.label_studio.controller import CONFIG_TEMPLATES

        pid = self.svc.get_or_create_project(GHI_PROJECT_TITLE, CONFIG_TEMPLATES["solar_ghi_verify"]).id
        if self._cached:
            _cache["project_id"] = pid
        return pid

    def _read_all(self, project_id: int) -> dict[tuple[str, datetime], StoredLabel]:
        """Every label of the project from Label Studio -> {(station, slot): StoredLabel}."""
        out: dict[tuple[str, datetime], StoredLabel] = {}
        for t in self.svc.list_tasks_with_annotations(project_id):
            data = _get(t, "data", {}) or {}
            if not data.get("station_id") or not data.get("timestamp"):
                continue
            try:
                slot = parse_label_timestamp(data["timestamp"])
            except ValueError:
                continue
            ghi, ann_id = task_ghi(t)
            if ghi is not None:
                out[(data["station_id"], slot)] = StoredLabel(task_id=int(_get(t, "id")), annotation_id=ann_id, ghi=ghi)
        return out

    def _refresh_in_background(self, project_id: int) -> None:
        if _cache["refreshing"]:
            return
        _cache["refreshing"] = True

        def run() -> None:
            try:
                with _cache_lock:
                    labels = self._read_all(project_id)
                    _cache.update(labels=labels, at=time.monotonic())
            except Exception:  # noqa: BLE001  keep what we have; past LABEL_CACHE_MAX_SECONDS the error reaches the page
                pass
            finally:
                _cache["refreshing"] = False

        threading.Thread(target=run, name="label-cache-refresh", daemon=True).start()

    def _all_labels(self, project_id: int, fresh: bool) -> dict[tuple[str, datetime], StoredLabel]:
        if not self._cached:
            return self._read_all(project_id)
        labels, age = _cache["labels"], time.monotonic() - _cache["at"]
        if labels is not None and not fresh:
            if age < LABEL_CACHE_SECONDS:
                return labels
            if age < LABEL_CACHE_MAX_SECONDS:
                self._refresh_in_background(project_id)
                return labels
        with _cache_lock:
            if not fresh and _cache["labels"] is not None and time.monotonic() - _cache["at"] < LABEL_CACHE_SECONDS:
                return _cache["labels"]  # another request read it while this one waited
            labels = self._read_all(project_id)
            _cache.update(labels=labels, at=time.monotonic())
            return labels

    def _remember(self, station_id: str, slot: datetime, label: StoredLabel) -> None:
        if self._cached and _cache["labels"] is not None:
            _cache["labels"][(station_id, slot)] = label

    def index(self, project_id: int, station_id: str, start: datetime, end: datetime, fresh: bool = False) -> dict[datetime, StoredLabel]:
        """label ของสถานีในช่วง [start, end) -> {ช่องเวลา: StoredLabel}. fresh=True อ่านจาก Label Studio ใหม่เสมอ."""
        return {
            slot: label
            for (sid, slot), label in self._all_labels(project_id, fresh).items()
            if sid == station_id and start <= slot < end
        }

    def upsert(self, station_id: str, rows: list[tuple[int, datetime, float, dict[str, Any]]]) -> UpsertSummary:
        """rows = [(index, slot, ghi, extra)] ที่ผ่าน validation แล้ว. ช่องเวลาที่มีอยู่แล้ว -> อัปเดต, ไม่มี -> สร้าง."""
        summary = UpsertSummary()
        if not rows:
            return summary
        pid = self.project_id()
        slots = [r[1] for r in rows]
        # read from Label Studio itself before writing: a slot that already has a task must be updated, not duplicated
        existing = self.index(pid, station_id, min(slots), max(slots) + timedelta(seconds=1), fresh=True)

        for index, slot, ghi, extra in rows:
            data = make_task_data(station_id, slot, ghi, extra)
            try:
                cur = existing.get(slot)
                if cur is None:
                    task = self.svc.create_task(pid, data)
                    ann = self.svc.create_annotation(task_id=task.id, result=make_annotation_result(ghi), ground_truth=True)
                    summary.items.append(ItemResult(index, "created", task_id=task.id, annotation_id=ann.id))
                    self._remember(station_id, slot, StoredLabel(task_id=int(task.id), annotation_id=ann.id, ghi=ghi))
                elif abs(cur.ghi - ghi) < 1e-6:
                    summary.items.append(ItemResult(index, "unchanged", task_id=cur.task_id, annotation_id=cur.annotation_id))
                else:
                    ann_id = cur.annotation_id
                    if ann_id is None:  # หา annotation เดิมของ task (ถ้าไม่มีให้สร้างใหม่)
                        anns = self.svc.list_annotations(cur.task_id)
                        ann_id = _get(anns[-1], "id") if anns else None
                    self.svc.update_task(cur.task_id, data)
                    if ann_id is None:
                        ann_id = self.svc.create_annotation(
                            task_id=cur.task_id, result=make_annotation_result(ghi), ground_truth=True
                        ).id
                    else:
                        self.svc.update_annotation(ann_id, make_annotation_result(ghi), ground_truth=True)
                    summary.items.append(ItemResult(index, "updated", task_id=cur.task_id, annotation_id=ann_id))
                    self._remember(station_id, slot, StoredLabel(task_id=cur.task_id, annotation_id=ann_id, ghi=ghi))
            except Exception as e:  # noqa: BLE001
                summary.items.append(ItemResult(index, "rejected", reason=f"label_studio_error: {e}"))
        return summary


# ----------------------------------------------------------------------------- retrain trigger
async def schedule_retrain(station_id: str, changed: int) -> tuple[bool, str]:
    """นัด retrain LSTM หลังมี label ใหม่/แก้ไข — รวมหลายครั้งที่ส่งใกล้กัน (debounce) เป็นรอบเดียว.

    trainer อ่าน label ทั้งหมดจาก Label Studio ตอนรัน จึงไม่ต้องส่ง label ไปกับ job.
    """
    if changed <= 0:
        return False, "no_new_labels"
    if not settings.enable_retrain:
        return False, "retrain_disabled (standby)"

    from api.jobs.service import JobService

    delay = settings.retrain_debounce_seconds
    pool = await JobService.get_pool()
    try:
        if not await pool.set(RETRAIN_SCHEDULED_KEY, "1", nx=True, ex=delay + 900):
            return False, "already_scheduled (รวมกับรอบที่นัดไว้)"
        try:
            await pool.enqueue_job(
                "train_timeseries_lstm",
                json.dumps({"station_id": station_id, "reason": "labels_submitted"}),
                _queue_name="train_queue",
                _defer_by=timedelta(seconds=delay),
            )
        except Exception as e:  # noqa: BLE001
            await pool.delete(RETRAIN_SCHEDULED_KEY)
            return False, f"enqueue_failed: {e}"
        return True, f"scheduled (เริ่มใน {delay} วินาที)"
    except Exception as e:  # noqa: BLE001
        return False, f"enqueue_failed: {e}"
    finally:
        await pool.close()
