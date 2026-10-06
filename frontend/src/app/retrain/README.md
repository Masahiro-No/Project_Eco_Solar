# สถานะ retrain (`/retrain`)

**ใครเห็น:** admin

รุ่นที่ใช้งานของ LSTM และ ConvLSTM รอบที่รออยู่ ประวัติของแต่ละรอบ (นำไปใช้หรือถูกปฏิเสธ พร้อมเหตุผลและค่าตรวจก่อนหลัง) และกราฟการเรียนรู้ราย epoch ของรอบที่เลือก

| | |
|---|---|
| API ที่เรียก | `GET /api/retrain/status`, `GET /api/retrain/runs/{run_id}/curves` |
| ชิ้นส่วนหลัก | `LearningCurves.tsx`, `services/dayViewApi.ts` |

ไฟล์เดียวในโฟลเดอร์คือ `page.tsx`
