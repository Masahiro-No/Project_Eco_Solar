"""Put weather_history rows on the 10-minute grid the LSTM was trained on.

weather_history holds rows at :00/:10/:20... (catch-up) and at :15/:45 (live fetch). Feeding the newest N rows
as they are gives the model a window that is shorter than it believes (36 rows covered 260 minutes instead of
350). This module does what service/training/features.py::build_station_frame does for training:

  1. every row goes to its nearest 10-minute slot (half a step rounds up); rows in the same slot are averaged
  2. the window is `lookback` consecutive slots ending at the newest slot
  3. a gap of at most MAX_GAP_FILL slots is filled by linear interpolation between its neighbours
  4. a window that still has an empty slot is not usable: nothing is made up for it

No database or pandas here, so the rule can be checked on its own.
"""

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

STEP = timedelta(minutes=10)
MAX_GAP_FILL = 2  # slots (20 minutes), the same limit as in training
TH_TZ = timezone(timedelta(hours=7))

# columns that must be present in every slot / columns with the default the training frame uses
REQUIRED = ("ghi", "dni", "clearsky_ghi", "solar_zenith_angle", "temperature", "relative_humidity", "wind_speed")
DEFAULTS = {"dhi": 0.0, "surface_pressure": 1008.0}
COLUMNS = REQUIRED + tuple(DEFAULTS)


def _utc(ts: datetime) -> datetime:
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)


def slot_of(ts: datetime) -> datetime:
    """Nearest 10-minute slot (UTC); exactly half a step goes to the later slot."""
    t = _utc(ts) + STEP / 2
    return t.replace(minute=(t.minute // 10) * 10, second=0, microsecond=0)


def _fill_short_gaps(values: list[Optional[float]]) -> list[Optional[float]]:
    """Linear interpolation over runs of at most MAX_GAP_FILL missing values that have a value on both sides."""
    out = list(values)
    i, n = 0, len(out)
    while i < n:
        if out[i] is not None:
            i += 1
            continue
        j = i
        while j < n and out[j] is None:
            j += 1
        if i > 0 and j < n and (j - i) <= MAX_GAP_FILL:
            left, right = out[i - 1], out[j]
            for k in range(i, j):
                out[k] = left + (right - left) * (k - i + 1) / (j - i + 1)
        i = j
    return out


def build_feature_window(rows: Iterable[Any], lookback: int) -> tuple[Optional[list[list[float]]], Optional[datetime], Optional[str]]:
    """16 aligned features for `lookback` consecutive 10-minute slots ending at the newest row.

    rows: objects with .timestamp and the weather_history columns. Returns (features, newest slot, None),
    or (None, newest slot or None, reason) when the window cannot be built from real data.
    """
    sums: dict[datetime, dict[str, list[float]]] = {}
    for r in rows:
        bucket = sums.setdefault(slot_of(r.timestamp), {c: [] for c in COLUMNS})
        for c in COLUMNS:
            v = getattr(r, c, None)
            if v is not None:
                bucket[c].append(float(v))
    if not sums:
        return None, None, f"insufficient_history (0/{lookback} slots)"

    end = max(sums)
    grid = [end - STEP * (lookback - 1 - i) for i in range(lookback)]
    if grid[0] < min(sums):
        have = sum(1 for s in grid if s in sums)
        return None, end, f"insufficient_history ({have}/{lookback} slots)"

    series: dict[str, list[Optional[float]]] = {}
    for c in COLUMNS:
        raw = [(sum(sums[s][c]) / len(sums[s][c])) if (s in sums and sums[s][c]) else None for s in grid]
        series[c] = _fill_short_gaps(raw)

    empty = sum(1 for i in range(lookback) if any(series[c][i] is None for c in REQUIRED))
    if empty:
        return None, end, f"gap_in_history ({empty}/{lookback} slots have no data after filling gaps of up to {MAX_GAP_FILL * 10} min)"

    features: list[list[float]] = []
    for i, slot in enumerate(grid):
        local = slot.astimezone(TH_TZ)
        minute_of_day = local.hour * 60 + local.minute
        day_of_year = local.timetuple().tm_yday
        ghi, clearsky = series["ghi"][i], series["clearsky_ghi"][i]
        clearsky_ratio = min(1.0, max(0.0, max(ghi, 0.0) / clearsky)) if clearsky >= 10.0 else 0.0
        dhi = series["dhi"][i]
        pressure = series["surface_pressure"][i]
        features.append([
            ghi,
            series["dni"][i],
            DEFAULTS["dhi"] if dhi is None else dhi,
            clearsky,
            series["solar_zenith_angle"][i],
            clearsky_ratio,
            series["temperature"][i],
            series["relative_humidity"][i],
            DEFAULTS["surface_pressure"] if pressure is None else pressure,
            series["wind_speed"][i],
            round(math.sin(2 * math.pi * minute_of_day / 1440.0), 6),
            round(math.cos(2 * math.pi * minute_of_day / 1440.0), 6),
            round(math.sin(2 * math.pi * day_of_year / 365.25), 6),
            round(math.cos(2 * math.pi * day_of_year / 365.25), 6),
            round(math.sin(2 * math.pi * (local.month - 1) / 12.0), 6),
            round(math.cos(2 * math.pi * (local.month - 1) / 12.0), 6),
        ])
    return features, end, None
