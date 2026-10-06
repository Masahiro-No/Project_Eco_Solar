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
from service.training.features import (
    build_station_frame,
    day_folds,
    forecast_days,
    make_live_windows,
    make_windows,
    measured_slots_per_day,
)

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


def test_label_claiming_sunlight_at_night_is_ignored():
    w = _synthetic_weather(days=1, start="2026-10-02 00:00")
    night_utc = pd.Timestamp("2026-10-02 16:10", tz="UTC")  # 23:10 เวลาไทย
    f = build_station_frame(w, labels=pd.Series([579.8, 0.0], index=[night_utc, night_utc + pd.Timedelta(minutes=10)]))
    assert f.loc[night_utc, "GHI"] == 0.0 and not bool(f.loc[night_utc, "is_label"])
    # ค่า 0 ตอนกลางคืนเป็นค่าที่วัดได้จริง จึงยังใช้
    assert bool(f.loc[night_utc + pd.Timedelta(minutes=10), "is_label"])


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


def _measured(frame: pd.DataFrame, stamps: list, value: float = 400.0) -> pd.Series:
    """ค่าที่วัดจริงบนช่องเวลาของ frame: มีค่าเฉพาะที่ stamps นอกนั้นเป็น NaN"""
    s = pd.Series(np.nan, index=frame.index)
    s.loc[stamps] = value
    return s


def _day_stamps(day: int, slots: int = 18) -> list:
    """ช่องเวลา 10:00 น. ไทยเป็นต้นไปของวันที่ `day` ต.ค. 2026"""
    return [pd.Timestamp(f"2026-10-{day:02d} 03:00", tz="UTC") + pd.Timedelta(minutes=10 * i) for i in range(slots)]


def test_live_windows_take_inputs_from_weather_and_targets_from_measured_values():
    w = _synthetic_weather(days=4, start="2026-10-01 00:00")
    plain = build_station_frame(w)
    stamps = _day_stamps(3)
    night = pd.Timestamp("2026-10-03 16:00", tz="UTC")   # 23:00 น. ไทย: วัดได้ 0 จริง แต่ผลกลางคืนไม่ถูกใช้
    measured = _measured(plain, stamps)
    measured.loc[night] = 0.0

    X, Y, M, starts = make_live_windows(plain, measured, stride=1)
    assert X.shape[1:] == (LOOKBACK_STEPS, 16) and Y.shape == M.shape == (len(X), FORECAST_STEPS)
    assert M.any(axis=1).all()                      # ทุก window มีค่าวัดจริงให้เรียนอย่างน้อย 1 ช่อง
    assert np.all(Y[M] == 400.0)                    # เป้าหมายที่ใช้คือค่าที่วัดจริง
    assert int(M.sum()) == len(stamps) * FORECAST_STEPS   # แต่ละค่าวัดเป็นเป้าหมายของ 18 window; ค่ากลางคืนไม่ถูกนับ

    # ข้อมูลป้อนคือสภาพอากาศ: ค่าที่วัดจริงไม่เคยเข้าไปอยู่ใน GHI ของช่วงย้อนหลัง
    ghi_col = ALIGNED_FEATURE_COLS.index("GHI")
    by_start = {pd.Timestamp(s, tz="UTC"): i for i, s in enumerate(starts)}
    start = stamps[-1] - pd.Timedelta(minutes=10 * (LOOKBACK_STEPS + 3))   # window ที่ช่วงย้อนหลังคร่อมเวลาที่มีค่าวัด
    lookback_slots = pd.date_range(start, periods=LOOKBACK_STEPS, freq="10min")
    assert len(set(lookback_slots) & set(stamps)) > 0
    assert np.allclose(X[by_start[start], :, ghi_col], plain.loc[lookback_slots, "GHI"].to_numpy(np.float32))
    assert not np.any(X[by_start[start], :, ghi_col] == 400.0)

    # ไม่มีค่าวัดจริงเลย: ไม่มี window ให้เรียน
    assert len(make_live_windows(plain, _measured(plain, []), stride=1)[0]) == 0


def test_every_measured_day_is_held_out_once_and_never_trained_on_in_its_own_fold():
    w = _synthetic_weather(days=7, start="2026-10-01 00:00")
    plain = build_station_frame(w)
    measured = _measured(plain, [s for d in (3, 4, 6) for s in _day_stamps(d)])
    X, Y, M, starts = make_live_windows(plain, measured, stride=1)
    days = forecast_days(starts)
    assert days.shape == M.shape

    folds = day_folds(days, M)
    assert [f["days"] for f in folds] == [["2026-10-03"], ["2026-10-04"], ["2026-10-06"]]   # 3 วัน: กันทีละวัน
    for fold in folds:
        held = np.array(fold["days"], dtype="datetime64[D]")
        assert len(fold["train_idx"]) and len(fold["test_idx"]) and not set(fold["train_idx"]) & set(fold["test_idx"])
        assert not np.isin(days[fold["train_idx"]], held).any()            # ไม่มี window เทรนที่ช่องพยากรณ์แตะวันที่กันไว้
        assert fold["test_mask"].shape == (len(fold["test_idx"]), FORECAST_STEPS)
        assert np.isin(days[fold["test_idx"]][fold["test_mask"]], held).all()
    # ค่าวัดจริงทุกค่าถูกใช้ตรวจหนึ่งครั้งพอดี
    assert sum(int(f["test_mask"].sum()) for f in folds) == int(M.sum())

    # วันมากกว่าจำนวนกลุ่ม: แจกวันเข้ากลุ่มสลับกันตามเวลา ทุกวันยังถูกกันไว้ครั้งเดียว
    two = day_folds(days, M, max_folds=2)
    assert [f["days"] for f in two] == [["2026-10-03", "2026-10-06"], ["2026-10-04"]]
    assert sum(int(f["test_mask"].sum()) for f in two) == int(M.sum())

    # มีค่าวัดจริงวันเดียว: ไม่มีวันให้เทรน จึงแบ่งไม่ได้
    _, _, M1, starts1 = make_live_windows(plain, _measured(plain, _day_stamps(3)), stride=1)
    assert day_folds(forecast_days(starts1), M1) == []


