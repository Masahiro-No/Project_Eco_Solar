# การทดสอบและเครื่องมือตรวจ

[← กลับไปที่ README](../README.md) · [เอกสารทั้งหมด](README.md)

รายละเอียดของแต่ละชุดทดสอบอยู่ใน [service/tests/](../service/tests/README.md) และ [backend/scripts/](../backend/scripts/README.md)

## ชุดทดสอบ

ชุดทดสอบของ worker (48 รายการ):

```bash
docker exec trainer-worker sh -c 'cd /workspace && pip install -q pytest && python -m pytest service/tests -q'
```

สูตรที่เขียนไว้สองฝั่ง (ตำแหน่งพิกเซลของสถานี ตำแหน่งดวงอาทิตย์ เกณฑ์ภาพดำ) ต้องให้ผลตรงกัน ตรวจใน ingestion-worker ซึ่งมีโค้ดทั้งสองฝั่ง:

```bash
docker exec ingestion-worker sh -c 'cd /workspace && pip install -q pytest && python -m pytest service/tests/test_same_formulas.py -q'
```

ตรวจฝั่ง backend 8 หมวด (ช่องเวลา 10 นาที, กฎกันแถวซ้ำ, การเก็บสภาพอากาศ, ตรวจภาพ, กติกาเวลา, ไฟล์ตัวอย่าง, การบันทึก label, flow ผ่าน HTTP) ใช้ฐานข้อมูลในหน่วยความจำ ไม่แตะข้อมูลจริง:

```bash
docker exec fastapi sh -c 'cd /app && uv run --with aiosqlite --with httpx python scripts/check_ground_truth_flow.py'
```

ฝั่งหน้าเว็บตรวจด้วย `npx tsc --noEmit` และ `npx next lint` ในโฟลเดอร์ `frontend/`

## รันโมเดลกับข้อมูลจริงย้อนหลัง

รันโมเดลจริงกับข้อมูลจริงของเวลาที่ระบุ โดยไม่เขียนฐานข้อมูล:

```bash
docker exec fastapi sh -c 'cd /app && PYTHONPATH=/app uv run python scripts/replay_inference.py ST-002 2026-10-04T07:00:00+00:00'
```

## ดูการทำงานของระบบ

Grafana มี dashboard `SolarDSS Operations` (รอบ ingestion, รอบพยากรณ์ต่อสถานี, สถานะภาพดาวเทียม, รุ่นโมเดล, log ของ worker)

## ลบข้อมูลทดสอบ

บัญชี, bucket, สถานี และแถวพยากรณ์ที่ค้างจากการทดสอบ ลบด้วยสคริปต์ที่แสดงรายการก่อนเสมอ คำสั่งแรกไม่ลบอะไร:

```bash
docker exec fastapi sh -c 'cd /app && uv run python scripts/cleanup_test_data.py'
```

เมื่อรายการถูกต้อง รันคำสั่งที่สองแล้วพิมพ์ `DELETE` เพื่อยืนยัน (ย้อนกลับไม่ได้):

```bash
docker exec -it fastapi sh -c 'cd /app && uv run python scripts/cleanup_test_data.py --apply'
```

เลือกหมวดได้ด้วย `--only users,buckets,predictions,stations` บัญชีที่ไม่ตรงรูปแบบบัญชีทดสอบจะไม่ถูกลบเว้นแต่ระบุ `--delete-user EMAIL` และกันบัญชีไว้ได้ด้วย `--keep-user EMAIL`
