import sys
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler

# 1. จัดการโฟลเดอร์สำหรับเก็บ Log (ถอยกลับ 3 ระดับไปที่ backend)
# ใช้เทคนิค .parents[2] ซึ่งเขียนสั้นและดูโปรน่าอ่านกว่า .parent.parent.parent
PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_DIRECTORY = PROJECT_ROOT / "logs"

# สั่งสร้างโฟลเดอร์ได้เลย (ตัว exist_ok=True จะเช็คให้เองว่ามีหรือยัง ไม่ต้องเขียน if ดัก)
LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)

# ==========================================
# 2. ส่วนตั้งค่า Configuration (จัดกลุ่มใส่ Dictionary ให้ดูเป็นระเบียบ)
# ==========================================
LOGGING_CONFIG = {
    "filepath": LOG_DIRECTORY / "system.log",
    "format": "[%(asctime)s] - %(levelname)s - <%(name)s> - %(filename)s:%(lineno)d : %(message)s",
    "time_format": "%Y-%m-%d %H:%M:%S",
    "max_size_bytes": 5242880,  # 5 * 1024 * 1024 (5MB)
    "backup_limit": 3
}

def setup_project_logger(logger_name: str, base_level: int = logging.DEBUG) -> logging.Logger:
    """ฟังก์ชันสร้าง Logger สำหรับโปรเจกต์ (Console + Rotating File)"""
    
    app_logger = logging.getLogger(logger_name)

    # ใช้เมธอด hasHandlers() ซึ่งเป็นวิธีเช็คมาตรฐานของไลบรารี logging 
    if app_logger.hasHandlers():
        return app_logger

    app_logger.setLevel(base_level)
    
    # ดึงค่าจาก Dictionary มาสร้าง Format
    log_formatter = logging.Formatter(
        fmt=LOGGING_CONFIG["format"],
        datefmt=LOGGING_CONFIG["time_format"]
    )

    # --- ช่องทางที่ 1: แสดงผลออกทางหน้าจอ (สำหรับ Docker ดักจับ) ---
    terminal_handler = logging.StreamHandler(sys.stdout)
    terminal_handler.setLevel(logging.INFO)
    terminal_handler.setFormatter(log_formatter)

    # --- ช่องทางที่ 2: บันทึกลงไฟล์พร้อมระบบสับเปลี่ยนอัตโนมัติ ---
    rotating_handler = RotatingFileHandler(
        filename=LOGGING_CONFIG["filepath"],
        maxBytes=LOGGING_CONFIG["max_size_bytes"],
        backupCount=LOGGING_CONFIG["backup_limit"],
        encoding="utf-8"
    )
    rotating_handler.setLevel(logging.DEBUG)
    rotating_handler.setFormatter(log_formatter)

    # ผูกเข้ากับตัว Logger หลัก
    app_logger.addHandler(terminal_handler)
    app_logger.addHandler(rotating_handler)

    return app_logger