# Users Module (`backend/api/users`)

## Overview
มอดูล **Users** ทำหน้าที่ดู แก้ไข และลบบัญชีผู้ใช้ โดยมีระบบ Authorization ป้องกันไม่ให้ผู้ใช้ดู แก้ไข หรือลบข้อมูลของผู้อื่น (การสร้างบัญชีอยู่ที่มอดูล auth)

## Authorization & Security Rules
- **JWT Required**: ทุก Endpoints ในมอดูลนี้จำเป็นต้องส่ง Bearer Token ใน HTTP Header
- **Self-Management**: ผู้ใช้ที่ล็อกอินดู แก้ไข (PATCH) หรือลบ (DELETE) ได้เฉพาะบัญชีของตนเอง หากพยายามทำกับบัญชีของผู้อื่น ระบบจะตอบกลับเป็น `403 Forbidden`
- **Admin**: ดูรายชื่อผู้ใช้ทั้งหมด จัดการบัญชีของผู้อื่น และเปลี่ยน role ได้ ผู้ใช้ทั่วไปเปลี่ยน role ไม่ได้แม้เป็นบัญชีของตนเอง

## API Endpoints

| Method | Endpoint | Description | Auth Required |
| --- | --- | --- | --- |
| `GET` | `/api/users` | ดึงรายการผู้ใช้ทั้งหมดในระบบ | Yes (admin) |
| `GET` | `/api/users/{id}` | ดึงข้อมูลรายละเอียดของผู้ใช้ตาม ID | Yes (เจ้าของบัญชีหรือ admin) |
| `PATCH` | `/api/users/{id}` | อัปเดตข้อมูลผู้ใช้; เปลี่ยน role ได้เฉพาะ admin | Yes (เจ้าของบัญชีหรือ admin) |
| `DELETE` | `/api/users/{id}` | ลบบัญชีผู้ใช้งาน | Yes (เจ้าของบัญชีหรือ admin) |

## File Structure
- `router.py`: กำหนด API Routes สำหรับจัดการข้อมูลผู้ใช้ (`/api/users/...`)
- `controller.py`: รับข้อมูล Controller, ตรวจสอบ Authorization Token และสิทธิ์การจัดการข้อมูลผู้ใช้
- `schema.py`: Pydantic Models สำหรับ Request Update Payload และ User Response DTOs
