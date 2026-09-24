# Users Module (`backend/api/users`)

## Overview
มอดูล **Users** ทำหน้าที่จัดการข้อมูลผู้ใช้งานแบบ CRUD (Create, Read, Update, Delete) ในระบบ โดยมีระบบ Authorization ป้องกันไม่ให้ผู้ใช้แก้ไขหรือลบข้อมูลของผู้อื่น

## Authorization & Security Rules
- **JWT Required**: ทุก Endpoints ในมอดูลนี้จำเป็นต้องส่ง Bearer Token ใน HTTP Header
- **Self-Management Only**: ผู้ใช้ที่ล็อกอินมีสิทธิ์แก้ไข (PATCH) หรือลบ (DELETE) เฉพาะบัญชีของตนเองเท่านั้น หากพยายามแก้ไขข้อมูลของผู้ใช้อื่น ระบบจะตอบกลับเป็น `403 Forbidden`

## API Endpoints

| Method | Endpoint | Description | Auth Required |
| --- | --- | --- | --- |
| `GET` | `/api/users` | ดึงรายการผู้ใช้ทั้งหมดในระบบ | Yes |
| `GET` | `/api/users/{id}` | ดึงข้อมูลรายละเอียดของผู้ใช้ตาม ID | Yes |
| `PATCH` | `/api/users/{id}` | อัปเดตข้อมูลผู้ใช้ (เฉพาะบัญชีของตนเอง) | Yes |
| `DELETE` | `/api/users/{id}` | ลบบัญชีผู้ใช้งาน (เฉพาะบัญชีของตนเอง) | Yes |

## File Structure
- `router.py`: กำหนด API Routes สำหรับจัดการข้อมูลผู้ใช้ (`/api/users/...`)
- `controller.py`: รับข้อมูล Controller, ตรวจสอบ Authorization Token และสิทธิ์การจัดการข้อมูลผู้ใช้
- `schema.py`: Pydantic Models สำหรับ Request Update Payload และ User Response DTOs
