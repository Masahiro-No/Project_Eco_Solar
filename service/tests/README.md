# Tests (`service/tests`)

ชุดทดสอบของ worker และการ retrain ใช้ข้อมูลที่สร้างในการทดสอบเท่านั้น ไม่แตะฐานข้อมูลหรือข้อมูลจริง

| ไฟล์ | ตรวจอะไร | จำนวน |
|---|---|---:|
| `test_forecast_pipeline.py` | สัดส่วนเมฆ การรวมผลสองโมเดล กฎการตัดสินใจ แถบความไม่แน่นอน ตัวล็อกรอบดึงข้อมูล กฎเว้นเฟรมที่ขาด การตรวจ calibration กราฟการเรียนรู้ | 28 |
| `test_retrain_timeseries.py` | การสร้างชุดข้อมูลจากค่าวัดจริงโดยไม่ให้ค่าวัดเข้าไปในข้อมูลป้อน การนับวันใหม่ การแบ่งวันเป็นกลุ่มสำหรับกันไว้ตรวจ loss เฉพาะช่องที่มีค่าวัดจริง เกณฑ์รับโมเดลใหม่ของ LSTM | 12 |
| `test_retrain_convlstm.py` | การนับภาพ การตัดภาพที่ถูกปฏิเสธ เกณฑ์รับโมเดลใหม่ของ ConvLSTM | 9 |
| `test_same_formulas.py` | สูตรที่เขียนสองฝั่ง (API และ worker) ให้ผลตรงกัน: ตำแหน่งพิกเซล ตำแหน่งดวงอาทิตย์ เกณฑ์ภาพดำ | 3 |

```bash
docker exec trainer-worker sh -c 'cd /workspace && pip install -q pytest && python -m pytest service/tests -q'
```

`test_same_formulas.py` ต้องรันที่ที่มีโค้ดทั้งสองฝั่ง คือ `ingestion-worker` (ในคอนเทนเนอร์อื่นจะถูกข้าม)

```bash
docker exec ingestion-worker sh -c 'cd /workspace && pip install -q pytest && python -m pytest service/tests/test_same_formulas.py -q'
```
