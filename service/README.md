# Workers (`service/`)

งานเบื้องหลังของ SolarDSS แยก process จาก API และรับงานจากคิวใน Redis ด้วย ARQ มี worker สามตัว แต่ละตัวมีคิวและ container ของตัวเอง
ภาพรวมของทั้งระบบและเหตุผลของแต่ละวิธีอยู่ใน [README หลัก](../README.md)

| Worker | container | คิว | ตั้งค่าใน `main.py` | ทำอะไร |
|---|---|---|---|---|
| Ingestion | `ingestion-worker` | `ingest_queue` | `IngestionWorkerSettings` | ทุก 10 นาที (นาทีที่ 8, 18, …, 58) และหนึ่งรอบทันทีเมื่อ worker เริ่ม ดึงสภาพอากาศและภาพดาวเทียมของทุกสถานี เติมช่องที่ขาด สั่งพยากรณ์ทีละสถานี และทุกนาทีเก็บผลพยากรณ์ที่เสร็จแล้วลงฐานข้อมูล |
| Inference | `inference-worker` | `inference_queue` | `InferenceWorkerSettings` | รันโมเดลของหนึ่งสถานี: LSTM, ConvLSTM, รวมผล, ตัดสินใจ |
| Trainer | `trainer-worker` | `train_queue` | `WorkerSettings` | retrain LSTM และ ConvLSTM และตรวจสูตรแสงจากภาพดาวเทียมกับค่าวัดจริง |

## โครงสร้าง

```text
service/
├── main.py                       ตั้งค่า worker ทั้งสามและการต่อ Redis
├── workers/
│   ├── ingestion_worker.py       รอบดึงข้อมูล, สั่งพยากรณ์, เก็บผล, นับภาพใหม่เพื่อเริ่ม retrain ConvLSTM
│   ├── inference_worker.py       งานพยากรณ์หนึ่งสถานี
│   ├── satellite_preprocessor.py โหลดภาพ Himawari จริง 12 เฟรม (cache ใน MinIO) ตัดภาพดำทิ้ง และเก็บภาพที่ ConvLSTM ทำนาย
│   ├── round_lock.py             ให้รอบดึงข้อมูลรันทีละรอบ (รอบที่มาซ้อนถูกข้าม)
│   ├── cloud_coverage.py         สัดส่วนเมฆและความสว่างใน AOI, ดัชนีฟ้าใสจากภาพ, ระดับผลกระทบ
│   ├── ghi_blend.py              รวมผล LSTM กับภาพดาวเทียมด้วยน้ำหนัก w(t)
│   ├── decision.py               เป้าตามแดด, ΔP, ระดับการเตือน, กำลังสำรอง, แถบความไม่แน่นอน
│   ├── solar_geometry.py         มุมดวงอาทิตย์
│   ├── convlstm_batch.py         นับเวลาสแกนใหม่และสถานะรอบ retrain ของ ConvLSTM
│   └── train_worker.py           งานของ trainer: retrain สองงาน และ check_satellite_calibration
├── training/
│   ├── train.py                  เทรน LSTM ตั้งต้นและทดลองความยาวข้อมูลย้อนหลัง (--ablation)
│   ├── features.py               จัดข้อมูลลงช่อง 10 นาที สร้าง window และกันวันที่มี label ไว้ตรวจ
│   ├── curves.py                 บันทึกค่าราย epoch ของรอบ retrain ลง MLflow (กราฟการเรียนรู้)
│   ├── retrain_timeseries.py     fine-tune LSTM จาก label
│   ├── retrain_convlstm.py       retrain ConvLSTM จากภาพจริง (--status, --backfill-days N, --run)
│   ├── calibrate_satellite_ghi.py  fit ค่า a, b ของดัชนีฟ้าใสจากภาพกับ GHI ที่วัดจริง (--write) หรือวัดความคลาดของสูตรเดิมรายสถานี (--check)
│   └── backtest_cloud.py         ทดสอบย้อนหลังความแม่นของ % เมฆ
├── models/solar_lstm.py          โครงสร้าง LSTM (PyTorch) ที่ใช้ตอนเทรน; โครงสร้าง ConvLSTM อยู่ใน retrain_convlstm.py
└── tests/                        ชุดทดสอบ 47 รายการ
```

## งานพยากรณ์หนึ่งรอบ (`run_inference`)

