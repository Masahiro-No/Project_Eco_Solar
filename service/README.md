# Worker Service (`service`)

## Overview

มอดูล **Worker Service** เป็นระบบประมวลผลฉากหลัง (Background Worker Process) ที่ถูกแยก Process การทำงานอิสระออกจาก Central Backend API Server โดยรับหน้าที่คอยดึงงาน (Job Task) ที่ถูกส่งเข้ามายัง **Redis Queue** ไปประมวลผลแบบ Asynchronous

## Architecture & How It Works

- **Process Isolation**: ทำงานเป็นกระบวนการแยกส่วน (Separate Process) ไม่บล็อก Main Thread หรือ HTTP Server ของ FastAPI
- **Redis Queue Consumer**: เชื่อมต่อเข้ากับ Redis Server และคอยรอรับ Job Functions ที่ลงทะเบียนไว้ใน `WorkerSettings`

```text
[ Central Backend ] ──(Enqueue Job)──> [ Redis Queue ]
                                              │
                                              ▼ (Poll & Consume Job)
                                     [ ARQ Worker Process ]
                                       └─ Executing worker functions
                                          (e.g., simple_work)
```

## File Structure

- `main.py`: กำหนดค่า `WorkerSettings` ลงทะเบียนฟังก์ชันการทำงาน (`functions`) และตั้งค่า Redis connection (`RedisSettings`)
- `workers/simple_worker.py`: นิยามฟังก์ชันประมวลผลงานเบื้องหลัง เช่น `simple_work()`

## How to Run Worker

ติดตั้ง dependencies และเริ่มรัน ARQ Worker Process:

```bash
uv sync
arq service.main.WorkerSettings
```

## How to Scale Workers

เนื่องจาก Worker Service แยกตัวออกจาก API Server อย่างอิสระ การขยายขีดความสามารถ (Scaling) สามารถทำได้อย่างง่ายดาย:

- **Horizontal Scaling**: รันคำสั่ง `arq service.main.WorkerSettings` เพิ่มเติมในหลายๆ Terminal, Process หรือสั่งงานผ่าน Docker Containers / Kubernetes pods หลาย Instance พร้อมกัน
- ARQ จะทำหน้าที่กระจายงาน (Work Distribution) จาก Redis Queue ไปยัง Worker Instances ที่ว่างอยู่อย่างสม่ำเสมออัตโนมัติ (Competing Consumers Pattern)
