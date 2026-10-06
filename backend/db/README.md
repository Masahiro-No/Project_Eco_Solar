# Database Module (`backend/db`)

## Overview
มอดูล **Database** จัดการการเชื่อมต่อฐานข้อมูล **PostgreSQL** แบบ Asynchronous สำหรับ FastAPI Backend Application โดยดูแล lifecycle ของ Session และการสร้าง Database Schema อัตโนมัติ

## Tech Stack & Drivers
- **SQLAlchemy (Async)**: ORM (Object Relational Mapper) หลักสำหรับจัดการโมเดลข้อมูลและ query
- **`asyncpg`**: High-performance Async Database Driver สำหรับ PostgreSQL

## Key Features
- **Async Database Connection Pool**: สร้าง `AsyncEngine` และ `async_sessionmaker` เพื่อรองรับการทำงานแบบ non-blocking I/O
- **Automatic Schema Creation**: ฟังก์ชัน `create_database_schema()` จะรันขึ้นมาตอนแอปพลิเคชันเริ่มทำงาน (Lifespan Event ใน `main.py`) เพื่อสร้างตารางฐานข้อมูลที่ถูกนิยามใน SQLAlchemy Base models โดยอัตโนมัติ และเพิ่มคอลัมน์ที่เพิ่มมาภายหลังให้ตาราง `predictions` และ `users` ที่มีอยู่แล้ว (ไม่ใช้ migration tool)
- **Seed**: `seed_default_stations()` สร้างสถานีตั้งต้น 5 แห่ง และบัญชีจากค่าใน `.env` เท่านั้น: admin จาก `ADMIN_EMAIL` / `ADMIN_PASSWORD` และ operator จาก `OPERATOR_PASSWORD` ถ้าไม่ได้ตั้งรหัสผ่าน บัญชีนั้นไม่ถูกสร้าง ไม่มีรหัสผ่านตั้งต้นในโค้ด ถ้ารหัสผ่านใน `.env` เปลี่ยน รหัสผ่านของบัญชีจะถูกเปลี่ยนตามตอน API เริ่มทำงาน
- **กฎกันแถวซ้ำ**: `weather_history` (สถานี, เวลา, แหล่งข้อมูล) และ `satellite_frames` (สถานี, เวลาสแกน) มีกฎ unique ซึ่ง `_ensure_unique_rules()` เพิ่มให้ฐานข้อมูลเดิมตอนเริ่ม ถ้ามีแถวที่ขัดกฎอยู่แล้ว API ยังเริ่มได้และเขียนคำเตือน
- **การแก้โครงสร้าง**: `create_all()` ไม่แก้ตารางที่มีอยู่ คอลัมน์และกฎที่เพิ่มภายหลังจึงเพิ่มด้วยฟังก์ชัน `_ensure_*` ในไฟล์นี้ ไม่มีเครื่องมือ migration
- **ตาราง**: `users`, `stations`, `weather_history`, `satellite_frames`, `predictions`, `satellite_frame_reviews` (ฐานข้อมูลเดียวกันนี้มีตารางของ Label Studio และ MLflow อยู่ด้วย)

## File Structure
- `database.py`:
  - นิยาม `Base` declarative class สำหรับ SQLAlchemy Models
  - สร้าง `engine` จาก `settings.DATABASE_URL` (แบบ `postgresql+asyncpg://`)
  - ให้บริการ `get_db_session()` dependency generator สำหรับฉีด Database Session (`AsyncSession`) เข้าไปใน FastAPI endpoints
  - ให้บริการ `create_database_schema()` สำหรับสร้าง Database tables
