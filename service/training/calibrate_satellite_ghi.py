"""Calibrate the satellite branch against measured GHI.

For every measured GHI value (ground-truth labels in Label Studio) that has a real satellite frame of the
same station and time:

    k   = GHI_measured / GHI_clearsky                      measured clear-sky index
    rho = mean(pixel / 255) in the 5x5 px AOI / cos(zenith)   sun-normalised brightness

and a straight line k = intercept - slope * rho is fitted by least squares. The error is reported for days
the line was not fitted on (leave one day out). The result is written to model/satellite/ghi_calibration.json,
which the inference worker reads on its next job.

This is how human-provided measurements improve the satellite branch: every uploaded GHI file adds pairs.

The fitted line is applied to every station. `--check` measures how far it is off at each station that has
measured GHI, without changing the line, and records that in the file (`checked`): the web page then says
whether the relation was compared with the sensor of the station on screen.

CLI (trainer container, /workspace):
    python -m service.training.calibrate_satellite_ghi            # report only
    python -m service.training.calibrate_satellite_ghi --write    # also write the calibration file
    python -m service.training.calibrate_satellite_ghi --check    # error of the current line per station -> `checked`
"""

import argparse
import json
from datetime import datetime, timezone
from typing import Any

import numpy as np

from service.training import retrain_convlstm as rc
from service.workers.cloud_coverage import CALIBRATION_FILE, MIN_COS_ZENITH, aoi_brightness
from service.workers.solar_geometry import clearsky_ghi_at, cos_zenith_at

K_MIN, K_MAX = 0.05, 1.15
MIN_PAIRS = 30


def collect_pairs(lookback_days: int) -> list[dict[str, Any]]:
    """Measured GHI paired with the real frame of the same station and 10-minute slot (daylight only)."""
    from service.training.retrain_timeseries import fetch_labels_from_label_studio

    labels = fetch_labels_from_label_studio(lookback_days)
    coords = rc.station_coordinates()
    client = rc._minio_client()
    pairs = []
    for row in labels.itertuples(index=False):
        if row.station_id not in coords:
            continue
        lat, lon = coords[row.station_id]
        ts = row.timestamp.to_pydatetime().astimezone(timezone.utc).replace(second=0, microsecond=0)
        ts = ts.replace(minute=(ts.minute // 10) * 10)
        cos_z = cos_zenith_at(lat, lon, ts)
        if cos_z < MIN_COS_ZENITH:
            continue
        try:
            frame = rc.load_frame(client, row.station_id, ts)
        except Exception:  # noqa: BLE001  no frame cached for this slot
            continue
        if float(frame.max()) == 0.0:  # NICT's "no image" tile
            continue
        pairs.append({
            "station_id": row.station_id,
            "time": ts,
            "k": float(row.ghi_actual) / clearsky_ghi_at(lat, lon, ts),
            "rho": aoi_brightness(frame, [cos_z])[0],
        })
    return pairs


def _line(rho: np.ndarray, k: np.ndarray) -> tuple[float, float]:
    """Least-squares (intercept, slope) of k = intercept - slope * rho."""
    a, b = np.linalg.lstsq(np.vstack([np.ones_like(rho), rho]).T, k, rcond=None)[0]
    return float(a), float(-b)


def fit(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    rho = np.array([p["rho"] for p in pairs])
    k = np.array([p["k"] for p in pairs])
    days = np.array([p["time"].strftime("%Y-%m-%d") for p in pairs])
    intercept, slope = _line(rho, k)
    predict = lambda a, b, x: np.clip(a - b * x, K_MIN, K_MAX)  # noqa: E731

    held_out = []
    for day in sorted(set(days)):
        train, test = days != day, days == day
        if train.sum() < 2:
            continue
        a, b = _line(rho[train], k[train])
        held_out.extend(np.abs(predict(a, b, rho[test]) - k[test]))
    return {
        "intercept": round(intercept, 4),
        "slope": round(slope, 4),
        "k_min": K_MIN,
        "k_max": K_MAX,
        "pairs": int(len(pairs)),
        "days": sorted(set(days.tolist())),
        "stations": sorted({p["station_id"] for p in pairs}),
        "correlation": round(float(np.corrcoef(rho, k)[0, 1]), 3),
        "mae_in_sample": round(float(np.mean(np.abs(predict(intercept, slope, rho) - k))), 4),
        "mae_leave_one_day_out": round(float(np.mean(held_out)), 4) if held_out else None,
        "mae_constant_mean": round(float(np.mean(np.abs(k - k.mean()))), 4),
        "measured_k_mean": round(float(k.mean()), 3),
        "fitted_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }


def check(pairs: list[dict[str, Any]], current: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Error of the line in `current` at every station with at least MIN_PAIRS measured slots."""
    intercept, slope = float(current["intercept"]), float(current["slope"])
    k_min, k_max = float(current.get("k_min", K_MIN)), float(current.get("k_max", K_MAX))
    fitted_on = set(current.get("stations") or [])
    checked: dict[str, dict[str, Any]] = {}
    for station in sorted({p["station_id"] for p in pairs}):
        mine = [p for p in pairs if p["station_id"] == station]
        if len(mine) < MIN_PAIRS:
            continue
        rho = np.array([p["rho"] for p in mine])
        k = np.array([p["k"] for p in mine])
        checked[station] = {
            "fitted": station in fitted_on,
            "pairs": int(len(mine)),
            "days": int(len({p["time"].strftime("%Y-%m-%d") for p in mine})),
            "mae": round(float(np.mean(np.abs(np.clip(intercept - slope * rho, k_min, k_max) - k))), 4),
            "mae_constant_mean": round(float(np.mean(np.abs(k - k.mean()))), 4),
            "measured_k_mean": round(float(k.mean()), 3),
            "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        }
    return checked


def main() -> None:
    parser = argparse.ArgumentParser(description="Fit the satellite brightness -> clear-sky index relation on measured GHI")
    parser.add_argument("--lookback-days", type=int, default=45)
    parser.add_argument("--write", action="store_true", help="write model/satellite/ghi_calibration.json")
    parser.add_argument("--check", action="store_true", help="keep the line; record its error per station in the file")
    args = parser.parse_args()

    pairs = collect_pairs(args.lookback_days)
    if args.check:
        current = json.loads(CALIBRATION_FILE.read_text(encoding="utf-8"))
        current["checked"] = check(pairs, current)
        print(json.dumps(current["checked"], indent=2))
        CALIBRATION_FILE.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
        print(f"written to {CALIBRATION_FILE} (line unchanged: {current['intercept']} - {current['slope']} * rho)")
        return
    if len(pairs) < MIN_PAIRS:
        raise SystemExit(f"only {len(pairs)} measured slots have a real frame (need {MIN_PAIRS}): nothing fitted")
    result = fit(pairs)
    print(json.dumps(result, indent=2))
    if result["slope"] <= 0:
        raise SystemExit("the fitted slope is not positive (brighter AOI should mean less irradiance): not written")
    if args.write:
        CALIBRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
        CALIBRATION_FILE.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"written to {CALIBRATION_FILE}")


if __name__ == "__main__":
    main()
