# SolarDSS — Solar Power Forecasting & Decision Support System

ระบบพยากรณ์กำลังผลิตไฟฟ้าจากแสงอาทิตย์ล่วงหน้า 3 ชั่วโมง (ทุก 10 นาที) และแนะนำการสำรองกำลังไฟฟ้าให้ผู้ควบคุมระบบ
ใช้ข้อมูลจริงทั้งหมด: สภาพอากาศจาก Open-Meteo, ภาพดาวเทียม Himawari Band 03 จาก NICT และค่า GHI ที่วัดจริงซึ่งผู้ดูแลอัปโหลดเป็นไฟล์
ไม่มีข้อมูลจำลองในระบบ ถ้าข้อมูลส่วนใดขาด หน้าจอจะแสดงว่าไม่มีข้อมูลแทนการแสดงค่าทดแทน

## ความสามารถ

- พยากรณ์ GHI และกำลังผลิตของแต่ละสถานีล่วงหน้า 3 ชั่วโมง ทุก 10 นาที พร้อมแถบความไม่แน่นอน
- รวมผลสองโมเดล: LSTM จากสภาพอากาศ และ ConvLSTM จากภาพดาวเทียม ด้วยน้ำหนักที่ลดลงตามระยะพยากรณ์
- บอกระดับการเตือน (ปกติ เฝ้าระวัง เตือน วิกฤต) และกำลังสำรองที่ควรเตรียม
- หน้าเว็บ: แดชบอร์ด พยากรณ์ของทั้งวันเทียบกับค่าวัดจริง ตัวเล่นภาพเมฆ ข้อมูลป้อนโมเดล การแจ้งเตือน และสถานี (ไทย / อังกฤษ ธีมสว่าง / มืด)
- ผู้ดูแลบันทึกค่า GHI ที่วัดจริงและตรวจภาพดาวเทียม ระบบ retrain ทั้งสองโมเดลจากข้อมูลนั้น และนำโมเดลใหม่ไปใช้เมื่อผ่านเกณฑ์เท่านั้น
- ดูการทำงานของระบบได้จาก Grafana (metric, log, trace)

## สถาปัตยกรรม

![การไหลของข้อมูลและโซน Public / Private ของ SolarDSS](diagrams/overview.png)

```text
Open-Meteo (สภาพอากาศ) + NICT Himawari (ภาพดาวเทียม)
  → ingestion-worker   ดึงข้อมูลทุก 10 นาที และเติมช่องที่ขาด
  → inference-worker   LSTM + ConvLSTM → รวม GHI → กำลังผลิต → ระดับการเตือน
  → PostgreSQL         ผลพยากรณ์ของแต่ละรอบ
  → API (FastAPI)      → หน้าเว็บ (Next.js) อ่านผลล่าสุดทุก 1 นาที
```

รายละเอียดของแต่ละบริการ โซนการเข้าถึง และหน้าเว็บอยู่ใน [docs/architecture.md](docs/architecture.md)

## โมเดล

| | LSTM | ConvLSTM |
|---|---|---|
| ข้อมูลเข้า | สภาพอากาศย้อนหลัง 36 ช่อง ช่องละ 10 นาที (6 ชั่วโมง) 16 ฟีเจอร์ | ภาพดาวเทียมรอบสถานี 12 เฟรมล่าสุด (64×64 พิกเซล) |
| ผลลัพธ์ | GHI 18 ก้าว (3 ชั่วโมง) | ภาพ 18 เฟรมถัดไป (3 ชั่วโมง) |
| หน้าที่ | แนวโน้มของแสงตามสภาพอากาศ | เมฆที่เห็นจริงและที่กำลังจะมารอบสถานี |

ภาพดาวเทียมถูกแปลงเป็นดัชนีฟ้าใส k แล้วรวมกับผลของ LSTM:

```
GHI_blend(t) = w(t) · k(t) · GHI_clearsky(t) + (1 − w(t)) · GHI_lstm(t)      w(t) = 0.9 · exp(−t / 102)
```

