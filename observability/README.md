# Observability (`observability`)

ไฟล์ตั้งค่าของชุดเครื่องมือดูการทำงานของระบบ ถูก mount เข้าคอนเทนเนอร์ตาม `compose.yml`

| ไฟล์ | บริการ | หน้าที่ |
|---|---|---|
| `otel-collector.yml` | OpenTelemetry Collector | รับ trace และ metric จาก API และ worker แล้วส่งต่อ |
| `prometheus.yml` | Prometheus | เก็บ metric (จำนวนรอบ เวลาที่ใช้ สถานะฝั่งดาวเทียม) |
| `tempo-config.yml` | Tempo | เก็บ trace ของแต่ละคำขอและแต่ละรอบ |
| `loki-config.yml` | Loki | เก็บ log |
| `promtail-config.yml` | Promtail | อ่าน log ของคอนเทนเนอร์ส่งเข้า Loki |
| [grafana/](grafana/) | Grafana | แหล่งข้อมูลและ dashboard ที่ตั้งให้อัตโนมัติ |

เปิด Grafana ที่ http://localhost:3002 (ผูกกับ `127.0.0.1` เท่านั้น) dashboard ชื่อ `SolarDSS Operations`
