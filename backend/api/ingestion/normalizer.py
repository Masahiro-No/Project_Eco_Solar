from datetime import datetime, timezone
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field

from api.ingestion.solar_calculator import SolarCalculator


class CanonicalWeatherRecord(BaseModel):
    """Canonical Unified Weather Record for all solar forecasting models & database."""
    timestamp: datetime
    station_id: str
    ghi: float = Field(..., description="Global Horizontal Irradiance in W/m^2")
    dni: float = Field(default=0.0, description="Direct Normal Irradiance in W/m^2")
    dhi: Optional[float] = Field(default=None, description="Diffuse Horizontal Irradiance in W/m^2")
    clearsky_ghi: float = Field(default=0.0, description="Calculated Clear-Sky GHI in W/m^2 (Haurwitz model)")
    clearsky_index: float = Field(default=0.0, description="Clear-Sky Index k_c = GHI / Clearsky_GHI (range 0.0-1.2)")
    solar_zenith_angle: float = Field(default=90.0, description="Solar Zenith Angle in degrees (0 = overhead, 90 = horizon)")
    is_daylight: bool = Field(default=False, description="True if sun is above threshold (> 10 W/m^2)")
    temperature: float = Field(..., description="Air temperature in Celsius")
    relative_humidity: float = Field(..., description="Relative humidity in percentage (0-100)")
    wind_speed: float = Field(default=0.0, description="Wind speed in m/s")
    cloud_cover: float = Field(default=0.0, description="Effective cloud cover percentage (0-100)")
    surface_pressure: Optional[float] = Field(default=None, description="Surface pressure in hPa")
    source: str = Field(..., description="Source origin: 'open_meteo', 'nsrdb', 'openweather'")

    model_config = ConfigDict(from_attributes=True)


