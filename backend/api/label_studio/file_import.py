"""อ่านไฟล์ CSV / XLSX ของค่า GHI จริง (ผู้ใช้เลือกคอลัมน์เวลา + คอลัมน์ GHI เอง หรือใช้ที่ระบบเดาให้).

รองรับไฟล์ export ของระบบวัดรังสี (ID, Station ID, Station Name, Province, Solar Intensity Value, Status, Date/Time)
และรูปแบบง่าย ๆ (timestamp, ghi_actual).

กติกา:
- เวลา: ISO (2026-10-04 14:45:02), วัน/เดือน/ปี (4/10/2026 14:45), ค่าวันที่ของ Excel; ปี พ.ศ. (>2400) -> ค.ศ.
  ไม่มี timezone = เวลาไทย; ปัดลงเป็นช่อง 10 นาที (ground_truth.parse_label_timestamp)
- ไฟล์เดียวมีได้หลายวัน: เก็บทุกแถวตั้งแต่ 'วันเริ่มต้น' ที่เลือกเป็นต้นไป (เวลาไทย) ถ้าระบุ start_day; แถวก่อนวันนั้นถูกข้าม
- ค่าติดลบเล็กน้อย (>= -10) เป็น offset ของเซ็นเซอร์ตอนกลางคืน -> 0; ติดลบมากกว่านั้นถือว่าใช้ไม่ได้
- ช่อง 10 นาทีซ้ำกัน: เก็บแถวที่ ID สูงสุด (ถ้าไม่มีคอลัมน์ ID ใช้แถวท้ายสุดในไฟล์)
"""

from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional

from api.label_studio.ground_truth import TH_TZ, parse_label_timestamp

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 20000
NEGATIVE_TOLERANCE = 10.0  # W/m²

_TS_HINTS = ("timestamp", "date/time", "datetime", "date time", "date_time", "time", "date", "เวลา")
_GHI_HINTS = ("ghi_actual", "solar intensity value", "solar_intensity_value", "ghi", "solar intensity", "intensity", "รังสี")


class FileImportError(ValueError):
    """ไฟล์อ่านไม่ได้ / รูปแบบไม่รองรับ (ข้อความพร้อมแสดงให้ผู้ใช้)."""


@dataclass
class Table:
    headers: list[str]
    rows: list[list[Any]]


@dataclass
class ParsedFile:
    items: list[dict[str, Any]] = field(default_factory=list)  # {"timestamp": ISO ช่อง UTC, "ghi_actual": float, "notes": str}
    total_rows: int = 0
    invalid: list[tuple[int, str]] = field(default_factory=list)  # (เลขแถวในไฟล์, เหตุผล)
    before_start: int = 0  # แถวที่อยู่ก่อนวันเริ่มต้นที่เลือก (ไม่นำเข้า)
    days: list[date] = field(default_factory=list)  # วัน (เวลาไทย) ของ items ที่นำเข้า เรียงตามเวลา
    file_first_day: Optional[date] = None  # วันแรกและวันสุดท้ายของแถวที่อ่านได้ทั้งไฟล์ (ใช้บอกผู้ใช้เมื่อเลือกวันเริ่มต้นผิด)
    file_last_day: Optional[date] = None
    duplicates_collapsed: int = 0
    clamped_negative: int = 0


def read_table(filename: str, content: bytes) -> Table:
    if len(content) > MAX_BYTES:
        raise FileImportError(f"ไฟล์ใหญ่เกินไป (สูงสุด {MAX_BYTES // (1024 * 1024)} MB)")
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        import openpyxl

        try:
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            raw = [list(r) for r in wb.active.iter_rows(values_only=True)]
        except Exception as e:  # noqa: BLE001
            raise FileImportError(f"อ่านไฟล์ Excel ไม่ได้: {e}") from None
    elif name.endswith((".csv", ".txt")):
        text: Optional[str] = None
        for enc in ("utf-8-sig", "cp874"):  # cp874 = ไฟล์ภาษาไทยจาก Excel เก่า
            try:
                text = content.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            raise FileImportError("ไม่สามารถถอดรหัสไฟล์ CSV (รองรับ UTF-8 / TIS-620)")
        delim = max([",", ";", "\t"], key=text[:4096].count)
        raw = list(csv.reader(io.StringIO(text), delimiter=delim))
    else:
        raise FileImportError("รองรับเฉพาะไฟล์ .csv และ .xlsx")

    raw = [r for r in raw if any(c not in (None, "") for c in r)]
    if len(raw) < 2:
        raise FileImportError("ไม่พบข้อมูล (ต้องมีแถวหัวตาราง + อย่างน้อย 1 แถวข้อมูล)")
    headers = [str(h).strip().lstrip("﻿") if h not in (None, "") else f"column_{i + 1}" for i, h in enumerate(raw[0])]
    if len(raw) - 1 > MAX_ROWS:
        raise FileImportError(f"แถวเยอะเกินไป (สูงสุด {MAX_ROWS} แถวต่อไฟล์)")
    return Table(headers=headers, rows=raw[1:])


