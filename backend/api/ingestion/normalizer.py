from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from api.ingestion.solar_calculator import SolarCalculator

# The variables both Open-Meteo requests ask for. A weather row is stored only when Open-Meteo gave every one of
# them: a missing value is never replaced by a constant.
OPEN_METEO_VARIABLES = (
    "temperature_2m", "relative_humidity_2m", "surface_pressure", "wind_speed_10m", "cloud_cover",
    "direct_normal_irradiance", "diffuse_radiation", "shortwave_radiation",
)
OPEN_METEO_STEP_MINUTES = 15  # spacing of the minutely_15 values


class MissingWeatherValue(ValueError):
    """Open-Meteo gave no value for a variable this system needs, so there is no row to store."""


class CanonicalWeatherRecord(BaseModel):
    """Canonical Unified Weather Record for all solar forecasting models & database."""
    timestamp: datetime
    station_id: str
    ghi: float = Field(..., description="Global Horizontal Irradiance in W/m^2")
    dni: float = Field(..., description="Direct Normal Irradiance in W/m^2")
    dhi: float = Field(..., description="Diffuse Horizontal Irradiance in W/m^2")
    clearsky_ghi: float = Field(..., description="Calculated Clear-Sky GHI in W/m^2 (Haurwitz model)")
    clearsky_index: float = Field(..., description="Clear-Sky Index k_c = GHI / Clearsky_GHI (range 0.0-1.2)")
    solar_zenith_angle: float = Field(..., description="Solar Zenith Angle in degrees (0 = overhead, 90 = horizon)")
    is_daylight: bool = Field(..., description="True if sun is above threshold (> 10 W/m^2)")
    temperature: float = Field(..., description="Air temperature in Celsius")
    relative_humidity: float = Field(..., description="Relative humidity in percentage (0-100)")
    wind_speed: float = Field(..., description="Wind speed in m/s")
    cloud_cover: float = Field(..., description="Cloud cover percentage (0-100)")
    surface_pressure: float = Field(..., description="Surface pressure in hPa")
    source: str = Field(..., description="Source origin: 'open_meteo'")

    model_config = ConfigDict(from_attributes=True)


class WeatherDataNormalizer:
    """Maps Open-Meteo answers to the rows of weather_history."""

    @staticmethod
    def normalize_open_meteo(raw_json: dict[str, Any], station_id: str, lat: float, lon: float) -> CanonicalWeatherRecord:
        """Map the `current` block of an Open-Meteo answer. Raises MissingWeatherValue when a value is not there."""
        current = raw_json.get("current") or {}
        missing = [k for k in ("time",) + OPEN_METEO_VARIABLES if current.get(k) is None]
        if missing:
            raise MissingWeatherValue(f"Open-Meteo gave no value for: {', '.join(missing)}")

        dt = datetime.fromisoformat(current["time"]).replace(tzinfo=timezone.utc)
        ghi = float(current["shortwave_radiation"])

        # Universal astronomical solar calculations
        solar = SolarCalculator.get_solar_metrics(lat=lat, lon=lon, dt_utc=dt, measured_ghi=ghi)

        return CanonicalWeatherRecord(
            timestamp=dt,
            station_id=station_id,
            ghi=ghi,
            dni=float(current["direct_normal_irradiance"]),
            dhi=float(current["diffuse_radiation"]),
            clearsky_ghi=solar.clearsky_ghi,
            clearsky_index=solar.clearsky_index,
            solar_zenith_angle=solar.zenith_degrees,
            is_daylight=solar.is_daylight,
            temperature=float(current["temperature_2m"]),
            relative_humidity=float(current["relative_humidity_2m"]),
            wind_speed=float(current["wind_speed_10m"]),
            cloud_cover=float(current["cloud_cover"]),
            surface_pressure=float(current["surface_pressure"]),
            source="open_meteo",
        )

    @staticmethod
    def open_meteo_ten_minute_rows(minutely: dict[str, Any]):
        """Open-Meteo 15-minute values on the 10-minute grid of weather_history (DataFrame indexed by UTC time).

        A slot between two Open-Meteo times is interpolated in time between them. A slot is kept only when
        Open-Meteo gave every variable at the time before it and at the time after it, and those two are at most
        one 15-minute step apart. Nothing is carried forward or backward, so a gap in the source stays a gap.
        Raises MissingWeatherValue when a variable is not in the answer at all.
        """
        import pandas as pd

        missing = [k for k in ("time",) + OPEN_METEO_VARIABLES if k not in minutely]
        if missing:
            raise MissingWeatherValue(f"Open-Meteo gave no value for: {', '.join(missing)}")

        source = pd.DataFrame(
            {k: minutely[k] for k in OPEN_METEO_VARIABLES}, index=pd.to_datetime(minutely["time"], utc=True), dtype="float64"
        )
        source = source[~source.index.duplicated()].sort_index()
        if source.empty:
            return source

        grid = pd.date_range(source.index[0].ceil("10min"), source.index[-1].floor("10min"), freq="10min")
        every = source.index.union(grid)
        given = source.notna().all(axis=1).reindex(every, fill_value=False)
        stamp = every.to_series()
        span = stamp.where(given).bfill() - stamp.where(given).ffill()  # distance between the given times around a slot
        rows = source.reindex(every).interpolate(method="time", limit_area="inside")
        return rows[(span <= pd.Timedelta(minutes=OPEN_METEO_STEP_MINUTES)).to_numpy()].reindex(grid).dropna()
