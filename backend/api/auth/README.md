# Auth Module (`backend/api/auth`)

## Overview
มอดูล **Auth** จัดการการลงทะเบียนผู้ใช้ การเข้าสู่ระบบ การแฮชรหัสผ่านอย่างปลอดภัย และการออก/ตรวจสอบ **JWT (JSON Web Token)** เพื่อใช้สิทธิ์เข้าถึง Protected Endpoints ต่างๆ ภายในระบบ

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
| `POST` | `/api/auth/register` | สมัครสมาชิกใหม่ (ส่ง username, email, password) | No |
| `POST` | `/api/auth/login` | เข้าสู่ระบบและขอรับ JWT Access Token | No |
| `GET` | `/api/auth/me` | ดึงข้อมูลผู้ใช้ปัจจุบันที่ล็อกอินอยู่ | Yes (Bearer Token) |

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
