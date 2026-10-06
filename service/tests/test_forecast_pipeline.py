"""Tests for the cloud coverage, blend and decision modules (pure functions, no network).

Run inside a worker container:  python -m pytest service/tests/test_forecast_pipeline.py -q
"""

from datetime import datetime, timezone

import numpy as np
import pytest

from service.workers import decision
from service.workers.cloud_coverage import (
    SatelliteCalibration,
    aoi_brightness,
    aoi_cloud_fraction,
    ghi_loss,
    held_observation_weight,
    impact_level,
    load_calibration,
    max_impact_level,
    model_share,
    observed_then_forecast,
)
from service.workers.ghi_blend import blend_ghi, satellite_weight
from service.workers.solar_geometry import clearsky_ghi_at, solar_zenith_deg

STEP_METRICS = {
    "test_rmse_plus_10min": 53.6, "test_rmse_plus_30min": 70.38, "test_rmse_plus_60min": 80.43,
    "test_rmse_plus_120min": 90.26, "test_rmse_plus_180min": 96.2,
}
AREA, ETA = 30000.0, 0.18  # 5.4 kW per W/m2


# ----------------------------------------------------------------------------- cloud coverage
def test_cloud_fraction_counts_cloudy_pixels_in_the_centre_box():
    frame = np.zeros((64, 64), dtype=np.float32)
    frame[30:35, 30:35] = 0.1          # the 5x5 AOI, all clear
    frame[30, 30:35] = 0.6             # one cloudy row -> 5 of 25 pixels
    frame[0:10, 0:10] = 0.9            # cloud outside the AOI must not count
    assert aoi_cloud_fraction(frame)[0] == pytest.approx(5 / 25)


def test_cloud_fraction_accepts_model_output_shape():
    frames = np.zeros((1, 18, 1, 64, 64), dtype=np.float32)
    frames[0, 3, 0] = 1.0
    out = aoi_cloud_fraction(frames)
    assert len(out) == 18 and out[3] == 1.0 and out[0] == 0.0


def test_brightness_is_normalised_by_sun_height_and_low_sun_is_not_used():
    frames = np.full((3, 64, 64), 0.10, dtype=np.float32)
    # same brightness: clear at high sun (0.10 / 0.9 < 0.25), cloudy at lower sun (0.10 / 0.35 > 0.25), unusable at 0.2
    assert aoi_cloud_fraction(frames, cos_zenith=[0.9, 0.35, 0.2]) == [0.0, 1.0, None]
    with pytest.raises(ValueError):
        aoi_cloud_fraction(frames, cos_zenith=[0.9])


def test_near_leads_use_the_observed_cloud_cover_and_later_leads_the_forecast():
    assert model_share(10, 30, 90) == 0.0 and model_share(60, 30, 90) == 0.5 and model_share(120, 30, 90) == 1.0
    assert observed_then_forecast(0.6, 0.0, 20, 30, 90) == 0.6        # observed cover is held
    assert observed_then_forecast(0.6, 0.0, 60, 30, 90) == pytest.approx(0.3)
    assert observed_then_forecast(0.6, 0.2, 150, 30, 90) == 0.2       # ConvLSTM forecast
    # nothing is substituted for a part that is missing
    assert observed_then_forecast(0.6, None, 20, 30, 90) == 0.6
    assert observed_then_forecast(0.6, None, 60, 30, 90) is None
    assert observed_then_forecast(0.6, None, 150, 30, 90) is None


def test_brightness_gives_the_clear_sky_index_through_the_calibration():
    cal = SatelliteCalibration(intercept=1.4, slope=3.2)
    frames = np.full((2, 64, 64), 0.10, dtype=np.float32)
    rho = aoi_brightness(frames, cos_zenith=[0.5, 0.2])
    assert rho[0] == pytest.approx(0.2) and rho[1] is None             # low sun is not used
    assert cal.clear_sky_index(0.2) == pytest.approx(1.4 - 0.64)
    assert cal.clear_sky_index(0.0) == cal.k_max and cal.clear_sky_index(1.0) == cal.k_min   # kept in range


