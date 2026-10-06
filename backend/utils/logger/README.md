# Logger (`backend/utils/logger`)

`custom_logger.py` ตั้งค่า `logging` ให้เขียนทั้งหน้าจอและไฟล์หมุนเวียนในโฟลเดอร์ `logs/`

**สถานะ:** มาจาก template และยังไม่มีโค้ดใน backend เรียกใช้ API ใช้ logger ชื่อ `solar.api` ของ `logging` โดยตรง (ดู `backend/main.py`) ส่วน log ของคอนเทนเนอร์ถูกส่งเข้า Loki ผ่าน Promtail (ดู `observability/`)
