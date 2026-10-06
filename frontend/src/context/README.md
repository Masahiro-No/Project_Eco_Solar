# Context (`frontend/src/context`)

สถานะที่ใช้ทั้งแอป ครอบไว้ใน `components/layout/AppLayout.tsx`

| ไฟล์ | ให้อะไร |
|---|---|
| `AuthContext.tsx` | ล็อกอิน สมัคร ออกจากระบบ ผู้ใช้ปัจจุบันและ role (`useAuth`) เก็บ token ใน `localStorage` และออกจากระบบเองเมื่อ API ตอบ 401 |
| `ForecastContext.tsx` | รายชื่อสถานี สถานีที่เลือก ผลพยากรณ์ล่าสุด และข้อมูลของกราฟ (`useForecast`) ดึงใหม่ทุก 60 วินาทีและเมื่อกลับมาที่แท็บ |
| `LanguageContext.tsx` | ภาษาไทยหรืออังกฤษ (`useLanguage`) |
| `ThemeContext.tsx` | ธีมสว่างหรือมืด (`useTheme`) จำค่าในเบราว์เซอร์ด้วยคีย์ `solar_theme` |
