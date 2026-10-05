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
    return_label_mask: bool = False,
):
    """ตัด window ที่ไม่มี NaN เลยตลอดช่วง lookback+horizon.

    return_label_mask=True คืนค่าเพิ่มอีกตัว: label_mask (n, horizon) bool บอกว่าช่องพยากรณ์ไหนเป็น GHI ที่วัดจริง

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
    if return_label_mask:
        empty = empty + (np.empty((0, horizon), bool),)
    if len(frame) < span:
        return empty
    feats = frame[ALIGNED_FEATURE_COLS].to_numpy(dtype=np.float32)
    ghi = frame["GHI"].to_numpy(dtype=np.float32)
    lab = frame["is_label"].to_numpy(dtype=bool)
    bad = np.isnan(feats).any(axis=1).astype(np.int32)
    csum = np.concatenate([[0], np.cumsum(bad)])

    xs, ys, starts, has_label, masks = [], [], [], [], []
    idx = frame.index.tz_convert("UTC").tz_localize(None).to_numpy()
    for s in range(0, len(frame) - span + 1, stride):
        if csum[s + span] - csum[s] != 0:
            continue
        xs.append(feats[s:s + lookback])
        ys.append(ghi[s + lookback:s + span])
        starts.append(idx[s])
        has_label.append(bool(lab[s + lookback:s + span].any()))
        masks.append(lab[s + lookback:s + span].copy())
    if not xs:
        return empty
    out = (np.stack(xs), np.stack(ys), np.array(starts, dtype="datetime64[ns]"), np.array(has_label, dtype=bool))
    return out + (np.stack(masks),) if return_label_mask else out


def label_holdout(
    starts: np.ndarray,
    label_mask: np.ndarray,
    lookback: int = LOOKBACK_STEPS,
    min_points: int = 20,
) -> Optional[dict]:
    """กันค่าที่วัดจริงของ "วันล่าสุดที่มี label" ไว้ตรวจ (ไม่ใช้เทรน) เพื่อวัดว่าโมเดลใหม่แม่นขึ้นเทียบกับค่าจริงหรือไม่.

    ต้องมี label อย่างน้อย 2 วัน (วันหนึ่งไว้เทรน วันล่าสุดไว้ตรวจ) และจุดที่ตรวจได้อย่างน้อย min_points
    Returns None ถ้าทำไม่ได้ มิฉะนั้น dict:
        day        วันที่กันไว้ (เวลาไทย, 'YYYY-MM-DD')
        val_idx    window ที่ช่วงพยากรณ์มี label ของวันนั้น
        val_mask   (len(val_idx), horizon) bool: ช่องพยากรณ์ที่เป็น label ของวันนั้น (วัด MAE เฉพาะช่องเหล่านี้)
        touches    (n,) bool: window ที่ช่วงเวลาทั้งหมดแตะวันนั้น ต้องตัดออกจาก train ทั้งหมด
    """
    if len(starts) == 0 or not label_mask.any():
        return None
    horizon = label_mask.shape[1]
    step = np.timedelta64(10, "m")
    th = np.timedelta64(7, "h")
    target_times = starts[:, None] + step * (lookback + np.arange(horizon))[None, :]   # เวลาของแต่ละช่องพยากรณ์ (UTC)
    target_days = (target_times + th).astype("datetime64[D]")
    label_days = np.unique(target_days[label_mask])
    if len(label_days) < 2:
        return None
    day = label_days[-1]
    val_mask_all = label_mask & (target_days == day)
    val_idx = np.where(val_mask_all.any(axis=1))[0]
    if int(val_mask_all.sum()) < min_points:
        return None
    first_day = (starts + th).astype("datetime64[D]")
    last_day = (starts + step * (lookback + horizon - 1) + th).astype("datetime64[D]")
    touches = (first_day <= day) & (last_day >= day)
    return {"day": str(day), "val_idx": val_idx, "val_mask": val_mask_all[val_idx], "touches": touches}


def split_by_day(
    starts: np.ndarray,
    has_label: np.ndarray,
    lookback: int = LOOKBACK_STEPS,
    horizon: int = FORECAST_STEPS,
    val_every: int = 5,
) -> tuple[np.ndarray, np.ndarray]:
    """แบ่ง train/val ตามวัน (เวลาไทย) โดยไม่ให้เป้าหมาย (target) ของ validation รั่วเข้า train.

    - "วันของ window" = วันที่ช่วงพยากรณ์เริ่ม; ทุก ๆ วันที่ val_every เป็นวัน validation
    - วันที่มี label จะไม่ถูกใช้เป็น validation (label ต้องได้เทรนเสมอ)
    - window ที่ช่วงเวลารวม (lookback+horizon) แตะวัน validation จะถูกตัดออกจาก train ยกเว้น window ที่มี label
      (หน้าต่างพวกนี้ target อยู่นอกวัน validation อยู่แล้ว; มีเพียง input ที่ซ้อนกับวัน validation)
    Returns: (train_idx, val_idx)
    """
    empty = np.array([], dtype=int)
    if len(starts) == 0:
        return empty, empty
    step = np.timedelta64(10, "m")
    to_day = lambda a: (a + np.timedelta64(7, "h")).astype("datetime64[D]").astype(np.int64)  # noqa: E731
    d_first = to_day(starts)                                   # วันของช่องแรกใน window
    d_key = to_day(starts + step * lookback)                   # วันที่ช่วงพยากรณ์เริ่ม
    d_last = to_day(starts + step * (lookback + horizon - 1))  # วันของช่องสุดท้าย

    all_days = np.unique(np.concatenate([d_first, d_key, d_last]))
    label_days = set(np.concatenate([d_key[has_label], d_last[has_label]]).tolist()) if has_label.any() else set()
    val_days = np.array(
        [d for i, d in enumerate(all_days) if i % val_every == val_every - 1 and int(d) not in label_days],
        dtype=np.int64,
    )

    in_val = np.isin(d_key, val_days) & np.isin(d_last, val_days)
    touches_val = np.isin(d_first, val_days) | np.isin(d_key, val_days) | np.isin(d_last, val_days)
    # window ที่ target ล้ำเข้าวัน validation (key ไม่ใช่ val แต่ last เป็น val) ก็ถูกตัดจาก train ผ่าน touches_val
    train_mask = (~touches_val) | has_label
    val_mask = np.isin(d_key, val_days) & ~has_label
    del in_val
    return np.where(train_mask & ~val_mask)[0], np.where(val_mask)[0]
