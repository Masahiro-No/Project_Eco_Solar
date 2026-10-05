"""ลบข้อมูลทดสอบที่ค้างในระบบ: แสดงรายการก่อนเสมอ และลบจริงเฉพาะเมื่อสั่ง --apply แล้วพิมพ์ยืนยัน

รันในคอนเทนเนอร์ api (ต้องใช้ -it ตอนลบจริง เพราะต้องพิมพ์ยืนยัน):

  ดูรายการ (ไม่ลบอะไร):
    docker exec fastapi sh -c 'cd /app && uv run python scripts/cleanup_test_data.py'
  ลบจริง:
    docker exec -it fastapi sh -c 'cd /app && uv run python scripts/cleanup_test_data.py --apply'

สิ่งที่สคริปต์จัดการ (เลือกบางหมวดได้ด้วย --only users,buckets,predictions,stations,leftovers):

  users        บัญชีที่สคริปต์ทดสอบสร้าง (ชื่อลงท้ายด้วยเลขเวลา โดเมน solar.internal) เท่านั้น
               บัญชีอื่นต้องระบุเองด้วย --delete-user EMAIL และกันบัญชีไว้ได้ด้วย --keep-user EMAIL
               บัญชี admin และบัญชีที่ระบบสร้างตอนเริ่ม (KEEP_ALWAYS) ไม่ถูกลบไม่ว่ากรณีใด
  buckets      bucket ชื่อ test-bucket-<เลข> ใน MinIO พร้อมไฟล์ทุกเวอร์ชันข้างใน
  predictions  แถวพยากรณ์ที่ source เป็น legacy หรือว่าง (มาจากช่วงก่อนใช้โมเดลจริง)
  stations     สถานี ST-TEST-* พร้อมข้อมูลที่ผูกอยู่ (พยากรณ์ อากาศ ภาพดาวเทียม ผลตรวจภาพ label) และไฟล์ภาพใน MinIO

  leftovers    แถวที่ระบบรุ่นก่อนทิ้งไว้ ซึ่งไม่มีโมเดลหรือหน้าเว็บใดใช้ (รวมของสถานีจริง):
               แถวใน satellite_frames ที่ชี้ไปภาพทั้งดวง (nict_*) แทนภาพ B03 ของสถานี พร้อมไฟล์ nict_* ใน MinIO
               และแถว weather_history ที่ซ้ำกันทุกค่า (เก็บแถวแรกไว้ 1 แถว)

ไม่แตะ: ข้อมูลอื่นของสถานีจริง ST-001..ST-005, bucket อื่น, ข้อมูลใน Label Studio และ MLflow
"""

import argparse
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from api.storage.service import get_minio_client  # noqa: E402
from db.database import SessionLocal  # noqa: E402

SECTIONS = ("users", "buckets", "predictions", "stations", "leftovers")
KEEP_ALWAYS = {"admin@solardss.io", "operator@solardss.io"}      # สร้างโดยระบบตอนเริ่ม (db/database.py)
GENERATED_ACCOUNT = re.compile(r"^(user|user_e2e|tester)_\d{9,}@solar\.internal$")
TEST_BUCKET = re.compile(r"^test-bucket-\d+$")
TEST_STATION_LIKE = "ST-TEST-%"
SATELLITE_BUCKET = "satellite-cache"
# ตารางที่มี foreign key ไปยัง stations.id (ต้องลบแถวก่อนตัวสถานี) อ่านจากฐานข้อมูลเอง ไม่เขียนชื่อตายตัว
STATION_FK_SQL = """
    select c.conrelid::regclass::text, a.attname
    from pg_constraint c join pg_attribute a on a.attrelid = c.conrelid and a.attnum = c.conkey[1]
    where c.contype = 'f' and c.confrelid = 'stations'::regclass
    order by 1
"""
# แถวเฟรมที่ชี้ไปภาพทั้งดวง 550x550 (nict_*) และแถวสภาพอากาศ w ที่เหมือนแถว k ซึ่งเก็บไว้ก่อนทุกค่า
FULL_DISK_FRAME = "strpos(image_url, '/nict_') > 0"
SAME_WEATHER_ROW = (
    "k.id < w.id and k.station_id = w.station_id and k.timestamp = w.timestamp and k.source = w.source "
    "and k.ghi = w.ghi and k.dni = w.dni and k.dhi is not distinct from w.dhi and k.temperature = w.temperature "
    "and k.relative_humidity = w.relative_humidity and k.wind_speed = w.wind_speed and k.cloud_cover = w.cloud_cover "
    "and k.surface_pressure is not distinct from w.surface_pressure"
)


def _say(line: str = "") -> None:
    print(line, flush=True)


