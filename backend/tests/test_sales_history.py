# -*- coding: utf-8 -*-
"""SOTUVLAR TARIXI: sana oralig'i + ish kuni bo'yicha guruhlash (feature/sales-history-filter).

MANHATTAN so'rovi: 08.10–12.10 tanlansa faqat shu oraliq, kunlarga bo'lingan,
har kunning jami bilan. Kun chegarasi `core/business_day.py` qoidasida
(kalendar 00:00 yoki smena) — dashboard/hisobotlar bilan bir xil.

Qotiriladi:
  1) davr filtri — oraliqdan tashqari chek KIRMAYDI
  2) kunlik guruhlash + kunlik jami (faqat completed)
  3) smena rejimi: tungi chek smena ochilgan kunga
  4) davr jami (summary) == Σ kunlik jami; bekor qilingan sanalmaydi
  5) sahifalash: jamilar sahifadan MUSTAQIL; has_more; tartib yangisi birinchi
  6) kassir faqat o'z sotuvini ko'radi (server majbur qiladi)
  7) N+1 yo'q — sahifa kattaligi so'rovlar sonini o'zgartirmaydi
  8) GOLDEN: `/orders/history` `/{order_id}` ga tushmaydi; chek (reprint) va
     eski `/orders/` ro'yxati ishlaydi

SQLite zona tuzog'i — test_business_day.py izohiga qara (mahalliy zona = UTC).

Ishga tushirish:  cd backend && py -m pytest tests/test_sales_history.py -v -p no:randomly
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import core.timeutils as tu
from core.business_day import MODE_SHIFT, set_mode
from core.security import get_password_hash
from database import Base, get_db
from main import app
from models import (Cafe, Category, Order, OrderItem, Payment, Permission, Product,
                    Role, Shift, User)

PW = "SotTarix9x"
ADMIN_PHONE = "+998900000404"
KASSIR_PHONE = "+998900000405"


@pytest.fixture()
def _utc_local(monkeypatch):
    monkeypatch.setattr(tu, "_local_tz", lambda tz_name=None: timezone.utc)


@pytest.fixture()
def engine(_utc_local):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def db_session(engine):
    s = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    try:
        yield s
    finally:
        s.close()


def _at(d, hour, minute=0):
    return datetime(d.year, d.month, d.day) + timedelta(hours=hour, minutes=minute)


@pytest.fixture()
def seeded(db_session):
    db = db_session
    perms = {c: Permission(code=c, description=c)
             for c in ("view_analytics", "view_reports", "process_payments")}
    db.add_all(perms.values()); db.flush()
    admin_role = Role(name="admin", description="Administrator")
    admin_role.permissions = list(perms.values())
    kassir_role = Role(name="cashier", description="Kassir")
    kassir_role.permissions = [perms["process_payments"], perms["view_reports"]]
    db.add_all([admin_role, kassir_role]); db.flush()
    cafe = Cafe(name="TARIX", code="tr", access_code="100.200.404",
                business_type="store", subscription_plan="pro", is_active=True)
    db.add(cafe); db.flush()
    kat = Category(name="KAT", tenant_id=cafe.id); db.add(kat); db.flush()
    admin = User(username="a404", email="404@x.uz", full_name="ADMIN", phone=ADMIN_PHONE,
                 hashed_password=get_password_hash(PW), is_active=True, is_superuser=False,
                 tenant_id=cafe.id, role_id=admin_role.id)
    kassir = User(username="k405", email="405@x.uz", full_name="KASSIR", phone=KASSIR_PHONE,
                  hashed_password=get_password_hash(PW), is_active=True, is_superuser=False,
                  tenant_id=cafe.id, role_id=kassir_role.id)
    db.add_all([admin, kassir]); db.flush()
    p = Product(name="P", price=100, cost_price=50, sale_unit="pcs",
                category_id=kat.id, tenant_id=cafe.id, is_active=True)
    db.add(p); db.flush()

    today = tu.tenant_now().date()
    D0 = today - timedelta(days=6)   # oraliqdan TASHQARI (oldin)
    D1 = today - timedelta(days=5)   # oraliq boshi
    D2 = today - timedelta(days=4)
    D3 = today - timedelta(days=3)   # oraliq oxiri
    D4 = today - timedelta(days=2)   # oraliqdan TASHQARI (keyin)
    shift = Shift(tenant_id=cafe.id, user_id=admin.id, start_time=_at(D3, 9),
                  end_time=_at(D4, 2))
    db.add(shift); db.flush()

    plan = [
        # (vaqt, summa, status, kassir, smena)
        (_at(D0, 12), 1,    "completed", admin,  None),       # tashqarida
        (_at(D1, 10), 10,   "completed", admin,  None),
        (_at(D1, 15), 20,   "completed", kassir, None),
        (_at(D1, 16), 999,  "cancelled", admin,  None),       # jamiga kirmaydi
        (_at(D2, 11), 40,   "completed", admin,  None),
        (_at(D3, 12), 80,   "completed", kassir, shift.id),
        (_at(D4, 1),  160,  "completed", admin,  shift.id),   # tungi: smena→D3, kalendar→D4
        (_at(D4, 12), 320,  "completed", admin,  None),       # tashqarida
    ]
    ids = []
    for i, (ts, amt, st, who, sid) in enumerate(plan):
        o = Order(order_number=f"H{i:04d}", daily_number=i + 1, tenant_id=cafe.id, status=st,
                  total_amount=amt, final_amount=amt, discount_amount=0, waiter_id=who.id,
                  shift_id=sid, created_at=ts)
        db.add(o); db.flush()
        db.add(OrderItem(order_id=o.id, product_id=p.id, quantity=1, tenant_id=cafe.id,
                         unit_price=amt, total_price=amt, unit_cost=50))
        db.add(Payment(tenant_id=cafe.id, order_id=o.id, amount=amt, method="cash",
                       status="paid", cashier_id=who.id, created_at=ts))
        ids.append(o.id)
    db.commit()
    return {"cafe": cafe.id, "D": [D0, D1, D2, D3, D4], "ids": ids, "kassir": kassir.id}


@pytest.fixture()
def client(db_session):
    def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _hdr(client, phone=ADMIN_PHONE):
    r = client.post("/api/v1/auth/login", data={"username": phone, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _hist(client, h, D1, D3, **extra):
    q = f"date_from={D1.isoformat()}&date_to={D3.isoformat()}"
    for k, v in extra.items():
        q += f"&{k}={v}"
    r = client.get(f"/api/v1/orders/history?{q}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_davr_filtri_tashqaridagini_kiritmaydi(seeded, client):
    _, D1, _, D3, _ = seeded["D"]
    r = _hist(client, _hdr(client), D1, D3)
    amounts = sorted(it["final_amount"] for it in r["items"])
    assert amounts == [10, 20, 40, 80, 999]          # 1 (oldin) va 160/320 (keyin) yo'q
    assert r["date_from"] == D1.isoformat() and r["date_to"] == D3.isoformat()


def test_kunlik_guruhlash_va_jami_kalendar(seeded, client):
    _, D1, D2, D3, _ = seeded["D"]
    r = _hist(client, _hdr(client), D1, D3)
    days = {d["date"]: (d["count"], d["total"], d["other"]) for d in r["days"]}
    assert days == {D1.isoformat(): (2, 30.0, 1), D2.isoformat(): (1, 40.0, 0),
                    D3.isoformat(): (1, 80.0, 0)}
    assert [d["date"] for d in r["days"]] == [D3.isoformat(), D2.isoformat(), D1.isoformat()]
    for it in r["items"]:
        assert it["business_date"] in days


def test_smena_rejimida_tungi_chek_smena_kuniga(db_session, seeded, client):
    set_mode(db_session, seeded["cafe"], MODE_SHIFT)
    _, D1, _, D3, D4 = seeded["D"]
    r = _hist(client, _hdr(client), D1, D3)
    days = {d["date"]: d["total"] for d in r["days"]}
    assert days[D3.isoformat()] == 240.0             # 80 + tungi 160
    night = [it for it in r["items"] if it["final_amount"] == 160]
    assert night and night[0]["business_date"] == D3.isoformat()
    # Ertangi kun (D4) so'ralsa tungi chek u yerda YO'Q
    r4 = _hist(client, _hdr(client), D4, D4)
    assert sorted(it["final_amount"] for it in r4["items"]) == [320]


def test_davr_jami_kunlik_yigindiga_teng_bekor_sanalmaydi(seeded, client):
    _, D1, _, D3, _ = seeded["D"]
    r = _hist(client, _hdr(client), D1, D3)
    assert r["summary"] == {"count": 4, "total": 150.0, "orders": 5}
    assert sum(d["total"] for d in r["days"]) == r["summary"]["total"]
    assert sum(d["count"] for d in r["days"]) == r["summary"]["count"]


def test_sahifalash_jamilar_sahifadan_mustaqil(seeded, client):
    _, D1, _, D3, _ = seeded["D"]
    h = _hdr(client)
    p1 = _hist(client, h, D1, D3, page=1, page_size=2)
    p2 = _hist(client, h, D1, D3, page=2, page_size=2)
    p3 = _hist(client, h, D1, D3, page=3, page_size=2)
    assert [len(p["items"]) for p in (p1, p2, p3)] == [2, 2, 1]
    assert (p1["has_more"], p2["has_more"], p3["has_more"]) == (True, True, False)
    assert p1["summary"] == p3["summary"] and p1["days"] == p3["days"]
    seen = [it["id"] for p in (p1, p2, p3) for it in p["items"]]
    assert len(set(seen)) == 5
    times = [it["created_at"] for p in (p1, p2, p3) for it in p["items"]]
    assert times == sorted(times, reverse=True)       # yangisi birinchi


def test_kassir_faqat_oz_sotuvini_koradi(seeded, client):
    _, D1, _, D3, _ = seeded["D"]
    h = _hdr(client, KASSIR_PHONE)
    r = _hist(client, h, D1, D3)
    assert sorted(it["final_amount"] for it in r["items"]) == [20, 80]
    # boshqa kassir id sini so'rasa ham — o'zinikini oladi
    other = _hist(client, h, D1, D3, cashier_id=seeded["kassir"] + 999)
    assert sorted(it["final_amount"] for it in other["items"]) == [20, 80]
    assert r["summary"]["total"] == 100.0


def test_admin_kassir_boyicha_filtrlay_oladi(seeded, client):
    _, D1, _, D3, _ = seeded["D"]
    r = _hist(client, _hdr(client), D1, D3, cashier_id=seeded["kassir"])
    assert sorted(it["final_amount"] for it in r["items"]) == [20, 80]


def test_n_plus_1_yoq(engine, seeded, client):
    _, D1, _, D3, _ = seeded["D"]
    h = _hdr(client)
    counts = []

    def _count(*_a, **_k):
        counts[-1] += 1

    event.listen(engine, "before_cursor_execute", _count)
    try:
        for ps in (1, 5):
            counts.append(0)
            _hist(client, h, D1, D3, page_size=ps)
    finally:
        event.remove(engine, "before_cursor_execute", _count)
    assert counts[0] == counts[1], counts


def test_golden_marshrut_va_reprint(seeded, client):
    h = _hdr(client)
    oid = seeded["ids"][1]
    r = client.get(f"/api/v1/orders/{oid}/receipt", headers=h)
    assert r.status_code == 200, r.text
    lst = client.get("/api/v1/orders/?page=1&page_size=50", headers=h)
    assert lst.status_code == 200 and lst.json()["total"] == 8
    one = client.get(f"/api/v1/orders/{oid}", headers=h)
    assert one.status_code == 200


def test_notogri_davr_400(seeded, client):
    _, D1, _, D3, _ = seeded["D"]
    r = client.get(f"/api/v1/orders/history?date_from={D3}&date_to={D1}", headers=_hdr(client))
    assert r.status_code == 400
    r = client.get("/api/v1/orders/history?date_from=xx", headers=_hdr(client))
    assert r.status_code == 400


def test_standart_joriy_ish_kuni(seeded, client):
    r = client.get("/api/v1/orders/history", headers=_hdr(client))
    assert r.status_code == 200
    today = tu.tenant_now().date().isoformat()
    assert r.json()["date_from"] == r.json()["date_to"] == today
