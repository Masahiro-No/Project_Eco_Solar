# Jobs Queue Module (`backend/api/jobs`)

## Overview
มอดูล **Jobs** ทำหน้าที่เป็น Job Producer ในระบบ Asynchronous Job Processing โดยการรับคำร้องขอสร้างงานเบื้องหลังส่งต่อไปยัง **Redis Queue** เพื่อให้ Worker Service ดึงงานไปประมวลผลต่อ

## Library & Infrastructure Used
- **`arq`**: Redis-based Asynchronous Job Queue Library สำหรับ Python
- **Redis**: ทำหน้าที่เป็น Message Broker สำหรับเก็บ Job Queue และสถานะของ Job

## Processing Flow
```text
1. Clientส่ง Request ไปยัง Backend
   └─ POST /api/jobs/enqueue (ระบุ function_name และ arguments)

2. Backend enqueues job ลง Redis
   └─ `arq` connection pool ส่ง Job ID เข้า Redis Queue

3. Worker Process ใน service/ คอยดึงงาน (Poll) จาก Redis
   └─ ดึง Job ไปประมวลผล Asynchronously

4. Client สามารถติดตามสถานะของ Job ได้
   └─ GET /api/jobs/{job_id} เพื่อดูสถานะและผลลัพธ์
```

## API Endpoints

| Method | Endpoint | Description | Request / Response |
| --- | --- | --- | --- |
| `POST` | `/api/jobs/enqueue` | ส่งงานเข้าสู่ Redis Job Queue | Body: `{ "function_name": "...", "args": [...] }` |
| `GET` | `/api/jobs/{job_id}` | ตรวจสอบสถานะและผลลัพธ์ของ Job ตาม Job ID | Return Job Status & Result |

## File Structure
- `router.py`: กำหนด HTTP Endpoints สำหรับจัดการ Jobs (`/api/jobs/...`)
- `controller.py`: รับ Request payload และส่งต่อคำสั่ง enqueue/get_job ให้กับ Service
- `service.py`: จัดการความเชื่อมโยงกับ Redis ผ่าน `arq.create_pool` เพื่อส่งงานและอ่านสถานะ Job
- `schema.py`: Pydantic Schemas สำหรับ Enqueue Job Request และ Job Status Response
