# -*- coding: utf-8 -*-
"""DAVR TA'RIFI BIRXILLASHTIRILDI + sana oralig'i (2026-09).

MUAMMO (jonli, FAZZA): bir xil "7 kun" uchun ikki foyda ekrani 984 000 so'm
farq ko'rsatardi.
  * profit.py:_period_range  -> KALENDAR kun (bugun-6 00:00 ... bugun oxiri)
  * analytics.py (11 joyda)  -> SURILUVCHI 168 SOAT (`tenant_now() - 7 days`)

168 soatlik oyna kun bo'yi "suzib" turadi: bugun 14:00 bo'lsa, 7 kun oldingi
kunning 14:00 dan KEYINGI savdosi hisobga kiradi, ERTALABKISI kirmaydi.

Bu fayl to'rt narsani qotiradi:
  1) GOLDEN - `/profit/summary` va `/analytics/store-margin` bir xil davr uchun
     AYNAN bir xil jami tushum beradi (period va date_from/date_to bilan ham)
  2) KALENDAR ta'rif - kun-(-7) dagi savdo "7 kun" ga KIRMAYDI (168 soat bilan
     kirardi), kun-(-6) dagi esa KIRADI
  3) date_from/date_to ishlaydi, KELAJAK kesiladi, buzuq sana -> 400
  4) `period` parametri SAQLANGAN - eski klientlar buzilmaydi

Ishga tushirish:  cd backend && py -m pytest tests/test_date_range_unified.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.security import get_password_hash
from core.timeutils import day_bounds, period_bounds, period_dates, report_bounds, tenant_now
from database import Base, get_db
from main import app
from models import Cafe, Category, Order, OrderItem, Permission, Product, Role, User

PW    = "DavrTest9x"
PHONE = "+998900000202"

#: kun siljishi -> shu kundagi savdo summasi. Har xil summa - qaysi kun
#: qamralgani raqamdan ANIQ bilinadi (yig'indi yagona yechimga ega).
SAVDO = {
    0:    10_000.0,   # bugun
    -1:   20_000.0,
    -3:   40_000.0,
    -6:   60_000.0,   # "7 kun" ning ENG CHETI - kirishi SHART
    -7:  100_000.0,   # "7 kun" dan TASHQARI - 168 soatlik oyna bilan kirardi
    -40:  80_000.0,   # "30 kun" dan tashqari
}
MARJA = 0.6  # tan narx = narx * 0.6


@pytest.fixture()
def db_session():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng, autocommit=False, autoflush=False)()
    try:
        yield s
    finally:
        s.close()
        Base.metadata.drop_all(eng)
        eng.dispose()


def _naive_local(dt):
    """SQLite ustunlari naive saqlaydi - aware qiymatni naive mahalliyga keltiradi."""
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


@pytest.fixture()
def seeded(db_session):
    db = db_session
    perms = [Permission(code=c, description=c) for c in ("view_analytics", "view_finance")]
    db.add_all(perms); db.flush()
    role = Role(name="admin", description="Administrator"); role.permissions = perms
    db.add(role); db.flush()

    cafe = Cafe(name="DAVR", code="d", access_code="100.200.202",
                business_type="supermarket", subscription_plan="pro", is_active=True)
    db.add(cafe); db.flush()
    kat = Category(name="KAT", tenant_id=cafe.id); db.add(kat); db.flush()
    db.add(User(username="u202", email="202@x.uz", full_name="ADMIN", phone=PHONE,
                hashed_password=get_password_hash(PW), is_active=True,
                is_superuser=False, tenant_id=cafe.id, role_id=role.id))

    today  = tenant_now().date()
    kunlar = {}
    for i, (siljish, narx) in enumerate(sorted(SAVDO.items())):
        d = today + timedelta(days=siljish)
        # Savdo vaqti: o'tgan kunlar uchun KUN OXIRIGA yaqin (23:00). Aynan shu
        # nuqta ikki ta'rifni ajratadi - 168 soatlik oyna kun-(-7) ning 23:00 ini
        # QAMRARDI, kalendar ta'rif esa yo'q. Bugungi savdo `end = now` dan
        # oshib ketmasligi kerak -> 1 soat orqaga olinadi.
        start_d, _ = day_bounds(d)
        vaqt = start_d.replace(hour=23) if siljish < 0 else tenant_now() - timedelta(hours=1)
        if vaqt < start_d:                    # yarim tundan keyin ishga tushsa
            vaqt = start_d
        tan = narx * MARJA
        p = Product(name=f"P{i}", price=narx, cost_price=tan, sale_unit="pcs",
                    category_id=kat.id, tenant_id=cafe.id, is_active=True)
        db.add(p); db.flush()
        o = Order(order_number=f"D{i:04d}", tenant_id=cafe.id, status="completed",
                  total_amount=narx, final_amount=narx, discount_amount=0,
                  created_at=_naive_local(vaqt))
        db.add(o); db.flush()
        db.add(OrderItem(order_id=o.id, product_id=p.id, quantity=1,
                         unit_price=narx, total_price=narx, unit_cost=tan))
        kunlar[siljish] = {"sana": d, "narx": narx}
    db.commit()
    return {"cafe": cafe.id, "today": today, "kunlar": kunlar}


@pytest.fixture()
def client(db_session):
    def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _login(client):
    r = client.post("/api/v1/auth/login", data={"username": PHONE, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _get(client, hdr, url, code=200):
    r = client.get(f"/api/v1{url}", headers=hdr)
    assert r.status_code == code, f"{url} -> {r.status_code}: {r.text}"
    return r.json()


def _kutilgan(*siljishlar):
    return sum(SAVDO[s] for s in siljishlar)


# ==============================================================================
# 1) GOLDEN - ikki ekran bir xil jami tushum
# ==============================================================================

@pytest.mark.parametrize("period", ["today", "week", "month"])
def test_golden_ikki_ekran_bir_xil_tushum(seeded, client, period):
    """`/profit/summary` va `/analytics/store-margin` AJRALMASIN.

    Aynan shu farq FAZZA'da 984 000 so'm bo'lib ko'rinardi.
    """
    hdr = _login(client)
    p = _get(client, hdr, f"/profit/summary?period={period}")
    m = _get(client, hdr, f"/analytics/store-margin?period={period}")
    assert m["total_revenue"] == pytest.approx(p["revenue"], abs=1), (
        f"period={period}: profit={p['revenue']} margin={m['total_revenue']}"
    )


def test_golden_ikki_ekran_sana_oraligida_ham_bir_xil(seeded, client):
    """date_from/date_to bilan ham ikkala ekran bir xil qolsin."""
    hdr   = _login(client)
    today = seeded["today"]
    df    = (today - timedelta(days=7)).isoformat()
    dt    = today.isoformat()
    p = _get(client, hdr, f"/profit/summary?date_from={df}&date_to={dt}")
    m = _get(client, hdr, f"/analytics/store-margin?date_from={df}&date_to={dt}")
    assert m["total_revenue"] == pytest.approx(p["revenue"], abs=1)
    # 8 kunlik oraliq -> kun-(-7) ham ichida
    assert p["revenue"] == pytest.approx(_kutilgan(0, -1, -3, -6, -7), abs=1)


# ==============================================================================
# 2) KALENDAR ta'rif - 168 soatlik oyna yo'q
# ==============================================================================

def test_hafta_kalendar_kun_boyicha(seeded, client):
    """"7 kun" = bugun-6 ... bugun. kun-(-7) dagi 23:00 savdosi KIRMASIN.

    ILGARI (`now - timedelta(days=7)`): kun-(-7) ning 23:00 i oynaga tushardi
    (hozir 23:00 dan oldin bo'lsa) -> hafta jami 100 000 ga oshiq chiqardi.
    """
    hdr = _login(client)
    for url in ("/profit/summary?period=week", "/analytics/store-margin?period=week"):
        d   = _get(client, hdr, url)
        got = d.get("revenue", d.get("total_revenue"))
        assert got == pytest.approx(_kutilgan(0, -1, -3, -6), abs=1), url


def test_bugun_faqat_bugungi_savdo(seeded, client):
    hdr = _login(client)
    d = _get(client, hdr, "/profit/summary?period=today")
    assert d["revenue"] == pytest.approx(SAVDO[0], abs=1)


def test_oy_30_kalendar_kun(seeded, client):
    """"30 kun" = bugun-29 ... bugun -> kun-(-40) kirmaydi."""
    hdr = _login(client)
    d = _get(client, hdr, "/analytics/store-margin?period=month")
    assert d["total_revenue"] == pytest.approx(_kutilgan(0, -1, -3, -6, -7), abs=1)


def test_all_hammasini_qamraydi(seeded, client):
    hdr = _login(client)
    d = _get(client, hdr, "/analytics/store-margin?period=all")
    assert d["total_revenue"] == pytest.approx(sum(SAVDO.values()), abs=1)


# ==============================================================================
# 3) date_from / date_to
# ==============================================================================

def test_bitta_kunlik_oraliq(seeded, client):
    """Aniq bitta kun -> faqat shu kunning savdosi."""
    hdr = _login(client)
    d3  = (seeded["today"] - timedelta(days=3)).isoformat()
    for url, key in (("/profit/summary", "revenue"),
                     ("/analytics/store-margin", "total_revenue")):
        d = _get(client, hdr, f"{url}?date_from={d3}&date_to={d3}")
        assert d[key] == pytest.approx(SAVDO[-3], abs=1), url


def test_date_from_period_dan_ustun(seeded, client):
    """`period=today` berilsa ham `date_from` ustun turadi."""
    hdr = _login(client)
    d40 = (seeded["today"] - timedelta(days=40)).isoformat()
    d   = _get(client, hdr, f"/analytics/store-margin?period=today&date_from={d40}&date_to={d40}")
    assert d["total_revenue"] == pytest.approx(SAVDO[-40], abs=1)


def test_kelajak_sanasi_kesiladi(seeded, client):
    """Ertangi oraliq -> 0 (bugungi savdoni QAYTARMASIN)."""
    hdr = _login(client)
    ert = (seeded["today"] + timedelta(days=1)).isoformat()
    for url, key in (("/profit/summary", "revenue"),
                     ("/analytics/store-margin", "total_revenue")):
        d = _get(client, hdr, f"{url}?date_from={ert}&date_to={ert}")
        assert d[key] == pytest.approx(0, abs=1), f"{url} kelajakni kesmadi: {d[key]}"


def test_kelajak_date_to_bugunga_qisqaradi(seeded, client):
    """`date_to` kelajakda bo'lsa - bugunda to'xtaydi, xato bermaydi."""
    hdr = _login(client)
    d1  = (seeded["today"] - timedelta(days=1)).isoformat()
    kel = (seeded["today"] + timedelta(days=365)).isoformat()
    d   = _get(client, hdr, f"/analytics/store-margin?date_from={d1}&date_to={kel}")
    assert d["total_revenue"] == pytest.approx(_kutilgan(0, -1), abs=1)


@pytest.mark.parametrize("url", [
    "/analytics/store-margin?date_from=2026-13-45",
    "/analytics/store-margin?date_to=bugun",
    "/analytics/summary?date_from=29.09.2026",
    "/profit/summary?date_from=not-a-date",
    "/profit/timeline?date_from=2026-9-31",
])
def test_buzuq_sana_400(seeded, client, url):
    """Buzuq sana -> 400 (ilgari ushlanmagan ValueError -> 500 edi)."""
    hdr = _login(client)
    _get(client, hdr, url, code=400)


# ==============================================================================
# 4) `period` SAQLANGAN - eski klientlar buzilmaydi
# ==============================================================================

ESKI_KLIENT_URLS = [
    "/analytics/summary?period=week",
    "/analytics/waiter-report?period=today",
    "/analytics/cashier-report?period=month",
    "/analytics/store-margin?period=all",
    "/analytics/abc-analysis?period=quarter",
    "/analytics/turnover?period=week",
    "/profit/summary?period=week",
    "/profit/expenses?period=month",
    # `/profit/timeline` bu ro'yxatda YO'Q: u PostgreSQL `date_trunc()` ga
    # tayanadi (profit.py:597) — SQLite test bazasida ishlamaydi. Bu SHU
    # o'zgarishdan OLDIN ham shunday edi; sana tekshiruvi (400) baribir
    # sinaladi, chunki u SQL'ga yetmasdan ishlaydi.
    "/profit/top-products?days=7",
    "/profit/by-category?days=7",
]


@pytest.mark.parametrize("url", ESKI_KLIENT_URLS)
def test_eski_period_parametri_ishlaydi(seeded, client, url):
    _get(client, _login(client), url)


YANGI_URLS = [
    "/analytics/summary",
    "/analytics/waiter-report",
    "/analytics/cashier-report",
    "/analytics/store-margin",
    "/analytics/abc-analysis",
    "/analytics/turnover",
    "/analytics/peak-hours",
    "/profit/summary",
    "/profit/expenses",
    "/profit/top-products",
    "/profit/by-category",
]


@pytest.mark.parametrize("url", YANGI_URLS)
def test_yangi_sana_parametrlari_qabul_qilinadi(seeded, client, url):
    """14+4 endpoint date_from/date_to ni qabul qilsin (additiv)."""
    hdr = _login(client)
    df  = (seeded["today"] - timedelta(days=3)).isoformat()
    _get(client, hdr, f"{url}?date_from={df}&date_to={seeded['today'].isoformat()}")


# ==============================================================================
# 5) Yagona manba - sof funksiya darajasida
# ==============================================================================

def test_period_dates_kalendar_kun():
    today = tenant_now().date()
    assert period_dates("today")   == (today, today)
    assert period_dates("week")    == (today - timedelta(days=6), today)
    assert period_dates("month")   == (today - timedelta(days=29), today)
    assert period_dates("quarter") == (today - timedelta(days=89), today)


def test_period_bounds_kun_chegarasi():
    """start = 00:00, end = kun oxiri (bugun uchun `now` da kesiladi)."""
    today = tenant_now().date()
    s, e  = period_bounds("week")
    assert (s.hour, s.minute, s.second) == (0, 0, 0)
    assert s.date() == today - timedelta(days=6)
    assert e <= tenant_now()


def test_profit_va_analytics_bir_xil_oraliq():
    """Ikki router AYNAN bir xil funksiyadan davr oladi."""
    import routers.profit as pr
    for period in ("today", "week", "month"):
        assert pr._period_range(period, None, None) == period_dates(period)


def test_report_dates_xulqi_ozgarmadi():
    """`report.py:_dates()` = `report_bounds()`, standart 30 kun, kun to'liq."""
    import routers.report as rp
    assert rp._dates is report_bounds

    today = tenant_now().date()
    s, e  = rp._dates(None, None)
    assert s.date() == today - timedelta(days=30)
    assert (e.date(), e.hour, e.minute, e.second) == (today, 23, 59, 59)

    # P0-3: `date_from = date_to = bugun` TO'LIQ kunni qamrasin (bo'sh emas)
    s, e = rp._dates(today.isoformat(), today.isoformat())
    assert s.date() == today and e.date() == today
    assert (e - s) > timedelta(hours=23)
