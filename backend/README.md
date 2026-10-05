# Backend — FastAPI (`backend/`)

API กลางของ SolarDSS ให้บริการหน้าเว็บ ตรวจสิทธิ์ผู้ใช้ และเป็นทางเดียวที่หน้าเว็บเข้าถึง PostgreSQL, MinIO, Label Studio และคิวงานใน Redis
ภาพรวมของทั้งระบบอยู่ใน [README หลัก](../README.md)

## โครงสร้าง

```text
backend/
├── main.py             จุดเริ่มของ FastAPI: lifespan (สร้างตาราง, seed สถานี, ตั้งบัญชี admin), CORS, รวม router
├── core/config.py      ค่าตั้งจาก .env (pydantic-settings)
├── db/database.py      engine และ session แบบ async, สร้างตาราง, เพิ่มคอลัมน์ใหม่, seed
├── api/
│   ├── auth/           สมัคร ล็อกอิน JWT และ role (operator, admin)
│   ├── users/          รายชื่อผู้ใช้ แก้ไข ลบ
│   ├── stations/       สถานี: สร้าง แก้ ปิดใช้ กู้คืน หาสถานีใกล้พิกัด
│   ├── ingestion/      สภาพอากาศ (Open-Meteo) และภาพดาวเทียม (NICT) ที่ ingestion-worker เรียกใช้
│   ├── inference/      สั่งพยากรณ์ อ่านผลล่าสุด ประวัติ และผลรายวันเทียบกับค่าจริง
│   ├── dashboard/      สรุปทั้งระบบ รายสถานี และรายการแจ้งเตือน
│   ├── label_studio/   รับค่า GHI ที่วัดจริง (กรอกหรืออัปโหลดไฟล์) เก็บใน Label Studio แล้วนัด retrain LSTM
│   ├── frame_review/   ผู้ดูแลตรวจภาพดาวเทียมที่จะใช้ retrain ConvLSTM
│   ├── jobs/           ดูและจัดการคิวงานใน Redis
│   └── storage/        bucket และไฟล์ใน MinIO
└── scripts/            สคริปต์ตรวจระบบและดูแลข้อมูล (ดูด้านล่าง)
```

แต่ละโมดูลแบ่งชั้นเหมือนกัน: `router.py` (เส้นทาง) → `controller.py` (ตรวจสิทธิ์ ตรวจ request จัดรูป response) → `service.py` (งานจริง) และ `schema.py` (Pydantic), `model.py` (ตาราง SQLAlchemy) เมื่อมี

## Endpoints

ทุกเส้นทางขึ้นต้นด้วย `/api` ยกเว้น `/health` รายการเต็มพร้อมตัวอย่างอยู่ที่ Swagger

| โมดูล | เส้นทาง | สิทธิ์ |
|---|---|---|
| auth | `POST /auth/register`, `POST /auth/login`, `GET /auth/me` | สมัครและล็อกอินไม่ต้องมี token |
| users | `GET /users`, `GET·PATCH·DELETE /users/{id}` | รายชื่อทั้งหมด: admin; รายคน: เจ้าของบัญชีหรือ admin |
| stations | `GET /stations`, `GET /stations/{id}`, `GET /stations/nearest` | ผู้ใช้ที่ล็อกอิน |
| stations | `POST`, `PUT`, `PATCH`, `DELETE /stations…`, `GET /stations/archived`, `PATCH /stations/{id}/restore` | admin |
| ingestion | `GET /ingestion/status`, `/weather/{id}/recent`, `/satellite/{id}/frames`, `/satellite/{id}/latest.png` | ผู้ใช้ที่ล็อกอิน |
| ingestion | `POST /ingestion/trigger`, `POST /ingestion/catchup` | admin |
| inference | `GET /inference/latest/{id}`, `/history/{id}`, `/predictions-by-date`, `/result/{job_id}` | ผู้ใช้ที่ล็อกอิน |
| inference | `POST /inference/predict` | admin |
| dashboard | `GET /dashboard/summary`, `/station/{id}`, `/alerts`, `/grafana-links` | ผู้ใช้ที่ล็อกอิน |
| label-studio | `POST /label-studio/ground-truth/submit`, `/batch-submit`, `/upload/preview`, `/upload` และ projects, tasks, annotations | admin |
| frame-review | `GET·POST /frame-review/frames`, `GET /frame-review/status` | admin |
| jobs | `GET /jobs/queues`, `/queues/{name}/jobs`, `GET·DELETE /jobs/{id}`, `POST /jobs/{id}/retry`, `DELETE /jobs/queues/{name}/clear` | admin |
| storage | `GET·POST /storage/buckets`, `POST /storage/upload`, `GET /storage/download/{bucket}/{object}`, `PUT /storage/buckets/{bucket}/versioning` | admin |

