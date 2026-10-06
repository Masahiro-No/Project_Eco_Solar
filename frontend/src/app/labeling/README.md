# บันทึกค่าวัดจริง (`/labeling`)

**ใครเห็น:** admin

บันทึกค่า GHI ที่วัดจริงของสถานี โดยกรอกรายช่อง 10 นาทีหรืออัปโหลดไฟล์ CSV / XLSX (ดูตัวอย่างก่อนบันทึก) กราฟเทียบค่าวัดจริงกับเส้นรวม LSTM และ Open-Meteo ค่าที่บันทึกใช้ retrain LSTM และตรวจสูตรแสงจากภาพดาวเทียม มีการ์ดบอกรุ่น LSTM ที่ใช้งานและสถานะการตรวจสูตรของสถานี

| | |
|---|---|
| API ที่เรียก | `/api/label-studio/ground-truth/*`, `GET /api/inference/predictions-by-date` |
| ชิ้นส่วนหลัก | `services/labelingApi.ts`, `LstmStatusPanel.tsx`, `CalibrationStatusPanel.tsx` |

ไฟล์เดียวในโฟลเดอร์คือ `page.tsx`
