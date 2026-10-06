# MLflow Image (`mlflow`)

`Dockerfile` สร้าง image ของ MLflow server ที่ `compose.yml` ใช้ ต่อยอดจาก image ทางการแล้วเพิ่มไดรเวอร์สองตัว

- `psycopg2-binary` ให้ MLflow เก็บรายการทดลองใน PostgreSQL ตัวเดียวกับระบบ
- `boto3` ให้เก็บไฟล์ของแต่ละรอบใน MinIO

MLflow ใช้เก็บประวัติของทุกรอบ retrain: ค่าตรวจก่อนและหลัง ผลว่านำไปใช้หรือปฏิเสธ และกราฟการเรียนรู้ราย epoch หน้าสถานะ retrain อ่านจากที่นี่ผ่าน `backend/api/retrain`
