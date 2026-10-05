# Jobs Module (`backend/api/jobs`)

ให้ผู้ดูแลดูและจัดการคิวงานของ worker ใน Redis (ARQ) ทุกเส้นทางต้องเป็น role `admin`

โมดูลนี้ไม่ได้ใช้สั่งงานใหม่ งานในระบบเกิดจากสามทาง:

| งาน | คิว | ใครนัด |
| --- | --- | --- |
| รอบดึงข้อมูล และเก็บผลพยากรณ์ | `ingest_queue` | ตารางเวลาของ ingestion-worker เอง (ทุก 10 นาที และทุกนาที) |
| `run_inference` | `inference_queue` | ingestion-worker หลังดึงข้อมูลแต่ละรอบ หรือ `POST /api/inference/predict` |
| `train_timeseries_lstm` | `train_queue` | โมดูล label_studio หลังบันทึกค่า GHI จริง |
| `train_convlstm_nowcaster` | `train_queue` | ingestion-worker เมื่อภาพใหม่ครบ 50 เวลาสแกน |

## API Endpoints

| Method | Endpoint | ใช้ทำอะไร |
| --- | --- | --- |
| `GET` | `/api/jobs/queues` | จำนวนงานที่รอในแต่ละคิว |
| `GET` | `/api/jobs/queues/{name}/jobs` | รายการ job id ที่รอในคิว |
| `DELETE` | `/api/jobs/queues/{name}/clear` | ล้างงานที่รอทั้งหมดในคิว |
| `GET` | `/api/jobs/{job_id}` | สถานะและผลของงาน |
| `POST` | `/api/jobs/{job_id}/retry` | ส่งงานเดิมเข้าคิวอีกครั้ง |
| `DELETE` | `/api/jobs/{job_id}` | เอางานออกจากคิว |

`GET /api/jobs/queues` นับเฉพาะงานที่รอ ช่อง `active` และ `failed` ยังเป็น 0 เสมอ เพราะยังไม่ได้อ่านค่าจาก worker

## ไฟล์

- `router.py` เส้นทาง
- `controller.py` ตรวจสิทธิ์และจัดรูป response
- `service.py` ต่อ Redis ด้วย `arq.create_pool` (timeout 10 วินาที) โมดูลอื่นใช้ `JobService.get_pool()` เมื่อต้องนัดงาน
- `schema.py` Pydantic models
