# Ingestion Module (`backend/api/ingestion`)

เก็บสภาพอากาศจาก Open-Meteo และภาพดาวเทียม Himawari จาก NICT ลงฐานข้อมูลและ MinIO โค้ดส่วนเก็บข้อมูลถูกเรียกโดย `ingestion-worker` ทุก 10 นาที ส่วน API ให้หน้าเว็บอ่านข้อมูลที่เก็บไว้

| Method | Endpoint | ใช้ทำอะไร | ใครเรียกได้ |
|---|---|---|---|
| `GET` | `/api/ingestion/weather/{station_id}/recent` | แถวสภาพอากาศย้อนหลัง (หน้าข้อมูลป้อนโมเดลใช้) | ผู้ใช้ที่ล็อกอิน |
| `GET` | `/api/ingestion/satellite/{station_id}/day-frames` | ภาพ B03 จริงของวัน และภาพที่ ConvLSTM ทำนายในรอบล่าสุด | ผู้ใช้ที่ล็อกอิน |
| `GET` | `/api/ingestion/satellite/{station_id}/latest.png` | ภาพสีจริงล่าสุดรอบสถานี | ผู้ใช้ที่ล็อกอิน |
| `GET` | `/api/ingestion/satellite/{station_id}/frames` | รายการเฟรมล่าสุดจากตาราง `satellite_frames` | ผู้ใช้ที่ล็อกอิน |
| `GET` | `/api/ingestion/status` | เวลาของข้อมูลล่าสุดและจำนวนแถวที่เก็บ | ผู้ใช้ที่ล็อกอิน |
| `POST` | `/api/ingestion/catchup` | ดึงข้อมูลที่ขาดของสถานีที่ระบุทันที (ต้องระบุ `station_id`) | admin |

## กติกาสำคัญ

- **ไม่มีค่าทดแทน** แถวสภาพอากาศถูกบันทึกเมื่อ Open-Meteo ส่งครบทุกตัวแปรที่ขอ (อุณหภูมิ ความชื้น ความกดอากาศ ลม เมฆ DNI DHI GHI) ช่องที่ขาดไม่ถูกเติม
- **หน่วย** ความเร็วลมขอเป็น ม./วินาที ตามหน่วยที่ใช้เทรน
- **ภาพดำ** ภาพกลางวันที่ดำทั้งภาพคือ NICT ยังไม่มีภาพของเวลานั้น ไม่เก็บ
- **กันแถวซ้ำ** ตาราง `weather_history` และ `satellite_frames` มีกฎ unique และการเขียนใช้ `insert_once` (ON CONFLICT DO NOTHING)
- **ไม่บล็อก** การดาวน์โหลดและอัปโหลดรันใน thread

## ไฟล์

- `service.py` ดึง Open-Meteo และ NICT เติมช่องที่ขาด (`auto_catchup_weather`, `auto_catchup_satellite`) ดึงสภาพอากาศของวันเก่าที่มีค่าวัดจริงแต่ระบบยังไม่มีสภาพอากาศ (`backfill_weather_for_days` เรียกจากมอดูล `label_studio` ตอนบันทึกค่าวัดจริง แถวที่ได้มี `source = open_meteo_backfill`) และอ่านข้อมูลให้ API
- `normalizer.py` แปลงคำตอบของ Open-Meteo เป็นแถว และจัดค่าราย 15 นาทีลงช่อง 10 นาที
- `solar_calculator.py` ตำแหน่งดวงอาทิตย์และ GHI ฟ้าใส (สูตรเดียวกับ `service/workers/solar_geometry.py`)
- `forecast_frames.py` อ่านภาพที่ ConvLSTM ทำนายจาก bucket `satellite-forecast`
- `model.py` ตารางและ `insert_once`, `schema.py`, `controller.py`, `router.py`
