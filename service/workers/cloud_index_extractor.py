"""Cloud Index Extractor & Meteorological Motion Classifier.

Processes future 18-frame satellite sequences (64x64) produced by ConvLSTM:
1. Extracts Center ROI Cloud Indices (CI) over the solar farm / pyranometer sensor.
2. Modulates 18-step Time-Series LSTM solar irradiance (GHI) curve:
   GHI_final(t) = GHI_lstm(t) * (1.0 - CI_t)
3. Analyzes cloud movement speed (km/h) and direction using Farneback Optical Flow or Centroid Shift.
4. Classifies meteorological state (Clear, Inward, Outward, Overcast) and provides BESS dispatch directives.
"""

import math
from typing import Any, Optional

import numpy as np


def extract_center_roi_cloud_indices(frames: np.ndarray, roi_size: int = 5) -> np.ndarray:
    """Extract mean pixel intensity in center ROI for each frame (18 steps).

    Args:
        frames: shape (18, 64, 64) or (1, 18, 1, 64, 64) with pixel values in [0.0, 1.0].
        roi_size: Square dimension of the target station sensor at domain center (default 5x5).

    Returns:
        np.ndarray of shape (18,) representing Cloud Index (CI) in [0.0, 1.0].
    """
    if frames.ndim == 5:
        # (1, 18, 1, 64, 64) -> (18, 64, 64)
        frames = frames[0, :, 0, :, :]
    elif frames.ndim == 4:
        # (18, 1, 64, 64) -> (18, 64, 64)
        frames = frames[:, 0, :, :]

    cy, cx = frames.shape[1] // 2, frames.shape[2] // 2
    r = roi_size // 2
    roi = frames[:, cy - r : cy + r + 1, cx - r : cx + r + 1]
    ci = np.mean(roi, axis=(1, 2))
    return np.clip(ci, 0.0, 1.0)


def modulate_lstm_ghi(ghi_lstm: Any, ci_array: Any) -> np.ndarray:
    """Apply physical cloud shading attenuation formula.

    Formula:
        GHI_final(t) = GHI_lstm(t) * (1.0 - CI_t)

    Args:
        ghi_lstm: 18-step unmodulated GHI forecast from LSTM (W/m2).
        ci_array: 18-step Cloud Index values in [0.0, 1.0].

    Returns:
        np.ndarray of shape (18,) modulated solar irradiance (W/m2).
    """
    ghi = np.array(ghi_lstm, dtype=np.float32)
    ci = np.array(ci_array, dtype=np.float32)
    modulated = ghi * (1.0 - ci)
    return np.maximum(0.0, modulated)


