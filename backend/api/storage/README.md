# Storage Module (`backend/api/storage`)

## Overview
มอดูล **Storage** ทำหน้าที่เชื่อมต่อกับ **MinIO Object Storage** (S3-Compatible) เพื่อจัดการ Buckets, การอัปโหลดไฟล์ และดาวน์โหลดไฟล์มัลติมีเดียต่างๆ ของระบบ AI Ecosystem

## Library Used
- **`minio`**: Official Python SDK สำหรับจัดการ MinIO Server (Bucket Creation, Object Put/Get, Bucket Versioning)

## API Endpoints

| Method | Endpoint | Description | Request Format | Response Format |
| --- | --- | --- | --- | --- |
| `GET` | `/api/storage/buckets` | ดึงรายการ Buckets ทั้งหมดที่มีใน MinIO | - | JSON List |
| `POST` | `/api/storage/buckets` | สร้าง Bucket ใหม่ใน MinIO | JSON Body | JSON Message |
| `POST` | `/api/storage/upload` | อัปโหลดไฟล์ไปยัง MinIO Bucket | `multipart/form-data` | JSON Metadata |
| `GET` | `/api/storage/download/{bucket}/{object}` | ดาวน์โหลดไฟล์จาก MinIO | Path Params | `StreamingResponse` |
| `PUT` | `/api/storage/buckets/{bucket}/versioning` | เปิด/ปิดการใช้งาน Object Versioning | JSON Body | JSON Message |

## File Upload & Download Details
- **File Upload (`POST /api/storage/upload`)**: รับไฟล์ผ่าน HTTP Request ในรูปแบบ `multipart/form-data` (พร้อมระบุ target bucket) และส่งไฟล์เข้าสู่ MinIO Object Storage
- **File Download (`GET /api/storage/download/{bucket}/{object}`)**: อ่านไฟล์จาก MinIO ในลักษณะ Data Stream และส่งกลับให้ Client ผ่าน FastAPI `StreamingResponse` ช่วยประหยัด Memory ในการส่งไฟล์ขนาดใหญ่

## File Structure
- `router.py`: กำหนด API Endpoints สำหรับบริการจัดเก็บไฟล์ (`/api/storage/...`)
- `controller.py`: รับ Request payload, ข้อมูลอัปโหลดไฟล์ `UploadFile` และเรียกใช้ Storage Service
- `service.py`: ห่อหุ้มคำสั่งเรียกใช้ `minio` Python SDK ในการติดต่อกับ MinIO Server
- `schema.py`: Pydantic Schemas สำหรับ Bucket Request/Response และ Versioning configuration
