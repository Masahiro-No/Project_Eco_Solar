# Scripts (`backend/scripts`)

สคริปต์ที่รันด้วยมือ ไม่ได้ถูกเรียกตอนระบบทำงาน รันในคอนเทนเนอร์ `fastapi` จากโฟลเดอร์ `/app`

| ไฟล์ | ใช้ทำอะไร | เขียนข้อมูลจริงไหม |
|---|---|---|
| `check_ground_truth_flow.py` | ตรวจ 8 หมวด: ช่องเวลา 10 นาที, กฎกันแถวซ้ำ, การเก็บสภาพอากาศ, ตรวจภาพ, กติกาเวลา, ไฟล์ตัวอย่าง, การบันทึก label, flow ผ่าน HTTP | ไม่ ใช้ SQLite ในหน่วยความจำ |
| `replay_inference.py` | รันโมเดลจริงกับข้อมูลจริงของสถานีและเวลาที่ระบุ | ไม่เขียนฐานข้อมูล |
| `cleanup_test_data.py` | แสดงรายการข้อมูลทดสอบและแถวค้าง แล้วลบเมื่อสั่ง `--apply` และพิมพ์ยืนยัน | ลบ เมื่อสั่งเท่านั้น |
| `convert_wind_speed_to_ms.py` | แปลงความเร็วลมของแถวเก่าจาก กม./ชม. เป็น ม./วินาที ครั้งเดียว (รันแล้ว และไม่ยอมทำซ้ำ) | เขียน |
| `openapi_to_csv.py` | สร้าง `api_snapshot.csv` และ `.xlsx` จากรายการ API ของเซิร์ฟเวอร์ที่รันอยู่ | เขียนเฉพาะสองไฟล์นั้น |
| `api_snapshot.csv`, `api_snapshot.xlsx` | รายการ API ทั้ง 59 เส้นทาง (สร้างจากสคริปต์ข้างบน) | — |
| [samples/](samples/) | ไฟล์ตัวอย่างค่า GHI ที่วัดจริง | — |

```bash
docker exec fastapi sh -c 'cd /app && uv run --with aiosqlite --with httpx python scripts/check_ground_truth_flow.py'
```

```bash
docker exec fastapi sh -c 'cd /app && uv run python scripts/cleanup_test_data.py'
```
