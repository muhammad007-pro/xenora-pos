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

DIQQAT (fayl tarixi): bu fayl `test_*.py` deb nomlangan, lekin ichida `test_`
funksiya YO'Q edi — qo'lda ishlatiladigan skript edi. Ya'ni `pytest` uni "0 ta
test" deb jimgina o'tkazib yuborardi va qo'riqchi AMALDA YO'Q edi. Endi haqiqiy
pytest testlari.

Ishga tushirish:  cd backend && py -m pytest tests/test_dashboard_timezone.py -v
"""
import asyncio
import calendar
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from core.timeutils import tenant_now, to_local
from database import Base
from models import Category, Order, OrderItem, Product

import routers.analytics as an


# ── Postgres `to_char` uchun sqlite shim ─────────────────────────────────────
# AnalyticsService daromad grafigini `to_char(...)` bilan guruhlaydi — bu faqat
# Postgres'da bor. Testlar sqlite'da ishlaydi, shim bo'lmasa /dashboard chaqiruvi
# OperationalError beradi va T5 ni HAQIQIY endpoint bilan sinab bo'lmaydi.
_TO_CHAR_FMT = {
    "YYYY-MM-DD HH24:00": "%Y-%m-%d %H:00",
    "YYYY-MM-DD": "%Y-%m-%d",
    "YYYY-MM": "%Y-%m",
}


def _sqlite_to_char(value, fmt):
    if value is None:
        return None
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if fmt == "IYYY-IW":                       # ISO yil-hafta
        iso = dt.isocalendar()
        return f"{iso[0]:04d}-{iso[1]:02d}"
    return dt.strftime(_TO_CHAR_FMT.get(fmt, "%Y-%m-%d"))


# ── Soxta foydalanuvchilar ───────────────────────────────────────────────────
class _Perm:
    def __init__(self, code):
        self.code = code


class _Role:
    def __init__(self, codes):
        self.permissions = [_Perm(c) for c in codes]


class _User:
    """Oddiy admin — view_finance YO'Q (kassir/ofitsiant darajasi)."""
    is_superuser = False
    tenant_id = 1
    id = 1
    role = None


class _FinanceUser(_User):
    """Moliyani ko'ra oladigan foydalanuvchi — sof foyda + oylik maqsad ochiladi."""
    role = _Role(["view_analytics", "view_finance"])


# ── Fixtura ──────────────────────────────────────────────────────────────────
@pytest.fixture()
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})

    @event.listens_for(eng, "connect")
    def _register_to_char(dbapi_conn, _rec):   # create_all'dan OLDIN ulanishi shart
        dbapi_conn.create_function("to_char", 2, _sqlite_to_char)

    Base.metadata.create_all(bind=eng)
    session = sessionmaker(bind=eng)()
    session.add(Category(id=1, name="Parfum", tenant_id=1))
    session.add(Product(id=1, name="Ayva", price=45000, cost_price=30000,
                        category_id=1, tenant_id=1))
    session.commit()
    yield session
    session.close()


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


def _dashboard(db, user):
    return asyncio.run(an.get_dashboard_data(range="today", db=db, current_user=user))


def _freeze(monkeypatch, y, m, d, hour=12):
    """`tenant_now()` ni qotirish — days_left ni AYNIQ son bilan sinash uchun."""
    frozen = tenant_now().replace(year=y, month=m, day=d, hour=hour,
                                  minute=0, second=0, microsecond=0)
    monkeypatch.setattr(an, "tenant_now", lambda: frozen)
    return frozen


# ── T1: SOTUVSIZ do'kon — ilgari ham ishlardi, buzilmasin ────────────────────
def test_sotuvsiz_dokon(db):
    _seed(db, [])
    r = _summary(db)
    assert r["total_revenue"] == 0
    assert r["total_orders"] == 0
    assert len(r["daily_revenue"]) == 7


# ── T2: SOTUV BOR — ASOSIY REGRESSIYA (ilgari bu yerda 500 bo'lardi) ─────────
def test_sotuv_bor_endpoint_qulamaydi(db):
    # DIQQAT: "now - 2 soat" ISHLATILMAYDI — test yarim tundan keyin ishga
    # tushirilsa u KECHAGI kunga tushib, testni yolg'on yiqitadi (aynan shunday
    # bo'ldi). Mahalliy kun boshidan +1 soat — har doim BUGUN ichida.
    now = tenant_now()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    _seed(db, [day_start + timedelta(hours=1)])
    r = _summary(db)                 # eski (buzuq) kodda shu yerda TypeError -> 500
    assert r["total_revenue"] == 45000
    assert r["total_orders"] == 1
    assert len(r["daily_revenue"]) == 7


