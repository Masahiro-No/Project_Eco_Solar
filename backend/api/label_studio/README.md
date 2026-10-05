# Label Studio Module (`backend/api/label_studio`)

รับค่า GHI ที่วัดจริงจากผู้ดูแล เก็บเป็น label ใน Label Studio แล้วนัดงาน retrain LSTM
หน้าเว็บที่ใช้โมดูลนี้คือ *บันทึกค่าวัดจริง* (`/labeling`) ทุกเส้นทางต้องเป็น role `admin`

## ทางเดินของข้อมูล

```text
ผู้ดูแลกรอกค่าในตาราง หรืออัปโหลดไฟล์ csv / xlsx
        │
        ▼
ตรวจค่า (0–1500 W/m², ไม่เป็นเวลาอนาคต, สถานีมีจริง)  ──ไม่ผ่าน──▶ คืนรายการที่ถูกปฏิเสธพร้อมเหตุผล
        │
        ▼
Label Studio project "Solar GHI Ground Truth Verification"
หนึ่ง label = หนึ่ง task + หนึ่ง annotation, คีย์ = (สถานี, ช่องเวลา 10 นาที) ส่งซ้ำคือแก้ค่าเดิม
        │
        ▼
นัดงาน train_timeseries_lstm ใน train_queue หลังรอ RETRAIN_DEBOUNCE_SECONDS (ค่าเริ่มต้น 300 วินาที)
label ที่ส่งมาในช่วงรอจะรวมเป็นรอบเดียว และไม่นัดเมื่อ ENABLE_RETRAIN=false
```

## กติกาเวลา

- เวลาที่ไม่มี timezone ถือเป็นเวลาไทย (UTC+7)
- เวลาถูกปัดลงเป็นช่อง 10 นาที (12:05 → 12:00) เพราะระบบบันทึกข้อมูลที่นาที :00, :10, …
- ค่าหลายแถวในช่องเดียวกันของไฟล์เดียว: แถวหลังสุดชนะ

## API Endpoints

| Method | Endpoint | ใช้ทำอะไร |
| --- | --- | --- |
| `POST` | `/api/label-studio/ground-truth/submit` | บันทึกค่า GHI จริง 1 ค่า |
| `POST` | `/api/label-studio/ground-truth/batch-submit` | บันทึกหลายค่าจากตารางหน้าเว็บ (ไม่เกิน 2,000 ค่าต่อครั้ง) คืนจำนวนที่สร้าง แก้ ไม่เปลี่ยน และรายการที่ถูกปฏิเสธ |
| `POST` | `/api/label-studio/ground-truth/upload/preview` | อ่านหัวตารางและแถวตัวอย่างของไฟล์ และเดาคอลัมน์เวลากับ GHI ให้ผู้ใช้เลือก |
| `POST` | `/api/label-studio/ground-truth/upload` | นำเข้าไฟล์ csv / xlsx เฉพาะแถวของวันที่เลือก (เวลาไทย) ไฟล์ไม่เกิน 5 MB และ 20,000 แถว |
| `GET` `POST` | `/api/label-studio/projects` | ดูและสร้าง project ใน Label Studio |
| `GET` `POST` | `/api/label-studio/projects/{id}/tasks` | ดูและเพิ่ม task |
| `GET` `POST` | `/api/label-studio/projects/{id}/tasks/{task_id}/annotations` | ดูและเพิ่ม annotation |

ค่าที่บันทึกแล้วอ่านกลับพร้อมค่าพยากรณ์ของวันเดียวกันได้ที่ `GET /api/inference/predictions-by-date` (โมดูล inference)

## ไฟล์

- `router.py` เส้นทางทั้งหมดของโมดูล
- `ground_truth_controller.py` เส้นทาง ground-truth: ตรวจค่า บันทึก และนัด retrain
- `ground_truth.py` กติกาเวลา การตรวจค่า การอ่านและเขียน label ใน Label Studio และการนัด retrain
- `file_import.py` อ่านไฟล์ csv / xlsx เดาคอลัมน์ และแปลงเวลา
- `controller.py`, `service.py` เส้นทาง projects, tasks, annotations ผ่าน `label-studio-sdk`
- `schema.py` Pydantic models

## การตั้งค่า

- `LABEL_STUDIO_URL`, `LABEL_STUDIO_API_KEY` ใน `.env` (token สร้างจากหน้า Account & Settings ของ Label Studio)
- Label Studio เก็บ SECRET_KEY ไว้ใน volume `label-studio-data` ถ้า volume หาย token เดิมจะใช้ไม่ได้และต้องสร้างใหม่
- ทดสอบการบันทึก label ด้วยสถานี `ST-TEST-99` เท่านั้น ค่าที่วัดจริงให้ใส่กับสถานีของมันเอง
