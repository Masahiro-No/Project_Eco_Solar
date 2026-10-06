# Datasources (`observability/grafana/provisioning/datasources`)

`datasources.yml` ตั้งแหล่งข้อมูลของ Grafana สามตัว

| ชื่อ | ข้อมูล |
|---|---|
| Prometheus | metric ของ API และ worker |
| Loki | log ของคอนเทนเนอร์ |
| Tempo | trace |

dashboard อ้างแหล่งข้อมูลด้วย uid (เช่น `prometheus`) ถ้าเปลี่ยน uid ในไฟล์นี้ต้องแก้ใน dashboard ด้วย