def extract_optical_flow_dynamics(frames: np.ndarray) -> dict[str, Any]:
    """Calculate cloud tracking motion dynamics (speed in km/h and angle in degrees).

    Uses OpenCV Farneback Dense Optical Flow when available, with an automatic
    pure-NumPy centroid tracking fallback.
    """
    if frames.ndim == 5:
        frames = frames[0, :, 0, :, :]
    elif frames.ndim == 4:
        frames = frames[:, 0, :, :]

    speed_px = 0.5
    angle_deg = 45.0

    try:
        import cv2

        f0 = (frames[0] * 255.0).astype(np.uint8)
        f_mid = (frames[len(frames) // 2] * 255.0).astype(np.uint8)
        flow = cv2.calcOpticalFlowFarneback(f0, f_mid, None, 0.5, 3, 15, 3, 5, 1.2, 0)
        mag, ang = cv2.cartToPolar(flow[..., 0], flow[..., 1], angleInDegrees=True)
        speed_px = float(np.mean(mag))
        angle_deg = float(np.mean(ang))
    except Exception:
        # Pure NumPy cloud centroid tracking
        shifts = []
        for t in range(len(frames) - 1):
            mask_t = frames[t] > 0.25
            mask_next = frames[t + 1] > 0.25
            if np.sum(mask_t) > 15 and np.sum(mask_next) > 15:
                y_t, x_t = np.where(mask_t)
                y_next, x_next = np.where(mask_next)
                dy = float(np.mean(y_next) - np.mean(y_t))
                dx = float(np.mean(x_next) - np.mean(x_t))
                shifts.append((dx, dy))

        if shifts:
            avg_dx = float(np.mean([s[0] for s in shifts]))
            avg_dy = float(np.mean([s[1] for s in shifts]))
            speed_px = math.hypot(avg_dx, avg_dy)
            angle_deg = math.degrees(math.atan2(-avg_dy, avg_dx)) % 360.0

    # Level-2d 550 tile resolution: ~2.5 km per pixel at Thailand latitude
    # 10-minute forecast cadence -> 1 px / 10 min = 2.5 km / (1/6 h) = 15.0 km/h
    speed_kmh = float(speed_px * 15.0)

    return {
        "speed_kmh": round(speed_kmh, 1),
        "angle_deg": round(angle_deg, 1),
        "speed_pixels_per_step": round(float(speed_px), 2),
    }


def classify_bess_motion_state(ci_array: Any, flow_stats: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Classify meteorological state into Clear, Inward, Outward, Overcast and provide BESS command.

    Classification matrix conforms to cloud_seq2seq_metadata.json:
      - Clear: CI_mean < 0.20
      - Overcast: CI_mean > 0.70
      - Inward: CI_delta > +0.15 or advancing cloud front
      - Outward: CI_delta < -0.10 or retreating cloud front
    """
    ci = np.array(ci_array, dtype=np.float32)
    ci_mean = float(np.mean(ci))
    ci_delta = float(ci[-1] - ci[0])
    half = len(ci) // 2
    ci_first_half = float(np.mean(ci[:half]))
    ci_second_half = float(np.mean(ci[half:]))

    if ci_mean < 0.20:
        state = "Clear"
        state_th = "ท้องฟ้าโปร่ง"
        desc = "ฟ้าโปร่ง ไร้เมฆบดบัง แดดดีต่อเนื่อง"
        action = "คงการชาร์จแบตเตอรี่ปกติ ไม่จำเป็นต้องสำรองไฟฉุกเฉิน"
    elif ci_mean > 0.70:
        state = "Overcast"
        state_th = "เมฆแช่นิ่ง"
        desc = "เมฆหนาทึบปกคลุมแช่นิ่งต่อเนื่อง ฟ้าปิดสนิท"
        action = "เตรียมจ่ายไฟจาก BESS เสริมความเสถียร แดดตกต่ำต่อเนื่องยาวนาน 3 ชม."
    elif ci_delta > 0.15 or (ci_second_half - ci_first_half > 0.12):
        state = "Inward"
        state_th = "เคลื่อนที่เข้า"
        desc = "กลุ่มเมฆพุ่งเข้าหาฟาร์ม แดดจะตกเฉียบพลัน"
        action = "แจ้งเตือนแดดดรอปเฉียบพลัน! สั่งเตรียมปล่อยกำลังไฟ BESS Ramp-up รองรับ"
    elif ci_delta < -0.10 or (ci_first_half - ci_second_half > 0.10):
        state = "Outward"
        state_th = "เคลื่อนที่ออก"
        desc = "กลุ่มเมฆพ้นสถานีออกไป แดดเริ่มฟื้นตัว"
        action = "กลุ่มเมฆกำลังพ้นสถานี แดดจะฟื้นตัวกลับมา เตรียมลดการจ่ายไฟ BESS"
    else:
        if ci_mean < 0.40:
            state = "Clear"
            state_th = "ฟ้าโปร่งเป็นส่วนใหญ่"
            desc = "มีเมฆประปรายเล็กน้อย แดดส่องสม่ำเสมอ"
            action = "คงการชาร์จแบตเตอรี่ปกติ แดดส่องสม่ำเสมอเป็นส่วนใหญ่"
        else:
            state = "Overcast"
            state_th = "เมฆปกคลุมปานกลาง"
            desc = "มีเมฆบดบังบางช่วง"
            action = "เตรียมจ่ายไฟจาก BESS เสริมความเสถียร รองรับความผันผวนของเมฆ"

    variance = float(np.var(ci))
    confidence = round(float(np.clip(0.95 - (variance * 0.4), 0.82, 0.98)), 2)

    return {
        "state": state,
        "state_th": state_th,
        "description": desc,
        "bess_action": action,
        "mean_cloud_index": round(ci_mean, 3),
        "confidence": confidence,
    }
