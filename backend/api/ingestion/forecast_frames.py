"""Frames the ConvLSTM predicted in the newest forecast round of a station.

The inference worker overwrites them every round in the bucket `satellite-forecast`
(service/workers/satellite_preprocessor.py::save_forecast_frames): <station>/step_01.png ... and
<station>/meta.json. A round in which the ConvLSTM did not run writes meta.json with 0 steps, so what is
read here always belongs to the newest round.
"""

import base64
import json
from datetime import datetime, timedelta
from typing import Any, Optional

from api.storage.service import StorageService

FORECAST_BUCKET = "satellite-forecast"


def _read(client, name: str) -> bytes:
    resp = client.get_object(FORECAST_BUCKET, name)
    try:
        return resp.read()
    finally:
        resp.close()
        resp.release_conn()


def read_forecast_frames(station_id: str) -> Optional[dict[str, Any]]:
    """The stored forecast frames with their times (blocking: call in a thread); None when nothing is stored yet."""
    client = StorageService().client
    try:
        meta = json.loads(_read(client, f"{station_id}/meta.json"))
    except Exception:  # noqa: BLE001  no forecast round has stored anything for this station
        return None

    end_time = datetime.fromisoformat(meta["end_time"]) if meta.get("end_time") else None
    step = timedelta(minutes=int(meta.get("step_minutes") or 10))
    cloud = meta.get("cloud_pct") or []
    frames = []
    if end_time is not None:
        for j in range(int(meta.get("steps") or 0)):
            try:
                png = _read(client, f"{station_id}/step_{j + 1:02d}.png")
            except Exception:  # noqa: BLE001  a frame that could not be read is left out, never replaced
                continue
            frames.append({
                "timestamp": end_time + step * (j + 1),
                "lead_minutes": int(step.total_seconds() // 60) * (j + 1),
                "cloud_pct": cloud[j] if j < len(cloud) else None,
                "image_b64": base64.b64encode(png).decode("ascii"),
            })
    return {
        "end_time": end_time,
        "created_at": meta.get("created_at"),
        "status": meta.get("status") or "missing",
        "reason": meta.get("reason"),
        "frames": frames,
    }
