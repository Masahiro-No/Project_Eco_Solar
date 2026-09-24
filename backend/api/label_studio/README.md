# Label Studio Module (`backend/api/label_studio`)

## Overview
มอดูล **Label Studio** ทำหน้าที่เป็นตัวกลางในการเชื่อมต่อระหว่าง Central Backend API Server กับ **Label Studio Platform** เพื่อจัดการโปรเจกต์กำกับข้อมูล (Data Annotation Projects) และงานสำหรับกำกับข้อมูล (Tasks)

## Library Used
- **`label-studio-sdk`**: Official Python Client Library สำหรับจัดการ Label Studio API

## API Endpoints

| Method | Endpoint | Description | Request / Response |
| --- | --- | --- | --- |
| `GET` | `/api/label-studio/projects` | ดึงรายการ Projects ทั้งหมดใน Label Studio | Return JSON List |
| `POST` | `/api/label-studio/projects` | สร้าง Project ใหม่ใน Label Studio | JSON Payload (title, description) |
| `GET` | `/api/label-studio/projects/{id}/tasks` | ดึงรายการ Tasks ทั้งหมดใน Project ตาม ID | Return JSON List |
| `POST` | `/api/label-studio/projects/{id}/tasks` | เพิ่ม Task กำกับข้อมูลใหม่เข้าไปใน Project | JSON Payload (data payload) |

## File Structure
- `router.py`: กำหนด HTTP Endpoints สำหรับ Label Studio (`/api/label-studio/...`)
- `controller.py`: จัดการ Request Validation และส่งต่อคำสั่งให้ Service
- `service.py`: เรียกใช้ `label-studio-sdk` ในการติดต่อกับ Label Studio Server Instance
- `schema.py`: Pydantic Schemas สำหรับ Project และ Task Data Models