# ── T3: YARIM TUNDAN KEYINGI sotuv (00:57 Toshkent) o'z kuniga tushsin ───────
def test_yarim_tundagi_sotuv_oz_kuniga_tushadi(db):
    # Chekdagi haqiqiy holat. UTC'da bu OLDINGI kun (19:57) — noto'g'ri kunga
    # tushmasligi kerak.
    now = tenant_now()
    local_0057 = now.replace(hour=0, minute=57, second=0, microsecond=0)
    if local_0057 > now:                       # hozir 00:57 dan oldin bo'lsa
        local_0057 -= timedelta(days=1)
    _seed(db, [local_0057])
    r = _summary(db)

    own_day = local_0057.date().isoformat()
    row = next((d for d in r["daily_revenue"] if d["date"] == own_day), None)
    assert row is not None, f"{own_day} grafikda yo'q"
    assert row["revenue"] == 45000

    # UTC'da bu sotuv oldingi kunga tushardi — o'sha kun BO'SH bo'lishi kerak
    utc_day = local_0057.astimezone(timezone.utc).date().isoformat()
    if utc_day != own_day:
        wrong = next((d for d in r["daily_revenue"] if d["date"] == utc_day), None)
        assert (wrong or {}).get("revenue", 0) == 0


# ── T4: to_local() — UTC timestampni Toshkent kuniga to'g'ri o'giradi ────────
def test_to_local_utc_dan_toshkentga():
    utc_1957 = datetime(2026, 8, 14, 19, 57, tzinfo=timezone.utc)
    assert to_local(utc_1957).date().isoformat() == "2026-08-15"
    assert to_local(utc_1957).hour == 0
    # naive qiymat UTC deb qaraladi (DB ustunlari UTC saqlaydi)
    assert to_local(datetime(2026, 8, 14, 19, 57)).date().isoformat() == "2026-08-15"


def test_to_local_solishtirish_xato_bermaydi():
    # aware/naive aralashuvi endi YO'Q — aynan shu TypeError dashboardni buzgan edi.
    # Solishtirishning O'ZI muhim: TypeError chiqsa test shu yerda yiqiladi.
    assert isinstance(to_local(datetime(2026, 8, 14, 19, 57)) <= tenant_now(), bool)


# ── T5: oylik maqsad — qolgan kunlar BUGUNNI sanamaydi ───────────────────────
# HAQIQIY endpoint chaqiriladi (ilgari bu yerda sof arifmetika sinalardi:
# `31 - 15 == 16` — backend kodiga TEGMASDI, ya'ni `+ 1` qaytsa ushlamasdi).
def test_days_left_bugunni_sanamaydi(db, monkeypatch):
    """15-avgust — mijoz aytgan holat: 16 kutiladi (ilgari `+ 1` bilan 17 chiqardi)."""
    frozen = _freeze(monkeypatch, 2026, 8, 15)
    _seed(db, [frozen.replace(hour=10)])

    r = _dashboard(db, _FinanceUser())

    assert r["days_left"] == 16, "eski `last_day - now.day + 1` qaytib kelgan"
    assert r["days_left"] == calendar.monthrange(2026, 8)[1] - 15
    # moliya bloki HAQIQATAN bajarilgani (aks holda days_left None bo'lardi):
    assert r["net_profit"] == 15000        # 45000 sotuv - 30000 tannarx
    assert r["monthly_actual"] == 45000


def test_days_left_oyning_oxirgi_kunida_nol(db, monkeypatch):
    """Oxirgi kunda 0 — UI "oxirgi kun" deb ko'rsatadi ("0 kun ichida" emas)."""
    frozen = _freeze(monkeypatch, 2026, 8, 31)
    _seed(db, [frozen.replace(hour=10)])

    r = _dashboard(db, _FinanceUser())

    assert r["days_left"] == 0


def test_days_left_faqat_moliya_ruxsati_bilan(db, monkeypatch):
    """view_finance yo'q foydalanuvchiga maqsad ham, sof foyda ham KO'RINMAYDI."""
    frozen = _freeze(monkeypatch, 2026, 8, 15)
    _seed(db, [frozen.replace(hour=10)])

    r = _dashboard(db, _User())            # role=None -> view_finance yo'q

    assert r["days_left"] is None
    assert r["net_profit"] is None
    assert r["monthly_actual"] is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
