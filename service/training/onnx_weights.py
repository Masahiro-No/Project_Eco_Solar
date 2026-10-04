"""
ONNX -> PyTorch weight loader for SolarLSTMForecaster.

ใช้ไฟล์ .onnx เป็นแหล่งความจริงเดียว (ไม่ต้องมี .pth): อ่านน้ำหนักจากกราฟ ONNX
แล้วโหลดเข้า SolarLSTMForecaster เพื่อ fine-tune ต่อ จากนั้นค่อย export กลับเป็น ONNX

จุดสำคัญ: ลำดับ gate ของ LSTM ต่างกัน
    ONNX    : [i, o, f, c]  (แต่ละก้อนยาว hidden_size)
    PyTorch : [i, f, g, o]  (g == c)
และ ONNX เก็บ bias เป็น B = [Wb(4H) || Rb(4H)] ซึ่งตรงกับ bias_ih / bias_hh

ทดสอบความเทียบเท่า (รันจาก root ของ repo):
    python -m service.training.onnx_weights --onnx model/time-series/solar_ghi_lstm.onnx
"""

from __future__ import annotations

import argparse
from typing import Dict, List

import numpy as np
import onnx
import torch
from onnx import numpy_helper

# ตำแหน่งของ gate แต่ละตัวใน ONNX [i, o, f, c]
_ONNX_I, _ONNX_O, _ONNX_F, _ONNX_C = 0, 1, 2, 3


def _reorder_gates(arr: np.ndarray, hidden: int) -> np.ndarray:
    """จัดลำดับ gate จาก ONNX [i,o,f,c] -> PyTorch [i,f,g,o] (แกนแรกคือ 4*hidden)."""
    blocks = [arr[k * hidden:(k + 1) * hidden] for k in range(4)]
    return np.concatenate(
        [blocks[_ONNX_I], blocks[_ONNX_F], blocks[_ONNX_C], blocks[_ONNX_O]], axis=0
    )


def extract_onnx_state_dict(onnx_path: str) -> Dict[str, torch.Tensor]:
    """อ่านน้ำหนักจากไฟล์ ONNX แล้วคืน state_dict ที่ใช้กับ SolarLSTMForecaster ได้ตรง ๆ."""
    model = onnx.load(onnx_path)
    inits = {i.name: numpy_helper.to_array(i) for i in model.graph.initializer}

    lstm_nodes = [n for n in model.graph.node if n.op_type == "LSTM"]
    if not lstm_nodes:
        raise ValueError("ไม่พบ LSTM node ในไฟล์ ONNX")

    state: Dict[str, torch.Tensor] = {}
    for layer, node in enumerate(lstm_nodes):
        hidden = next(a.i for a in node.attribute if a.name == "hidden_size")
        direction = next((a.s for a in node.attribute if a.name == "direction"), b"forward")
        if direction != b"forward":
            raise ValueError("รองรับเฉพาะ LSTM แบบ forward")

        w_name, r_name, b_name = node.input[1], node.input[2], node.input[3]
        if w_name not in inits or r_name not in inits:
            raise ValueError(f"LSTM layer {layer}: ไม่พบ initializer ของ W/R")
        w = inits[w_name][0]  # [4H, in]
        r = inits[r_name][0]  # [4H, H]
        if b_name and b_name in inits:
            b = inits[b_name][0]  # [8H]
        else:
            b = np.zeros(8 * hidden, dtype=w.dtype)

        state[f"lstm.weight_ih_l{layer}"] = torch.from_numpy(_reorder_gates(w, hidden).copy())
        state[f"lstm.weight_hh_l{layer}"] = torch.from_numpy(_reorder_gates(r, hidden).copy())
        state[f"lstm.bias_ih_l{layer}"] = torch.from_numpy(_reorder_gates(b[: 4 * hidden], hidden).copy())
        state[f"lstm.bias_hh_l{layer}"] = torch.from_numpy(_reorder_gates(b[4 * hidden:], hidden).copy())

    # head: Gemm(transB=1) เก็บ weight เป็น [out, in] ซึ่งตรงกับ nn.Linear
    for idx in (0, 3):
        state[f"head.{idx}.weight"] = torch.from_numpy(inits[f"head.{idx}.weight"].copy())
        state[f"head.{idx}.bias"] = torch.from_numpy(inits[f"head.{idx}.bias"].copy())
    return state


def load_onnx_into_model(model: torch.nn.Module, onnx_path: str) -> torch.nn.Module:
    """โหลดน้ำหนักจาก ONNX เข้าโมเดล (strict) แล้วคืนโมเดลเดิม."""
    model.load_state_dict(extract_onnx_state_dict(onnx_path), strict=True)
    return model


def check_equivalence(onnx_path: str, n_samples: int = 8, seed: int = 0) -> float:
    """เทียบ output PyTorch กับ onnxruntime คืนค่า max |diff| (หน่วยเดียวกับ output)."""
    import onnxruntime as ort

    from service.models.solar_lstm import SolarLSTMForecaster
    from service.training.dataset import LOOKBACK_STEPS

    model = SolarLSTMForecaster()
    load_onnx_into_model(model, onnx_path)
    model.eval()

    rng = np.random.default_rng(seed)
    x = rng.random((n_samples, LOOKBACK_STEPS, 16), dtype=np.float32)

    sess = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
    in_name = sess.get_inputs()[0].name
    onnx_out = sess.run(None, {in_name: x})[0]
    with torch.no_grad():
        torch_out = model(torch.from_numpy(x)).numpy()

    return float(np.abs(onnx_out - torch_out).max())


def _main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--onnx", required=True)
    p.add_argument("--tol", type=float, default=1e-4)
    args = p.parse_args()

    diff = check_equivalence(args.onnx)
    status = "PASS" if diff <= args.tol else "FAIL"
    print(f"max|onnxruntime - pytorch| = {diff:.3e}  (tol {args.tol:.0e})  -> {status}")
    raise SystemExit(0 if status == "PASS" else 1)


if __name__ == "__main__":
    _main()
