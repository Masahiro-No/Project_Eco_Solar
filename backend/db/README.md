# Database Module (`backend/db`)

## Overview
มอดูล **Database** จัดการการเชื่อมต่อฐานข้อมูล **PostgreSQL** แบบ Asynchronous สำหรับ FastAPI Backend Application โดยดูแล lifecycle ของ Session และการสร้าง Database Schema อัตโนมัติ

## Tech Stack & Drivers
- **SQLAlchemy (Async)**: ORM (Object Relational Mapper) หลักสำหรับจัดการโมเดลข้อมูลและ query
- **`asyncpg`**: High-performance Async Database Driver สำหรับ PostgreSQL

## Key Features
- **Async Database Connection Pool**: สร้าง `AsyncEngine` และ `async_sessionmaker` เพื่อรองรับการทำงานแบบ non-blocking I/O
- **Automatic Schema Creation**: ฟังก์ชัน `create_database_schema()` จะรันขึ้นมาตอนแอปพลิเคชันเริ่มทำงาน (Lifespan Event ใน `main.py`) เพื่อสร้างตารางฐานข้อมูลที่ถูกนิยามใน SQLAlchemy Base models โดยอัตโนมัติ และเพิ่มคอลัมน์ที่เพิ่มมาภายหลังให้ตาราง `predictions` และ `users` ที่มีอยู่แล้ว (ไม่ใช้ migration tool)
- **Seed**: `seed_default_stations()` สร้างสถานีตั้งต้น 5 แห่ง บัญชี operator ตั้งต้น และบัญชี admin จาก `ADMIN_EMAIL` / `ADMIN_PASSWORD` เมื่อยังไม่มี ไม่ seed ค่าพยากรณ์หรือข้อมูลสภาพอากาศ
- **ตาราง**: `users`, `stations`, `weather_history`, `satellite_frames`, `predictions`, `satellite_frame_reviews` (ฐานข้อมูลเดียวกันนี้มีตารางของ Label Studio และ MLflow อยู่ด้วย)

## File Structure
- `database.py`:
  - นิยาม `Base` declarative class สำหรับ SQLAlchemy Models
  - สร้าง `engine` จาก `settings.DATABASE_URL` (แบบ `postgresql+asyncpg://`)
  - ให้บริการ `get_db_session()` dependency generator สำหรับฉีด Database Session (`AsyncSession`) เข้าไปใน FastAPI endpoints
  - ให้บริการ `create_database_schema()` สำหรับสร้าง Database tables
