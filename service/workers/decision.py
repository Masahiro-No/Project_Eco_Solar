"""Decision support: one rule set for the whole system.

P_gen is always computed from the blended GHI (LSTM + satellite), never from the raw LSTM curve:

    P_gen(t) = A * eta * GHI_blend(t) / 1000   [kW]
    dP_max   = max over the daylight steps of (P_target - P_gen(t))

The alert level pairs "is the target met over the next 3 hours" with the cloud impact level in the
next hour:

                       cloud low   cloud medium            cloud high
    target met         normal      watch                   warning (prepare reserve)
    shortfall          warning     warning (+ buffer)      critical

No satellite information counts as an uncertain cloud state: a shortfall then gets the buffer too.
Night is its own state and never an alert. The buffer is the forecast uncertainty in kW,
A * eta * RMSE(lead) / 1000, with the model's test RMSE at that lead time.
"""

from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

from service.workers.cloud_coverage import max_impact_level
from service.workers.solar_geometry import NIGHT_CLEARSKY_GHI

CLOUD_LOOKAHEAD_MIN = 60

LEVEL_TH = {"low": "ต่ำ", "medium": "กลาง", "high": "สูง"}


@dataclass
class Decision:
    alert_level: str                      # night | normal | watch | warning | critical
    recommendation_text: str
    estimated_power_kw: float             # P_gen at the first forecast step
    delta_p_kw: float                     # dP_max, 0 when the target is met
    reserve_kw: float                     # dP_max + buffer (what to hold in reserve)
    buffer_kw: float
    cloud_impact_level: Optional[str]     # low | medium | high | None (no satellite information)
    is_night: bool
    shortfall_in_min: Optional[int]       # minutes until the first step below target
    power_forecast_kw: list[float] = field(default_factory=list)


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


def evaluate(
    ghi_blend: Sequence[float],
    clearsky: Sequence[float],
    panel_area_m2: float,
    efficiency: float,
    target_power_kw: float,
    cloud_fraction: Sequence[Optional[float]],
    cloud_fraction_now: Optional[float] = None,
    step_metrics: Optional[Mapping[str, float]] = None,
    step_minutes: int = 10,
) -> Decision:
    power = [round(power_kw(panel_area_m2, efficiency, g), 2) for g in ghi_blend]
    daylight = [i for i, cs in enumerate(clearsky) if cs >= NIGHT_CLEARSKY_GHI]

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
        )

    lookahead_steps = CLOUD_LOOKAHEAD_MIN // step_minutes
    level = max_impact_level([cloud_fraction_now] + list(cloud_fraction[:lookahead_steps]))
    known = [c for c in [cloud_fraction_now] + list(cloud_fraction[:lookahead_steps]) if c is not None]
    cloud_pct = round(max(known) * 100) if known else None

    gaps = {i: target_power_kw - power[i] for i in daylight}
    worst = max(gaps, key=gaps.get)
    delta_p = max(0.0, gaps[worst])
    shortfall = delta_p > 0.0
    first_short = next((i for i in daylight if gaps[i] > 0.0), None)
    shortfall_in_min = (first_short + 1) * step_minutes if first_short is not None else None

    # forecast uncertainty at the lead time that matters: the worst step, or the cloud look-ahead when the target is met
    buffer_lead = (worst + 1) * step_minutes if shortfall else CLOUD_LOOKAHEAD_MIN
    rmse = rmse_at_lead(step_metrics, buffer_lead)
    buffer_kw = power_kw(panel_area_m2, efficiency, rmse) if rmse is not None else 0.0

    cloud_txt = f"เมฆในกรอบสถานีกระทบระดับ{LEVEL_TH[level]} (สูงสุด {cloud_pct}% ใน 1 ชั่วโมงข้างหน้า)" if level else "ไม่มีข้อมูลภาพดาวเทียม ใช้ผล LSTM อย่างเดียว"

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
    )