ช่วงใกล้เชื่อภาพดาวเทียมมาก ช่วงไกลเชื่อ LSTM มาก จากนั้นคิดกำลังผลิต `P = พื้นที่แผง × ประสิทธิภาพ × GHI ÷ 1000` เทียบกับเป้า แล้วเลือกระดับการเตือน
รายละเอียด: [โมเดลและการรวมผล](docs/models.md) · [calibration ของภาพดาวเทียม](docs/calibration.md) · [กฎการตัดสินใจ](docs/decision.md)

## แหล่งข้อมูล

| ข้อมูล | แหล่ง | ใช้ทำอะไร |
|---|---|---|
| สภาพอากาศ (GHI, DNI, DHI, อุณหภูมิ, ความชื้น, ความกดอากาศ, ลม, เมฆ) | Open-Meteo | ข้อมูลป้อน LSTM |
| ภาพดาวเทียม Himawari Band 03 | NICT | ข้อมูลป้อน ConvLSTM และวัดเมฆรอบสถานี |
| GHI ที่วัดจริง | ผู้ดูแลกรอกหรืออัปโหลดไฟล์ CSV / XLSX | เทียบความแม่น retrain LSTM และ calibration ของภาพดาวเทียม |
| NSRDB หาดใหญ่ ปี 2016–2020 | ชุดข้อมูลเทรนตั้งต้น | เทรน LSTM รุ่นแรก |

## เทคโนโลยี

| ส่วน | ที่ใช้ |
|---|---|
| หน้าเว็บ | Next.js 15, TypeScript, Tailwind CSS, Recharts, next-intl, Leaflet |
| API | FastAPI, SQLAlchemy (async), Pydantic, PostgreSQL |
| งานเบื้องหลัง | ARQ บน Redis: worker สามตัว (ingestion, inference, trainer) |
| โมเดล | PyTorch (เทรน), ONNX Runtime (ใช้งาน), MLflow (ประวัติ retrain) |
| ที่เก็บไฟล์และค่าวัดจริง | MinIO, Label Studio |
| ดูการทำงาน | OpenTelemetry, Prometheus, Loki, Tempo, Grafana |
| การรัน | Docker Compose |

## โครงสร้างโปรเจกต์

```text
backend/         REST API (FastAPI) และสคริปต์ตรวจระบบ
service/         worker ทั้งสาม การเทรนและ retrain และชุดทดสอบ
frontend/        หน้าเว็บ (Next.js)
model/           ไฟล์โมเดลที่ใช้งานอยู่ และค่า calibration
observability/   ไฟล์ตั้งค่าของ Prometheus, Loki, Tempo, OTel collector, Grafana
diagrams/        แผนภาพของระบบ
docs/            เอกสารเชิงลึก
compose.yml      ทุกบริการ
PLAN.md          แผนงาน ข้อกำหนด และสถานะรายข้อ
```

ทุกโฟลเดอร์มี README ของตัวเอง เริ่มได้จาก [backend](backend/README.md), [service](service/README.md), [frontend](frontend/README.md), [model](model/README.md) และ [observability](observability/README.md)

## เริ่มใช้งาน

ต้องมี Docker Desktop และอินเทอร์เน็ต (ระบบดึงสภาพอากาศจาก Open-Meteo และภาพดาวเทียมจาก NICT) ไม่ต้องมี GPU การ build ครั้งแรกใช้เวลานานเพราะ image ของ worker มีขนาดใหญ่

**1. สร้างไฟล์ตั้งค่าสองไฟล์** (ทั้งสองไฟล์ไม่อยู่ใน git ทุกเครื่องต้องสร้างเอง)

```bash
cp .env.example .env
```

```bash
cp backend/.env.example backend/.env
```

**2. แก้ `backend/.env`** ใส่ `jwt_secret_key` เป็นข้อความสุ่มของเครื่องนี้ อย่างน้อย 16 ตัวอักษร (ใช้เซ็น token ตอนล็อกอิน ถ้าเว้นว่าง API จะไม่เริ่มทำงาน) ค่าอื่นในไฟล์ตรงกับ `compose.yml` อยู่แล้ว สร้างข้อความสุ่มได้ด้วย

```bash
docker run --rm python:3.12-slim python -c "import secrets; print(secrets.token_urlsafe(48))"
```

