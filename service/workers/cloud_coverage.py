"""Satellite cloud information in the area of interest (AOI) around a station.

Two quantities are taken from a Himawari Band 03 crop (64x64 px of the level-2d tile, 1100 px full disk):

1. Cloud coverage ratio C: cloudy pixels / all pixels in the AOI. This replaces cloud tracking and is
   what the operator sees.
2. Mean sun-normalised brightness rho of the AOI, which gives the clear-sky index of the satellite branch

       k = intercept - slope * rho          (k = GHI / clear-sky GHI)

   The two coefficients are fitted on GHI measured at a station (service/training/calibrate_satellite_ghi.py)
   and live in model/satellite/ghi_calibration.json. The expected loss of irradiance 1 - k sets the impact
   level: low < 10%, medium 10-30%, high > 30%.

Geometry: at the stations one pixel is about 15 km east-west x 11 km north-south, so the 5x5 px AOI is
about 78 x 55 km and holds 25 pixels (the ratio moves in steps of 4%).

Brightness: the tile values are reflected radiance, which falls with the sun's height. Each frame is
therefore divided by cos(solar zenith) at its scan time, and frames taken with the sun lower than
MIN_COS_ZENITH are not used (clear sky looks bright there).

Why not Kasten & Czeplak: the first version converted C to irradiance with k = 1 - 0.75 * C^3.4. Against the
GHI measured at ST-002 (1-5 Oct 2026) that relation gave k of about 0.98 almost always while the measured
mean was 0.64 (MAE 0.37); the fitted brightness relation has an MAE of 0.20 on days it was not fitted on,
and it made the blended forecast better than the LSTM alone at lead times up to an hour.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np

AOI_SIZE = int(os.environ.get("CLOUD_AOI_SIZE_PX", "5"))
CLOUD_REFLECTANCE_THRESHOLD = float(os.environ.get("CLOUD_REFLECTANCE_THRESHOLD", "0.25"))

MIN_COS_ZENITH = float(os.environ.get("CLOUD_MIN_COS_ZENITH", "0.30"))  # sun at least ~17 degrees above the horizon

# Expected loss of GHI (1 - k) at which the impact level changes
LOSS_MEDIUM = 0.10
LOSS_HIGH = 0.30
IMPACT_LEVELS = ("low", "medium", "high")

# Satellite value at a lead time t (minutes after the newest real frame): up to OBSERVED_UNTIL_MIN what that
# frame shows, from MODEL_FROM_MIN on the ConvLSTM forecast, a linear cross-fade in between. Backtest on real
# frames (service/training/backtest_cloud.py, 4 Oct 2026): holding the observed value has the lower error up to
# ~50 min, the ConvLSTM beyond ~70 min.
OBSERVED_UNTIL_MIN = float(os.environ.get("CLOUD_OBSERVED_UNTIL_MIN", "30"))
MODEL_FROM_MIN = float(os.environ.get("CLOUD_MODEL_FROM_MIN", "90"))
# Without a complete 12-frame window (every day after the 02:40 UTC scan gap) there is no ConvLSTM forecast:
# the value of the newest real frame is then held, at most this long after that frame.
OBSERVED_HOLD_MAX_MIN = float(os.environ.get("CLOUD_OBSERVED_HOLD_MAX_MIN", "60"))

CALIBRATION_FILE = Path(
    os.environ.get("SAT_CALIBRATION_FILE")
    or Path(__file__).resolve().parent.parent.parent / "model" / "satellite" / "ghi_calibration.json"
)


@dataclass(frozen=True)
class SatelliteCalibration:
    """Clear-sky index from the AOI brightness: k = intercept - slope * rho, kept inside [k_min, k_max]."""

    intercept: float
    slope: float
    k_min: float = 0.05
    k_max: float = 1.15

    def clear_sky_index(self, rho: float) -> float:
        return min(self.k_max, max(self.k_min, self.intercept - self.slope * float(rho)))


def load_calibration(path: Optional[Path] = None) -> Optional[SatelliteCalibration]:
    """The fitted coefficients, or None when there is no calibration file.

    Without a calibration the satellite branch gets no weight: there are no built-in numbers to fall back on.
    """
    try:
        data = json.loads(Path(path or CALIBRATION_FILE).read_text(encoding="utf-8"))
        return SatelliteCalibration(
            intercept=float(data["intercept"]),
            slope=float(data["slope"]),
            k_min=float(data.get("k_min", 0.05)),
            k_max=float(data.get("k_max", 1.15)),
        )
    except (OSError, KeyError, TypeError, ValueError):
        return None


def _as_frames(frames: Any) -> np.ndarray:
    """Accept (H, W), (T, H, W), (T, 1, H, W) or (1, T, 1, H, W) and return (T, H, W)."""
    arr = np.asarray(frames, dtype=np.float32)
    if arr.ndim == 5:
        arr = arr[0, :, 0, :, :]
    elif arr.ndim == 4:
        arr = arr[:, 0, :, :]
    elif arr.ndim == 2:
        arr = arr[np.newaxis, :, :]
    if arr.ndim != 3:
        raise ValueError(f"unsupported frame shape {np.asarray(frames).shape}")
    return arr


def _aoi(frames: Any, aoi_size: int) -> np.ndarray:
    arr = _as_frames(frames)
    cy, cx = arr.shape[1] // 2, arr.shape[2] // 2
    r = aoi_size // 2
    return arr[:, cy - r : cy + r + 1, cx - r : cx + r + 1]


def _cos_per_frame(cos_zenith: Any, n_frames: int) -> np.ndarray:
    cos = np.atleast_1d(np.asarray(cos_zenith, dtype=np.float64))
    if cos.shape[0] != n_frames:
        raise ValueError(f"cos_zenith needs one value per frame ({cos.shape[0]} != {n_frames})")
    return cos


def aoi_cloud_fraction(
    frames: Any,
    cos_zenith: Any = None,
    aoi_size: int = AOI_SIZE,
    threshold: float = CLOUD_REFLECTANCE_THRESHOLD,
) -> list[Optional[float]]:
    """Cloud fraction per frame: cloudy pixels / all pixels in the centre AOI.

    cos_zenith: cos(solar zenith) at each frame's scan time (one value per frame). The brightness is
    divided by it before thresholding; a frame with the sun below MIN_COS_ZENITH gives None.
    Without cos_zenith the raw brightness is thresholded (only meaningful for tests).
    """
    aoi = _aoi(frames, aoi_size)
    if cos_zenith is None:
        return [float(v) for v in (aoi >= threshold).mean(axis=(1, 2))]
    cos = _cos_per_frame(cos_zenith, aoi.shape[0])
    return [float((a / c >= threshold).mean()) if c >= MIN_COS_ZENITH else None for a, c in zip(aoi, cos)]


def aoi_brightness(frames: Any, cos_zenith: Any, aoi_size: int = AOI_SIZE) -> list[Optional[float]]:
    """Mean sun-normalised brightness rho of the AOI per frame; None when the sun is below MIN_COS_ZENITH."""
    aoi = _aoi(frames, aoi_size)
    cos = _cos_per_frame(cos_zenith, aoi.shape[0])
    return [float(a.mean() / c) if c >= MIN_COS_ZENITH else None for a, c in zip(aoi, cos)]


def model_share(lead_min: float, observed_until: float = OBSERVED_UNTIL_MIN, model_from: float = MODEL_FROM_MIN) -> float:
    """Share of the ConvLSTM forecast in the satellite value at this lead time, in [0, 1]."""
    if model_from <= observed_until:
        return 1.0 if lead_min > observed_until else 0.0
    return min(1.0, max(0.0, (lead_min - observed_until) / (model_from - observed_until)))


def observed_then_forecast(
    observed: Optional[float],
    forecast: Optional[float],
    lead_min: float,
    observed_until: float = OBSERVED_UNTIL_MIN,
    model_from: float = MODEL_FROM_MIN,
) -> Optional[float]:
    """Satellite value at one lead time: what the newest real frame shows first, the ConvLSTM forecast later.

    None when the part that is needed at this lead time is not available (no value is substituted).
    """
    share = model_share(lead_min, observed_until, model_from)
    if share >= 1.0:
        return forecast
    if share <= 0.0:
        return observed
    if observed is None or forecast is None:
        return None
    return (1.0 - share) * observed + share * forecast


def held_observation_weight(lead_min: float, step_min: float = 10.0) -> float:
    """Weight factor of an observation that is held without a ConvLSTM forecast.

    1 up to OBSERVED_UNTIL_MIN, then falling linearly to 0 one step after OBSERVED_HOLD_MAX_MIN, so the
    blended curve returns to the LSTM gradually instead of in one jump.
    """
    end = OBSERVED_HOLD_MAX_MIN + step_min
    if end <= OBSERVED_UNTIL_MIN:
        return 1.0 if lead_min <= OBSERVED_UNTIL_MIN else 0.0
    return min(1.0, max(0.0, (end - lead_min) / (end - OBSERVED_UNTIL_MIN)))


def ghi_loss(clear_sky_index: float) -> float:
    """Expected relative loss of irradiance against clear sky, in [0, 1]."""
    return min(1.0, max(0.0, 1.0 - float(clear_sky_index)))


def impact_level(loss: Optional[float]) -> Optional[str]:
    """low | medium | high from the expected loss of GHI; None without satellite information."""
    if loss is None:
        return None
    if loss > LOSS_HIGH:
        return "high"
    if loss >= LOSS_MEDIUM:
        return "medium"
    return "low"


def max_impact_level(losses: Iterable[Optional[float]]) -> Optional[str]:
    """Highest impact level among the given losses; None when none is available."""
    known = [x for x in losses if x is not None]
    return impact_level(max(known)) if known else None
