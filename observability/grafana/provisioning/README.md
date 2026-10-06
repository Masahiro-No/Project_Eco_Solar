# Grafana Provisioning (`observability/grafana/provisioning`)

ถูก mount เข้า `/etc/grafana/provisioning` แบบอ่านอย่างเดียว

| โฟลเดอร์ | เนื้อหา |
|---|---|
| [datasources](datasources/) | แหล่งข้อมูลสามตัว: Prometheus, Loki, Tempo |
| [dashboards](dashboards/) | dashboard `SolarDSS Operations` |

เมื่อแก้ไฟล์ในนี้ ให้สั่ง `docker compose restart grafana`
