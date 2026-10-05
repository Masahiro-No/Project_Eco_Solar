"""Decision support: one rule set for the whole system.

P_gen is always computed from the blended GHI (LSTM + satellite), never from the raw LSTM curve:

    P_gen(t)    = A * eta * GHI_blend(t) / 1000                      [kW]
    target(t)   = min(P_target, f * A * eta * GHI_clearsky(t) / 1000)    f = TARGET_CLEARSKY_FRACTION
    dP_max      = max over the daylight steps of (target(t) - P_gen(t))

The target follows the sun: a plant cannot deliver its full dispatch target at 8 a.m., so it is held to the
smaller of the dispatch target and a share f of what clear sky would give at that time. A shortfall is then
a loss caused by the weather, not by the hour of the day.

The alert level pairs "is the target met over the next 3 hours" with the impact level the satellite branch
expects in the next hour (loss of irradiance: low < 10%, medium 10-30%, high > 30%):

                       impact low  impact medium           impact high
    target met         normal      watch                   warning (prepare reserve)
    shortfall          warning     warning (+ buffer)      critical

No satellite information counts as an uncertain cloud state: a shortfall then gets the buffer too.
Night is its own state and never an alert. The buffer is the forecast uncertainty in kW,
A * eta * RMSE(lead) / 1000, with the model's test RMSE at that lead time.
"""

import os
from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

from service.workers.cloud_coverage import max_impact_level
from service.workers.solar_geometry import NIGHT_CLEARSKY_GHI

CLOUD_LOOKAHEAD_MIN = 60
# share of the clear-sky output a plant is expected to deliver (measured GHI at ST-002 reaches clear sky on its best quarter of slots)
TARGET_CLEARSKY_FRACTION = float(os.environ.get("TARGET_CLEARSKY_FRACTION", "0.8"))

# upper limit of the uncertainty band: GHI measured at ST-002 peaked at 1.18 x clear sky (light reflected by cloud edges)
UNCERTAINTY_MAX_CLEARSKY_RATIO = 1.2

LEVEL_TH = {"low": "ต่ำ", "medium": "กลาง", "high": "สูง"}


@dataclass
class Decision:
    alert_level: str                      # night | normal | watch | warning | critical
    recommendation_text: str
    estimated_power_kw: float             # P_gen at the first forecast step
    delta_p_kw: float                     # dP_max against the target that follows the sun, 0 when it is met
    reserve_kw: float                     # dP_max + buffer (what to hold in reserve)
    buffer_kw: float
    cloud_impact_level: Optional[str]     # low | medium | high | None (no satellite information)
    is_night: bool
    shortfall_in_min: Optional[int]       # minutes until the first step below target
    power_forecast_kw: list[float] = field(default_factory=list)
    target_profile_kw: list[float] = field(default_factory=list)   # target(t) per step


def power_kw(panel_area_m2: float, efficiency: float, ghi_w_m2: float) -> float:
    return panel_area_m2 * efficiency * max(0.0, ghi_w_m2) / 1000.0


def rmse_at_lead(step_metrics: Optional[Mapping[str, float]], lead_min: float) -> Optional[float]:
    """Test RMSE (W/m2) at a lead time, linearly interpolated between the leads stored in model_meta.json."""
    if not step_metrics:
        return None
    points = []
    for key, value in step_metrics.items():
        if key.startswith("test_rmse_plus_") and key.endswith("min"):
            try:
                points.append((float(key[len("test_rmse_plus_") : -len("min")]), float(value)))
            except ValueError:
                continue
    if not points:
        return None
    points.sort()
    if lead_min <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if lead_min <= x1:
            return y0 + (y1 - y0) * (lead_min - x0) / (x1 - x0)
    return points[-1][1]


def daylight_rmse_metrics(meta: Mapping) -> Optional[dict[str, float]]:
    """RMSE per lead time on the daylight part of the model's test set, with the keys rmse_at_lead reads.

    Models stored before the daylight metrics existed only have the all-hours values, which are used then.
    """
    day = {
        key.replace("test_day_rmse_", "test_rmse_"): float(value)
        for key, value in (meta.get("daylight_metrics") or {}).items()
        if key.startswith("test_day_rmse_plus_")
    }
    return day or (dict(meta.get("step_metrics") or {}) or None)


def uncertainty_band(
    ghi: Sequence[float],
    clearsky: Sequence[float],
    metrics: Optional[Mapping[str, float]],
    step_minutes: int = 10,
) -> Optional[tuple[list[float], list[float]]]:
    """Typical error range of the forecast: GHI(t) -/+ RMSE(lead time), kept inside [0, 1.2 x clear sky].

    RMSE is the model's test error at that lead time, so about two thirds of the test cases fall inside.
    A point sensor under broken cloud swings more than that. None when the model has no error metrics.
    """
    lower, upper = [], []
    for i, (g, cs) in enumerate(zip(ghi, clearsky)):
        if cs < NIGHT_CLEARSKY_GHI:
            lower.append(0.0)
            upper.append(0.0)
            continue
        rmse = rmse_at_lead(metrics, (i + 1) * step_minutes)
        if rmse is None:
            return None
        lower.append(round(max(0.0, g - rmse), 2))
        upper.append(round(max(g, min(g + rmse, UNCERTAINTY_MAX_CLEARSKY_RATIO * cs)), 2))
    return lower, upper


