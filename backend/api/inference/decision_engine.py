from enum import StrEnum
from typing import NamedTuple


class CloudTrend(StrEnum):
    CLEAR = "Clear"
    INWARD = "Inward"
    OUTWARD = "Outward"
    OVERCAST = "Overcast"


class AlertLevel(StrEnum):
    NORMAL = "Normal"
    EARLY_WARNING = "Early Warning"
    CRITICAL_ALERT = "Critical Alert"
    RECOVERY = "Recovery"
    STEADY_LOW = "Steady Low"


class DecisionResult(NamedTuple):
    estimated_power_kw: float
    target_power_kw: float
    raw_delta_p_kw: float
    recommended_delta_p_kw: float
    alert_level: AlertLevel
    recommendation_text: str


def calculate_solar_power(panel_area_m2: float, efficiency: float, ghi_w_m2: float) -> float:
    """Calculate generated power in kW from GHI: P_gen = (A * eta * GHI) / 1000."""
    power_watts = panel_area_m2 * efficiency * max(0.0, ghi_w_m2)
    return round(power_watts / 1000.0, 2)


def evaluate_decision_support(
    panel_area_m2: float,
    efficiency: float,
    current_ghi_w_m2: float,
    target_power_kw: float,
    cloud_trend: str | CloudTrend,
) -> DecisionResult:
    """Evaluate dual-model rule-based decision support matrix.
    
    Pairs quantitative solar power (P_gen) with qualitative cloud motion (ConvLSTM)
    to output reserve power advice (Delta P) and alert severity.
    """
    if isinstance(cloud_trend, str):
        try:
            cloud_trend = CloudTrend(cloud_trend)
        except ValueError:
            cloud_trend = CloudTrend.CLEAR

    p_gen = calculate_solar_power(panel_area_m2, efficiency, current_ghi_w_m2)
    raw_delta_p = round(target_power_kw - p_gen, 2)

    is_sufficient = p_gen >= target_power_kw

    if is_sufficient:
        if cloud_trend == CloudTrend.INWARD:
            alert_level = AlertLevel.EARLY_WARNING
            recommendation = (
                "กำลังผลิตยังได้ตามเป้า แต่ตรวจพบความเสี่ยงเมฆกำลังเข้าบดบัง "
                "แจ้งเตือนเฝ้าระวัง (Early Warning) ให้เตรียมระบบสำรองไฟล่วงหน้า"
            )
            # Standby extra buffer
            recommended_delta_p = round(max(0.0, raw_delta_p) + (0.15 * target_power_kw), 2)
        else:
            alert_level = AlertLevel.NORMAL
            recommendation = (
                "กำลังผลิตเพียงพอตามเป้าหมาย ดำเนินการจ่ายไฟตามปกติ "
                "สำรองไฟตามค่า ΔP พื้นฐาน"
            )
            recommended_delta_p = round(max(0.0, raw_delta_p), 2)
    else:
        # P_gen < P_target
        if cloud_trend == CloudTrend.INWARD:
            alert_level = AlertLevel.CRITICAL_ALERT
            recommendation = (
                "กำลังผลิตไม่พอและมีเมฆเข้ามาซ้ำ แจ้งเตือนวิกฤต (Critical Alert) "
                "แนะนำเร่งจ่ายกำลังไฟฟ้าสำรองฉุกเฉินทันที"
            )
            recommended_delta_p = round(max(0.0, raw_delta_p) + (0.25 * target_power_kw), 2)
        elif cloud_trend == CloudTrend.OUTWARD:
            alert_level = AlertLevel.RECOVERY
            recommendation = (
                "กำลังผลิตต่ำชั่วคราวแต่กลุ่มเมฆกำลังเคลื่อนตัวพ้นสถานี "
                "แจ้งเตือนสภาวะฟื้นตัว (Recovery) แนะนำชะลอการสั่งจ่ายไฟสำรองเพิ่มเติม"
            )
            recommended_delta_p = round(max(0.0, raw_delta_p), 2)
        else:
            alert_level = AlertLevel.STEADY_LOW
            recommendation = (
                "กำลังผลิตต่ำกว่าเป้าหมายจากสภาพเมฆคงที่ "
                "วางแผนจ่ายไฟสำรองตามส่วนต่าง ΔP ต่อเนื่อง"
            )
            recommended_delta_p = round(max(0.0, raw_delta_p), 2)

    return DecisionResult(
        estimated_power_kw=p_gen,
        target_power_kw=target_power_kw,
        raw_delta_p_kw=raw_delta_p,
        recommended_delta_p_kw=recommended_delta_p,
        alert_level=alert_level,
        recommendation_text=recommendation,
    )
