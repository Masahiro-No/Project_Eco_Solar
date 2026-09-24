# Core Configuration Module (`backend/core`)

## Overview

มอดูล **Core** รับหน้าที่จัดการการตั้งค่าและ Environment Variables ทั้งหมดของระบบ Central Backend API Server โดยรับข้อมูลคอนฟิกจากไฟล์ `.env` หรือ Environment Variables ของระบบ

## Configuration Framework

- **`pydantic-settings`**: ใช้สำหรับ Type-safe Configuration Management ตรวจสอบชนิดข้อมูลและความถูกต้องของตัวแปรสภาพแวดล้อมโดยอัตโนมัติ

## Main Configuration Settings

ระบบมีการจัดการตั้งค่าครอบคลุมส่วนประกอบสำคัญดังนี้:

| Category           | Configuration Variables                                                  | Description                                                     |
| ------------------ | ------------------------------------------------------------------------ | --------------------------------------------------------------- |
| **Database**       | `DATABASE_URL`                                                           | PostgreSQL Async Connection String (`postgresql+asyncpg://...`) |
| **Security / JWT** | `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`         | Secret key และระยะเวลาหมดอายุของ JWT Token                      |
| **MinIO Storage**  | `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_SECURE` | การเชื่อมต่อกับ MinIO Object Storage                            |
| **Label Studio**   | `LABEL_STUDIO_URL`, `LABEL_STUDIO_API_KEY`                               | URL และ API Key สำหรับสิทธิ์เชื่อมต่อ Label Studio              |
| **Redis / Worker** | `REDIS_HOST`, `REDIS_PORT`                                               | การเชื่อมต่อ Redis Server สำหรับ Job Queue                      |

## File Structure

- `config.py`: นิยามคลาส `Settings` (สืบทอดจาก `BaseSettings`) พร้อมโหลดตัวแปรจากไฟล์ `.env` และสร้าง Singleton instance `settings` ให้มอดูลอื่นเรียกใช้ได้ทันที
