# Auth Module (`backend/api/auth`)

## Overview
มอดูล **Auth** จัดการการลงทะเบียนผู้ใช้ การเข้าสู่ระบบ การแฮชรหัสผ่านอย่างปลอดภัย การออก/ตรวจสอบ **JWT (JSON Web Token)** และ role ของผู้ใช้ (`operator`, `admin`) ที่มอดูลอื่นใช้ตรวจสิทธิ์

## Authentication Flow
```text
1. User Register (POST /api/auth/register)
   └─ Hash password ด้วย pwdlib (Argon2) → บันทึกข้อมูลลง PostgreSQL Database

2. User Login (POST /api/auth/login)
   └─ ตรวจสอบ Credentials → สร้าง Bearer JWT Access Token ส่งกลับให้ Client

3. Access Protected Routes (เช่น GET /api/auth/me)
   └─ Client แนบ Header `Authorization: Bearer <token>` → Verify JWT Token
```

## API Endpoints

| Method | Endpoint | Description | Auth Required |
| --- | --- | --- | --- |
| `POST` | `/api/auth/register` | สมัครสมาชิกใหม่ (ส่ง email และ password อย่างน้อย 8 ตัว) ได้ role `operator` เสมอ | No |
| `POST` | `/api/auth/login` | เข้าสู่ระบบและขอรับ JWT Access Token | No |
| `GET` | `/api/auth/me` | ดึงข้อมูลผู้ใช้ปัจจุบันที่ล็อกอินอยู่ | Yes (Bearer Token) |

## Roles
- **`operator`**: ได้จากการสมัครเอง อ่านข้อมูลของระบบได้ (โซน Public) บัญชี `operator@solardss.io` ถูกสร้างเมื่อตั้ง `OPERATOR_PASSWORD` ใน `.env` เท่านั้น ไม่มีรหัสผ่านตั้งต้นในโค้ด
- **`admin`**: สร้างหรืออัปเดตรหัสผ่านตอน API เริ่มทำงาน จาก `ADMIN_EMAIL` และ `ADMIN_PASSWORD` ใน `.env` ไม่มีทางสมัครเป็น admin ผ่าน API; admin เปลี่ยน role ของผู้อื่นได้ที่ `PATCH /api/users/{id}`
- `get_current_user` (ต้องล็อกอิน) และ `require_admin` (ต้องเป็น admin) ใน `service.py` คือ dependency ที่ controller ของมอดูลอื่นใช้ ไม่มี token ได้ 401 role ไม่ถึงได้ 403

## Tech Stack & Libraries Used
- **`pyjwt`**: ใช้สำหรับ Encoding / Decoding JSON Web Tokens
- **`pwdlib`** (พร้อมด้วย **Argon2** backend): ใช้สำหรับ Password Hashing และ Verification อย่างปลอดภัย

## File Structure & Layer Responsibilities
- `router.py`: กำหนด URL Routes และ HTTP Endpoints (`/api/auth/...`)
- `controller.py`: รับ Request Payload, ตรวจสอบ Validation และส่งต่อให้ Service
- `service.py`: บิสซิเนสลอจิก เช่น การตรวจสอบรหัสผ่าน การสร้าง JWT Token
- `repository.py`: ติดต่อกับ PostgreSQL Database ในการค้นหาและสร้าง User record
- `schema.py`: Pydantic Models สำหรับ Request และ Response DTOs
- `model.py`: SQLAlchemy ORM Model สำหรับตาราง `users`
