"""Tests for the cloud coverage, blend and decision modules (pure functions, no network).

Run inside a worker container:  python -m pytest service/tests/test_forecast_pipeline.py -q
"""

from datetime import datetime, timezone

import numpy as np
import pytest

from service.workers import decision
from service.workers.cloud_coverage import (
    IMPACT_HIGH_FROM,
    IMPACT_MEDIUM_FROM,
    aoi_cloud_fraction,
    clear_sky_index_from_cloud,
    impact_level,
    max_impact_level,
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


def test_impact_thresholds_come_from_kasten_czeplak():
    # 10% and 30% loss of GHI
    assert 1 - clear_sky_index_from_cloud(IMPACT_MEDIUM_FROM) == pytest.approx(0.10)
    assert 1 - clear_sky_index_from_cloud(IMPACT_HIGH_FROM) == pytest.approx(0.30)
    assert round(IMPACT_MEDIUM_FROM, 2) == 0.55 and round(IMPACT_HIGH_FROM, 2) == 0.76
    assert [impact_level(c) for c in (0.0, 0.54, 0.56, 0.75, 0.77, 1.0)] == ["low", "low", "medium", "medium", "high", "high"]
    assert impact_level(None) is None
    assert max_impact_level([None, 0.2, 0.8, None]) == "high" and max_impact_level([None, None]) is None


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
    ghi, w = blend_ghi([100.0], cs, [1.0], [0.0], w0=1.0, tau_min=102)
    assert w == [1.0] and ghi[0] == pytest.approx(cs[0] * 0.25)  # overcast: 1 - 0.75


def test_blend_is_between_the_two_models_and_moves_to_lstm_later():
    cs = [800.0] * 18
    lstm = [700.0] * 18
    cloud = [1.0] * 18
    lead = [10.0 * (i + 1) for i in range(18)]
    ghi, w = blend_ghi(lstm, cs, cloud, lead, w0=0.9, tau_min=102)
    assert all(200.0 <= g <= 700.0 for g in ghi)
    assert ghi == sorted(ghi) and w == sorted(w, reverse=True)


def test_night_steps_are_zero_and_steps_without_cloud_forecast_keep_the_lstm():
    ghi, w = blend_ghi([50.0, 40.0, 300.0], [0.0, 30.0, 600.0], [1.0, None, 0.0], [10.0, None, 30.0])
    assert ghi[0] == 0.0 and w[0] == 0.0          # night
    assert ghi[1] == 40.0 and w[1] == 0.0         # no usable frame for this step (e.g. sun too low)
    assert w[2] > 0.0


# ----------------------------------------------------------------------------- solar geometry
def test_clearsky_is_zero_at_night_and_high_at_noon_in_hat_yai():
    lat, lon = 7.0086, 100.4988
    assert clearsky_ghi_at(lat, lon, datetime(2026, 10, 4, 17, 0, tzinfo=timezone.utc)) == 0.0   # 00:00 local
    noon = clearsky_ghi_at(lat, lon, datetime(2026, 10, 4, 5, 20, tzinfo=timezone.utc))          # ~12:20 local
    assert 900.0 < noon < 1100.0
    assert solar_zenith_deg(lat, lon, datetime(2026, 10, 4, 5, 20, tzinfo=timezone.utc)) < 20.0


# ----------------------------------------------------------------------------- decision
def _decide(ghi, cloud, cloud_now=None, target=2000.0, cs=None):
    cs = cs or [900.0] * len(ghi)
    return decision.evaluate(ghi, cs, AREA, ETA, target, cloud, cloud_now, STEP_METRICS)


def test_decision_matrix_target_met():
    ghi = [600.0] * 18  # 3240 kW >= 2000
    assert _decide(ghi, [0.1] * 18).alert_level == "normal"
    assert _decide(ghi, [0.6] * 18).alert_level == "watch"
    d = _decide(ghi, [0.9] * 18)
    assert d.alert_level == "warning" and d.delta_p_kw == 0.0 and d.reserve_kw == d.buffer_kw > 0.0


def test_decision_matrix_shortfall():
    ghi = [300.0] * 18  # 1620 kW < 2000 -> 380 kW short
    low, mid, high = _decide(ghi, [0.1] * 18), _decide(ghi, [0.6] * 18), _decide(ghi, [0.9] * 18)
    assert (low.alert_level, mid.alert_level, high.alert_level) == ("warning", "warning", "critical")
    assert low.delta_p_kw == pytest.approx(380.0) and low.reserve_kw == pytest.approx(380.0)
    assert mid.reserve_kw == pytest.approx(380.0 + mid.buffer_kw) and mid.buffer_kw > 0.0
    assert high.reserve_kw == mid.reserve_kw and low.shortfall_in_min == 10


def test_decision_uses_only_the_next_hour_of_cloud_and_the_newest_real_frame():
    ghi = [600.0] * 18
    late_cloud = [0.1] * 6 + [0.95] * 12          # heavy cloud only after 60 minutes
    assert _decide(ghi, late_cloud).alert_level == "normal"
    assert _decide(ghi, [0.1] * 18, cloud_now=0.95).alert_level == "warning"


def test_decision_without_satellite_is_uncertain_not_clear():
    ok = _decide([600.0] * 18, [None] * 18)
    short = _decide([300.0] * 18, [None] * 18)
    assert ok.alert_level == "normal" and ok.cloud_impact_level is None
    assert short.alert_level == "warning" and short.reserve_kw > short.delta_p_kw


def test_night_is_not_an_alert():
    d = _decide([0.0] * 18, [None] * 18, cs=[0.0] * 18, target=5000.0)
    assert d.is_night and d.alert_level == "night" and d.delta_p_kw == 0.0 and d.reserve_kw == 0.0


def test_shortfall_only_counts_daylight_steps():
    # sunset inside the horizon: the dark steps must not create a 5000 kW "shortfall"
    cs = [400.0] * 6 + [0.0] * 12
    ghi = [450.0] * 6 + [0.0] * 12        # 2430 kW in daylight, target 2000
    d = _decide(ghi, [0.1] * 18, cs=cs)
    assert not d.is_night and d.alert_level == "normal" and d.delta_p_kw == 0.0


def test_rmse_interpolation():
    assert decision.rmse_at_lead(STEP_METRICS, 10) == 53.6
    assert decision.rmse_at_lead(STEP_METRICS, 20) == pytest.approx((53.6 + 70.38) / 2)
    assert decision.rmse_at_lead(STEP_METRICS, 500) == 96.2
    assert decision.rmse_at_lead(None, 60) is None and decision.rmse_at_lead({}, 60) is None
