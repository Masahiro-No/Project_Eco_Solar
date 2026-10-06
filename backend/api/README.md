# API Modules (`backend/api`)

โค้ดของ REST API ทั้งหมด แบ่งเป็นมอดูลตามหน้าที่ ทุกเส้นทางขึ้นต้นด้วย `/api` (ต่อเข้าแอปใน `backend/main.py`)

| โฟลเดอร์ | หน้าที่ | ใครเรียกได้ |
|---|---|---|
| [auth](auth/) | สมัคร ล็อกอิน ออก token และ dependency ตรวจสิทธิ์ที่มอดูลอื่นใช้ | ทุกคน |
| [users](users/) | ดู แก้ ลบบัญชีผู้ใช้ และเปลี่ยน role | เจ้าของบัญชี / admin |
| [stations](stations/) | ข้อมูลสถานี พื้นที่แผง ประสิทธิภาพ เป้ากำลังผลิต | อ่าน: ผู้ใช้ที่ล็อกอิน, แก้: admin |
| [ingestion](ingestion/) | เก็บสภาพอากาศ (Open-Meteo) และภาพดาวเทียม (NICT) และให้หน้าเว็บอ่าน | ผู้ใช้ที่ล็อกอิน |
| [inference](inference/) | สร้างข้อมูลป้อน LSTM สั่งพยากรณ์ บันทึกและอ่านผลพยากรณ์ | ผู้ใช้ที่ล็อกอิน |
| [dashboard](dashboard/) | สรุปของหน้าแรกและรายการแจ้งเตือน | ผู้ใช้ที่ล็อกอิน |
| [label_studio](label_studio/) | บันทึกค่า GHI ที่วัดจริง (กรอกหรืออัปโหลดไฟล์) และนัด retrain LSTM | admin |
| [frame_review](frame_review/) | ให้ผู้ดูแลตรวจภาพดาวเทียมก่อนใช้ retrain ConvLSTM | admin |
| [retrain](retrain/) | สถานะและประวัติ retrain ของทั้งสองโมเดล | admin |
| [jobs](jobs/) | ดูและจัดการคิวงานของ worker ใน Redis | admin |
| [storage](storage/) | จัดการ bucket และไฟล์ใน MinIO | admin |

## โครงของแต่ละมอดูล

- `router.py` ประกาศเส้นทางและรูปแบบคำตอบ
- `controller.py` ตรวจสิทธิ์ รับค่า และจัดรูปคำตอบ
- `service.py` ตรรกะของมอดูล
- `repository.py` คำสั่งกับฐานข้อมูล (มีเฉพาะบางมอดูล)
- `model.py` ตารางของ SQLAlchemy, `schema.py` รูปแบบข้อมูลของ Pydantic

ไม่มีข้อมูลจำลองในมอดูลใด ถ้าไม่มีข้อมูลจริง API ตอบว่าไม่มี
