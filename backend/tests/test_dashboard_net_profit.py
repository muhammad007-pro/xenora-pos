# -*- coding: utf-8 -*-
"""DASHBOARD: bugungi SOF foyda bloki (feature/dashboard-net-profit).

Blok: savdo − tannarx = yalpi foyda − xarajat ulushi = SOF foyda.
Raqamlar `/analytics/dashboard` → `profit_breakdown` da; u `/profit/summary`
endpoint funksiyasining O'ZINI chaqiradi — yangi formula YO'Q.

Qotiriladi:
  1) GOLDEN: profit_breakdown == /profit/summary?period=today (aynan)
  2) sof = yalpi − xarajat; taqsimlangan xarajatdan BUGUNGI ulush + bugungi
     oddiy xarajat; boshqa kunning oddiy xarajati kirmaydi
  3) xarajat 0 → qator 0, sof == yalpi
  4) smena rejimi: kechagi smenaning tungi savdosi bugungi blokka KIRMAYDI
  5) takroriy shablon nusxasi DASHBOARD ochilganda yaratiladi (bir marta)
  6) GOLDEN: mavjud maydonlar (net_profit=yalpi, total_orders) o'zgarmagan
  7) view_finance yo'q → blok yo'q

Vaqt qat'iy (`_FAKE_NOW`) — yarim tunda yolg'on yiqilmasin. SQLite zona
tuzog'i: mahalliy zona = UTC (test_business_day.py izohiga qara).

Ishga tushirish:  cd backend && py -m pytest tests/test_dashboard_net_profit.py -v -p no:randomly
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date as Date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import core.business_day as bdmod
import core.timeutils as tu
import routers.analytics as an
import routers.profit as pr
from core.business_day import MODE_SHIFT, set_mode
from core.security import get_password_hash
from database import Base, get_db
from main import app
from models import (Cafe, Category, Expense, Order, OrderItem, Payment, Permission,
                    Product, Role, Shift, User)
from services.expense_allocation import share_in_range

PW = "SofFoyda9x"
PHONE = "+998900000601"
KASSIR = "+998900000602"
_FAKE_NOW = datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc)
TODAY = _FAKE_NOW.date()
YESTERDAY = TODAY - timedelta(days=1)


@pytest.fixture()
def _clock(monkeypatch):
    monkeypatch.setattr(tu, "_local_tz", lambda tz_name=None: timezone.utc)
    fake = lambda tz_name=None: _FAKE_NOW   # noqa: E731
    for mod in (tu, bdmod, an, pr):
        monkeypatch.setattr(mod, "tenant_now", fake)


@pytest.fixture()
def db_session(_clock):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng, autocommit=False, autoflush=False)()
    try:
        yield s
    finally:
        s.close()
        Base.metadata.drop_all(eng)
        eng.dispose()


def _at(d, h, m=0):
    return datetime(d.year, d.month, d.day) + timedelta(hours=h, minutes=m)


@pytest.fixture()
def seeded(db_session):
    db = db_session
    perms = {c: Permission(code=c, description=c) for c in ("view_analytics", "view_finance")}
    db.add_all(perms.values()); db.flush()
    admin = Role(name="admin", description="a"); admin.permissions = list(perms.values())
    analyst = Role(name="analyst", description="b"); analyst.permissions = [perms["view_analytics"]]
    db.add_all([admin, analyst]); db.flush()
    cafe = Cafe(name="SOF", code="sf", access_code="100.200.601", business_type="store",
                subscription_plan="pro", is_active=True)
    db.add(cafe); db.flush()
    kat = Category(name="K", tenant_id=cafe.id); db.add(kat); db.flush()
    u = User(username="u601", email="601@x.uz", full_name="ADMIN", phone=PHONE,
             hashed_password=get_password_hash(PW), is_active=True, is_superuser=False,
             tenant_id=cafe.id, role_id=admin.id)
    u2 = User(username="u602", email="602@x.uz", full_name="ANALITIK", phone=KASSIR,
              hashed_password=get_password_hash(PW), is_active=True, is_superuser=False,
              tenant_id=cafe.id, role_id=analyst.id)
    db.add_all([u, u2]); db.flush()
    p = Product(name="P", price=1000, cost_price=600, sale_unit="pcs", category_id=kat.id,
                tenant_id=cafe.id, is_active=True)
    db.add(p); db.flush()
    night_shift = Shift(tenant_id=cafe.id, user_id=u.id, start_time=_at(YESTERDAY, 20))
    db.add(night_shift); db.flush()

    def sale(ts, qty, sid=None, n=[0]):
        n[0] += 1
        amt = 1000 * qty
        o = Order(order_number=f"S{n[0]:03d}", tenant_id=cafe.id, status="completed",
                  total_amount=amt, final_amount=amt, discount_amount=0, waiter_id=u.id,
                  shift_id=sid, created_at=ts)
        db.add(o); db.flush()
        db.add(OrderItem(order_id=o.id, product_id=p.id, quantity=qty, tenant_id=cafe.id,
                         unit_price=1000, total_price=amt, unit_cost=600))
        db.add(Payment(tenant_id=cafe.id, order_id=o.id, amount=amt, method="cash",
                       status="paid", cashier_id=u.id, created_at=ts))

    sale(_at(TODAY, 2), 3, night_shift.id)   # tungi: smena rejimida KECHAGA
    sale(_at(TODAY, 9), 7)                    # bugun
    sale(_at(YESTERDAY, 15), 50)              # kecha — bugungi blokka kirmaydi
    db.commit()
    return {"cafe": cafe.id, "user": u.id}


@pytest.fixture()
def client(db_session):
    def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _hdr(client, phone=PHONE):
    r = client.post("/api/v1/auth/login", data={"username": phone, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _dash(client, h):
    r = client.get("/api/v1/analytics/dashboard?range=today", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _summary(client, h):
    r = client.get("/api/v1/profit/summary?period=today", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _exp(db, cafe, amount, d, am_from=None, am_to=None, **kw):
    e = Expense(tenant_id=cafe, category="rent", name="X", amount=amount, expense_date=d,
                amortize_from=am_from, amortize_to=am_to, **kw)
    db.add(e); db.commit(); db.refresh(e)
    return e


KEYS = ("revenue", "cost", "gross_profit", "expenses", "net_profit")


def test_GOLDEN_profit_summary_bilan_aynan(db_session, seeded, client):
    _exp(db_session, seeded["cafe"], 3_000_000, TODAY, TODAY.replace(day=1), Date(2026, 10, 31))
    _exp(db_session, seeded["cafe"], 1_500, TODAY)
    h = _hdr(client)
    pb = _dash(client, h)["profit_breakdown"]
    s = _summary(client, h)
    assert {k: pb[k] for k in KEYS} == {k: s[k] for k in KEYS}
    assert pb["expense_info"] == s["expense_info"]


def test_sof_yalpi_minus_xarajat_va_taqsimlangan_ulush(db_session, seeded, client):
    cafe = seeded["cafe"]
    am = _exp(db_session, cafe, 3_000_000, TODAY, TODAY.replace(day=1), Date(2026, 10, 31))
    _exp(db_session, cafe, 1_500, TODAY)            # bugungi oddiy
    _exp(db_session, cafe, 9_999, YESTERDAY)        # kechagi oddiy — kirmaydi
    pb = _dash(client, _hdr(client))["profit_breakdown"]
    ulush = share_in_range(am, TODAY, TODAY)
    # 3 mln / 31 kun, kumulyativ yaxlitlash: cum(13) − cum(12) = 1 258 064.52 − 1 161 290.32
    assert ulush == 96_774.20
    assert pb["revenue"] == 10_000 and pb["cost"] == 6_000 and pb["gross_profit"] == 4_000
    assert pb["expenses"] == round(ulush + 1_500, 0)
    assert pb["net_profit"] == pb["gross_profit"] - pb["expenses"]
    assert pb["expense_info"]["is_split"] is True


def test_xarajat_nol(seeded, client):
    pb = _dash(client, _hdr(client))["profit_breakdown"]
    assert pb["expenses"] == 0
    assert pb["net_profit"] == pb["gross_profit"] == 4_000


def test_smena_rejimida_tungi_savdo_kechaga(db_session, seeded, client):
    set_mode(db_session, seeded["cafe"], MODE_SHIFT)
    h = _hdr(client)
    pb = _dash(client, h)["profit_breakdown"]
    assert (pb["revenue"], pb["cost"], pb["gross_profit"]) == (7_000, 4_200, 2_800)
    s = _summary(client, h)
    assert {k: pb[k] for k in KEYS} == {k: s[k] for k in KEYS}


def test_takroriy_nusxa_dashboardda_bir_marta_yaratiladi(db_session, seeded, client):
    cafe = seeded["cafe"]
    tpl = Expense(tenant_id=cafe, category="rent", name="IJARA", amount=3_100_000,
                  expense_date=Date(2026, 9, 13), is_recurring=True, recurrence_period="monthly",
                  recurrence_day=13, amortize_from=Date(2026, 9, 1), amortize_to=Date(2026, 9, 30))
    db_session.add(tpl); db_session.commit()
    h = _hdr(client)
    pb = _dash(client, h)["profit_breakdown"]
    _dash(client, h)
    copies = db_session.query(Expense).filter(Expense.recurrence_parent_id == tpl.id).all()
    assert len(copies) == 1
    assert (copies[0].expense_date, copies[0].amortize_from, copies[0].amortize_to) == \
           (Date(2026, 10, 13), Date(2026, 10, 1), Date(2026, 10, 31))
    assert pb["expenses"] == 100_000                 # 3.1 mln / 31 kun


def test_GOLDEN_mavjud_maydonlar_ozgarmagan(seeded, client):
    h = _hdr(client)
    d = _dash(client, h)
    assert d["net_profit"] == 4_000                  # avvalgidek: YALPI foyda (xarajatsiz)
    assert d["profit_kind"] == "gross"
    assert d["total_orders"] == 2
    s = client.get("/api/v1/analytics/summary?period=today", headers=h).json()
    assert (s["total_revenue"], s["total_orders"]) == (10_000, 2)


def test_view_finance_yoq_blok_yoq(seeded, client):
    d = _dash(client, _hdr(client, KASSIR))
    assert d["profit_breakdown"] is None and d["net_profit"] is None
