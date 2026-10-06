"""สร้างฟีเจอร์ 16 ตัว + sliding window จาก weather_history สำหรับ retrain LSTM.

ต้องตรงกับ backend/api/inference/service.py::extract_latest_weather_features ทุกประการ
(ลำดับคอลัมน์ = ALIGNED_FEATURE_COLS, cyclical encoding ใช้เวลาไทย UTC+7, clearsky_ratio = clip(kc, 0, 1))
เพื่อไม่ให้ train/inference เพี้ยนกัน. ไฟล์นี้ไม่พึ่ง torch/DB เพื่อให้เทสต์ง่าย.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from service.training.dataset import ALIGNED_FEATURE_COLS, FORECAST_STEPS, LOOKBACK_STEPS

SLOT = "10min"
TH_OFFSET = pd.Timedelta(hours=7)
SPAN = LOOKBACK_STEPS + FORECAST_STEPS  # 162 ช่อง ต่อ 1 window
NIGHT_CLEARSKY_GHI = 10.0   # W/m²: ต่ำกว่านี้ถือว่าดวงอาทิตย์ตกแล้ว
NIGHT_LABEL_MAX_GHI = 20.0  # W/m²: ค่า "วัดจริง" ที่สูงกว่านี้ตอนกลางคืนเป็นไปไม่ได้ จึงไม่นำมาใช้
MAX_GAP_FILL = 2  # เติมช่องว่างสั้น ๆ (<= 20 นาที) ด้วย linear interpolation เท่านั้น

_RAW_COLS = [
    "ghi", "dni", "dhi", "clearsky_ghi", "solar_zenith_angle", "temperature",
    "relative_humidity", "surface_pressure", "wind_speed",
]


def build_station_frame(
    weather: pd.DataFrame,
    labels: Optional[pd.Series] = None,
    max_gap_fill: int = MAX_GAP_FILL,
) -> pd.DataFrame:
    """แปลง weather_history ของ 1 สถานี เป็นตารางฟีเจอร์บนกริด 10 นาทีต่อเนื่อง.

    Args:
        weather: คอลัมน์ timestamp (UTC) + _RAW_COLS (ชื่อตามตาราง weather_history)
        labels: Series (index = เวลา UTC ที่ snap 10 นาที, ค่า = GHI จริง W/m²) ใช้ทับค่า ghi (ground truth ชนะ Open-Meteo)
    Returns:
        DataFrame index = เวลา UTC, คอลัมน์ = ALIGNED_FEATURE_COLS (หน่วยจริง); ช่องที่ไม่มีข้อมูลเป็น NaN
        และคอลัมน์ `is_label` (bool) บอกว่าช่องนั้นมี GHI จริงจาก label
    """
    if weather.empty:
        return pd.DataFrame(columns=ALIGNED_FEATURE_COLS + ["is_label"])

    df = weather[["timestamp"] + _RAW_COLS].copy()
    # weather: ปัดเป็นช่อง 10 นาทีแบบ "ใกล้สุด กึ่งกลางปัดขึ้น" (ทนต่อ jitter ไม่กี่วินาที)
    df["timestamp"] = (pd.to_datetime(df["timestamp"], utc=True) + pd.Timedelta(minutes=5)).dt.floor(SLOT)
    df = df.groupby("timestamp", sort=True).mean(numeric_only=True)

    grid = pd.date_range(df.index.min(), df.index.max(), freq=SLOT, tz="UTC")
    df = df.reindex(grid)
    df = df.interpolate(method="linear", limit=max_gap_fill, limit_area="inside")

    is_label = pd.Series(False, index=df.index)
    if labels is not None and len(labels):
        lab = labels.copy()
        lab.index = pd.to_datetime(lab.index, utc=True).floor(SLOT)  # label: ปัด "ลง" เป็นช่อง 10 นาที (xx:x5 -> xx:x0)
        lab = lab[~lab.index.duplicated(keep="last")]
        lab = lab[lab.index.isin(df.index)]
        # label ที่บอกว่ามีแดดตอนกลางคืน (GHI ฟ้าใส < 10 W/m²) ไม่ใช่ค่าที่วัดได้จริง: ไม่ใช้
        night = (df.loc[lab.index, "clearsky_ghi"] < NIGHT_CLEARSKY_GHI).values
        lab = lab[~(night & (lab.values > NIGHT_LABEL_MAX_GHI))]
        df.loc[lab.index, "ghi"] = lab.values
        is_label.loc[lab.index] = True

    cs = df["clearsky_ghi"]
    kc = np.where(cs >= 10.0, np.maximum(df["ghi"], 0.0) / cs.where(cs >= 10.0, 1.0), 0.0)
    kc = np.where(np.isnan(df["ghi"]) | np.isnan(cs), np.nan, kc)

    local = df.index + TH_OFFSET
    minute_of_day = local.hour * 60 + local.minute
    doy = local.dayofyear.values
    out = pd.DataFrame(index=df.index)
    out["GHI"] = df["ghi"]
    out["DNI"] = df["dni"]
    out["DHI"] = df["dhi"].fillna(0.0)
    out["Clearsky GHI"] = cs
    out["Solar Zenith Angle"] = df["solar_zenith_angle"]
    out["clearsky_ratio"] = np.clip(kc, 0.0, 1.0)
    out["Temperature"] = df["temperature"]
    out["Relative Humidity"] = df["relative_humidity"]
    out["Pressure"] = df["surface_pressure"].fillna(1008.0)
    out["Wind Speed"] = df["wind_speed"]
    out["hour_sin"] = np.sin(2 * np.pi * minute_of_day / 1440.0)
    out["hour_cos"] = np.cos(2 * np.pi * minute_of_day / 1440.0)
    out["day_sin"] = np.sin(2 * np.pi * doy / 365.25)
    out["day_cos"] = np.cos(2 * np.pi * doy / 365.25)
    out["month_sin"] = np.sin(2 * np.pi * (local.month - 1) / 12.0)
    out["month_cos"] = np.cos(2 * np.pi * (local.month - 1) / 12.0)
    out = out[ALIGNED_FEATURE_COLS]
    out["is_label"] = is_label.values
    return out


def make_windows(
    frame: pd.DataFrame,
    lookback: int = LOOKBACK_STEPS,
    horizon: int = FORECAST_STEPS,
    stride: int = 1,
):
    """ตัด window ที่ไม่มี NaN เลยตลอดช่วง lookback+horizon.

    Returns:
        X (n, lookback, 16) หน่วยจริง, Y (n, horizon) GHI จริง,
        starts (n,) เวลา UTC ของช่องแรกของ window (datetime64[ns]),
        has_label (n,) bool — ช่วงพยากรณ์ของ window มี GHI จริงจาก label อย่างน้อย 1 ช่อง
    """
    span = lookback + horizon
    empty = (
        np.empty((0, lookback, len(ALIGNED_FEATURE_COLS)), np.float32),
        np.empty((0, horizon), np.float32),
        np.empty((0,), "datetime64[ns]"),
        np.empty((0,), bool),
    )
    if len(frame) < span:
        return empty
    feats = frame[ALIGNED_FEATURE_COLS].to_numpy(dtype=np.float32)
    ghi = frame["GHI"].to_numpy(dtype=np.float32)
    lab = frame["is_label"].to_numpy(dtype=bool)
    bad = np.isnan(feats).any(axis=1).astype(np.int32)
    csum = np.concatenate([[0], np.cumsum(bad)])

    xs, ys, starts, has_label = [], [], [], []
    idx = frame.index.tz_convert("UTC").tz_localize(None).to_numpy()
    for s in range(0, len(frame) - span + 1, stride):
        if csum[s + span] - csum[s] != 0:
            continue
        xs.append(feats[s:s + lookback])
        ys.append(ghi[s + lookback:s + span])
        starts.append(idx[s])
        has_label.append(bool(lab[s + lookback:s + span].any()))
    if not xs:
        return empty
    return np.stack(xs), np.stack(ys), np.array(starts, dtype="datetime64[ns]"), np.array(has_label, dtype=bool)


def make_live_windows(
    inputs: pd.DataFrame,
    measured: pd.Series,
    lookback: int = LOOKBACK_STEPS,
    horizon: int = FORECAST_STEPS,
    stride: int = 1,
):
    """window สำหรับเรียนจากค่าที่วัดจริง ในเงื่อนไขเดียวกับตอนใช้งาน

    ตอนพยากรณ์จริง โมเดลได้รับเฉพาะสภาพอากาศ (ค่าที่วัดจริงมาถึงทีหลังเป็นไฟล์ ไม่เคยอยู่ในข้อมูลป้อน)
    ข้อมูลป้อนของ window จึงมาจาก `inputs` ที่สร้างโดยไม่ใส่ label ส่วนเป้าหมายคือค่าที่วัดจริงของช่วงพยากรณ์

    Args:
        inputs: ผลของ build_station_frame(weather) ที่ไม่ได้ส่ง labels
        measured: Series index เดียวกับ inputs, ค่า = GHI ที่วัดจริง (NaN = ช่องนั้นไม่มีค่าวัด)
    Returns:
        X (n, lookback, 16) หน่วยจริง, Y (n, horizon) GHI ที่วัดจริง (0 ในช่องที่ไม่มีค่าวัด),
        mask (n, horizon) bool ช่องที่มีค่าวัดจริงตอนกลางวัน (ใช้คิด loss และ MAE),
        starts (n,) เวลา UTC ของช่องแรกของ window — คืนเฉพาะ window ที่ mask มี True อย่างน้อย 1 ช่อง
    """
    span = lookback + horizon
    empty = (
        np.empty((0, lookback, len(ALIGNED_FEATURE_COLS)), np.float32),
        np.empty((0, horizon), np.float32),
        np.empty((0, horizon), bool),
        np.empty((0,), "datetime64[ns]"),
    )
    if len(inputs) < span:
        return empty
    feats = inputs[ALIGNED_FEATURE_COLS].to_numpy(dtype=np.float32)
    clearsky = inputs["Clearsky GHI"].to_numpy(dtype=np.float32)
    meas = measured.reindex(inputs.index).to_numpy(dtype=np.float32)
    usable = ~np.isnan(meas) & (clearsky >= NIGHT_CLEARSKY_GHI)   # กลางคืนผลของโมเดลไม่ถูกใช้ จึงไม่เรียนและไม่วัด
    bad = np.isnan(feats).any(axis=1).astype(np.int32)
    csum = np.concatenate([[0], np.cumsum(bad)])

    xs, ys, masks, starts = [], [], [], []
    idx = inputs.index.tz_convert("UTC").tz_localize(None).to_numpy()
    for s in range(0, len(inputs) - span + 1, stride):
        target = slice(s + lookback, s + span)
        if csum[s + span] - csum[s] != 0 or not usable[target].any():
            continue
        xs.append(feats[s:s + lookback])
        ys.append(np.nan_to_num(meas[target], nan=0.0))
        masks.append(usable[target].copy())
        starts.append(idx[s])
    if not xs:
        return empty
    return np.stack(xs), np.stack(ys), np.stack(masks), np.array(starts, dtype="datetime64[ns]")


def forecast_days(starts: np.ndarray, lookback: int = LOOKBACK_STEPS, horizon: int = FORECAST_STEPS) -> np.ndarray:
    """วัน (เวลาไทย) ของทุกช่องพยากรณ์ของแต่ละ window -> (n, horizon) datetime64[D]"""
    step = np.timedelta64(10, "m")
    times = starts[:, None] + step * (lookback + np.arange(horizon))[None, :]
    return (times + np.timedelta64(7, "h")).astype("datetime64[D]")


def measured_slots_per_day(starts: np.ndarray, mask: np.ndarray, lookback: int = LOOKBACK_STEPS) -> dict[str, int]:
    """จำนวนช่องเวลาที่มีค่าวัดจริงของแต่ละวัน (เวลาไทย) จาก window ของสถานีเดียว

    ค่าวัดหนึ่งช่องเป็นเป้าหมายของหลาย window จึงนับช่องละครั้ง -> {'YYYY-MM-DD': จำนวนช่อง}
    """
    if len(starts) == 0 or not mask.any():
        return {}
    step = np.timedelta64(10, "m")
    times = starts[:, None] + step * (lookback + np.arange(mask.shape[1]))[None, :]
    slots = np.unique(times[mask])
    days, counts = np.unique((slots + np.timedelta64(7, "h")).astype("datetime64[D]"), return_counts=True)
    return {str(d): int(c) for d, c in zip(days, counts)}


def day_folds(days: np.ndarray, mask: np.ndarray, max_folds: int = 7, test_on: Optional[np.ndarray] = None) -> list[dict]:
    """แบ่งวันที่ใช้ตรวจเป็นกลุ่ม ให้ทุกวันถูกกันไว้ตรวจหนึ่งครั้ง (cross-validation ตามวัน)

    วันเรียงตามเวลาแล้วแจกเข้ากลุ่มทีละวันวนไป: มีไม่เกิน max_folds วัน = กันทีละวัน
    window ที่ช่องพยากรณ์แตะวันของกลุ่มที่กันไว้ไม่ถูกใช้เทรนในรอบของกลุ่มนั้น

    Args:
        days: ผลของ forecast_days, mask: ผลของ make_live_windows
        test_on: (n, horizon) bool ช่องที่ใช้ตรวจได้ (None = ทุกช่องที่มีค่าวัดจริง) ใช้ตัดวันที่โมเดลที่ใช้งานอยู่
            เคยเทรนไปแล้วออกจากการตรวจ วันเหล่านั้นยังใช้เทรนได้
    Returns [] เมื่อไม่มีวันให้ตรวจ หรือมีค่าวัดจริงน้อยกว่า 2 วัน มิฉะนั้น list ของ dict:
        days (list 'YYYY-MM-DD'), train_idx, test_idx, test_mask (len(test_idx), horizon)
    """
    check = mask if test_on is None else mask & test_on
    if not check.any() or len(np.unique(days[mask])) < 2:
        return []
    measured = np.unique(days[check])
    k = min(len(measured), max_folds)
    folds = []
    for f in range(k):
        on_held = np.isin(days, measured[f::k])
        test_mask = check & on_held
        test_idx = np.where(test_mask.any(axis=1))[0]
        folds.append({
            "days": [str(d) for d in measured[f::k]],
            "train_idx": np.where(~on_held.any(axis=1))[0],
            "test_idx": test_idx,
            "test_mask": test_mask[test_idx],
        })
    return folds
