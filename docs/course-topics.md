# เนื้อหารายวิชาที่ใช้ในระบบ

[← กลับไปที่ README](../README.md) · [เอกสารทั้งหมด](README.md)

เทียบกับสไลด์วิชา 241-353 (AI Ecosystem Module)

| หัวข้อในสไลด์ | ที่ใช้ในระบบ |
|---|---|
| Encoder–decoder (n1) | ConvLSTM แบบ seq2seq: encoder อ่าน 12 เฟรม decoder ทำนาย 18 เฟรม |
| Train / validation / test split (n4) | retrain แบ่งชุดเทรนกับชุดตรวจตามเวลา และ LSTM ใช้ cross-validation ตามวัน: วันที่มีค่าวัดจริงถูกกันไว้ตรวจทีละกลุ่มจนครบทุกวัน โมเดลที่ถูกวัดไม่เคยเห็นวันนั้น |
| เครื่องมือทำ annotation: Label Studio (n4) | ค่า GHI ที่วัดจริงเก็บเป็น task และ annotation ใน Label Studio ผ่านหน้า *บันทึกค่าวัดจริง* |
| Training log, กราฟ loss และ learning rate, การดูว่าโมเดลลู่เข้า (n5 TensorBoard) | ค่าราย epoch ของทุกรอบ retrain ใน MLflow และกราฟในหน้า *สถานะ retrain* |
| L2 regularization (n5) | AdamW weight decay 1e-4 ทั้งสองโมเดล |
| Learning rate scheduling (n6) | ConvLSTM ใช้ cosine annealing ส่วนการเทรน LSTM ตั้งต้นใช้ ReduceLROnPlateau (fine-tune ของ LSTM ใช้ค่าคงที่) |
| Loss ผสมสำหรับงานภาพ (n3) | ConvLSTM ใช้ loss ผสมสี่ส่วน (MSE, L1, 1 − SSIM และผลต่างของ gradient เชิงพื้นที่) และวัดผลด้วย MSE, SSIM และความคลาดของ % เมฆในกรอบ |

ยังไม่ได้ใช้: data augmentation, model pruning (n6), dataset card (n4), YOLO และ U-Net / YOLACT (n2, n3) สองหัวข้อหลังต้องมีภาพที่ระบายหน้ากากเมฆด้วยมือ ซึ่งระบบนี้ไม่มี
