# Dashboard Module (`backend/api/dashboard`)

สรุปข้อมูลจากผลพยากรณ์ล่าสุดของทุกสถานีให้หน้าเว็บ ทุกเส้นทางต้องล็อกอิน

| Method | Endpoint | ใช้ทำอะไร |
|---|---|---|
| `GET` | `/api/dashboard/alerts` | รายการสถานีที่ผลพยากรณ์ล่าสุดอยู่ในระดับเฝ้าระวังขึ้นไป (หน้าการแจ้งเตือนและตัวเลขบนเมนูใช้) |
| `GET` | `/api/dashboard/summary` | ตัวเลขรวมของทุกสถานี |
| `GET` | `/api/dashboard/station/{station_id}` | สรุปของสถานีเดียว |
| `GET` | `/api/dashboard/grafana-links` | ที่อยู่ของ Grafana และ dashboard `solardss-operations` (ที่อยู่มาจากค่า `grafana_url`) |

หน้าเว็บเรียกเฉพาะ `/alerts` ส่วนกราฟและสถานะของหน้าแรกอ่านจาก `/api/inference/latest/{station_id}` โดยตรง

## ไฟล์

- `service.py` อ่านตาราง `predictions` และ `stations` แล้วสรุป ไม่มีค่าตั้งต้นเมื่อสถานียังไม่มีผลพยากรณ์
- `controller.py`, `router.py`, `schema.py`
