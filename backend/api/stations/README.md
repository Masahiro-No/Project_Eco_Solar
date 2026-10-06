# Stations Module (`backend/api/stations`)

ข้อมูลของสถานีผลิตไฟฟ้า: พิกัด พื้นที่แผง ประสิทธิภาพ และเป้ากำลังผลิต ค่าเหล่านี้ใช้คิดกำลังผลิตจาก GHI (`P = พื้นที่ × ประสิทธิภาพ × GHI ÷ 1000`) และใช้ตัดภาพดาวเทียมรอบสถานี

| Method | Endpoint | ใช้ทำอะไร | ใครเรียกได้ |
|---|---|---|---|
| `GET` | `/api/stations` | รายชื่อสถานี | ผู้ใช้ที่ล็อกอิน |
| `GET` | `/api/stations/{station_id}` | รายละเอียดสถานี | ผู้ใช้ที่ล็อกอิน |
| `GET` | `/api/stations/nearest` | สถานีที่ใกล้พิกัดที่ให้มากที่สุด | ผู้ใช้ที่ล็อกอิน |
| `GET` | `/api/stations/archived` | สถานีที่ถูกปิดใช้ | admin |
| `POST` | `/api/stations` | เพิ่มสถานี | admin |
| `PUT` / `PATCH` | `/api/stations/{station_id}` | แก้ทั้งหมด / แก้บางค่า (แผงตั้งค่าในหน้าสถานีใช้ `PATCH`) | admin |
| `DELETE` | `/api/stations/{station_id}` | ปิดใช้สถานี ข้อมูลเดิมยังอยู่ | admin |
| `PATCH` | `/api/stations/{station_id}/restore` | เปิดใช้อีกครั้ง | admin |

สถานีที่เปิดใช้อยู่เท่านั้นที่ `ingestion-worker` ดึงข้อมูลและพยากรณ์ ค่าที่แก้มีผลตั้งแต่รอบพยากรณ์ถัดไป สถานีตั้งต้น 5 แห่งถูกสร้างตอน API เริ่มทำงาน (`backend/db/database.py`)

## ไฟล์

- `service.py`, `repository.py`, `model.py` (ตาราง `stations`), `schema.py`, `controller.py`, `router.py`