def test_no_calibration_file_means_no_calibration(tmp_path):
    assert load_calibration(tmp_path / "missing.json") is None
    path = tmp_path / "calibration.json"
    path.write_text('{"intercept": 1.39, "slope": 3.23, "pairs": 73}', encoding="utf-8")
    cal = load_calibration(path)
    assert (cal.intercept, cal.slope) == (1.39, 3.23)


def test_impact_level_comes_from_the_expected_loss_of_irradiance():
    assert ghi_loss(1.1) == 0.0 and ghi_loss(0.75) == pytest.approx(0.25) and ghi_loss(-0.2) == 1.0
    assert [impact_level(x) for x in (0.0, 0.09, 0.10, 0.30, 0.31, 1.0)] == ["low", "low", "medium", "medium", "high", "high"]
    assert impact_level(None) is None
    assert max_impact_level([None, 0.05, 0.4, None]) == "high" and max_impact_level([None, None]) is None


# ----------------------------------------------------------------------------- blend
def test_weight_decays_with_lead_time():
    assert satellite_weight(60, w0=0.9, tau_min=102) == pytest.approx(0.5, abs=0.005)
    assert satellite_weight(10, 0.9, 102) > satellite_weight(60, 0.9, 102) > satellite_weight(180, 0.9, 102)
    assert satellite_weight(180, 0.9, 102) == pytest.approx(0.154, abs=0.005)


def test_blend_without_satellite_equals_lstm():
    lstm, cs = [500.0, 400.0, 300.0], [800.0, 700.0, 600.0]
    ghi, w = blend_ghi(lstm, cs, [None] * 3, [None] * 3)
    assert ghi == lstm and w == [0.0, 0.0, 0.0]


def test_blend_with_full_weight_equals_satellite():
    cs = [800.0]
    ghi, w = blend_ghi([100.0], cs, [0.25], [0.0], w0=1.0, tau_min=102)
    assert w == [1.0] and ghi[0] == pytest.approx(cs[0] * 0.25)  # satellite clear-sky index 0.25


def test_blend_is_between_the_two_models_and_moves_to_lstm_later():
    cs = [800.0] * 18
    lstm = [700.0] * 18
    k_sat = [0.25] * 18
    lead = [10.0 * (i + 1) for i in range(18)]
    ghi, w = blend_ghi(lstm, cs, k_sat, lead, w0=0.9, tau_min=102)
    assert all(200.0 <= g <= 700.0 for g in ghi)
    assert ghi == sorted(ghi) and w == sorted(w, reverse=True)


def test_night_steps_are_zero_and_steps_without_a_satellite_value_keep_the_lstm():
    ghi, w = blend_ghi([50.0, 40.0, 300.0], [0.0, 30.0, 600.0], [0.3, None, 0.9], [10.0, None, 30.0])
    assert ghi[0] == 0.0 and w[0] == 0.0          # night
    assert ghi[1] == 40.0 and w[1] == 0.0         # no usable frame for this step (e.g. sun too low)
    assert w[2] > 0.0


def test_held_observation_fades_out_instead_of_stopping():
    assert held_observation_weight(20) == 1.0 and held_observation_weight(30) == 1.0
    assert held_observation_weight(50) == pytest.approx(0.5) and held_observation_weight(70) == 0.0
    cs, lstm = [800.0] * 3, [400.0] * 3
    ghi, w = blend_ghi(lstm, cs, [1.0] * 3, [30.0, 50.0, 70.0], w0=0.9, tau_min=102, weight_scale=[1.0, 0.5, 0.0])
    assert w[0] > w[1] > w[2] == 0.0 and ghi[2] == 400.0 and ghi[0] > ghi[1] > ghi[2]


# ----------------------------------------------------------------------------- solar geometry
def test_clearsky_is_zero_at_night_and_high_at_noon_in_hat_yai():
    lat, lon = 7.0086, 100.4988
    assert clearsky_ghi_at(lat, lon, datetime(2026, 10, 4, 17, 0, tzinfo=timezone.utc)) == 0.0   # 00:00 local
    noon = clearsky_ghi_at(lat, lon, datetime(2026, 10, 4, 5, 20, tzinfo=timezone.utc))          # ~12:20 local
    assert 900.0 < noon < 1100.0
    assert solar_zenith_deg(lat, lon, datetime(2026, 10, 4, 5, 20, tzinfo=timezone.utc)) < 20.0