ไม่มี token ได้ 401 และ operator ที่เรียกเส้นทางของ admin ได้ 403

เอกสาร API: Swagger UI ที่ `http://localhost:8000/`, ReDoc ที่ `/redoc`, schema ที่ `/openapi.json`

## จุดที่ควรรู้

- **ไม่มีข้อมูลจำลอง** ถ้าสถานียังไม่มีผลพยากรณ์ API ตอบว่าไม่มี ไม่สร้างค่าแทน
- **ข้อมูลป้อน LSTM** สร้างที่ `api/inference/weather_grid.py`: จัดแถวสภาพอากาศลงช่อง 10 นาที เติมช่องว่างไม่เกิน 20 นาที ถ้ายังมีช่องว่างจะไม่พยากรณ์และคืนเหตุผล (`gap_in_history`, `insufficient_history`, `stale_data`)
- **ingestion-worker ใช้โค้ดโฟลเดอร์นี้** (สร้างข้อมูลป้อนโมเดลและบันทึกผลพยากรณ์) แก้ backend แล้วต้อง restart ทั้ง `api` และ `ingestion-worker`
- **บัญชี admin** สร้างหรืออัปเดตรหัสผ่านตอน API เริ่มทำงาน จาก `ADMIN_EMAIL` และ `ADMIN_PASSWORD` ใน `.env` ผู้ที่สมัครเองได้ role `operator` เสมอ
- **ป้ายสูตรแสงของสถานี** ฟิลด์ `sat_calibration_verified` ในผลพยากรณ์ อ่านจากรายชื่อ `stations` ใน `model/satellite/ghi_calibration.json`

## รัน

ในระบบจริง API รันใน container `fastapi` ผ่าน `docker compose up -d` โค้ดถูก mount เข้า container แต่ uvicorn ไม่ได้เปิด `--reload`

```bash
docker compose restart api ingestion-worker
```

รันบนเครื่องเองเพื่อพัฒนา (ต้องมี `.env` และบริการอื่นทำงานอยู่):

```bash
uv sync
uv run uvicorn main:app --reload
```

## สคริปต์ (`scripts/`)

| ไฟล์ | ใช้ทำอะไร |
|---|---|
| `check_ground_truth_flow.py` | ตรวจ 6 หมวด: ช่องเวลา 10 นาที, ตรวจภาพ, กติกาเวลา, ไฟล์ตัวอย่าง, การบันทึก label, flow ผ่าน HTTP ใช้ SQLite ในหน่วยความจำและ Label Studio จำลองเฉพาะในการทดสอบ ไม่แตะข้อมูลจริง |
| `replay_inference.py` | รันโมเดลจริงกับข้อมูลจริงของสถานีและเวลาที่ระบุ ไม่เขียนฐานข้อมูล |
| `cleanup_test_data.py` | แสดงรายการข้อมูลทดสอบที่ค้าง (บัญชี, bucket, สถานี `ST-TEST-*`, แถวพยากรณ์เก่า) และลบเมื่อสั่ง `--apply` แล้วพิมพ์ยืนยันเท่านั้น |
| `openapi_to_csv.py` | เขียนรายการ endpoint ลง `api_snapshot.csv` และ `api_snapshot.xlsx` |
| `samples/` | ไฟล์ GHI ตัวอย่าง (csv, xlsx) สำหรับสคริปต์ตรวจ |

```bash
docker exec fastapi sh -c 'cd /app && uv run --with aiosqlite --with httpx python scripts/check_ground_truth_flow.py'
```

## README ของโมดูล

[auth](api/auth/README.md) · [users](api/users/README.md) · [label_studio](api/label_studio/README.md) · [jobs](api/jobs/README.md) · [storage](api/storage/README.md) · [core](core/README.md) · [db](db/README.md)
