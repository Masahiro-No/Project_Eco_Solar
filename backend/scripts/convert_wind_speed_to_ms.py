"""แปลงความเร็วลมของแถวที่ดึงจาก Open-Meteo ก่อนวันที่แก้หน่วย จาก กม./ชม. เป็น ม./วินาที (หารด้วย 3.6) ครั้งเดียว

ที่มา: ก่อน 5 ต.ค. 2026 ระบบขอ wind_speed_10m จาก Open-Meteo โดยไม่ระบุหน่วย จึงได้ กม./ชม. (ค่าเริ่มต้นของ API)
ขณะที่ LSTM เทรนด้วยข้อมูล NSRDB ซึ่งเป็น ม./วินาที ตั้งแต่วันนั้นระบบขอ wind_speed_unit=ms แล้ว สคริปต์นี้แปลงแถวเก่า
ให้เป็นหน่วยเดียวกัน เพื่อให้หน้าต่างข้อมูลป้อนโมเดลและข้อมูล retrain ไม่มีสองหน่วยปนกัน

ต้องรันตอนที่ ingestion-worker หยุดอยู่ และก่อนเริ่มโค้ดที่ขอหน่วยใหม่ ไม่งั้นแถวใหม่อาจถูกหารซ้ำหรือค้างหน่วยเดิม:

  docker compose stop ingestion-worker
  docker exec fastapi sh -c 'cd /app && uv run python scripts/convert_wind_speed_to_ms.py'                      (ดูจำนวนแถว ไม่แก้อะไร)
  docker exec fastapi sh -c 'cd /app && uv run python scripts/convert_wind_speed_to_ms.py --apply --before <เวลา UTC แบบ ISO>'
  docker compose restart api && docker compose start ingestion-worker

--before คือเวลาที่หยุด worker: แปลงเฉพาะแถวที่ถูกเขียนก่อนเวลานั้น ระบบจดไว้ในตาราง data_migrations ว่าทำแล้ว และไม่ยอมทำซ้ำ
ย้อนกลับได้ด้วยการคูณ 3.6 กับแถวชุดเดียวกัน (แหล่ง open_meteo และ open_meteo_catchup ที่ created_at ก่อนเวลาที่จดไว้)
แถวจากแหล่งอื่น (เช่น nsrdb_2020) เป็น ม./วินาที อยู่แล้วและไม่ถูกแตะ
"""

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from db.database import SessionLocal  # noqa: E402

NAME = "wind_speed_kmh_to_ms"
SOURCES = ("open_meteo", "open_meteo_catchup")
FACTOR = 3.6


async def main() -> int:
    ap = argparse.ArgumentParser(description="แปลง wind_speed ของแถว Open-Meteo เก่า จาก กม./ชม. เป็น ม./วินาที (ค่าเริ่มต้น: แสดงจำนวนอย่างเดียว)")
    ap.add_argument("--apply", action="store_true", help="แปลงจริง")
    ap.add_argument("--before", help="เวลา UTC แบบ ISO: แปลงเฉพาะแถวที่ created_at ก่อนเวลานี้ (ต้องระบุเมื่อ --apply)")
    args = ap.parse_args()

    cutoff = None
    if args.before:
        cutoff = datetime.fromisoformat(args.before.replace("Z", "+00:00"))
        cutoff = cutoff if cutoff.tzinfo else cutoff.replace(tzinfo=timezone.utc)
    if args.apply and cutoff is None:
        ap.error("--apply ต้องระบุ --before (เวลาที่หยุด ingestion-worker)")

    async with SessionLocal() as db:
        await db.execute(text(
            "create table if not exists data_migrations (name varchar(100) primary key, applied_at timestamptz not null default now(), details text)"
        ))
        done = (await db.execute(text("select applied_at, details from data_migrations where name = :n"), {"n": NAME})).first()

        where = "source = any(:sources)" + (" and created_at < :cutoff" if cutoff else "")
        params = {"sources": list(SOURCES), **({"cutoff": cutoff} if cutoff else {})}
        rows = (await db.execute(text(
            f"select source, count(*), round(avg(wind_speed)::numeric, 2), round(max(wind_speed)::numeric, 2) from weather_history where {where} group by 1 order by 1"
        ), params)).all()
        print("แถวที่จะแปลง" + (f" (created_at ก่อน {cutoff.isoformat()})" if cutoff else " (ทุกแถวของแหล่งนี้)"))
        for source, n, mean, top in rows:
            print(f"  {source:<20} {n:>7} แถว  เฉลี่ย {mean} สูงสุด {top}  ->  เฉลี่ย {round(float(mean) / FACTOR, 2)} สูงสุด {round(float(top) / FACTOR, 2)} ม./วินาที")
        total = sum(r[1] for r in rows)

        if done:
            print(f"ทำไปแล้วเมื่อ {done[0].isoformat()} ({done[1]}) — ไม่ทำซ้ำ")
            await db.rollback()
            return 0 if not args.apply else 1
        if not args.apply:
            print("ยังไม่ได้แก้อะไร (โหมดแสดงจำนวน)")
            await db.commit()  # ตาราง data_migrations ว่าง ๆ เท่านั้น
            return 0

        # ธุรกรรมเดียว: จดว่าทำแล้ว และแปลงค่า (พลาดกลางทาง = ไม่มีอะไรเปลี่ยน)
        await db.execute(
            text("insert into data_migrations (name, details) values (:n, :d)"),
            {"n": NAME, "d": f"{total} rows of {', '.join(SOURCES)} created before {cutoff.isoformat()} divided by {FACTOR}"},
        )
        changed = (await db.execute(
            text(f"update weather_history set wind_speed = round((wind_speed / {FACTOR})::numeric, 2) where {where}"), params
        )).rowcount
        await db.commit()
        print(f"แปลงแล้ว {changed} แถว")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