# ----------------------------------------------------------------------------- decision
LOW, MEDIUM, HIGH = 0.05, 0.20, 0.50   # expected loss of irradiance from the satellite branch


def _decide(ghi, loss, loss_now=None, target=2000.0, cs=None):
    cs = cs or [900.0] * len(ghi)
    return decision.evaluate(ghi, cs, AREA, ETA, target, loss, loss_now, STEP_METRICS)


def test_decision_matrix_target_met():
    ghi = [600.0] * 18  # 3240 kW >= 2000
    assert _decide(ghi, [LOW] * 18).alert_level == "normal"
    assert _decide(ghi, [MEDIUM] * 18).alert_level == "watch"
    d = _decide(ghi, [HIGH] * 18)
    assert d.alert_level == "warning" and d.delta_p_kw == 0.0 and d.reserve_kw == d.buffer_kw > 0.0


def test_decision_matrix_shortfall():
    ghi = [300.0] * 18  # 1620 kW < 2000 -> 380 kW short
    low, mid, high = _decide(ghi, [LOW] * 18), _decide(ghi, [MEDIUM] * 18), _decide(ghi, [HIGH] * 18)
    assert (low.alert_level, mid.alert_level, high.alert_level) == ("warning", "warning", "critical")
    assert low.delta_p_kw == pytest.approx(380.0) and low.reserve_kw == pytest.approx(380.0)
    assert mid.reserve_kw == pytest.approx(380.0 + mid.buffer_kw) and mid.buffer_kw > 0.0
    assert high.reserve_kw == mid.reserve_kw and low.shortfall_in_min == 10


def test_decision_uses_only_the_next_hour_and_the_newest_real_frame():
    ghi = [600.0] * 18
    late = [LOW] * 6 + [0.95] * 12                # heavy loss only after 60 minutes
    assert _decide(ghi, late).alert_level == "normal"
    assert _decide(ghi, [LOW] * 18, loss_now=0.95).alert_level == "warning"


def test_decision_without_satellite_is_uncertain_not_clear():
    ok = _decide([600.0] * 18, [None] * 18)
    short = _decide([300.0] * 18, [None] * 18)
    assert ok.alert_level == "normal" and ok.cloud_impact_level is None
    assert short.alert_level == "warning" and short.reserve_kw > short.delta_p_kw


def test_night_is_not_an_alert():
    d = _decide([0.0] * 18, [None] * 18, cs=[0.0] * 18, target=5000.0)
    assert d.is_night and d.alert_level == "night" and d.delta_p_kw == 0.0 and d.reserve_kw == 0.0


def test_shortfall_only_counts_daylight_steps():
    # sunset inside the horizon: the dark steps must not create a "shortfall"
    cs = [400.0] * 6 + [0.0] * 12
    ghi = [450.0] * 6 + [0.0] * 12        # 2430 kW in daylight
    d = _decide(ghi, [LOW] * 18, cs=cs)
    assert not d.is_night and d.alert_level == "normal" and d.delta_p_kw == 0.0
    assert d.target_profile_kw[-1] == 0.0


def test_target_follows_the_sun():
    # morning: clear sky gives 5.4 * 300 = 1620 kW, far below the 5000 kW dispatch target
    cs = [300.0] * 18
    clear = _decide([280.0] * 18, [0.03] * 18, target=5000.0, cs=cs)        # 1512 kW >= 0.8 * 1620
    assert clear.alert_level == "normal" and clear.delta_p_kw == 0.0
    assert clear.target_profile_kw[0] == pytest.approx(0.8 * 1620.0)
    cloudy = _decide([150.0] * 18, [HIGH] * 18, target=5000.0, cs=cs)       # 810 kW < 1296
    assert cloudy.alert_level == "critical" and cloudy.delta_p_kw == pytest.approx(1296.0 - 810.0)
    # around noon the dispatch target is the limit again
    noon = _decide([900.0] * 18, [0.03] * 18, target=3000.0, cs=[1000.0] * 18)
    assert noon.target_profile_kw[0] == 3000.0