async def plan_users(db, keep: set[str], extra: set[str]) -> list[tuple[int, str]]:
    rows = (await db.execute(text("select id, email, role, created_at::date from users order by id"))).all()
    doomed: list[tuple[int, str]] = []
    _say("[users] บัญชีทั้งหมดในระบบ")
    for uid, email, role, created in rows:
        low = email.lower()
        if low in KEEP_ALWAYS or role == "admin":
            verdict = "เก็บ (บัญชีระบบ/admin)"
        elif low in keep:
            verdict = "เก็บ (--keep-user)"
        elif low in extra:
            verdict = "ลบ (--delete-user)"
            doomed.append((uid, email))
        elif GENERATED_ACCOUNT.match(low):
            verdict = "ลบ (สร้างโดยสคริปต์ทดสอบ)"
            doomed.append((uid, email))
        else:
            verdict = "เก็บ (ไม่ตรงรูปแบบบัญชีทดสอบ ถ้าจะลบให้ระบุ --delete-user)"
        _say(f"  {uid:>4}  {email:<42} {role:<9} {created}  -> {verdict}")
    unknown = extra - {e.lower() for _, e, _, _ in rows}
    for email in sorted(unknown):
        _say(f"  !! --delete-user {email}: ไม่มีบัญชีนี้")
    _say(f"  รวมจะลบ {len(doomed)} จาก {len(rows)} บัญชี")
    return doomed


def plan_buckets(client) -> list[tuple[str, list[tuple[str, str | None]]]]:
    found = []
    _say("[buckets] bucket ทดสอบใน MinIO")
    for b in client.list_buckets():
        if not TEST_BUCKET.match(b.name):
            continue
        objects = [(o.object_name, o.version_id) for o in client.list_objects(b.name, recursive=True, include_version=True)]
        found.append((b.name, objects))
        _say(f"  {b.name}: {len(objects)} ไฟล์/เวอร์ชัน " + ", ".join(sorted({n for n, _ in objects})[:5]))
    _say(f"  รวมจะลบ {len(found)} bucket")
    return found


async def plan_predictions(db) -> int:
    rows = (await db.execute(text(
        "select station_id, coalesce(source, '(ว่าง)'), count(*), min(created_at)::date, max(created_at)::date "
        "from predictions where source is null or source = 'legacy' group by 1, 2 order by 1, 2"
    ))).all()
    _say("[predictions] แถวพยากรณ์ที่ไม่ได้มาจากโมเดลจริง (source = legacy หรือว่าง)")
    for station, source, n, first, last in rows:
        _say(f"  {station:<14} source={source:<7} {n:>4} แถว  {first} ถึง {last}")
    total = sum(r[2] for r in rows)
    _say(f"  รวมจะลบ {total} แถว")
    return total


async def plan_stations(db, client) -> tuple[list[str], dict[tuple[str, str], int], list[str]]:
    stations = (await db.execute(text("select id, name, is_active from stations where id like :p order by id"), {"p": TEST_STATION_LIKE})).all()
    ids = [s[0] for s in stations]
    _say("[stations] สถานีทดสอบและข้อมูลที่ผูกอยู่")
    for sid, name, active in stations:
        _say(f"  {sid}  {name}  ({'เปิดใช้' if active else 'ปิดใช้'})")
    counts: dict[tuple[str, str], int] = {}
    for table, column in (await db.execute(text(STATION_FK_SQL))).all():
        n = (await db.execute(text(f"select count(*) from {table} where {column} like :p"), {"p": TEST_STATION_LIKE})).scalar_one()
        counts[(table, column)] = n
        _say(f"    {table:<26} {n:>6} แถว")
    objects: list[str] = []
    if client.bucket_exists(SATELLITE_BUCKET):
        for sid in ids:
            objects += [o.object_name for o in client.list_objects(SATELLITE_BUCKET, prefix=f"{sid}/", recursive=True)]
    _say(f"    ไฟล์ภาพใน {SATELLITE_BUCKET:<12} {len(objects):>6} ไฟล์")
    _say(f"  รวมจะลบ {len(ids)} สถานี")
    return ids, counts, objects


async def plan_leftovers(db, client) -> tuple[int, int, list[str]]:
    _say("[leftovers] แถวที่ระบบรุ่นก่อนทิ้งไว้ (ไม่มีโมเดลหรือหน้าเว็บใดใช้)")
    frames = (await db.execute(text(
        f"select station_id, count(*), min(frame_timestamp)::date, max(frame_timestamp)::date from satellite_frames "
        f"where {FULL_DISK_FRAME} group by 1 order by 1"
    ))).all()
    for station, n, first, last in frames:
        _say(f"  เฟรมที่ชี้ไปภาพทั้งดวง (nict_*)  {station:<14} {n:>4} แถว  {first} ถึง {last}")
    copies = (await db.execute(text(
        f"select w.station_id, w.timestamp, w.source, count(*) from weather_history w "
        f"where exists (select 1 from weather_history k where {SAME_WEATHER_ROW}) group by 1, 2, 3 order by 1, 2"
    ))).all()
    for station, ts, source, n in copies:
        _say(f"  สภาพอากาศที่เก็บซ้ำ            {station:<14} {n:>4} แถว  {ts:%Y-%m-%d %H:%M} UTC source={source} (เก็บแถวแรกไว้)")
    objects: list[str] = []
    if client.bucket_exists(SATELLITE_BUCKET):
        objects = [o.object_name for o in client.list_objects(SATELLITE_BUCKET, recursive=True)
                   if o.object_name.rsplit("/", 1)[-1].startswith("nict_")]
    n_frames, n_weather = sum(r[1] for r in frames), sum(r[3] for r in copies)
    _say(f"  ไฟล์ภาพทั้งดวงใน {SATELLITE_BUCKET}: {len(objects)} ไฟล์")
    _say(f"  รวมจะลบ เฟรม {n_frames} แถว สภาพอากาศซ้ำ {n_weather} แถว ไฟล์ {len(objects)} ไฟล์")
    return n_frames, n_weather, objects


