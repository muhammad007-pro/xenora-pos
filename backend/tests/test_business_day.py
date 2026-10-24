# -*- coding: utf-8 -*-
"""HISOBOT KUNI: kalendar / smena bo'yicha (feature/business-day, 2026-10).

MUAMMO (jonli, MANHATTAN): kechasi 01:00 gacha ishlaydigan do'konda yarim
tundan keyingi savdo kalendar bo'yicha ERTANGI kunga tushardi. Bundan tashqari
hisobotlarning kunlik qatorlari UTC bo'yicha (kun 05:00 dan), jami esa Toshkent
00:00 dan hisoblanardi — bitta hisobotda ikki qoida. `reports/sales` nasiyani
umuman ko'rmasdi.

Qotiriladi:
  1) SMENA rejimi: D kuni ochilgan smena, D+1 01:00 dagi savdo → D kuniga
  2) HIMOYA: uzoq ochiq smena (D−5 da ochilgan) → D+1 03:00 savdo D+1 da qoladi
  3) shift_id NULL → kalendar kuni, YO'QOLMAYDI
  4) KALENDAR rejimi: avvalgidek (tungi savdo ertangi kunda)
  5) Jami == Σ kunlik qatorlar (reports/sales, reports/profit) — ikkala rejimda
  6) Nasiya reports/sales da sotuv kunida ko'rinadi
  7) profit/summary == store-margin == analytics/summary (GOLDEN mosligi)
  8) Sozlama endpointi + uzoq ochiq smena ogohlantirishi

⚠️ SQLite TUZOG'I: SQLite vaqtni zonasiz saqlaydi va filtrni DEVOR SOATI
bo'yicha solishtiradi, `to_local()` esa zonasiz qiymatni UTC deb o'qiydi.
Toshkent (+5) bilan bu ikkisi testda bir-biriga zid bo'lardi. Shu sabab
endpoint testlarida mahalliy zona UTC ga tenglanadi (`_utc_local` fikstura) —
mantiq (yarim tun, 06:00 chegara, smena kuni) aynan shu. Zona konvertatsiyasi
alohida sof testda (aware vaqtlar bilan, Toshkent zonasida) tekshiriladi.

Ishga tushirish:  cd backend && py -m pytest tests/test_business_day.py -v -p no:randomly
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import core.timeutils as tu
from core import business_day as bdmod
from core.business_day import BusinessDay, MODE_CALENDAR, MODE_SHIFT, set_mode
from core.security import get_password_hash
from database import Base, get_db
from main import app
from models import (Cafe, Category, Order, OrderItem, Payment, Permission, Product,
                    Role, Shift, User)

PW = "BizDay9x"
PHONE = "+998900000303"
MARJA = 0.5


@pytest.fixture()
def _utc_local(monkeypatch):
    """Mahalliy zona = UTC (yuqoridagi SQLite tuzog'i izohi)."""
    monkeypatch.setattr(tu, "_local_tz", lambda tz_name=None: timezone.utc)


@pytest.fixture()
def db_session(_utc_local):
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


def _at(d, hour, minute=0):
    """D kuni HH:MM (mahalliy = UTC, naive — SQLite ustuni uchun)."""
    return datetime(d.year, d.month, d.day) + timedelta(hours=hour, minutes=minute)


@pytest.fixture()
def seeded(db_session):
    db = db_session
    perms = [Permission(code=c, description=c)
             for c in ("view_analytics", "view_finance", "view_reports", "manage_settings")]
    db.add_all(perms); db.flush()
    role = Role(name="admin", description="Administrator"); role.permissions = perms
    db.add(role); db.flush()
    cafe = Cafe(name="TUN", code="t", access_code="100.200.303",
                business_type="store", subscription_plan="pro", is_active=True)
    db.add(cafe); db.flush()
    kat = Category(name="KAT", tenant_id=cafe.id); db.add(kat); db.flush()
    user = User(username="u303", email="303@x.uz", full_name="ADMIN", phone=PHONE,
                hashed_password=get_password_hash(PW), is_active=True,
                is_superuser=False, tenant_id=cafe.id, role_id=role.id)
    db.add(user); db.flush()

    D = tu.tenant_now().date() - timedelta(days=3)
    N = D + timedelta(days=1)
    # `/shifts/open-alerts` O'TGAN SOATNI `utc_now()` dan hisoblaydi → seed ham
    # shu asosda (kalendar "kun 10:00" UTC 10:00 gacha 7 kun berardi).
    s_old = Shift(tenant_id=cafe.id, user_id=user.id,
                  start_time=tu.utc_now() - timedelta(days=8, hours=1))
    s_day = Shift(tenant_id=cafe.id, user_id=user.id, start_time=_at(D, 9),
                  end_time=_at(N, 1, 30))
    s_next = Shift(tenant_id=cafe.id, user_id=user.id, start_time=_at(N, 10),
                   end_time=_at(N, 22))
    db.add_all([s_old, s_day, s_next]); db.flush()

    plan = [
        # (vaqt, smena, summa, usul, holat)
        (_at(D, 12),   s_day.id,  100.0, "cash",   "paid"),
        (_at(N, 1),    s_day.id,  200.0, "cash",   "paid"),     # tungi → D (smena)
        (_at(N, 2),    None,      400.0, "card",   "paid"),     # smenasiz → N
        (_at(N, 12),   s_next.id, 800.0, "credit", "pending"),  # nasiya → N
        (_at(N, 3),    s_old.id, 1600.0, "cash",   "paid"),     # himoya → N
    ]
    for i, (ts, sid, amt, method, status) in enumerate(plan):
        p = Product(name=f"P{i}", price=amt, cost_price=amt * MARJA, sale_unit="pcs",
                    category_id=kat.id, tenant_id=cafe.id, is_active=True)
        db.add(p); db.flush()
        o = Order(order_number=f"B{i:04d}", tenant_id=cafe.id, status="completed",
                  total_amount=amt, final_amount=amt, discount_amount=0,
                  shift_id=sid, waiter_id=user.id, created_at=ts)
        db.add(o); db.flush()
        db.add(OrderItem(order_id=o.id, product_id=p.id, quantity=1, tenant_id=cafe.id,
                         unit_price=amt, total_price=amt, unit_cost=amt * MARJA))
        db.add(Payment(tenant_id=cafe.id, order_id=o.id, amount=amt, method=method,
                       status=status, cashier_id=user.id, created_at=ts))
    db.commit()
    return {"cafe": cafe.id, "D": D, "N": N, "s_old": s_old.id}


@pytest.fixture()
def client(db_session):
    def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _hdr(client):
    r = client.post("/api/v1/auth/login", data={"username": PHONE, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _get(client, hdr, url):
    r = client.get(f"/api/v1{url}", headers=hdr)
    assert r.status_code == 200, f"{url} -> {r.status_code}: {r.text}"
    return r.json()


def _day(d1, d2=None):
    return f"date_from={d1.isoformat()}&date_to={(d2 or d1).isoformat()}"


#: rejim → {kun: sotuv (nasiya bilan)}
KUTILGAN = {
    MODE_CALENDAR: {"D": 100.0, "N": 3000.0},
    MODE_SHIFT:    {"D": 300.0, "N": 2800.0},
}


def _set(db_session, seeded, mode):
    set_mode(db_session, seeded["cafe"], mode)


@pytest.mark.parametrize("mode", [MODE_CALENDAR, MODE_SHIFT])
def test_jami_hamma_ekranda_bir_xil_va_rejimga_mos(db_session, seeded, client, mode):
    _set(db_session, seeded, mode)
    h = _hdr(client)
    for key in ("D", "N"):
        q = _day(seeded[key])
        want = KUTILGAN[mode][key]
        assert _get(client, h, f"/analytics/summary?{q}")["total_revenue"] == want
        assert _get(client, h, f"/profit/summary?{q}")["revenue"] == want
        assert _get(client, h, f"/analytics/store-margin?{q}")["total_revenue"] == want
        assert round(_get(client, h, f"/reports/profit?{q}")["total_revenue"], 2) == want
        # reports/sales ham nasiya bilan — boshqa ekranlarga TENG
        assert _get(client, h, f"/reports/sales?{q}")["total_sales"] == want


def test_smena_rejimi_tungi_savdo_smena_kuniga(db_session, seeded, client):
    _set(db_session, seeded, MODE_SHIFT)
    h = _hdr(client)
    D, N = seeded["D"], seeded["N"]
    r = _get(client, h, f"/reports/profit?{_day(D, N)}")
    kunlar = {row["date"]: row["revenue"] for row in r["daily"]}
    assert kunlar == {D.isoformat(): 300.0, N.isoformat(): 2800.0}


def test_kalendar_rejimi_avvalgidek(db_session, seeded, client):
    h = _hdr(client)   # sozlama yozilmagan → standart kalendar
    D, N = seeded["D"], seeded["N"]
    r = _get(client, h, f"/reports/profit?{_day(D, N)}")
    kunlar = {row["date"]: row["revenue"] for row in r["daily"]}
    assert kunlar == {D.isoformat(): 100.0, N.isoformat(): 3000.0}


def test_smenasiz_savdo_kalendar_kuniga_tushadi_yoqolmaydi(db_session, seeded, client):
    _set(db_session, seeded, MODE_SHIFT)
    h = _hdr(client)
    N = seeded["N"]
    r = _get(client, h, f"/reports/sales?{_day(N)}")
    assert r["payment_methods"]
    card = {m["method"]: m["total"] for m in r["payment_methods"]}["card"]
    assert card == 400.0          # N 02:00 dagi smenasiz savdo — N kunida


def test_himoya_uzoq_ochiq_smena_savdosi_kalendar_kunida(db_session, seeded):
    bd = BusinessDay(db_session, tenant_id=seeded["cafe"], mode=MODE_SHIFT)
    N = seeded["N"]
    o = db_session.query(Order).filter(Order.shift_id == seeded["s_old"]).one()
    assert bd.day_of(o.created_at, o.shift_id) == N


@pytest.mark.parametrize("mode", [MODE_CALENDAR, MODE_SHIFT])
def test_jami_kunlik_qatorlar_yigindisiga_teng(db_session, seeded, client, mode):
    _set(db_session, seeded, mode)
    h = _hdr(client)
    q = _day(seeded["D"], seeded["N"])
    s = _get(client, h, f"/reports/sales?{q}")
    assert sum(r["total"] for r in s["daily_sales"]) == s["total_sales"] == 3100.0
    p = _get(client, h, f"/reports/profit?{q}")
    assert round(sum(r["revenue"] for r in p["daily"]), 2) == round(p["total_revenue"], 2) == 3100.0
    t = _get(client, h, f"/profit/timeline?{q}")
    assert sum(pt["revenue"] for pt in t["points"]) == 3100.0


def test_nasiya_sotuv_kunida_korinadi(db_session, seeded, client):
    h = _hdr(client)
    r = _get(client, h, f"/reports/sales?{_day(seeded['N'])}")
    assert r["credit_sales"] == 800.0
    assert r["paid_sales"] == 2200.0
    assert {m["method"]: m["total"] for m in r["payment_methods"]}["credit"] == 800.0


def test_bekor_qilingan_nasiya_sotuvga_kirmaydi(db_session, seeded, client):
    o = db_session.query(Order).filter(Order.final_amount == 800.0).one()
    o.status = "cancelled"
    db_session.commit()
    h = _hdr(client)
    r = _get(client, h, f"/reports/sales?{_day(seeded['N'])}")
    assert r["credit_sales"] == 0.0


def test_sozlama_endpointi(db_session, seeded, client):
    h = _hdr(client)
    assert _get(client, h, "/settings/report-day")["mode"] == MODE_CALENDAR
    r = client.patch("/api/v1/settings/report-day", json={"mode": "shift"}, headers=h)
    assert r.status_code == 200, r.text
    assert _get(client, h, "/settings/report-day") == {"mode": "shift", "grace_hours": 6}
    bad = client.patch("/api/v1/settings/report-day", json={"mode": "x"}, headers=h)
    assert bad.status_code == 400


def test_uzoq_ochiq_smena_ogohlantirishi(db_session, seeded, client):
    h = _hdr(client)
    a = _get(client, h, "/shifts/open-alerts")["alerts"]
    assert [x["shift_id"] for x in a] == [seeded["s_old"]]
    assert a[0]["days_open"] == 8
    assert a[0]["message"] == f"Smena {a[0]['days_open']} kundan beri ochiq"


def test_bugun_tunda_kechagi_ochiq_smena_kuni(db_session, seeded, monkeypatch):
    """Smena rejimida 01:00 da kecha ochilgan smena hali ochiq → "bugun" = kecha."""
    N = seeded["N"]
    sh = Shift(tenant_id=seeded["cafe"], user_id=None, start_time=_at(N, 18))
    db_session.add(sh); db_session.commit()
    fake_now = datetime(N.year, N.month, N.day, tzinfo=timezone.utc) + timedelta(days=1, hours=1)
    monkeypatch.setattr(bdmod, "tenant_now", lambda tz_name=None: fake_now)
    bd = BusinessDay(db_session, tenant_id=seeded["cafe"], mode=MODE_SHIFT)
    assert bd.today() == N
    assert BusinessDay(db_session, tenant_id=seeded["cafe"], mode=MODE_CALENDAR).today() == N + timedelta(days=1)


def test_toshkent_zonasi_sof_day_of(monkeypatch):
    """Zona konvertatsiyasi — haqiqiy Toshkent (+5), aware vaqtlar (PostgreSQL kabi)."""
    monkeypatch.setattr(tu, "_local_tz", lambda tz_name=None: timezone(timedelta(hours=5)))
    bd = BusinessDay(None, tenant_id=1, mode=MODE_SHIFT)
    from datetime import date
    bd._shift_day = {7: date(2026, 10, 10)}
    utc = timezone.utc
    # Toshkent 11.10 01:00 = UTC 10.10 20:00, smena 10.10 da → 10.10
    assert bd.day_of(datetime(2026, 10, 10, 20, 0, tzinfo=utc), 7) == date(2026, 10, 10)
    # Toshkent 11.10 06:30 = UTC 11.10 01:30 → chegaradan keyin → 11.10
    assert bd.day_of(datetime(2026, 10, 11, 1, 30, tzinfo=utc), 7) == date(2026, 10, 11)
    # smenasiz → kalendar 11.10
    assert bd.day_of(datetime(2026, 10, 10, 20, 0, tzinfo=utc), None) == date(2026, 10, 11)
    # kalendar rejimi → doim kalendar
    cal = BusinessDay(None, tenant_id=1, mode=MODE_CALENDAR)
    assert cal.day_of(datetime(2026, 10, 10, 20, 0, tzinfo=utc), 7) == date(2026, 10, 11)


def test_kalendar_rejimida_filtr_aynan_avvalgi_shart(db_session):
    """GOLDEN: kalendar rejimida window() = `ts >= start AND ts <= end` (SQL matni bir xil)."""
    from sqlalchemy import and_
    bd = BusinessDay(db_session, tenant_id=1, mode=MODE_CALENDAR)
    s, e = tu.day_bounds(tu.tenant_now().date())
    got = bd.window(Order.created_at, Order.shift_id, s, e)
    want = and_(Order.created_at >= s, Order.created_at <= e)
    assert str(got.compile()) == str(want.compile())
