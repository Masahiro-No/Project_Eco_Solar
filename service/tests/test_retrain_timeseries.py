"""เทสต์ pipeline retrain LSTM (ไม่ต้องใช้ DB/MinIO/Redis). รันจาก root ของ repo:

    python -m service.tests.test_retrain_timeseries
หรือ  python -m pytest service/tests -q
"""

import math
import tempfile
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from service.training.dataset import ALIGNED_FEATURE_COLS, FORECAST_STEPS, LOOKBACK_STEPS
from service.training.features import build_station_frame, make_windows, split_by_day

MODEL_DIR = Path(__file__).resolve().parents[2] / "model" / "time-series"


def _synthetic_weather(days: int = 12, start: str = "2026-09-01 00:00") -> pd.DataFrame:
    idx = pd.date_range(start, periods=days * 144, freq="10min", tz="UTC")
    local = idx + pd.Timedelta(hours=7)
    local_hour = (local.hour + local.minute / 60).values
    sun = np.clip(np.sin((local_hour - 6) / 12 * np.pi), 0, None)
    return pd.DataFrame(
        {
            "timestamp": idx,
            "ghi": 900 * sun,
            "dni": 700 * sun,
            "dhi": 100 * sun,
            "clearsky_ghi": 1000 * sun,
            "solar_zenith_angle": 90 - 80 * sun,
            "temperature": 28 + 4 * sun,
            "relative_humidity": 70 - 20 * sun,
            "surface_pressure": 1008.0,
            "wind_speed": 2.0,
        }
    )


def test_cyclical_features_use_thai_time():
    w = _synthetic_weather(days=1, start="2026-10-02 00:00")
    f = build_station_frame(w)
    row = f.iloc[0]  # 00:00 UTC = 07:00 เวลาไทย
    assert math.isclose(row["hour_sin"], math.sin(2 * math.pi * 420 / 1440), abs_tol=1e-9)
    assert math.isclose(row["hour_cos"], math.cos(2 * math.pi * 420 / 1440), abs_tol=1e-9)
    assert list(f.columns[:16]) == ALIGNED_FEATURE_COLS


def test_label_overrides_ghi_and_clearsky_ratio():
    w = _synthetic_weather(days=1, start="2026-10-02 00:00")
    noon_utc = pd.Timestamp("2026-10-02 05:00", tz="UTC")  # 12:00 เวลาไทย
    f0 = build_station_frame(w)
    f1 = build_station_frame(w, labels=pd.Series([321.0], index=[noon_utc]))
    assert f1.loc[noon_utc, "GHI"] == 321.0 and bool(f1.loc[noon_utc, "is_label"])
    cs = f1.loc[noon_utc, "Clearsky GHI"]
    assert math.isclose(f1.loc[noon_utc, "clearsky_ratio"], 321.0 / cs, rel_tol=1e-6)
    assert f0.loc[noon_utc, "GHI"] != 321.0 and not bool(f0["is_label"].any())


def test_gap_handling_and_windows():
    w = _synthetic_weather(days=4)
    w = w.drop(index=range(300, 302))  # ช่องว่าง 2 ช่อง -> เติมได้
    w = w.drop(index=range(400, 410))  # ช่องว่าง 10 ช่อง -> ต้องไม่มี window ที่คร่อม
    f = build_station_frame(w)
    X, Y, starts, hl = make_windows(f, stride=1)
    assert X.shape[1:] == (LOOKBACK_STEPS, 16) and Y.shape[1] == FORECAST_STEPS
    assert not np.isnan(X).any() and not np.isnan(Y).any()
    nan_rows = f.index[f[ALIGNED_FEATURE_COLS].isna().any(axis=1)]
    assert len(nan_rows) == 8  # ช่องว่าง 10 ช่อง: เติมได้ที่ปลายละ... ไม่เกิน limit=2 -> เหลือ NaN 8 ช่อง
    for s in starts:
        s = pd.Timestamp(s, tz="UTC")
        e = s + pd.Timedelta(minutes=10 * (LOOKBACK_STEPS + FORECAST_STEPS - 1))
        assert e < nan_rows[0] or s > nan_rows[-1]  # window ไม่คร่อมช่องว่างที่เหลือ


def test_split_has_val_and_no_target_leak():
    w = _synthetic_weather(days=20)
    f = build_station_frame(w)
    X, Y, starts, hl = make_windows(f, stride=2)
    tr, va = split_by_day(starts, hl)
    assert len(va) > 50 and len(tr) > 0
    assert not set(tr) & set(va)
    step = np.timedelta64(10, "m")
    to_day = lambda a: (a + np.timedelta64(7, "h")).astype("datetime64[D]")  # noqa: E731
    val_days = set(to_day(starts[va] + step * LOOKBACK_STEPS).tolist())
    for i in tr:  # ไม่มี train window ที่ช่วง target แตะวัน validation
        key = to_day(starts[i] + step * LOOKBACK_STEPS)
        last = to_day(starts[i] + step * (LOOKBACK_STEPS + FORECAST_STEPS - 1))
        assert key not in val_days and last not in val_days


