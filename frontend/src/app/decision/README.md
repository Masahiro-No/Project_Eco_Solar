# สนับสนุนการตัดสินใจ (`/decision`)

**ใครเห็น:** ทุกคนที่ล็อกอิน

ระดับการเตือนของสถานีที่เลือก คำแนะนำ กำลังสำรองที่ควรเตรียม และตารางที่ใช้ตัดสิน (ถึงเป้าหรือต่ำกว่าเป้า × ผลกระทบของเมฆ ต่ำ กลาง สูง) กฎอยู่ที่ `service/workers/decision.py` หน้านี้แสดงผลที่ worker คิดไว้ ไม่คิดซ้ำ

| | |
|---|---|
| API ที่เรียก | ผลพยากรณ์ล่าสุดผ่าน `ForecastContext` (`GET /api/inference/latest/{station_id}`) |
| ชิ้นส่วนหลัก | `components/UI/StatusHero.tsx`, `components/UI/DecisionSupport.tsx` |

ไฟล์เดียวในโฟลเดอร์คือ `page.tsx`
