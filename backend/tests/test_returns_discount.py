"""VOZVRATDA CHEK CHEGIRMASI (fix/returns-discount, 2026-10).

MUAMMO: buyurtma chegirmasi faqat `Order.discount_amount` da turadi, qator
summasi (`OrderItem.total_price`) esa CHEGIRMAGACHA. 580 000 lik tovar
chegirma bilan 515 000 ga sotilsa, vozvratda 580 000 chiqardi — do'konchi
65 000 ORTIQCHA qaytarardi.

BU TESTLAR QULFLAYDI:
  • chegirmali chek: to'liq qaytarish 515 000 (pul ham 515 000 qaytadi)
  • qisman: 0.5 → 257 500
  • chegirmasiz chek — AVVALGIDEK (GOLDEN)
  • bir nechta qatorda chegirma proporsional, yig'indi = chek summasi (tiyiniga)
  • bo'laklab qaytarishda ham jami = qatorning chegirmali summasi
  • /returns/lookup: sold_total chegirmali, sold_total_gross va discount_share

Ishga tushirish:  cd backend && py -m pytest tests/test_returns_discount.py -v
"""
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
from core.security import get_password_hash
from core.timeutils import utc_now
from database import Base, get_db
from main import app
from models import Cafe, Inventory, Order, OrderItem, Payment, Permission, Product, Role, Shift, User
from routers.returns import net_line_totals

PW, PHONE = "AdminRetD9", "+998900000081"
NOW = utc_now()


@pytest.fixture()
def eng():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(e)
    yield e
    Base.metadata.drop_all(e)
    e.dispose()


@pytest.fixture()
def db_session(eng, monkeypatch):
    Session = sessionmaker(bind=eng, autocommit=False, autoflush=False)
    monkeypatch.setattr(database, "SessionLocal", Session)
    s = Session()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def client(db_session):
    def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _perm(db, code):
    p = db.query(Permission).filter(Permission.code == code).first()
    if not p:
        p = Permission(code=code, description=code)
        db.add(p)
        db.flush()
    return p


@pytest.fixture()
def shop(db_session):
    db = db_session
    perms = [_perm(db, c) for c in ("process_payments", "manage_shifts", "view_reports",
                                    "view_finance", "manage_inventory")]
    role = db.query(Role).filter(Role.name == "admin").first()
    if not role:
        role = Role(name="admin", description="admin")
        db.add(role)
    role.permissions = perms
    cafe = Cafe(name="RETD", code="retd", access_code="100.200.81",
                business_type="store", subscription_plan="pro", is_active=True)
    db.add(cafe)
    db.flush()
    u = User(username="retd", email="retd@x.uz", full_name="Admin", phone=PHONE,
             hashed_password=get_password_hash(PW), is_active=True, tenant_id=cafe.id, role_id=role.id)
    db.add(u)
    db.flush()
    db.add(Shift(tenant_id=cafe.id, user_id=u.id, start_time=NOW - timedelta(hours=2), starting_cash=0.0))
    prods = []
    for i in range(3):
        p = Product(tenant_id=cafe.id, name=f"TOVAR{i}", price=1.0, cost_price=1.0)
        db.add(p)
        db.flush()
        db.add(Inventory(tenant_id=cafe.id, product_id=p.id, quantity=100.0, unit="dona"))
        prods.append(p.id)
    db.commit()
    return {"db": db, "cafe": cafe.id, "user": u.id, "prods": prods, "n": [0]}


def _sold(shop, lines, discount=0.0):
    """Tugallangan, naqd to'langan chek. lines: [(miqdor, birlik narxi), ...]"""
    db = shop["db"]
    shop["n"][0] += 1
    sub = sum(round(q * p, 2) for q, p in lines)
    o = Order(tenant_id=shop["cafe"], order_number=f"D-{shop['n'][0]}", daily_number=shop["n"][0],
              status="completed", total_amount=sub, discount_amount=discount,
              final_amount=round(sub - discount, 2), waiter_id=shop["user"],
              created_at=NOW - timedelta(minutes=30))
    db.add(o)
    db.flush()
    ois = []
    for (q, p), pid in zip(lines, shop["prods"]):
        oi = OrderItem(tenant_id=shop["cafe"], order_id=o.id, product_id=pid, quantity=q,
                       unit_price=p, unit_cost=1.0, total_price=round(q * p, 2))
        db.add(oi)
        db.flush()
        ois.append(oi)
    db.add(Payment(tenant_id=shop["cafe"], order_id=o.id, cashier_id=shop["user"],
                   amount=o.final_amount, method="cash", status="paid", transaction_id=f"T{o.id}"))
    db.commit()
    return o, ois


