# Satellite Calibration (`model/satellite`)

`ghi_calibration.json` เก็บความสัมพันธ์ที่ใช้แปลงความสว่างของภาพดาวเทียมเป็นดัชนีฟ้าใส

```
k = intercept − slope × ρ        (ρ = ความสว่างเฉลี่ยในกรอบรอบสถานี หารด้วย cos ของมุมซีนิท)
GHI จากดาวเทียม = k × GHI ฟ้าใส
```

| ช่องในไฟล์ | ความหมาย |
|---|---|
| `intercept`, `slope`, `k_min`, `k_max` | ค่าของสมการและขอบเขตของ k |
| `stations`, `pairs`, `days`, `fitted_at` | สถานีและจำนวนคู่ข้อมูลที่ใช้ fit |
| `mae_in_sample`, `mae_leave_one_day_out`, `correlation` | ความคลาดเคลื่อนของการ fit |
| `checked`, `insufficient`, `min_pairs`, `checked_at` | ผลตรวจสมการนี้กับค่าวัดจริงของแต่ละสถานี (หน้าเว็บใช้ติดป้ายว่าเทียบแล้วหรือยัง) |

ค่าในไฟล์ fit จาก GHI ที่วัดจริงของ ST-002 และใช้กับทุกสถานี สร้างและตรวจด้วย `service/training/calibrate_satellite_ghi.py` ระบบตรวจซ้ำเองหลังมีการบันทึกค่าวัดจริง ถ้าไม่มีไฟล์นี้ ฝั่งดาวเทียมจะมีน้ำหนัก 0 ไม่มีค่าตั้งต้นในโค้ด