class WeatherDataNormalizer:
    """Adapter class to map heterogeneous weather formats into CanonicalWeatherRecord."""

    @staticmethod
    def normalize_open_meteo(
        raw_json: dict[str, Any],
        station_id: str,
        lat: float = 7.0086,
        lon: float = 100.4988,
    ) -> CanonicalWeatherRecord:
        """Map Open-Meteo Current / Hourly API JSON response."""
        current = raw_json.get("current", {})

        time_str = current.get("time")
        if time_str:
            try:
                dt = datetime.fromisoformat(time_str).replace(tzinfo=timezone.utc)
            except Exception:
                dt = datetime.now(timezone.utc)
        else:
            dt = datetime.now(timezone.utc)

        ghi = float(current.get("shortwave_radiation", 0.0) or 0.0)
        dni = float(current.get("direct_normal_irradiance", 0.0) or 0.0)
        dhi = float(current.get("diffuse_radiation", 0.0) or 0.0) if "diffuse_radiation" in current else None

        # Universal astronomical solar calculations
        solar = SolarCalculator.get_solar_metrics(lat=lat, lon=lon, dt_utc=dt, measured_ghi=ghi)

        # Raw cloud cover from Open-Meteo or fallback to effective cloud cover
        cloud = float(current.get("cloud_cover", 0.0) or 0.0)

        return CanonicalWeatherRecord(
            timestamp=dt,
            station_id=station_id,
            ghi=ghi,
            dni=dni,
            dhi=dhi,
            clearsky_ghi=solar.clearsky_ghi,
            clearsky_index=solar.clearsky_index,
            solar_zenith_angle=solar.zenith_degrees,
            is_daylight=solar.is_daylight,
            temperature=float(current.get("temperature_2m", 25.0)),
            relative_humidity=float(current.get("relative_humidity_2m", 50.0)),
            wind_speed=float(current.get("wind_speed_10m", 0.0) or 0.0),
            cloud_cover=cloud,
            surface_pressure=float(current.get("surface_pressure", 1013.25)) if current.get("surface_pressure") else None,
            source="open_meteo",
        )

    @staticmethod
    def normalize_nsrdb_dict(
        row: dict[str, Any],
        station_id: str,
        lat: float = 7.0086,
        lon: float = 100.4988,
        tz_offset_hours: Optional[int] = None,
    ) -> CanonicalWeatherRecord:
        """Map a single row from NSRDB CSV/DataFrame."""
        clean_row = {k.strip(): v for k, v in row.items()}

        # Parse timestamp
        if "Datetime" in clean_row:
            dt_raw = clean_row["Datetime"]
            if isinstance(dt_raw, datetime):
                dt = dt_raw
            else:
                dt = datetime.fromisoformat(str(dt_raw))
        else:
            y = int(clean_row.get("Year", 2019))
            m = int(clean_row.get("Month", 1))
            d = int(clean_row.get("Day", 1))
            h = int(clean_row.get("Hour", 0))
            minute = int(clean_row.get("Minute", 0))
            dt = datetime(y, m, d, h, minute)

        # Detect timezone from row or argument (NSRDB often specifies 'Time Zone': 7 for Thailand)
        row_tz = tz_offset_hours
        if row_tz is None and "Time Zone" in clean_row:
            try:
                row_tz = int(clean_row["Time Zone"])
            except Exception:
                row_tz = 0

        if dt.tzinfo is None:
            if row_tz:
                from datetime import timedelta
                dt = dt.replace(tzinfo=timezone(timedelta(hours=row_tz))).astimezone(timezone.utc)
            else:
                dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)

        ghi = float(clean_row.get("GHI", clean_row.get("ghi", 0.0)) or 0.0)
        dni = float(clean_row.get("DNI", clean_row.get("dni", 0.0)) or 0.0)
        dhi = float(clean_row.get("DHI", clean_row.get("dhi", 0.0)) or 0.0)
        temp = float(clean_row.get("Temperature", clean_row.get("air_temperature", clean_row.get("temperature", 25.0))))
        rh = float(clean_row.get("Relative Humidity", clean_row.get("relative_humidity", 50.0)))
        wind = float(clean_row.get("Wind Speed", clean_row.get("wind_speed", 0.0)) or 0.0)
        pressure = float(clean_row.get("Pressure", clean_row.get("surface_pressure", 1013.25))) if "Pressure" in clean_row else None

        # Universal astronomical solar calculations
        solar = SolarCalculator.get_solar_metrics(lat=lat, lon=lon, dt_utc=dt, measured_ghi=ghi)

        # NSRDB lacks a direct 0-100% cloud_cover column; compute Effective Cloud Cover from Clearsky Index
        if "Cloud Cover" in clean_row or "cloud_cover" in clean_row:
            cloud = float(clean_row.get("Cloud Cover", clean_row.get("cloud_cover", 0.0)) or 0.0)
        else:
            # Effective cloud cover = (1 - k_c) * 100 during daylight, 0 at night
            cloud = round((1.0 - min(solar.clearsky_index, 1.0)) * 100.0, 2) if solar.is_daylight else 0.0

        return CanonicalWeatherRecord(
            timestamp=dt,
            station_id=station_id,
            ghi=ghi,
            dni=dni,
            dhi=dhi,
            clearsky_ghi=solar.clearsky_ghi,
            clearsky_index=solar.clearsky_index,
            solar_zenith_angle=solar.zenith_degrees,
            is_daylight=solar.is_daylight,
            temperature=temp,
            relative_humidity=rh,
            wind_speed=wind,
            cloud_cover=cloud,
            surface_pressure=pressure,
            source="nsrdb",
        )

    @staticmethod
    def normalize_openweather(
        raw_json: dict[str, Any],
        station_id: str,
        lat: float = 7.0086,
        lon: float = 100.4988,
    ) -> CanonicalWeatherRecord:
        """Map OpenWeather 2.5/3.0 API JSON response."""
        main = raw_json.get("main", {})
        wind = raw_json.get("wind", {})
        clouds = raw_json.get("clouds", {})

        dt_raw = raw_json.get("dt")
        dt = datetime.fromtimestamp(dt_raw, tz=timezone.utc) if dt_raw else datetime.now(timezone.utc)

        temp = float(main.get("temp", 25.0))
        if temp > 150:
            temp -= 273.15

        ghi = float(raw_json.get("ghi", 0.0) or 0.0)
        dni = float(raw_json.get("dni", 0.0) or 0.0)

        solar = SolarCalculator.get_solar_metrics(lat=lat, lon=lon, dt_utc=dt, measured_ghi=ghi)

        return CanonicalWeatherRecord(
            timestamp=dt,
            station_id=station_id,
            ghi=ghi,
            dni=dni,
            dhi=None,
            clearsky_ghi=solar.clearsky_ghi,
            clearsky_index=solar.clearsky_index,
            solar_zenith_angle=solar.zenith_degrees,
            is_daylight=solar.is_daylight,
            temperature=round(temp, 2),
            relative_humidity=float(main.get("humidity", 50.0)),
            wind_speed=float(wind.get("speed", 0.0) or 0.0),
            cloud_cover=float(clouds.get("all", 0.0) or 0.0),
            surface_pressure=float(main.get("pressure", 1013.25)) if "pressure" in main else None,
            source="openweather",
        )
