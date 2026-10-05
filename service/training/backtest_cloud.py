"""Backtest of the satellite branch on real frames: how good is the cloud cover forecast at each lead time?

For every held-out sequence of 30 real daytime frames (12 in -> 18 out) the cloud cover in the station's
AOI is computed on the real future frames and compared with
  - the ConvLSTM forecast (deployed ONNX),
  - persistence: the cloud cover of the newest observed frame, kept for all 18 steps,
  - the combination the inference worker uses: observed cover first, ConvLSTM later.

The result per lead time (MAE, bias, skill against persistence) decides how the satellite branch
builds its cloud cover: see OBSERVED_UNTIL_MIN / MODEL_FROM_MIN in service/workers/cloud_coverage.py.

CLI (needs the same environment as retrain_convlstm):
    python -m service.training.backtest_cloud [--onnx PATH] [--all] [--out results.json]
"""

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from service.training import retrain_convlstm as rc
from service.workers import convlstm_batch as batch
from service.workers.cloud_coverage import MIN_COS_ZENITH, aoi_cloud_fraction, observed_then_forecast
from service.workers.solar_geometry import cos_zenith_at


def backtest(onnx_path: Path, use_all_sequences: bool = False, lookback_days: int = 5, stride: int = 2) -> dict[str, Any]:
    import onnxruntime as ort

    client = rc._minio_client()
    coords = rc.station_coordinates()
    data = rc.build_dataset(client, coords, stride=stride, lookback_days=lookback_days)
    if use_all_sequences:
        idx = list(range(len(data["starts"])))
        subset = "all sequences"
    else:
        _, idx, cut = rc.split_by_time(data["starts"], 0.2)
        subset = f"held-out sequences from {cut:%Y-%m-%d %H:%M} UTC"
    if not idx:
        raise SystemExit("no sequences to backtest")

    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    name = session.get_inputs()[0].name

    steps = rc.OUT_FRAMES
    err_model = [[] for _ in range(steps)]
    err_persist = [[] for _ in range(steps)]
    err_used = [[] for _ in range(steps)]
    bias_model = [[] for _ in range(steps)]
    truth_all = [[] for _ in range(steps)]
    for i in idx:
        x, y = data["x"][i], data["y"][i]
        station_id, start = data["stations"][i], data["starts"][i]
        lat, lon = coords[station_id]
        t_last = start + (rc.IN_FRAMES - 1) * batch.FRAME_INTERVAL
        cos_last = cos_zenith_at(lat, lon, t_last)
        if cos_last < MIN_COS_ZENITH:
            continue
        now = aoi_cloud_fraction(x[-1, 0], cos_zenith=[cos_last])[0]
        pred = session.run(None, {name: x[np.newaxis]})[0][0]
        got = aoi_cloud_fraction(pred, cos_zenith=data["cos_out"][i])
        want = aoi_cloud_fraction(y, cos_zenith=data["cos_out"][i])
        for k in range(steps):
            if got[k] is None or want[k] is None:
                continue
            err_model[k].append(abs(got[k] - want[k]))
            bias_model[k].append(got[k] - want[k])
            err_persist[k].append(abs(now - want[k]))
            err_used[k].append(abs(observed_then_forecast(now, got[k], (k + 1) * 10.0) - want[k]))
            truth_all[k].append(want[k])

    rows = []
    for k in range(steps):
        if not err_model[k]:
            continue
        mae_m, mae_p = float(np.mean(err_model[k])), float(np.mean(err_persist[k]))
        rows.append({
            "lead_min": (k + 1) * 10,
            "n": len(err_model[k]),
            "true_cloud_pct": round(100 * float(np.mean(truth_all[k])), 1),
            "convlstm_mae_pct": round(100 * mae_m, 1),
            "convlstm_bias_pct": round(100 * float(np.mean(bias_model[k])), 1),
            "persistence_mae_pct": round(100 * mae_p, 1),
            "used_mae_pct": round(100 * float(np.mean(err_used[k])), 1),
            "skill_vs_persistence": round(1.0 - mae_m / mae_p, 3) if mae_p > 0 else None,
        })
    return {"onnx": str(onnx_path), "subset": subset, "sequences": len(idx), "by_lead": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description="Lead-time backtest of the cloud cover forecast")
    parser.add_argument("--onnx", default=str(rc.MODELS_DIR / rc.ONNX_NAME))
    parser.add_argument("--all", action="store_true", help="use every sequence, not only the held-out ones")
    parser.add_argument("--out", help="write the result as JSON")
    args = parser.parse_args()

    result = backtest(Path(args.onnx), use_all_sequences=args.all)
    print(f"{result['subset']}: {result['sequences']} sequences, model {Path(result['onnx']).name}")
    print("lead   n  true%  ConvLSTM MAE  bias  persistence MAE  used MAE  ConvLSTM skill vs persistence")
    for r in result["by_lead"]:
        print(f"{r['lead_min']:4d} {r['n']:4d} {r['true_cloud_pct']:6.1f} {r['convlstm_mae_pct']:10.1f} {r['convlstm_bias_pct']:8.1f}"
              f" {r['persistence_mae_pct']:12.1f} {r['used_mae_pct']:10.1f} {r['skill_vs_persistence']!s:>12}")
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
