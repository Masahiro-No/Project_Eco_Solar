"""Blend the LSTM irradiance forecast with the satellite cloud forecast.

For each forecast step t (minutes ahead of the newest satellite frame):

    k_L(t) = GHI_lstm(t) / GHI_cs(t)             clear-sky index implied by the LSTM
    k_S(t) = 1 - 0.75 * C(t)^3.4                 clear-sky index from the cloud fraction (Kasten-Czeplak)
    w(t)   = w0 * exp(-t / tau)                  trust in the satellite branch, decaying with lead time
    GHI(t) = GHI_cs(t) * [ w(t) * k_S(t) + (1 - w(t)) * k_L(t) ]
           = w(t) * k_S(t) * GHI_cs(t) + (1 - w(t)) * GHI_lstm(t)

The satellite sees the real cloud field now, so it leads at short lead times; the LSTM carries the
daily trend and leads later. w0 and tau are starting values (w = 0.5 at 60 min) to be calibrated
from the ConvLSTM skill per lead time.
"""

import math
import os
from typing import Optional, Sequence

from service.workers.cloud_coverage import clear_sky_index_from_cloud
from service.workers.solar_geometry import NIGHT_CLEARSKY_GHI

BLEND_W0 = float(os.environ.get("BLEND_W0", "0.9"))
BLEND_TAU_MIN = float(os.environ.get("BLEND_TAU_MIN", "102"))


def satellite_weight(lead_min: float, w0: float = BLEND_W0, tau_min: float = BLEND_TAU_MIN) -> float:
    return max(0.0, min(1.0, w0 * math.exp(-max(0.0, lead_min) / tau_min)))


def blend_ghi(
    ghi_lstm: Sequence[float],
    clearsky: Sequence[float],
    cloud_fraction: Sequence[Optional[float]],
    sat_lead_min: Sequence[Optional[float]],
    w0: float = BLEND_W0,
    tau_min: float = BLEND_TAU_MIN,
) -> tuple[list[float], list[float]]:
    """Return (blended GHI, satellite weight) per step.

    cloud_fraction[i] / sat_lead_min[i] are None where no satellite forecast covers step i:
    the weight is then 0 and the step equals the LSTM value. Night steps are 0.
    """
    if not (len(ghi_lstm) == len(clearsky) == len(cloud_fraction) == len(sat_lead_min)):
        raise ValueError("all inputs must have one value per forecast step")

    blended: list[float] = []
    weights: list[float] = []
    for g_lstm, g_cs, c, lead in zip(ghi_lstm, clearsky, cloud_fraction, sat_lead_min):
        if g_cs < NIGHT_CLEARSKY_GHI:
            blended.append(0.0)
            weights.append(0.0)
            continue
        w = 0.0
        if c is not None and lead is not None:
            w = satellite_weight(lead, w0, tau_min)
        g_sat = clear_sky_index_from_cloud(c) * g_cs if c is not None else 0.0
        blended.append(max(0.0, w * g_sat + (1.0 - w) * max(0.0, float(g_lstm))))
        weights.append(w)
    return blended, weights
