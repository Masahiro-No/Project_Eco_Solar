"""The formulas that exist twice (API side and worker / training side) must give the same result.

The API container has no worker code and the trainer container has no API code, so this file runs where both
are mounted, the ingestion worker:

    docker exec ingestion-worker sh -c 'cd /workspace && pip install -q pytest && python -m pytest service/tests/test_same_formulas.py -q'

Where the API code cannot be imported the tests are skipped.

Not covered here: the 10-minute grid of the model input (api/inference/weather_grid.py against
service/training/features.py). No container has both the API code and the training libraries, so that pair is
still kept in step by hand, and the power formula in the web page against service/workers/decision.py likewise.
"""

import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2] / "backend"
if BACKEND.exists() and str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
pytest.importorskip("api.ingestion.service", reason="the API code is not in this container")

UTC = timezone.utc
PLACES = [(7.0086, 100.4988), (6.931, 100.369), (14.74, 98.63), (6.87, 101.25), (7.56, 99.61), (13.75, 100.5), (18.8, 98.98)]
DAY = [datetime(2026, 10, 6, 0, 0, tzinfo=UTC) + timedelta(minutes=10 * i) for i in range(144)]


def test_a_station_is_at_the_same_pixel_on_both_sides():
    from api.ingestion.service import latlon_to_pixel as api_pixel
    from service.workers.satellite_preprocessor import latlon_to_pixel as worker_pixel

    for lat, lon in PLACES:
        assert tuple(api_pixel(lat, lon)) == tuple(worker_pixel(lat, lon))


def test_sun_position_and_clear_sky_are_the_same_on_both_sides():
    from api.ingestion.solar_calculator import SolarCalculator
    from service.workers.solar_geometry import clearsky_ghi_at, solar_zenith_deg

    for lat, lon in PLACES[:3]:
        for ts in DAY:
            zenith, _ = SolarCalculator.calculate_solar_position(lat, lon, ts)
            assert abs(zenith - solar_zenith_deg(lat, lon, ts)) < 1e-6
            stored = SolarCalculator.get_solar_metrics(lat=lat, lon=lon, dt_utc=ts, measured_ghi=0.0).clearsky_ghi
            assert abs(stored - clearsky_ghi_at(lat, lon, ts)) < 0.006   # the API side stores it rounded to 2 decimals


def test_a_black_tile_counts_as_missing_from_the_same_sun_height():
    from api.ingestion.service import BLANK_TILE_MIN_SUN_ELEVATION_DEG
    from service.workers.satellite_preprocessor import DAYLIGHT_COS_ZENITH

    assert abs(math.sin(math.radians(BLANK_TILE_MIN_SUN_ELEVATION_DEG)) - DAYLIGHT_COS_ZENITH) < 1e-9