def test_uncertainty_band_is_the_forecast_plus_minus_the_rmse_of_the_lead_time():
    meta = {"daylight_metrics": {"test_day_rmse_plus_10min": 80.0, "test_day_rmse_plus_30min": 100.0, "test_day_mae_plus_10min": 50.0},
            "step_metrics": STEP_METRICS}
    metrics = decision.daylight_rmse_metrics(meta)
    assert metrics == {"test_rmse_plus_10min": 80.0, "test_rmse_plus_30min": 100.0}      # daylight errors, RMSE only
    assert decision.daylight_rmse_metrics({"step_metrics": STEP_METRICS}) == STEP_METRICS  # older model
    lower, upper = decision.uncertainty_band([500.0, 40.0, 950.0, 30.0], [900.0, 900.0, 1000.0, 0.0], metrics)
    assert (lower[0], upper[0]) == (420.0, 580.0)            # +10 min: -/+ 80
    assert (lower[1], upper[1]) == (0.0, 130.0)              # +20 min: -/+ 90, never below 0
    assert (lower[2], upper[2]) == (850.0, 1050.0)           # +30 min: -/+ 100
    assert (lower[3], upper[3]) == (0.0, 0.0)                # night
    capped = decision.uncertainty_band([1150.0], [1000.0], metrics)
    assert capped[1][0] == 1200.0                            # at most 1.2 x clear sky
    assert decision.uncertainty_band([500.0], [900.0], None) is None


def test_rmse_interpolation():
    assert decision.rmse_at_lead(STEP_METRICS, 10) == 53.6
    assert decision.rmse_at_lead(STEP_METRICS, 20) == pytest.approx((53.6 + 70.38) / 2)
    assert decision.rmse_at_lead(STEP_METRICS, 500) == 96.2
    assert decision.rmse_at_lead(None, 60) is None and decision.rmse_at_lead({}, 60) is None


# ----------------------------------------------------------------------------- frames kept for the cloud player
class _FakeMinio:
    def __init__(self):
        self.objects = {}

    def bucket_exists(self, bucket):
        return True

    def put_object(self, bucket, name, data, length, content_type=None):
        self.objects[(bucket, name)] = data.read()


def test_forecast_frames_are_stored_with_their_meta_and_an_empty_round_says_so(monkeypatch):
    import io as _io
    import json

    from PIL import Image

    from service.workers import satellite_preprocessor as sp

    fake = _FakeMinio()
    monkeypatch.setattr(sp, "connect_minio", lambda read_timeout=1.5: fake)
    end = datetime(2026, 10, 5, 6, 0, tzinfo=timezone.utc)
    predicted = np.linspace(0.0, 1.0, 18 * 64 * 64, dtype=np.float32).reshape(1, 18, 1, 64, 64)   # the model's output shape

    stored = sp.save_forecast_frames("ST-X", end, predicted, [0.5] * 17 + [None], "ok")
    assert stored == 18
    names = sorted(n for b, n in fake.objects if b == sp.FORECAST_BUCKET)
    assert names[0] == "ST-X/meta.json" and names[1] == "ST-X/step_01.png" and names[-1] == "ST-X/step_18.png"
    meta = json.loads(fake.objects[(sp.FORECAST_BUCKET, "ST-X/meta.json")])
    assert meta["steps"] == 18 and meta["end_time"] == end.isoformat() and meta["status"] == "ok"
    assert meta["cloud_pct"][0] == 50.0 and meta["cloud_pct"][-1] is None      # low sun: no cloud cover for that frame
    first = np.asarray(Image.open(_io.BytesIO(fake.objects[(sp.FORECAST_BUCKET, "ST-X/step_01.png")])))
    assert first.shape == (64, 64) and first.dtype == np.uint8                 # the frame itself, 8-bit grey

    # a round without a ConvLSTM forecast: no frame is written, the meta says 0 steps (nothing old is shown as current)
    assert sp.save_forecast_frames("ST-X", end, None, None, "observed_only", "incomplete_window") == 0
    meta = json.loads(fake.objects[(sp.FORECAST_BUCKET, "ST-X/meta.json")])
    assert meta["steps"] == 0 and meta["status"] == "observed_only" and meta["cloud_pct"] == []

    # storage down: the forecast itself must not fail
    monkeypatch.setattr(sp, "connect_minio", lambda read_timeout=1.5: None)
    assert sp.save_forecast_frames("ST-X", end, predicted, None, "ok") == 0


