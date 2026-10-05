"""ConvLSTM retrain: batch rule, sequence building and the model rebuilt from the deployed ONNX file.

The tensors used here only check shapes, time logic and numerical equivalence; nothing in the
pipeline is trained or evaluated on them.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from service.workers import convlstm_batch as batch

HAT_YAI = (7.0086, 100.4988)
NOON_UTC = datetime(2026, 10, 4, 5, 0, tzinfo=timezone.utc)      # 12:00 local
MIDNIGHT_UTC = datetime(2026, 10, 4, 17, 0, tzinfo=timezone.utc)  # 00:00 local


def _run(start: datetime, n: int) -> list[datetime]:
    return [start + k * batch.FRAME_INTERVAL for k in range(n)]


def test_night_scans_do_not_count():
    assert batch.is_daytime(NOON_UTC, *HAT_YAI)
    assert not batch.is_daytime(MIDNIGHT_UTC, *HAT_YAI)
    scans = {"ST-001": _run(NOON_UTC, 6) + _run(MIDNIGHT_UTC, 6)}
    assert batch.daytime_scans(scans, {"ST-001": HAT_YAI}) == {"ST-001": _run(NOON_UTC, 6)}


def test_batch_counts_distinct_scan_times_after_last_retrain():
    coords = {"ST-001": HAT_YAI, "ST-002": (6.931, 100.369)}
    times = _run(NOON_UTC, 10)
    scans = {"ST-001": times, "ST-002": times[:8], "ST-UNKNOWN": times}

    status = batch.batch_status(scans, coords, since=None, batch_size=10)
    assert status["new_scans"] == 10 and status["due"]          # the same scan at two stations is one image
    assert "ST-UNKNOWN" not in status["stations"]

    status = batch.batch_status(scans, coords, since=times[5], batch_size=10)
    assert status["new_scans"] == 4 and not status["due"]
    assert status["newest_scan"] == times[-1].isoformat()


def test_sequences_need_consecutive_frames():
    times = _run(NOON_UTC, 12)
    del times[5]  # a missing scan breaks every run that covers it
    assert batch.find_sequences(times, length=5) == [times[0], times[5], times[6]]
    assert batch.find_sequences(_run(NOON_UTC, 9), length=5, stride=2) == [NOON_UTC, NOON_UTC + 2 * batch.FRAME_INTERVAL, NOON_UTC + 4 * batch.FRAME_INTERVAL]


def test_black_daytime_frame_is_not_an_observation():
    from service.workers.satellite_preprocessor import is_blank_daytime_frame

    black = np.zeros((64, 64), dtype=np.float32)
    cloudy = np.full((64, 64), 0.4, dtype=np.float32)
    assert is_blank_daytime_frame(black, *HAT_YAI, NOON_UTC)          # NICT's "no image" tile
    assert not is_blank_daytime_frame(cloudy, *HAT_YAI, NOON_UTC)
    assert not is_blank_daytime_frame(black, *HAT_YAI, MIDNIGHT_UTC)  # a visible-band frame is black at night


def test_parse_time_accepts_redis_bytes():
    assert batch.parse_time(b"2026-10-04T05:00:00+00:00") == NOON_UTC
    assert batch.parse_time(None) is None and batch.parse_time(b"not-a-time") is None


# ---------------------------------------------------------------- model (needs torch + the deployed ONNX)
torch = pytest.importorskip("torch")
retrain = pytest.importorskip("service.training.retrain_convlstm")
ONNX_PATH = retrain.MODELS_DIR / retrain.ONNX_NAME
needs_model = pytest.mark.skipif(not ONNX_PATH.exists(), reason="deployed ConvLSTM ONNX not present")


@needs_model
def test_pytorch_model_reproduces_deployed_onnx():
    model = retrain.CloudSeq2SeqConvLSTM()
    retrain.load_onnx_weights(model, ONNX_PATH)
    sample = np.random.default_rng(0).random((2, retrain.IN_FRAMES, 1, 64, 64), dtype=np.float32)
    assert retrain.onnx_max_deviation(model, ONNX_PATH, sample) < 1e-4


@needs_model
def test_export_keeps_tensor_names_and_matches_pytorch(tmp_path: Path):
    import onnxruntime as ort

    model = retrain.CloudSeq2SeqConvLSTM()
    retrain.load_onnx_weights(model, ONNX_PATH)
    out = tmp_path / "export.onnx"
    retrain.export_onnx(model, out)

    session = ort.InferenceSession(str(out), providers=["CPUExecutionProvider"])
    assert session.get_inputs()[0].name == retrain.INPUT_NAME
    assert session.get_outputs()[0].name == retrain.OUTPUT_NAME
    sample = np.random.default_rng(1).random((3, retrain.IN_FRAMES, 1, 64, 64), dtype=np.float32)
    assert session.run(None, {retrain.INPUT_NAME: sample})[0].shape == (3, retrain.OUT_FRAMES, 1, 64, 64)
    assert retrain.onnx_max_deviation(model, out, sample) < 1e-4


def test_time_split_keeps_train_and_validation_frames_apart():
    starts = [NOON_UTC + timedelta(minutes=20 * k) for k in range(40)]
    train, val, cut = retrain.split_by_time(starts, val_fraction=0.25)
    assert train and val and cut == starts[30]
    span = retrain.SEQ_FRAMES * batch.FRAME_INTERVAL
    assert max(starts[i] + span for i in train) <= min(starts[i] for i in val)
    assert retrain.split_by_time([], 0.2) == ([], [], None)


def test_retrain_is_skipped_while_disabled(monkeypatch):
    monkeypatch.setenv("ENABLE_RETRAIN", "false")
    assert retrain.execute_convlstm_retrain({})["status"] == "skipped"
