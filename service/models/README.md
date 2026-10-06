# Model Definitions (`service/models`)

โครงของโมเดลในรูปแบบ PyTorch ที่ใช้ตอนเทรน

| ไฟล์ | เนื้อหา |
|---|---|
| `solar_lstm.py` | `SolarLSTMForecaster`: LSTM ที่รับฟีเจอร์ 16 ตัวย้อนหลัง แล้วทำนาย GHI 18 ช่องถัดไป |

ตอนใช้งานจริง worker รันไฟล์ ONNX ใน `model/time-series/` ไม่ได้ใช้คลาสนี้ คลาสนี้ใช้ตอนเทรนตั้งต้น (`training/train.py`) และตอน retrain ซึ่งโหลดน้ำหนักจาก ONNX กลับเข้าคลาสนี้ด้วย `training/onnx_weights.py`

โครงของ ConvLSTM อยู่ใน `training/retrain_convlstm.py`