def test_calibration_check_reports_the_error_of_the_current_line_per_station():
    from service.training import calibrate_satellite_ghi as cal

    t0 = datetime(2026, 10, 5, 3, 0, tzinfo=timezone.utc)
    current = {"intercept": 1.0, "slope": 2.0, "k_min": 0.05, "k_max": 1.15, "stations": ["ST-A"]}
    on_line = [{"station_id": "ST-A", "time": t0, "rho": 0.1 + 0.005 * i, "k": 1.0 - 2.0 * (0.1 + 0.005 * i)} for i in range(40)]
    off_line = [{"station_id": "ST-B", "time": t0, "rho": 0.2, "k": 0.5} for _ in range(35)]      # the line gives 0.6
    too_few = [{"station_id": "ST-C", "time": t0, "rho": 0.2, "k": 0.6} for _ in range(5)]

    checked = cal.check(on_line + off_line + too_few, current)
    assert set(checked) == {"ST-A", "ST-B"}                                    # ST-C has too few measured slots to say anything
    assert checked["ST-A"]["fitted"] is True and checked["ST-A"]["mae"] == 0.0 and checked["ST-A"]["pairs"] == 40
    assert checked["ST-B"]["fitted"] is False and checked["ST-B"]["mae"] == pytest.approx(0.1) and checked["ST-B"]["pairs"] == 35


def test_learning_curve_is_logged_one_point_per_epoch():
    from service.training.curves import log_history

    class FakeMlflow:
        def __init__(self):
            self.points = []

        def log_metric(self, key, value, step=None):
            self.points.append((key, value, step))

    fake = FakeMlflow()
    history = [
        {"epoch": 0, "val_mae": 56.8},                                               # the deployed model, before any update
        {"epoch": 1, "train_loss": 0.021, "val_mae": 57.9, "lr": 1e-4, "aoi_frames": 654},
        {"epoch": 2, "train_loss": 0.018, "val_mae": float("nan"), "lr": 5e-5, "note": "text is ignored"},
    ]
    assert log_history(fake, history, skip=("aoi_frames",)) == 6
    assert ("epoch_val_mae", 56.8, 0) in fake.points and ("epoch_train_loss", 0.018, 2) in fake.points
    assert ("epoch_lr", 5e-5, 2) in fake.points
    assert not any(k in ("epoch_epoch", "epoch_aoi_frames", "epoch_note") for k, _, _ in fake.points)
    assert not any(v != v for _, v, _ in fake.points)                               # a NaN is never logged
    assert log_history(fake, None) == 0


def test_only_one_ingestion_round_runs_at_a_time():
    import asyncio

    from service.workers.round_lock import ROUND_LOCK_KEY, clear_round_lock, run_one_at_a_time

    class Redis:
        def __init__(self):
            self.keys = {}

        async def set(self, key, value, nx=False, ex=None):
            if nx and key in self.keys:
                return None
            self.keys[key] = value
            return True

        async def delete(self, key):
            self.keys.pop(key, None)

    redis, seen = Redis(), []

    async def other():
        raise AssertionError("a second round ran next to the first")

    async def first():
        seen.append(dict(redis.keys))                                # the lock is held while the round runs
        return await run_one_at_a_time(redis, other)                 # a scheduled round fires meanwhile

    assert asyncio.run(run_one_at_a_time(redis, first)) == (True, (False, None))
    assert seen == [{ROUND_LOCK_KEY: "1"}] and redis.keys == {}      # released afterwards

    async def fails():
        raise RuntimeError("round failed")

    with pytest.raises(RuntimeError):
        asyncio.run(run_one_at_a_time(redis, fails))
    assert redis.keys == {}                                          # a failed round does not block the next one

    redis.keys[ROUND_LOCK_KEY] = "1"                                 # left behind by a worker killed mid-round
    asyncio.run(clear_round_lock(redis))
    assert redis.keys == {}

    async def plain():
        return "done"

    assert asyncio.run(run_one_at_a_time(None, plain)) == (True, "done")
