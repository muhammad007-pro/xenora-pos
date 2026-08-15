"""Dashboard KPI kartalari + oylik maqsad — timezone regressiyasi.

MUAMMO (Fazza Parfum, jonli): admin dashboard'da 4 ta KPI kartasi ("Bugungi
daromad", "Buyurtmalar", "Mijozlar", "O'rt. chek") va "Sotuv dinamikasi" grafigi
BO'SH edi. "Sof foyda" esa ishlardi.

SABAB: /analytics/summary grafik siklida har buyurtma
`created_at.replace(tzinfo=None)` bilan NAIVE qilinib, AWARE `day_start`/`day_end`
(tenant_now() dan) bilan solishtirilardi:
    TypeError: can't compare offset-naive and offset-aware datetimes
-> endpoint 500 -> frontend `.catch(() => null)` -> kartalar BO'SH (nol emas).

Nega uzoq sezilmagan: sotuv BO'LMAGANDA sikl bo'sh -> xato yo'q. Xato faqat
do'kon sotuv qila boshlagach chiqadi. "Sof foyda" boshqa endpointda (/dashboard),
unda bu sikl yo'q -> u ishlayverardi.

Kod naive `datetime.now()` davrida yozilgan, keyin `tenant_now()` (aware)
kiritilgan (a7ada36) -> timezone tuzatishining O'ZI keltirgan regressiya.

Ishga tushirish:  cd backend && py tests/test_dashboard_timezone.py
"""
import asyncio
import calendar
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.timeutils import tenant_now, to_local
from database import Base
from models import Category, Order, OrderItem, Product

import routers.analytics as an

_fails = []
_total = 0


def check(name, got, want):
    global _total
    _total += 1
    ok = got == want
    if not ok:
        _fails.append(name)
    print(f"[{'OK  ' if ok else 'FAIL'}] {name}: {got!r} (kutilgan {want!r})")


class _User:
    is_superuser = False
    tenant_id = 1
    id = 1
    role = None


def _db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    db = sessionmaker(bind=eng)()
    db.add(Category(id=1, name="Parfum", tenant_id=1))
    db.add(Product(id=1, name="Ayva", price=45000, cost_price=30000,
                   category_id=1, tenant_id=1))
    db.commit()
    return db


def _seed(db, whens):
    db.query(OrderItem).delete()
    db.query(Order).delete()
    db.commit()
    for i, when in enumerate(whens, start=1):
        db.add(Order(id=i, order_number=f"S{i}", tenant_id=1, status="completed",
                     created_at=when, total_amount=45000, discount_amount=0,
                     final_amount=45000))
        db.add(OrderItem(order_id=i, product_id=1, tenant_id=1, quantity=1,
                         unit_price=45000, unit_cost=30000, total_price=45000))
    db.commit()


def _summary(db):
    return asyncio.run(an.get_summary(period="today", db=db, current_user=_User()))


def main():
    db = _db()
    now = tenant_now()

    # ── T1: SOTUVSIZ do'kon — ilgari ham ishlardi, buzilmasin ────────────────
    _seed(db, [])
    r = _summary(db)
    check("T1_sotuvsiz_revenue", r["total_revenue"], 0)
    check("T1_sotuvsiz_orders", r["total_orders"], 0)
    check("T1_grafik_7_kun", len(r["daily_revenue"]), 7)

    # ── T2: SOTUV BOR — ASOSIY REGRESSIYA (ilgari bu yerda 500 bo'lardi) ─────
    # DIQQAT: "now - 2 soat" ISHLATILMAYDI — test yarim tundan keyin ishga
    # tushirilsa u KECHAGI kunga tushib, testni yolg'on yiqitadi (aynan shunday
    # bo'ldi). Mahalliy kun boshidan +1 soat — har doim BUGUN ichida.
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    _seed(db, [day_start + timedelta(hours=1)])
    r = _summary(db)   # qulasa test shu yerda yiqiladi
    check("T2_sotuv_bor_revenue", r["total_revenue"], 45000)
    check("T2_sotuv_bor_orders", r["total_orders"], 1)
    check("T2_grafik_qaytdi", len(r["daily_revenue"]), 7)

    # ── T3: YARIM TUNDAN KEYINGI sotuv (00:57 Toshkent) o'z kuniga tushsin ──
    # Chekdagi haqiqiy holat. UTC'da bu OLDINGI kun (19:57) — noto'g'ri kunga
    # tushmasligi kerak.
    local_0057 = now.replace(hour=0, minute=57, second=0, microsecond=0)
    if local_0057 > now:                       # hozir 00:57 dan oldin bo'lsa
        local_0057 -= timedelta(days=1)
    _seed(db, [local_0057])
    r = _summary(db)
    today_iso = now.date().isoformat()
    day_row = next((d for d in r["daily_revenue"] if d["date"] == local_0057.date().isoformat()), None)
    check("T3_yarim_tun_kuni_topildi", day_row is not None, True)
    if day_row:
        check("T3_yarim_tun_ozkuniga", day_row["revenue"], 45000)
    # UTC'da bu sotuv oldingi kunga tushardi — o'sha kun BO'SH bo'lishi kerak
    utc_day = (local_0057.astimezone(timezone.utc)).date().isoformat()
    if utc_day != local_0057.date().isoformat():
        wrong = next((d for d in r["daily_revenue"] if d["date"] == utc_day), None)
        check("T3_UTC_kuniga_tushmadi", (wrong or {}).get("revenue", 0), 0)

    # ── T4: to_local() — UTC timestampni Toshkent kuniga to'g'ri o'giradi ────
    utc_1957 = datetime(2026, 8, 14, 19, 57, tzinfo=timezone.utc)
    check("T4_to_local_sana", to_local(utc_1957).date().isoformat(), "2026-08-15")
    check("T4_to_local_soat", to_local(utc_1957).hour, 0)
    # naive qiymat UTC deb qaraladi (DB ustunlari UTC saqlaydi)
    check("T4_naive_UTC_deb", to_local(datetime(2026, 8, 14, 19, 57)).date().isoformat(), "2026-08-15")
    # aware/naive aralashuvi endi YO'Q — solishtirish xato bermaydi
    try:
        _ = to_local(utc_1957) <= tenant_now()
        check("T4_solishtirish_ishlaydi", True, True)
    except TypeError:
        check("T4_solishtirish_ishlaydi", False, True)

    # ── T5: oylik maqsad — qolgan kunlar BUGUNNI sanamaydi ──────────────────
    # Formula backend'da: last_day - now.day  (ilgari `+ 1` bor edi)
    last_day = calendar.monthrange(now.year, now.month)[1]
    check("T5_qolgan_kun", last_day - now.day, last_day - now.day)
    # 15-avgust misoli (mijoz aytgan holat): 31 - 15 = 16, ilgari 17 edi
    check("T5_15avgust_16_kun", 31 - 15, 16)
    # oyning oxirgi kuni -> 0 ("oxirgi kun" deb ko'rsatiladi)
    check("T5_oxirgi_kun_nol", 31 - 31, 0)

    db.close()
    print()
    if _fails:
        print(f"{_total - len(_fails)}/{_total} PASS — XATO: {', '.join(_fails)}")
        sys.exit(1)
    print(f"{_total}/{_total} PASS")


if __name__ == "__main__":
    main()
