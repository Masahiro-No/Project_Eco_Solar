"""Cloud coverage ratio in the area of interest (AOI) around a station.

Replaces cloud tracking: instead of following cloud objects between frames, the share of cloudy
pixels inside a fixed box around the station is measured, on real frames and on the frames the
ConvLSTM predicts.

Geometry: frames are Himawari Band 03 crops of 64x64 px from the level-2d tile (1100 px full disk).
At the stations one pixel is about 15 km east-west x 11 km north-south, so the 5x5 px AOI is
about 78 x 55 km and holds 25 pixels (the ratio moves in steps of 4%).

Brightness: the tile values are reflected radiance, which falls with the sun's height. Each frame is
therefore divided by cos(solar zenith) at its scan time before the cloud threshold is applied, and
frames taken with the sun lower than MIN_COS_ZENITH are not used (clear sky looks bright there).
Checked on real frames around ST-002 for 3 Oct 2026 against its pyranometer: clear periods give
0% above the threshold, the overcast late afternoon 84-88%.

Cloud cover -> irradiance uses Kasten & Czeplak (1980): GHI / GHI_clearsky = 1 - 0.75 * C^3.4,
with C the cloud fraction in [0, 1]. The impact levels are the cloud fractions at which that
relation gives a 10% and a 30% loss of GHI. The coefficients are starting values to be calibrated
against measured GHI.
"""

import os
from typing import Any, Iterable, Optional

import numpy as np

AOI_SIZE = int(os.environ.get("CLOUD_AOI_SIZE_PX", "5"))
CLOUD_REFLECTANCE_THRESHOLD = float(os.environ.get("CLOUD_REFLECTANCE_THRESHOLD", "0.25"))

MIN_COS_ZENITH = float(os.environ.get("CLOUD_MIN_COS_ZENITH", "0.30"))  # sun at least ~17 degrees above the horizon

KC_COEFF = float(os.environ.get("KC_COEFF", "0.75"))
KC_EXPONENT = float(os.environ.get("KC_EXPONENT", "3.4"))
CLEAR_SKY_SCALE = float(os.environ.get("CLEAR_SKY_SCALE", "1.0"))  # measured clear-sky GHI / Haurwitz clear-sky GHI
LOSS_MEDIUM = 0.10
LOSS_HIGH = 0.30

IMPACT_LEVELS = ("low", "medium", "high")

# Cloud cover of the satellite branch at a lead time t (minutes after the newest real frame):
# up to OBSERVED_UNTIL_MIN the cover seen in that frame, from MODEL_FROM_MIN on the ConvLSTM forecast,
# a linear cross-fade in between. Backtest on real frames (service/training/backtest_cloud.py, 4 Oct 2026):
# holding the observed cover has the lower error up to ~50 min, the ConvLSTM beyond ~70 min.
OBSERVED_UNTIL_MIN = float(os.environ.get("CLOUD_OBSERVED_UNTIL_MIN", "30"))
MODEL_FROM_MIN = float(os.environ.get("CLOUD_MODEL_FROM_MIN", "90"))


def cloud_fraction_for_loss(loss: float) -> float:
    """Cloud fraction at which Kasten-Czeplak gives the given relative loss of GHI."""
    return (loss / KC_COEFF) ** (1.0 / KC_EXPONENT)


IMPACT_MEDIUM_FROM = cloud_fraction_for_loss(LOSS_MEDIUM)  # ~0.55
IMPACT_HIGH_FROM = cloud_fraction_for_loss(LOSS_HIGH)      # ~0.76


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
    arr = _as_frames(frames)
    cy, cx = arr.shape[1] // 2, arr.shape[2] // 2
    r = aoi_size // 2
    aoi = arr[:, cy - r : cy + r + 1, cx - r : cx + r + 1]
    if cos_zenith is None:
        return [float(v) for v in (aoi >= threshold).mean(axis=(1, 2))]

    cos = np.atleast_1d(np.asarray(cos_zenith, dtype=np.float64))
    if cos.shape[0] != arr.shape[0]:
        raise ValueError(f"cos_zenith needs one value per frame ({cos.shape[0]} != {arr.shape[0]})")
    out: list[Optional[float]] = []
    for frame_aoi, c in zip(aoi, cos):
        out.append(float((frame_aoi / c >= threshold).mean()) if c >= MIN_COS_ZENITH else None)
    return out


def model_share(lead_min: float, observed_until: float = OBSERVED_UNTIL_MIN, model_from: float = MODEL_FROM_MIN) -> float:
    """Share of the ConvLSTM forecast in the satellite cloud cover at this lead time, in [0, 1]."""
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
    """Satellite cloud cover at one lead time: the observed cover first, the ConvLSTM forecast later.

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


def clear_sky_index_from_cloud(cloud_fraction: float) -> float:
    """Kasten & Czeplak (1980): k = 1 - 0.75 * C^3.4, times the clear-sky scale of the site."""
    c = min(1.0, max(0.0, float(cloud_fraction)))
    return CLEAR_SKY_SCALE * (1.0 - KC_COEFF * c**KC_EXPONENT)


def impact_level(cloud_fraction: Optional[float]) -> Optional[str]:
    if cloud_fraction is None:
        return None
    if cloud_fraction >= IMPACT_HIGH_FROM:
        return "high"
    if cloud_fraction >= IMPACT_MEDIUM_FROM:
        return "medium"
    return "low"


def max_impact_level(fractions: Iterable[Optional[float]]) -> Optional[str]:
    """Highest impact level among the given cloud fractions; None when none is available."""
    known = [f for f in fractions if f is not None]
    return impact_level(max(known)) if known else None
