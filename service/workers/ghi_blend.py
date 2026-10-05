"""Blend the LSTM irradiance forecast with the satellite branch.

For each forecast step, with t the minutes after the newest real satellite frame:

    k_L(t) = GHI_lstm(t) / GHI_cs(t)             clear-sky index implied by the LSTM
    k_S(t) = intercept - slope * rho(t)          clear-sky index from the AOI brightness (cloud_coverage.py)
    w(t)   = w0 * exp(-t / tau)                  trust in the satellite branch, decaying with lead time
    GHI(t) = GHI_cs(t) * [ w(t) * k_S(t) + (1 - w(t)) * k_L(t) ]
           = w(t) * k_S(t) * GHI_cs(t) + (1 - w(t)) * GHI_lstm(t)

The satellite sees the real cloud field now, so it leads at short lead times; the LSTM carries the
daily trend and leads later. Checked against GHI measured at ST-002 on 5 Oct 2026 (94 forecast steps):
MAE of the satellite branch 88 vs 122 W/m2 for the LSTM at 10-30 min, 173 vs 113 at 70-120 min, and the
blend with w0 = 0.9, tau = 102 min (w = 0.5 at 60 min) 109 vs 118 overall. Other values of tau between
60 and 102 min gave the same error within 1 W/m2.
"""

import math
import os
from typing import Optional, Sequence

from service.workers.solar_geometry import NIGHT_CLEARSKY_GHI

BLEND_W0 = float(os.environ.get("BLEND_W0", "0.9"))
BLEND_TAU_MIN = float(os.environ.get("BLEND_TAU_MIN", "102"))


def satellite_weight(lead_min: float, w0: float = BLEND_W0, tau_min: float = BLEND_TAU_MIN) -> float:
    return max(0.0, min(1.0, w0 * math.exp(-max(0.0, lead_min) / tau_min)))


def blend_ghi(
    ghi_lstm: Sequence[float],
    clearsky: Sequence[float],
    sat_clear_sky_index: Sequence[Optional[float]],
    sat_lead_min: Sequence[Optional[float]],
    w0: float = BLEND_W0,
    tau_min: float = BLEND_TAU_MIN,
    weight_scale: Optional[Sequence[float]] = None,
) -> tuple[list[float], list[float]]:
    """Return (blended GHI, satellite weight) per step.

    sat_clear_sky_index[i] / sat_lead_min[i] are None where the satellite branch has no value for step i:
    the weight is then 0 and the step equals the LSTM value. Night steps are 0.
    weight_scale[i] in [0, 1] lowers the weight of a step (used to fade out a held observation).
    """
    if not (len(ghi_lstm) == len(clearsky) == len(sat_clear_sky_index) == len(sat_lead_min)):
        raise ValueError("all inputs must have one value per forecast step")

    blended: list[float] = []
    weights: list[float] = []
    scale = list(weight_scale) if weight_scale is not None else [1.0] * len(ghi_lstm)
    for g_lstm, g_cs, k_sat, lead, sc in zip(ghi_lstm, clearsky, sat_clear_sky_index, sat_lead_min, scale):
        if g_cs < NIGHT_CLEARSKY_GHI:
            blended.append(0.0)
            weights.append(0.0)
            continue
        w = satellite_weight(lead, w0, tau_min) * min(1.0, max(0.0, sc)) if (k_sat is not None and lead is not None) else 0.0
        g_sat = k_sat * g_cs if k_sat is not None else 0.0
        blended.append(max(0.0, w * g_sat + (1.0 - w) * max(0.0, float(g_lstm))))
        weights.append(w)
    return blended, weights
