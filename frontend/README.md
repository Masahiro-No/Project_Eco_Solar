# Frontend — Next.js (`frontend/`)

หน้าเว็บของ SolarDSS สำหรับผู้ควบคุมระบบ (operator) และผู้ดูแล (admin) เขียนด้วย Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS, Recharts และ Leaflet มีสองภาษา ไทยและอังกฤษ
ภาพรวมของทั้งระบบอยู่ใน [README หลัก](../README.md)

หน้าเว็บแสดงเฉพาะข้อมูลที่ได้จาก API ถ้าไม่มีข้อมูลจะบอกว่าไม่มี ไม่มีข้อมูลตัวอย่างหรือค่าทดแทนในโค้ด

## หน้า

| เส้นทาง | หน้า | ใครเห็น |
|---|---|---|
| `/login` | เข้าสู่ระบบ และสมัครบัญชี operator (แท็บ Sign Up) | ทุกคน |
| `/` | แดชบอร์ด: สถานะ ตัวเลขหลัก กราฟ GHI และกำลังผลิต 3 ชั่วโมง แผงเมฆ | ผู้ใช้ที่ล็อกอิน |
| `/forecast` | ระบบพยากรณ์: กราฟ GHI (เส้นที่รวมผล เส้น LSTM อย่างเดียว แถบความไม่แน่นอน) กราฟกำลังผลิต และแผงเมฆ | ผู้ใช้ที่ล็อกอิน |
| `/decision` | สนับสนุนการตัดสินใจ: ระดับการเตือน กำลังที่ขาด และกำลังสำรองที่แนะนำ | ผู้ใช้ที่ล็อกอิน |
| `/alerts` | การแจ้งเตือนและตารางสถานะของทุกสถานี | ผู้ใช้ที่ล็อกอิน |
| `/stations` | สถานีบนแผนที่และรายละเอียด; เพิ่ม แก้ ปิดใช้ ได้เฉพาะ admin | ผู้ใช้ที่ล็อกอิน |
| `/help` | คู่มือและคำอธิบายตัวย่อ | ผู้ใช้ที่ล็อกอิน |
| `/labeling` | Label ค่าจริง: กรอกหรืออัปโหลดค่า GHI ที่วัดจริง เทียบกับค่าพยากรณ์รายวัน | admin |
| `/frame-review` | ตรวจภาพดาวเทียมที่จะใช้ retrain ConvLSTM และสถานะรอบ retrain | admin |

เมนูซ่อนหน้าของ admin จาก operator (`components/UI/Sidebar.tsx`) และ API ตรวจ role ซ้ำทุกครั้ง การซ่อนเมนูจึงไม่ใช่ตัวกันสิทธิ์

## โครงสร้าง

```text
frontend/src/
├── app/                หน้า (App Router) หนึ่งโฟลเดอร์ต่อหนึ่งเส้นทาง, layout.tsx, globals.css
├── components/UI/      ชิ้นส่วนของหน้า: กราฟ, แผงเมฆ, การ์ดตัวเลข, ตารางสถานี, เมนู, แถบบน
├── components/layout/  โครงหน้า (AppLayout)
├── context/
│   ├── AuthContext.tsx       ล็อกอิน สมัคร เก็บ token ออกจากระบบเมื่อ token หมดอายุ
│   ├── ForecastContext.tsx   สถานีที่เลือกและผลพยากรณ์ล่าสุด ดึงใหม่ทุก 1 นาที
│   └── LanguageContext.tsx   ภาษาและฟังก์ชันแปลข้อความ
├── services/           เรียก API: api.ts (สถานี พยากรณ์ แจ้งเตือน), labelingApi.ts, frameReviewApi.ts
├── lib/                config.ts (ที่อยู่ API), levels.ts (ระดับการเตือนและระดับผลกระทบ), time.ts
└── messages/           th.json และ en.json ต้องมี key ครบเท่ากันทั้งสองไฟล์
```

## การตั้งค่า

| ตัวแปร | ความหมาย |
|---|---|
| `NEXT_PUBLIC_API_URL` | ที่อยู่ของ API (ค่าเริ่มต้น `http://localhost:8000`) |
| `NEXT_PUBLIC_DEMO_MODE` | `true` = เติมอีเมลและรหัสผ่านของบัญชี operator ตั้งต้นในหน้า login ให้ ต้องเป็น `false` เมื่อใช้งานจริง |

ค่า `NEXT_PUBLIC_*` ถูกฝังลงในไฟล์ตอน build แก้ค่าแล้วต้อง build ใหม่

## รัน

ในระบบจริงหน้าเว็บเป็น production build ใน container `frontend` แก้โค้ดแล้วต้อง build ใหม่ (ใช้เวลา 2–4 นาที):

```bash
docker compose up -d --build --no-deps frontend
```

พัฒนาบนเครื่อง (ต้องมี API ทำงานที่ `NEXT_PUBLIC_API_URL`):

```bash
npm install
npm run dev
```

## ตรวจก่อน commit

```bash
npx tsc --noEmit -p .
```

```bash
npm run lint
```
