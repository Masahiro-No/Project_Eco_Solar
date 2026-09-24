# Backend Service - FastAPI Central API Server

## Overview

ส่วนของ **Backend** ทำหน้าที่เป็น Central API Server พัฒนาด้วย **FastAPI** เพื่อให้บริการ RESTful APIs แก่ Client และแอปพลิเคชันอื่น โดยมีการเชื่อมต่อกับฐานข้อมูล PostgreSQL, MinIO Object Storage, Label Studio และระบบ ARQ Redis Job Queue

## Architecture Pattern

สถาปัตยกรรมภายใน Backend ใช้รูปแบบ **Feature-Driven Modular Architecture** จัดโครงสร้าง code ตาม feature (ฟีเจอร์) และในแต่ละ feature จะแยกเป็นรูปแบบ **_Layer Architecture_** เพื่อแยกความรับผิดชอบอย่างชัดเจน (Separation of Concerns):

```text
[ Client ]
    │
    ▼
┌──────────────┐
│    Router    │  (รับ request, กำหนด URL endpoints & HTTP Methods)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Controller  │  (จัดการ Request Validation, Response Models, HTTP Status Codes)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Service    │  (ประมวลผล Business Logic หลัก และเรียกใช้ Third-party SDKs)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Repository  │  (ติดต่อกับ Database / Persistence Layer ผ่าน SQLAlchemy)
└──────────────┘
```

## Directory Structure

```text
backend/
├── api/
│   ├── auth/           # Authentication module (JWT, Register, Login)
│   ├── users/          # Users management module (CRUD)
│   ├── storage/        # MinIO Storage integration module
│   ├── label_studio/   # Label Studio Integration module
│   └── jobs/           # ARQ Task Queue Producer module
├── core/               # Environment configuration settings (pydantic-settings)
├── db/                 # Database initialization and connection (SQLAlchemy Async)
├── scripts/            # Helper scripts (e.g. export API docs to CSV)
└── main.py             # FastAPI entrypoint application
```

## API Modules Overview

| Module           | Path                                           | Description                                                |
| ---------------- | ---------------------------------------------- | ---------------------------------------------------------- |
| **Auth**         | [api/auth](api/auth/README.md)                 | ระบบยืนยันตัวตน (Register, Login, JWT Authentication)      |
| **Users**        | [api/users](api/users/README.md)               | ระบบจัดการผู้ใช้งาน (CRUD Users, Self-Management)          |
| **Storage**      | [api/storage](api/storage/README.md)           | ระบบจัดการ Object Storage (MinIO Buckets, Upload/Download) |
| **Label Studio** | [api/label_studio](api/label_studio/README.md) | ระบบเชื่อมต่อ Label Studio Projects & Tasks                |
| **Jobs**         | [api/jobs](api/jobs/README.md)                 | ระบบส่ง Background Job ไปยัง Redis Queue                   |

## How to Run

ติดตั้ง dependencies และเริ่มรันพัฒนาในรูปแบบ Hot-Reload:

```bash
uv sync
uv run uvicorn main:app --reload
```

## Interactive API Documentation

เมื่อรัน API Server เรียบร้อย สามารถเข้าใช้งาน API Document ในรูปแบบต่างๆ ได้ที่:

- **Swagger UI**: `/` (หรือ `/docs`)
- **ReDoc**: `/redoc`
- **OpenAPI Schema (JSON)**: `/openapi.json`

## Exporting API Endpoints

สามารถส่งออกรายการ API ทั้งหมดของโปรเจกต์ให้อยู่ในรูปแบบไฟล์ CSV ได้โดยการรันสคริปต์:

```bash
python scripts/openapi_to_csv.py
```

_(ไฟล์ CSV จะถูกบันทึกที่ `api_list.csv`)_