def evaluate(
    ghi_blend: Sequence[float],
    clearsky: Sequence[float],
    panel_area_m2: float,
    efficiency: float,
    target_power_kw: float,
    sat_loss: Sequence[Optional[float]],
    sat_loss_now: Optional[float] = None,
    step_metrics: Optional[Mapping[str, float]] = None,
    step_minutes: int = 10,
    clearsky_fraction: float = TARGET_CLEARSKY_FRACTION,
) -> Decision:
    """sat_loss: expected loss of irradiance (1 - k) of the satellite branch per step, None where it has no value."""
    power = [round(power_kw(panel_area_m2, efficiency, g), 2) for g in ghi_blend]
    daylight = [i for i, cs in enumerate(clearsky) if cs >= NIGHT_CLEARSKY_GHI]
    target = [
        round(min(target_power_kw, clearsky_fraction * power_kw(panel_area_m2, efficiency, cs)), 2) if cs >= NIGHT_CLEARSKY_GHI else 0.0
        for cs in clearsky
    ]

    if not daylight:
        return Decision(
            alert_level="night",
            recommendation_text="กลางคืน ไม่มีการผลิตไฟฟ้าจากแสงอาทิตย์ในช่วง 3 ชั่วโมงข้างหน้า",
            estimated_power_kw=0.0,
            delta_p_kw=0.0,
            reserve_kw=0.0,
            buffer_kw=0.0,
            cloud_impact_level=None,
            is_night=True,
            shortfall_in_min=None,
            power_forecast_kw=power,
            target_profile_kw=target,
        )

    lookahead_steps = CLOUD_LOOKAHEAD_MIN // step_minutes
    near = [sat_loss_now] + list(sat_loss[:lookahead_steps])
    level = max_impact_level(near)
    known = [x for x in near if x is not None]
    loss_pct = round(max(known) * 100) if known else None

    gaps = {i: target[i] - power[i] for i in daylight}
    worst = max(gaps, key=gaps.get)
    delta_p = max(0.0, gaps[worst])
    shortfall = delta_p > 0.0
    first_short = next((i for i in daylight if gaps[i] > 0.0), None)
    shortfall_in_min = (first_short + 1) * step_minutes if first_short is not None else None

    # forecast uncertainty at the lead time that matters: the worst step, or the cloud look-ahead when the target is met
    buffer_lead = (worst + 1) * step_minutes if shortfall else CLOUD_LOOKAHEAD_MIN
    rmse = rmse_at_lead(step_metrics, buffer_lead)
    buffer_kw = power_kw(panel_area_m2, efficiency, rmse) if rmse is not None else 0.0

    cloud_txt = f"ภาพดาวเทียมชี้ว่าเมฆกระทบระดับ{LEVEL_TH[level]} (แสงลดสูงสุด {loss_pct}% ใน 1 ชั่วโมงข้างหน้า)" if level else "ไม่มีข้อมูลภาพดาวเทียม ใช้ผล LSTM อย่างเดียว"

    if not shortfall:
        if level == "high":
            alert, reserve = "warning", buffer_kw
            text = f"กำลังผลิตถึงเป้า แต่{cloud_txt} เตรียมกำลังสำรอง {reserve:,.0f} kW ไว้ล่วงหน้า"
        elif level == "medium":
            alert, reserve = "watch", 0.0
            text = f"กำลังผลิตถึงเป้า {cloud_txt} ให้เฝ้าระวัง"
        else:
            alert, reserve = "normal", 0.0
            text = f"กำลังผลิตถึงเป้าตลอด 3 ชั่วโมงข้างหน้า {cloud_txt} จ่ายไฟตามปกติ"
    else:
        when = f"ในอีก {shortfall_in_min} นาที" if shortfall_in_min and shortfall_in_min > step_minutes else "ตั้งแต่ช่วงถัดไป"
        base = f"กำลังผลิตจะต่ำกว่าเป้า{when} ขาดสูงสุด {delta_p:,.0f} kW"
        if level == "low":
            alert, reserve = "warning", delta_p
            text = f"{base} {cloud_txt} สำรองตามส่วนต่าง {reserve:,.0f} kW"
        elif level == "high":
            alert, reserve = "critical", delta_p + buffer_kw
            text = f"{base} และ{cloud_txt} จ่ายกำลังสำรอง {reserve:,.0f} kW ทันที"
        else:  # medium, or no satellite information
            alert, reserve = "warning", delta_p + buffer_kw
            text = f"{base} {cloud_txt} สำรอง {reserve:,.0f} kW (ส่วนต่างบวกค่ากันสำรอง {buffer_kw:,.0f} kW)"

    return Decision(
        alert_level=alert,
        recommendation_text=text,
        estimated_power_kw=power[0],
        delta_p_kw=round(delta_p, 2),
        reserve_kw=round(reserve, 2),
        buffer_kw=round(buffer_kw, 2),
        cloud_impact_level=level,
        is_night=False,
        shortfall_in_min=shortfall_in_min,
        power_forecast_kw=power,
        target_profile_kw=target,
    )