**3. แก้ `.env`** ใส่ `ADMIN_PASSWORD` (อย่างน้อย 8 ตัว) ค่าอื่นดูหัวข้อ [การตั้งค่า](#การตั้งค่า) ส่วน `LABEL_STUDIO_API_KEY` เว้นไว้ก่อน

**4. เปิดระบบ**

```bash
docker compose up -d
```

เปิด http://localhost:3000 แล้วล็อกอินด้วย `ADMIN_EMAIL` และ `ADMIN_PASSWORD` ในเครื่องใหม่ระบบจะดึงสภาพอากาศย้อนหลัง 2 วันและภาพดาวเทียม 12 เฟรมล่าสุดเอง ผลพยากรณ์แรกมาภายในไม่กี่นาทีหลัง worker เริ่มทำงาน จากนั้นทุก 10 นาที รายการ API ดูได้ที่ http://localhost:8000

**5. ต่อ Label Studio** (ใช้กับหน้าบันทึกค่าวัดจริงและการ retrain LSTM การพยากรณ์ไม่ต้องใช้)

เปิด http://localhost:8080 สมัครบัญชี แล้วคัดลอก Personal Access Token จาก Account & Settings มาใส่ที่ `LABEL_STUDIO_API_KEY` ใน `.env` จากนั้น

```bash
docker compose up -d api trainer-worker
```

**สิ่งที่ไม่ได้มากับ git** ค่า GHI ที่วัดจริง ประวัติพยากรณ์ และประวัติ retrain อยู่ในฐานข้อมูล Label Studio และ MLflow ของเครื่องที่รัน เครื่องใหม่จึงเริ่มจากว่าง ส่วนไฟล์โมเดลทั้งสองตัวและค่า calibration อยู่ใน `model/` และมากับ git

## การตั้งค่า

| ไฟล์ | ตัวแปร | ความหมาย |
|---|---|---|
| `.env` | `ADMIN_EMAIL`, `ADMIN_PASSWORD` | บัญชีผู้ดูแล สร้างตอน API เริ่มทำงาน ถ้าจะเปลี่ยนรหัสผ่าน ให้แก้ที่นี่แล้วสั่ง `docker compose up -d api` |
| `.env` | `OPERATOR_PASSWORD` | ไม่บังคับ ถ้าตั้งไว้ บัญชี `operator@solardss.io` จะถูกสร้างหรือเปลี่ยนรหัสผ่านตอน API เริ่มทำงาน ถ้าไม่ตั้ง ระบบไม่สร้างบัญชีนี้ |
| `.env` | `ENABLE_RETRAIN` | `true` เพื่อให้ retrain อัตโนมัติ (ค่าเดียวใช้กับทั้งสองโมเดล) |
| `.env` | `LABEL_STUDIO_API_KEY` | token ของ Label Studio ในเครื่องนี้ |
| `backend/.env` | `jwt_secret_key` | ข้อความลับที่ใช้เซ็น token ตอนล็อกอิน |

ค่าที่ใช้ในการพยากรณ์ (น้ำหนักรวมผล เกณฑ์เมฆ เป้าตามแดด กติกาเมื่อภาพขาด) ปรับได้ที่ `environment` ของ `inference-worker` ใน `compose.yml` ความหมายของแต่ละค่าอยู่ใน [docs/models.md](docs/models.md) และ [docs/missing-data.md](docs/missing-data.md)

## บทบาทผู้ใช้

| บทบาท | ได้มาอย่างไร | ทำอะไรได้ |
|---|---|---|
| `operator` | สมัครเองที่แท็บ Sign Up ของหน้า login (ได้สิทธิ์นี้เสมอ) | ดูแดชบอร์ด พยากรณ์ ข้อมูลป้อนโมเดล การตัดสินใจ การแจ้งเตือน สถานี และคู่มือ |
| `admin` | บัญชีจาก `.env` หรือ admin คนอื่นให้สิทธิ์ | ทุกอย่างของ operator และบันทึกค่าวัดจริง ตรวจภาพดาวเทียม ดูสถานะ retrain ตั้งค่าสถานี และใช้ API ของผู้ดูแล |

API ตรวจ token และ role ทุกคำขอ ไม่มีรหัสผ่านตั้งต้นในโค้ด บริการภายใน (ฐานข้อมูล Redis MinIO Label Studio MLflow Grafana) เปิดเฉพาะจากเครื่องที่รัน ดู [docs/architecture.md](docs/architecture.md)

## การพัฒนา

| ส่วนที่แก้ | คำสั่ง |
|---|---|
| `backend/` | `docker compose restart api ingestion-worker` (ingestion-worker ใช้โค้ด backend ตอนสร้างข้อมูลป้อนโมเดลและบันทึกผล) |
| `service/workers/`, `service/training/` | `docker compose restart ingestion-worker inference-worker trainer-worker` (อย่า restart `trainer-worker` ระหว่างที่กำลังเทรน) |
| `frontend/` | `docker compose up -d --build --no-deps frontend` |
| ค่าใน `compose.yml` หรือ `.env` | `docker compose up -d <service>` |

## การทดสอบ

```bash
docker exec trainer-worker sh -c 'cd /workspace && pip install -q pytest && python -m pytest service/tests -q'
```

```bash
docker exec fastapi sh -c 'cd /app && uv run --with aiosqlite --with httpx python scripts/check_ground_truth_flow.py'
```

ชุดแรกตรวจ worker และการ retrain ชุดที่สองตรวจฝั่ง API ทั้งสองชุดไม่แตะข้อมูลจริง คำสั่งอื่น (การเทียบสูตรสองฝั่ง การรันโมเดลย้อนหลัง การลบข้อมูลทดสอบ) อยู่ใน [docs/testing.md](docs/testing.md)

## เอกสาร

- [สถาปัตยกรรม](docs/architecture.md) — ทางเดินของข้อมูล บริการ โซนการเข้าถึง
- [โมเดลและการรวมผล](docs/models.md) — LSTM, ConvLSTM, สมการ, แถบความไม่แน่นอน
- [Calibration ของภาพดาวเทียม](docs/calibration.md) — ค่า a, b วิธี fit และการตรวจกับแต่ละสถานี
- [กฎการตัดสินใจ](docs/decision.md) — เป้าตามแดด ระดับการเตือน กำลังสำรอง
- [เมื่อข้อมูลขาด](docs/missing-data.md) — กติกาของภาพดาวเทียมและสภาพอากาศ
- [การ retrain](docs/retraining.md) — ขั้นตอน เกณฑ์รับโมเดลใหม่ และบทบาทของผู้ดูแล
- [ผลการทดลอง](docs/experiments.md) — ตัวเลขที่วัดได้และเหตุผลของค่าที่เลือก
- [การทดสอบ](docs/testing.md) · [ข้อจำกัด](docs/limitations.md) · [เนื้อหารายวิชาที่ใช้](docs/course-topics.md) · [แผนงานและสถานะ](PLAN.md)

## ข้อจำกัด

- LSTM เทรนจาก NSRDB หาดใหญ่ ส่วนข้อมูลที่ป้อนตอนใช้งานมาจาก Open-Meteo ซึ่งเป็นค่าจากแบบจำลอง ไม่ใช่เครื่องวัด
- ค่า GHI ที่วัดจริงมีเฉพาะบางสถานีและบางวัน ตัวเลขความแม่นจึงมาจากข้อมูลไม่กี่วัน
- สูตรแปลงภาพดาวเทียมเป็นแสง fit จากสถานีเดียว แล้วใช้กับทุกสถานี สถานีที่ยังไม่มีค่าวัดจริงยังไม่ได้ตรวจ
- 1 พิกเซลของภาพกว้าง 11–15 กม. ขณะที่เครื่องวัดเป็นจุดเดียว ความสัมพันธ์ระหว่างภาพกับแสงที่พื้นจึงยังหลวม
- Himawari ไม่สแกนเวลา 09:40 น. ของทุกวัน ช่วงสายระบบจึงใช้ชุดภาพที่เว้นรอบนั้น
- ค่าที่ตั้งไว้ (น้ำหนักรวมผล เกณฑ์เมฆ เป้าตามแดด) เป็นค่าตั้งต้น และผลของการ retrain วัดจากข้อมูล 4–6 วัน

รายละเอียดและตัวเลขของแต่ละข้ออยู่ใน [docs/limitations.md](docs/limitations.md)