def _h(client):
    r = client.post("/api/v1/auth/login", data={"username": PHONE, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _row(oi, qty):
    return {"product_id": oi.product_id, "order_item_id": oi.id, "quantity": qty,
            "unit_price": oi.unit_price, "restore_to_inventory": True}


def _ret(client, h, oid, rows):
    r = client.post("/api/v1/returns/", headers=h, json={
        "order_id": oid, "reason": "other", "refund_method": "cash", "items": rows})
    assert r.status_code == 200, r.text
    return r.json()


# ══════════════════════════════════════════════════════════════════════════════

def test_chegirmali_chek_toliq_515000(client, shop):
    h = _h(client)
    o, (oi,) = _sold(shop, [(1.0, 580_000.0)], discount=65_000.0)
    ret = _ret(client, h, o.id, [_row(oi, 1.0)])
    assert ret["total_amount"] == 515_000.0                 # ilgari 580 000
    assert ret["items"][0]["total"] == 515_000.0
    # Tasdiqlanganda kassadan chiqadigan pul ham 515 000
    a = client.post(f"/api/v1/returns/{ret['id']}/approve", headers=h)
    assert a.status_code == 200, a.text
    db = shop["db"]
    db.expire_all()
    qaytgan = -sum(p.amount for p in db.query(Payment).filter(Payment.order_id == o.id, Payment.amount < 0))
    assert qaytgan == 515_000.0


def test_qisman_yarim_257500(client, shop):
    o, (oi,) = _sold(shop, [(1.0, 580_000.0)], discount=65_000.0)
    assert _ret(client, _h(client), o.id, [_row(oi, 0.5)])["total_amount"] == 257_500.0


def test_GOLDEN_chegirmasiz_avvalgidek(client, shop):
    h = _h(client)
    o, (oi,) = _sold(shop, [(3.0, 100_000.0)])
    assert _ret(client, h, o.id, [_row(oi, 1.0)])["total_amount"] == 100_000.0
    lk = client.get(f"/api/v1/returns/lookup?q={o.order_number}", headers=h).json()
    it = lk["items"][0]
    assert it["sold_total"] == 300_000.0 and it["sold_total_gross"] == 300_000.0
    assert it["discount_share"] == 0


def test_lookup_chegirmali_narx(client, shop):
    o, _ = _sold(shop, [(1.0, 580_000.0)], discount=65_000.0)
    lk = client.get(f"/api/v1/returns/lookup?q={o.order_number}", headers=_h(client)).json()
    it = lk["items"][0]
    assert it["sold_total"] == 515_000.0
    assert it["sold_total_gross"] == 580_000.0
    assert it["discount_share"] == 65_000.0
    assert lk["discount_amount"] == 65_000.0


def test_bir_nechta_qator_proporsional_yigindi_chek_summasi(client, shop):
    # Yaxlitlash qoldig'i chiqadigan raqamlar
    o, ois = _sold(shop, [(1.0, 100_000.0), (1.0, 200_000.0), (3.0, 111_111.11)], discount=50_000.0)
    lk = client.get(f"/api/v1/returns/lookup?q={o.order_number}", headers=_h(client)).json()
    nets = [i["sold_total"] for i in lk["items"]]
    assert round(sum(nets), 2) == o.final_amount            # tiyiniga
    sub = o.total_amount
    for i, oi in zip(lk["items"], ois):                      # har biri proporsional (±1 tiyin)
        assert abs(i["sold_total"] - oi.total_price * (1 - 50_000.0 / sub)) <= 0.011


def test_hammasi_qaytsa_jami_chek_summasi(client, shop):
    h = _h(client)
    o, ois = _sold(shop, [(1.0, 100_000.0), (1.0, 200_000.0), (3.0, 111_111.11)], discount=50_000.0)
    jami = 0.0
    for oi in ois:                                           # har qator alohida vozvrat
        jami += _ret(client, h, o.id, [_row(oi, oi.quantity)])["total_amount"]
    assert round(jami, 2) == o.final_amount


def test_bolaklab_qaytarishda_dum_yoq(client, shop):
    h = _h(client)
    o, (oi,) = _sold(shop, [(3.0, 111_111.11)], discount=7_777.0)
    a = _ret(client, h, o.id, [_row(oi, 1.0)])["total_amount"]
    b = _ret(client, h, o.id, [_row(oi, 1.0)])["total_amount"]
    c = _ret(client, h, o.id, [_row(oi, 1.0)])["total_amount"]
    assert round(a + b + c, 2) == o.final_amount


def test_net_line_totals_birlik():
    class O:  # noqa: E701
        discount_amount = 65_000.0

    class I:
        def __init__(self, i, t): self.id, self.total_price = i, t
    assert net_line_totals(O(), [I(1, 580_000.0)]) == {1: 515_000.0}
    O.discount_amount = 0
    assert net_line_totals(O(), [I(1, 580_000.0)]) == {1: 580_000.0}       # GOLDEN
    O.discount_amount = 10 ** 9                                             # chegirma > summa
    assert net_line_totals(O(), [I(1, 100.0), I(2, 50.0)]) == {1: 0.0, 2: 0.0}