async def main() -> int:
    ap = argparse.ArgumentParser(description="ลบข้อมูลทดสอบ (ค่าเริ่มต้น: แสดงรายการอย่างเดียว)")
    ap.add_argument("--apply", action="store_true", help="ลบจริงหลังพิมพ์ยืนยัน")
    ap.add_argument("--only", default=",".join(SECTIONS), help=f"หมวดที่จะทำ คั่นด้วยจุลภาค: {', '.join(SECTIONS)}")
    ap.add_argument("--keep-user", action="append", default=[], metavar="EMAIL", help="บัญชีที่ห้ามลบ (ใส่ซ้ำได้)")
    ap.add_argument("--delete-user", action="append", default=[], metavar="EMAIL", help="บัญชีที่ต้องการลบเพิ่ม (ใส่ซ้ำได้)")
    args = ap.parse_args()

    only = [s.strip() for s in args.only.split(",") if s.strip()]
    bad = [s for s in only if s not in SECTIONS]
    if bad:
        ap.error(f"ไม่รู้จักหมวด: {', '.join(bad)}")
    keep = {e.lower() for e in args.keep_user}
    extra = {e.lower() for e in args.delete_user} - keep - KEEP_ALWAYS

    client = get_minio_client()
    async with SessionLocal() as db:
        users = await plan_users(db, keep, extra) if "users" in only else []
        _say()
        buckets = plan_buckets(client) if "buckets" in only else []
        _say()
        n_pred = await plan_predictions(db) if "predictions" in only else 0
        _say()
        station_ids, station_counts, station_objects = await plan_stations(db, client) if "stations" in only else ([], {}, [])
        _say()
        n_frames, n_weather, leftover_objects = await plan_leftovers(db, client) if "leftovers" in only else (0, 0, [])
        leftover_objects = [o for o in leftover_objects if o not in set(station_objects)]
        _say()

        nothing = not users and not buckets and not n_pred and not station_ids and not n_frames and not n_weather and not leftover_objects
        if not args.apply:
            _say("ยังไม่ได้ลบอะไร (โหมดแสดงรายการ)" + ("" if nothing else " — ถ้ารายการถูกต้อง รันอีกครั้งพร้อม --apply"))
            return 0
        if nothing:
            _say("ไม่มีอะไรให้ลบ")
            return 0
        if not sys.stdin.isatty():
            _say("ต้องรันแบบโต้ตอบ (docker exec -it ...) เพื่อพิมพ์ยืนยันก่อนลบ")
            return 2
        if input("การลบนี้ย้อนกลับไม่ได้ พิมพ์ DELETE เพื่อยืนยัน: ").strip() != "DELETE":
            _say("ยกเลิก ไม่ได้ลบอะไร")
            return 1

        # ฐานข้อมูล: ทำในธุรกรรมเดียว ถ้าพลาดกลางทางจะไม่มีอะไรถูกลบ
        if users:
            await db.execute(text("delete from users where id = any(:ids)"), {"ids": [u for u, _ in users]})
        if "predictions" in only:
            await db.execute(text("delete from predictions where source is null or source = 'legacy'"))
        if station_ids:
            for table, column in station_counts:
                await db.execute(text(f"delete from {table} where {column} like :p"), {"p": TEST_STATION_LIKE})
            await db.execute(text("delete from stations where id like :p"), {"p": TEST_STATION_LIKE})
        if "leftovers" in only:
            await db.execute(text(f"delete from satellite_frames where {FULL_DISK_FRAME}"))
            await db.execute(text(f"delete from weather_history w using weather_history k where {SAME_WEATHER_ROW}"))
        await db.commit()
        _say(f"ฐานข้อมูล: ลบบัญชี {len(users)} พยากรณ์เก่า {n_pred} แถว สถานีทดสอบ {len(station_ids)} สถานี "
             f"(ข้อมูลที่ผูกอยู่ {sum(station_counts.values())} แถว) เฟรมที่ชี้ไปภาพทั้งดวง {n_frames} แถว สภาพอากาศซ้ำ {n_weather} แถว")

    # MinIO: ลบหลังฐานข้อมูลสำเร็จแล้ว
    for name in station_objects + leftover_objects:
        client.remove_object(SATELLITE_BUCKET, name)
    for bucket, objects in buckets:
        for name, version in objects:
            client.remove_object(bucket, name, version_id=version)
        client.remove_bucket(bucket)
    _say(f"MinIO: ลบไฟล์ภาพของสถานีทดสอบ {len(station_objects)} ไฟล์ ไฟล์ภาพทั้งดวง {len(leftover_objects)} ไฟล์ "
         f"และ bucket ทดสอบ {len(buckets)} bucket")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
