# Dashboards (`observability/grafana/provisioning/dashboards`)

| ไฟล์ | เนื้อหา |
|---|---|
| `dashboards.yml` | บอก Grafana ให้โหลด dashboard จากโฟลเดอร์นี้ |
| `solardss-operations.json` | dashboard `SolarDSS Operations` (uid `solardss-operations`) |

แผงใน dashboard: จำนวนรอบดึงข้อมูลและรอบพยากรณ์ในชั่วโมงล่าสุด, เวลาที่ใช้ (p95), รอบพยากรณ์ต่อสถานี, สถานะฝั่งดาวเทียม, กำลังผลิตที่พยากรณ์ต่อสถานี, รุ่นโมเดลที่ใช้, คำขอและความหน่วงของ API, คำเตือนและข้อผิดพลาดของ worker

`GET /api/dashboard/grafana-links` ตอบลิงก์ของ dashboard นี้โดยใช้ uid เดียวกัน ถ้าเปลี่ยน uid ต้องแก้ `GRAFANA_DASHBOARD_UID` ใน `backend/api/dashboard/service.py` ด้วย