def guess_columns(headers: list[str]) -> dict[str, Optional[str]]:
    """เดาคอลัมน์เวลา / GHI จากชื่อหัวตาราง (ไม่แยกตัวพิมพ์เล็กใหญ่; ชื่อตรงเป๊ะชนะชื่อที่แค่มีคำนั้น)."""

    def pick(hints: tuple[str, ...]) -> Optional[str]:
        low = [h.lower() for h in headers]
        for hint in hints:  # ลำดับใน hints = ลำดับความสำคัญ
            for i, h in enumerate(low):
                if h == hint:
                    return headers[i]
        for hint in hints:
            for i, h in enumerate(low):
                if hint in h:
                    return headers[i]
        return None

    ts = pick(_TS_HINTS)
    ghi = pick(tuple(h for h in _GHI_HINTS if h != ts))
    return {"timestamp": ts, "ghi": ghi}


def _cell_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.isoformat(sep=" ")
    return str(v)


def preview(filename: str, content: bytes, sample: int = 5) -> dict[str, Any]:
    t = read_table(filename, content)
    g = guess_columns(t.headers)
    return {
        "filename": filename,
        "headers": t.headers,
        "guessed_timestamp": g["timestamp"],
        "guessed_ghi": g["ghi"],
        "sample_rows": [[_cell_str(c) for c in r[: len(t.headers)]] for r in t.rows[:sample]],
        "total_rows": len(t.rows),
    }


def _to_timestamp(value: Any) -> Optional[str]:
    """ค่าเวลาในเซลล์ -> ISO string (อาจไม่มี timezone) หรือ None."""
    if value is None or value == "":
        return None
    dt: Optional[datetime] = None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime(value.year, value.month, value.day)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        from openpyxl.utils.datetime import from_excel

        try:
            dt = from_excel(value)
        except Exception:  # noqa: BLE001
            return None
    else:
        s = str(value).strip()
        for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y"):  # วัน/เดือน/ปี แบบไทย
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
        if dt is None:
            try:
                dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            except ValueError:
                return None
    if dt.year > 2400:  # พ.ศ.
        try:
            dt = dt.replace(year=dt.year - 543)
        except ValueError:
            return None
    return dt.isoformat()


def _opt_float(value: Any) -> Optional[float]:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def parse_ground_truth_file(
    filename: str,
    content: bytes,
    timestamp_col: Optional[str] = None,
    ghi_col: Optional[str] = None,
    start_day: Optional[date] = None,
) -> ParsedFile:
    t = read_table(filename, content)
    guessed = guess_columns(t.headers)

    def col_index(name: Optional[str], fallback: Optional[str], label: str) -> int:
        want = (name or fallback or "").strip().lower()
        if not want:
            raise FileImportError(f"ยังไม่ได้เลือกคอลัมน์{label}")
        for i, h in enumerate(t.headers):
            if h.strip().lower() == want:
                return i
        raise FileImportError(f"ไม่พบคอลัมน์ '{name}' ในไฟล์ (คอลัมน์ที่มี: {', '.join(t.headers)})")

    i_ts = col_index(timestamp_col, guessed["timestamp"], "เวลา")
    i_ghi = col_index(ghi_col, guessed["ghi"], " GHI")
    if i_ts == i_ghi:
        raise FileImportError("คอลัมน์เวลาและคอลัมน์ GHI ต้องเป็นคนละคอลัมน์")
    i_id = next((i for i, h in enumerate(t.headers) if h.strip().lower() == "id"), None)

    out = ParsedFile(total_rows=len(t.rows))
    best: dict[datetime, tuple[float, dict[str, Any]]] = {}
    for line_no, row in enumerate(t.rows, start=2):  # แถว 1 = หัวตาราง
        def cell(i: Optional[int]) -> Any:
            return row[i] if i is not None and i < len(row) else None

        ts_iso = _to_timestamp(cell(i_ts))
        if ts_iso is None:
            out.invalid.append((line_no, "invalid_timestamp"))
            continue
        ghi = _opt_float(cell(i_ghi))
        if ghi is None:
            out.invalid.append((line_no, "invalid_ghi"))
            continue
        try:
            slot = parse_label_timestamp(ts_iso)
        except ValueError:
            out.invalid.append((line_no, "invalid_timestamp"))
            continue
        local_day = slot.astimezone(TH_TZ).date()
        out.file_first_day = local_day if out.file_first_day is None else min(out.file_first_day, local_day)
        out.file_last_day = local_day if out.file_last_day is None else max(out.file_last_day, local_day)
        if start_day is not None and local_day < start_day:
            out.before_start += 1
            continue
        if ghi < 0:
            if ghi >= -NEGATIVE_TOLERANCE:
                ghi = 0.0
                out.clamped_negative += 1
            else:
                out.invalid.append((line_no, "ghi_negative"))
                continue

        order = _opt_float(cell(i_id))
        order = order if order is not None else float(line_no)
        item = {"timestamp": slot.strftime("%Y-%m-%dT%H:%M:%SZ"), "ghi_actual": ghi, "notes": f"file:{filename}"}
        prev = best.get(slot)
        if prev is None:
            best[slot] = (order, item)
        else:
            out.duplicates_collapsed += 1
            if order >= prev[0]:
                best[slot] = (order, item)

    out.items = [best[s][1] for s in sorted(best)]
    out.days = sorted({s.astimezone(TH_TZ).date() for s in best})
    return out