def test_labeled_windows_always_train():
    w = _synthetic_weather(days=20)
    ts = pd.Timestamp("2026-09-05 05:00", tz="UTC")
    f = build_station_frame(w, labels=pd.Series([400.0], index=[ts]))
    X, Y, starts, hl = make_windows(f, stride=1)
    tr, va = split_by_day(starts, hl)
    assert hl.sum() > 0
    assert hl[tr].sum() == hl.sum()  # ทุก window ที่มี label อยู่ใน train
    assert not hl[va].any()


def test_label_timestamps_floor_to_10_minutes():
    """label ที่ลงเวลา xx:x5 (และ +วินาที) ต้องปัด 'ลง' ไปช่อง xx:x0; weather ปัดแบบใกล้สุด."""
    w = _synthetic_weather(days=1, start="2026-10-02 00:00")
    slot = pd.Timestamp("2026-10-02 05:00", tz="UTC")
    for raw in ("2026-10-02 05:05:00", "2026-10-02 05:09:59", "2026-10-02 05:00:02"):
        f = build_station_frame(w, labels=pd.Series([500.0], index=[pd.Timestamp(raw, tz="UTC")]))
        assert f.loc[slot, "GHI"] == 500.0 and int(f["is_label"].sum()) == 1, raw
    # weather ที่ jitter ก่อนเวลา 1 วินาที ยังต้องเข้าช่องเดิม (ไม่ถูกปัดลงช่องก่อนหน้า)
    w2 = w.copy()
    w2["timestamp"] = w2["timestamp"] - pd.Timedelta(seconds=1)
    f2 = build_station_frame(w2)
    assert f2.index[0] == pd.Timestamp("2026-10-02 00:00", tz="UTC") and len(f2) == 144


def test_parse_label_tasks_reads_annotation_first():
    from service.training.retrain_timeseries import parse_label_tasks

    since = pd.Timestamp("2026-09-01", tz="UTC")
    tasks = [
        {  # annotation ชนะ data (ผู้ใช้แก้ค่าใน Label Studio)
            "data": {"station_id": "ST-001", "timestamp": "2026-10-02T05:05:00Z", "ghi_actual": 100.0},
            "annotations": [{"was_cancelled": False, "result": [{"from_name": "ghi", "value": {"number": 321.5}}]}],
        },
        {"data": {"station_id": "ST-001", "timestamp": "2026-10-02T05:10:00+00:00", "ghi_actual": 50.0}, "annotations": []},
        {"data": {"station_id": "ST-001", "timestamp": "2026-08-01T05:10:00+00:00", "ghi_actual": 50.0}, "annotations": []},  # เก่าเกิน
        {"data": {"station_id": "ST-001"}, "annotations": []},  # ไม่มีค่า
    ]
    df = parse_label_tasks(tasks, since)
    assert len(df) == 2
    got = {str(r.timestamp): r.ghi_actual for r in df.itertuples()}
    assert got["2026-10-02 05:00:00+00:00"] == 321.5  # 05:05 -> ปัดลงเป็น 05:00
    assert got["2026-10-02 05:10:00+00:00"] == 50.0


def test_fine_tune_and_onnx_roundtrip():
    import torch

    from service.models.solar_lstm import SolarLSTMForecaster
    from service.training.onnx_weights import load_onnx_into_model
    from service.training.retrain_timeseries import evaluate_mae, export_onnx, fine_tune, verify_onnx_matches

    onnx_path = MODEL_DIR / "solar_ghi_lstm.onnx"
    fs = joblib.load(MODEL_DIR / "feature_scaler.joblib")
    ts = joblib.load(MODEL_DIR / "target_scaler.joblib")

    f = build_station_frame(_synthetic_weather(days=10))
    X, Y, starts, hl = make_windows(f, stride=6)
    n = len(X)
    Xs = fs.transform(X.reshape(-1, 16)).reshape(n, LOOKBACK_STEPS, 16).astype(np.float32)
    Ys = ts.transform(Y.reshape(-1, 1)).reshape(n, FORECAST_STEPS).astype(np.float32)
    cut = int(n * 0.8)

    model = SolarLSTMForecaster()
    load_onnx_into_model(model, str(onnx_path))
    dev = torch.device("cpu")
    before = evaluate_mae(model, Xs[cut:], Y[cut:], ts, dev)
    res = fine_tune(model, Xs[:cut], Ys[:cut], Xs[cut:], Y[cut:], ts, dev, epochs=2, lr=1e-3, batch_size=32)
    after = evaluate_mae(model, Xs[cut:], Y[cut:], ts, dev)
    assert math.isclose(res["baseline_val_mae"], before, rel_tol=1e-5)
    assert after <= before + 1e-6  # fine_tune เก็บ state ที่ดีที่สุด (รวมโมเดลเดิม) จึงไม่แย่ลง

    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "m.onnx"
        export_onnx(model, out)
        assert verify_onnx_matches(model, out) <= 1e-4
        import onnxruntime as ort

        sess = ort.InferenceSession(str(out), providers=["CPUExecutionProvider"])
        assert sess.get_inputs()[0].name == "weather_sequence"
        assert sess.get_outputs()[0].name == "ghi_forecast_18steps"
        assert sess.run(None, {"weather_sequence": Xs[:3]})[0].shape == (3, FORECAST_STEPS)  # batch ไดนามิก


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"{len(tests)} tests passed")
