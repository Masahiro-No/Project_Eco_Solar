# Retrain Module (`backend/api/retrain`)

ให้หน้าสถานะ retrain อ่านว่าโมเดลรุ่นไหนใช้งานอยู่ มีรอบไหนรออยู่ และประวัติของแต่ละรอบ ทุกเส้นทางต้องเป็น `admin` มอดูลนี้อ่านอย่างเดียว การ retrain เองทำใน `trainer-worker` (ดู `service/training/`)

| Method | Endpoint | ใช้ทำอะไร |
|---|---|---|
| `GET` | `/api/retrain/status` | รุ่นที่ใช้งานของ LSTM และ ConvLSTM รอบที่รอ และประวัติรอบ retrain |
| `GET` | `/api/retrain/runs/{run_id}/curves` | กราฟการเรียนรู้ราย epoch ของรอบหนึ่ง (loss ตอนเทรน ค่าตรวจ และ learning rate) |

## ที่มาของข้อมูล

- รุ่นที่ใช้งาน: ไฟล์ metadata ใน `model/`
- รอบที่รอ: ธงใน Redis ที่มอดูล `label_studio` และ `ingestion-worker` ตั้งไว้ และจำนวนวันที่มีค่าวัดจริงใหม่ของ LSTM (เช่น 3 / 7) ที่ `trainer-worker` บันทึกทุกครั้งที่นับ
- ประวัติและกราฟ: MLflow (`mlflow_tracking_uri`) แต่ละรอบบันทึกว่าโมเดลใหม่ถูกนำไปใช้หรือถูกปฏิเสธพร้อมเหตุผล

## ไฟล์

- `service.py`, `controller.py`, `router.py`, `schema.py`