1. รับฟีเจอร์ 36 ช่อง × 16 ค่าที่ ingestion-worker เตรียมไว้ (สร้างด้วย `backend/api/inference/weather_grid.py`)
2. LSTM (ONNX) ให้ GHI 18 ก้าว
3. ฝั่งดาวเทียม: ใช้เฟรมจริงล่าสุดและผลของ ConvLSTM (ONNX) คิดความสว่างใน AOI แล้วแปลงเป็นดัชนีฟ้าใสด้วยค่า calibration สถานะที่เป็นไปได้คือ `ok`, `shifted`, `gap_skipped` (เว้นรอบสแกนที่ขาดหนึ่งรอบ ใช้ภาพจริง 12 เฟรม), `observed_only`, `missing`, `low_sun`, `night`
4. รวมผลด้วย `w(t) = 0.9·exp(−t/102)` แล้วคำนวณ P_gen, เป้า, ΔP และระดับการเตือน
5. เก็บ 18 ภาพที่ ConvLSTM ทำนายในรอบนั้นลง bucket `satellite-forecast` (เขียนทับของเดิม รอบที่ไม่มีภาพบันทึกว่า 0 ภาพ) ให้ตัวเล่นภาพเมฆบนหน้าเว็บ
6. คืนผลให้ ingestion-worker บันทึกลงตาราง `predictions`

ถ้าข้อมูลส่วนใดขาด worker บันทึกสถานะและเหตุผล ไม่สร้างค่าแทน

## Retrain

เปิดปิดด้วย `ENABLE_RETRAIN` ใน `.env` ทั้งสองงานสำรองไฟล์เดิมไว้ที่ `model/<ชนิด>/backups/` และบันทึกผลทุกรอบใน MLflow พร้อมสถานะ เหตุผล และรุ่น ซึ่งหน้า *สถานะ retrain* อ่านไปแสดง

| งาน | เริ่มเมื่อ | เกณฑ์รับโมเดลใหม่ |
|---|---|---|
| `train_timeseries_lstm` | ผู้ดูแลบันทึกค่า GHI จริง (API นัดงานหลังรอ 5 นาทีเพื่อรวม label ที่ส่งใกล้กัน) | มี label 2 วันขึ้นไป: ต้องลด MAE เทียบกับค่าวัดจริงของวันล่าสุดที่กันไว้ และไม่แย่ลงเกิน 5% บนชุดตรวจที่ไม่มี label; มี label วันเดียว: MAE บนชุดตรวจไม่สูงกว่าเดิม |
| `train_convlstm_nowcaster` | มีภาพกลางวันใหม่ครบ 50 เวลาสแกน | MSE บนชุดตรวจ (ช่วงเวลาล่าสุด) ไม่สูงกว่าเดิม; ภาพที่ผู้ดูแลปฏิเสธที่หน้าตรวจภาพไม่เข้าชุดเทรน |

ทั้งสองงานบันทึกค่าของแต่ละ epoch (loss บนข้อมูลเทรน ค่าคลาดเคลื่อนบนข้อมูลตรวจ learning rate) ลง MLflow เป็น metric `epoch_*` โดย epoch 0 คือโมเดลก่อนเริ่มรอบ หน้า *สถานะ retrain* วาดเป็นกราฟการเรียนรู้

งานที่สามของ trainer คือ `check_satellite_calibration`: API นัดให้หลังผู้ดูแลบันทึกค่าวัดจริง งานนี้วัดความคลาดของสูตรแสงจากภาพดาวเทียมที่ทุกสถานีที่มีค่าวัดจริง (ต้องมีอย่างน้อย 30 คู่ที่มีภาพเวลาเดียวกัน) แล้วบันทึกผลลงไฟล์ calibration โดยไม่เปลี่ยนสูตร

ค่าที่ปรับได้อยู่ใน environment ของ `trainer-worker` ใน `compose.yml` เช่น `RETRAIN_LOOKBACK_DAYS`, `CONVLSTM_RETRAIN_THRESHOLD`, `CONVLSTM_LOOKBACK_DAYS`

```bash
docker exec trainer-worker sh -c 'cd /workspace && python -m service.training.retrain_convlstm --status'
```

## การต่อ Redis

worker ทั้งสามใช้ `_redis_settings()` ใน `main.py`: timeout 20 วินาที ลองซ้ำ 10 ครั้ง ค่าเริ่มต้นของ ARQ คือ 1 วินาที ซึ่งทำให้ worker หยุดเมื่องานหนึ่งกำลังใช้ event loop อยู่

## รัน

ในระบบจริงทั้งสามตัวเริ่มจาก `docker compose up -d` โค้ดถูก mount เข้า container แก้แล้วต้อง restart

```bash
docker compose restart ingestion-worker inference-worker trainer-worker
```

อย่า restart `trainer-worker` ระหว่างที่กำลังเทรน งานจะถูกยกเลิก

รัน worker เองนอก compose (ต้องตั้ง environment ให้ต่อ Redis, PostgreSQL, MinIO ได้):

```bash
arq service.main.InferenceWorkerSettings
```

เทรนด้วย GPU ทำบนเครื่อง host เพราะ container ของ trainer ใช้ CPU

## ทดสอบ

```bash
docker exec trainer-worker sh -c 'cd /workspace && pip install -q pytest && python -m pytest service/tests -q'
```