def test_new_days_are_counted_by_date_not_by_upload():
    from service.training.retrain_timeseries import days_with_new_values

    w = _synthetic_weather(days=7, start="2026-10-01 00:00")
    plain = build_station_frame(w)
    # 3 ต.ค. มีค่าวัด 18 ช่อง, 4 ต.ค. มี 2 ช่อง; ค่าหนึ่งช่องเป็นเป้าหมายของหลาย window แต่นับช่องละครั้ง
    _, _, M, starts = make_live_windows(plain, _measured(plain, _day_stamps(3) + _day_stamps(4, slots=2)), stride=1)
    assert measured_slots_per_day(starts, M) == {"2026-10-03": 18, "2026-10-04": 2}
    assert measured_slots_per_day(starts[:0], M[:0]) == {}

    used = {"ST-002|2026-10-01", "ST-002|2026-10-02"}
    assert days_with_new_values(used, used) == []
    # สองสถานีในวันเดียวกัน = 1 วัน; สถานีใหม่ในวันที่เคยใช้แล้วก็นับวันนั้น
    now = used | {"ST-002|2026-10-03", "ST-003|2026-10-03", "ST-003|2026-10-01"}
    assert days_with_new_values(now, used) == ["2026-10-01", "2026-10-03"]
    assert days_with_new_values(now, set()) == ["2026-10-01", "2026-10-02", "2026-10-03"]


def test_new_model_is_accepted_only_for_a_clear_improvement():
    from service.training.retrain_timeseries import accepts

    assert accepts(100.0, 96.9, 0.03)
    assert not accepts(100.0, 98.0, 0.03)   # ดีขึ้น 2%: อยู่ในระดับความแกว่ง ไม่รับ
    assert not accepts(100.0, 100.0, 0.03) and not accepts(100.0, 105.0, 0.03)
    assert accepts(100.0, 99.9, 0.0) and not accepts(100.0, 100.1, 0.0)


def test_fine_tune_learns_only_from_the_steps_it_is_given():
    """ช่องที่ไม่มีค่าวัดจริงใส่เป้าหมายเป็นค่าที่เป็นไปไม่ได้: ถ้า loss ไม่กรองช่อง โมเดลจะถูกดึงไปหาค่านั้น"""
    import torch

    from service.models.solar_lstm import SolarLSTMForecaster
    from service.training.onnx_weights import load_onnx_into_model
    from service.training.retrain_timeseries import evaluate_mae, fine_tune

    fs = joblib.load(MODEL_DIR / "feature_scaler.joblib")
    ts = joblib.load(MODEL_DIR / "target_scaler.joblib")
    f = build_station_frame(_synthetic_weather(days=8))
    X, Y, _, _ = make_windows(f, stride=6)
    n = len(X)
    Xs = fs.transform(X.reshape(-1, 16)).reshape(n, LOOKBACK_STEPS, 16).astype(np.float32)
    mask = np.zeros(Y.shape, bool)
    mask[:, :6] = True
    poisoned = np.where(mask, Y, 5000.0).astype(np.float32)
    Ys = ts.transform(poisoned.reshape(-1, 1)).reshape(n, FORECAST_STEPS).astype(np.float32)
    dev = torch.device("cpu")

    def run(train_mask):
        model = SolarLSTMForecaster()
        load_onnx_into_model(model, str(MODEL_DIR / "solar_ghi_lstm.onnx"))
        res = fine_tune(model, Xs, Ys, None, None, ts, dev, epochs=2, lr=1e-3, batch_size=32, train_mask=train_mask)
        return res, evaluate_mae(model, Xs, Y, ts, dev, mask=~mask)   # วัดบนช่องที่ไม่ได้ให้เรียน เทียบกับค่าจริงของช่องนั้น

    masked, masked_mae = run(mask)
    _, unmasked_mae = run(None)
    assert masked["best_epoch"] == 2 and "val_mae" not in masked["history"][-1]   # ไม่มีชุดตรวจ: ใช้สถานะสุดท้าย
    assert masked_mae < unmasked_mae / 2   # ไม่กรองช่อง: ช่องที่ใส่ค่า 5000 ลากผลพยากรณ์ไปไกลกว่ามาก


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
        export_onnx(model, out, LOOKBACK_STEPS)
        assert verify_onnx_matches(model, out, LOOKBACK_STEPS) <= 1e-4
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
