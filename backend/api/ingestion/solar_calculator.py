"""Solar Position & Clear-Sky Irradiance Calculator

Implements deterministic astronomical equations:
1. Solar Zenith Angle (theta_z) via NOAA / Spencer equations.
2. Clear-Sky Global Horizontal Irradiance (GHI_clearsky) via Haurwitz solar model.
3. Clear-Sky Index (k_c = GHI / GHI_clearsky) with robust night/twilight clamping and NaN protection.
"""

import math
from datetime import datetime, timezone
from typing import NamedTuple


class SolarMetrics(NamedTuple):
    zenith_degrees: float
    elevation_degrees: float
    clearsky_ghi: float
    clearsky_index: float
    is_daylight: bool


class SolarCalculator:
    """Universal deterministic solar astronomical calculator."""

    @staticmethod
    def calculate_solar_position(lat: float, lon: float, dt_utc: datetime) -> tuple[float, float]:
        """Calculate Solar Zenith Angle (degrees) and Solar Elevation Angle (degrees).

        Args:
            lat: Latitude in decimal degrees (e.g. 7.0086 for PSU Hat Yai)
            lon: Longitude in decimal degrees (e.g. 100.4988)
            dt_utc: Datetime object in UTC timezone

        Returns:
            (zenith_degrees, elevation_degrees)
        """
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        else:
            dt_utc = dt_utc.astimezone(timezone.utc)

        # Day of year (1-366)
        day_of_year = dt_utc.timetuple().tm_yday
        hour = dt_utc.hour + (dt_utc.minute / 60.0) + (dt_utc.second / 3600.0)

        # Fractional year in radians
        gamma = 2.0 * math.pi / 365.0 * (day_of_year - 1.0 + (hour - 12.0) / 24.0)

        # Equation of Time (EoT) in minutes (Spencer 1971)
        eot = 229.18 * (
            0.000075
            + 0.001868 * math.cos(gamma)
            - 0.032077 * math.sin(gamma)
            - 0.014615 * math.cos(2.0 * gamma)
            - 0.040849 * math.sin(2.0 * gamma)
        )

        # Solar declination angle in radians
        declination = (
            0.006918
            - 0.399912 * math.cos(gamma)
            + 0.070257 * math.sin(gamma)
            - 0.006758 * math.cos(2.0 * gamma)
            + 0.000907 * math.sin(2.0 * gamma)
            - 0.002697 * math.cos(3.0 * gamma)
            + 0.00148 * math.sin(3.0 * gamma)
        )

        # True Solar Time (TST) in minutes
        tst = (dt_utc.hour * 60.0 + dt_utc.minute + dt_utc.second / 60.0) + eot + (4.0 * lon)
        solar_hour_angle = math.radians((tst / 4.0) - 180.0)

        lat_rad = math.radians(lat)

        # Cosine of Solar Zenith Angle
        cos_zenith = (
            math.sin(lat_rad) * math.sin(declination)
            + math.cos(lat_rad) * math.cos(declination) * math.cos(solar_hour_angle)
        )
        cos_zenith = max(-1.0, min(1.0, cos_zenith))

        zenith_rad = math.acos(cos_zenith)
        zenith_deg = math.degrees(zenith_rad)
        elevation_deg = 90.0 - zenith_deg

        return zenith_deg, elevation_deg

    @staticmethod
    def calculate_clearsky_ghi(zenith_deg: float) -> float:
        """Calculate Clear-Sky GHI in W/m^2 using the robust Haurwitz clear-sky model.

        GHI_clearsky = 1098.0 * cos(theta_z) * exp(-0.057 / cos(theta_z))
        """
        cos_z = math.cos(math.radians(zenith_deg))
        if cos_z <= 0.015:  # Zenith > 89.1 degrees (night / below horizon)
            return 0.0

        ghi_cs = 1098.0 * cos_z * math.exp(-0.057 / cos_z)
        return round(max(0.0, ghi_cs), 2)

    @staticmethod
    def calculate_clearsky_index(ghi: float, clearsky_ghi: float) -> float:
        """Calculate Clearsky Index (k_c = GHI / GHI_clearsky).

        Edge-case Handling:
        1. Night / Twilight (clearsky_ghi < 10.0 W/m^2): k_c = 0.0 to prevent 0/0 and NaN.
        2. Negative sensor readings clamped to 0.0.
        3. Cloud enhancement effect clamped to 1.20 max.
        """
        if clearsky_ghi < 10.0:
            return 0.0

        measured_ghi = max(0.0, ghi)
        raw_kc = measured_ghi / clearsky_ghi

        # Clamping to valid physical range [0.0, 1.2]
        clamped_kc = min(max(raw_kc, 0.0), 1.2)
        return round(clamped_kc, 4)

    @classmethod
    def get_solar_metrics(cls, lat: float, lon: float, dt_utc: datetime, measured_ghi: float) -> SolarMetrics:
        """Compute full standardized solar metrics in one unified call."""
        zenith_deg, elevation_deg = cls.calculate_solar_position(lat, lon, dt_utc)
        cs_ghi = cls.calculate_clearsky_ghi(zenith_deg)
        kc = cls.calculate_clearsky_index(measured_ghi, cs_ghi)
        is_daylight = cs_ghi >= 10.0

        return SolarMetrics(
            zenith_degrees=round(zenith_deg, 2),
            elevation_degrees=round(elevation_deg, 2),
            clearsky_ghi=cs_ghi,
            clearsky_index=kc,
            is_daylight=is_daylight,
        )
