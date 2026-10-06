# เข้าสู่ระบบ (`/login`)

**ใครเห็น:** ทุกคน

แท็บเข้าสู่ระบบและแท็บสมัครบัญชี บัญชีที่สมัครเองได้ role `operator` เสมอ ไม่มีค่าเติมไว้ในช่องและไม่มีบัญชีทดลองในโค้ด token ที่ได้เก็บใน `localStorage` ของเบราว์เซอร์

| | |
|---|---|
| API ที่เรียก | `POST /api/auth/login`, `POST /api/auth/register`, `GET /api/auth/me` |
| ชิ้นส่วนหลัก | `context/AuthContext.tsx` |

ไฟล์เดียวในโฟลเดอร์คือ `page.tsx`
