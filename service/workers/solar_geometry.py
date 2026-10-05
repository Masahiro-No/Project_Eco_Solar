"""Solar zenith angle and clear-sky GHI for the workers.

Same equations as backend/api/ingestion/solar_calculator.py (Spencer 1971 solar position,
Haurwitz clear-sky model), so the clear-sky values here match the `clearsky_ghi` feature the
LSTM is fed with. The inference worker image does not contain the backend package, hence this copy.
"""

import math
from datetime import datetime, timezone

NIGHT_CLEARSKY_GHI = 10.0  # W/m2; below this the sun is treated as down (same limit as the backend)


def solar_zenith_deg(lat: float, lon: float, dt_utc: datetime) -> float:
    dt_utc = dt_utc.replace(tzinfo=timezone.utc) if dt_utc.tzinfo is None else dt_utc.astimezone(timezone.utc)
    day_of_year = dt_utc.timetuple().tm_yday
    hour = dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0
    gamma = 2.0 * math.pi / 365.0 * (day_of_year - 1.0 + (hour - 12.0) / 24.0)

    eot = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2.0 * gamma)
        - 0.040849 * math.sin(2.0 * gamma)
    )
    declination = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2.0 * gamma)
        + 0.000907 * math.sin(2.0 * gamma)
        - 0.002697 * math.cos(3.0 * gamma)
        + 0.00148 * math.sin(3.0 * gamma)
    )
    tst = dt_utc.hour * 60.0 + dt_utc.minute + dt_utc.second / 60.0 + eot + 4.0 * lon
    hour_angle = math.radians(tst / 4.0 - 180.0)
    lat_rad = math.radians(lat)
    cos_zenith = math.sin(lat_rad) * math.sin(declination) + math.cos(lat_rad) * math.cos(declination) * math.cos(hour_angle)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos_zenith))))


def clearsky_ghi(zenith_deg: float) -> float:
    """Haurwitz: GHI_cs = 1098 * cos(z) * exp(-0.057 / cos(z)); 0 when the sun is below the horizon."""
    cos_z = math.cos(math.radians(zenith_deg))
    if cos_z <= 0.015:
        return 0.0
    return max(0.0, 1098.0 * cos_z * math.exp(-0.057 / cos_z))


def clearsky_ghi_at(lat: float, lon: float, dt_utc: datetime) -> float:
    return clearsky_ghi(solar_zenith_deg(lat, lon, dt_utc))


def cos_zenith_at(lat: float, lon: float, dt_utc: datetime) -> float:
    return math.cos(math.radians(solar_zenith_deg(lat, lon, dt_utc)))
