"""ARALASH TO'LOVDA NASIYA — 170 000 naqd + 130 000 nasiya (feature/split-credit).

MUAMMO: 300 000 lik sotuvni qisman naqd, qisman nasiya qilib bo'lmasdi
(split'da nasiya yo'q edi). Ustiga nasiya qarzi frontendда sotuvdan KEYIN
alohida `POST /debts/` bilan yozilardi — limit oshsa tovar ketib, qarz qolmasdi.

BU TESTLAR QULFLAYDI:
  • 170k naqd + 130k nasiya → qarz FAQAT 130k, expected_cash +170k
  • limit oshsa nasiya ulushi rad etiladi va HECH NARSA yozilmaydi
  • mijozsiz nasiya → 400
  • `POST /debts/` order_id bo'yicha IDEMPOTENT (eski .exe'lar) — limitdan OLDIN
  • vozvrat: avval SHU chek qarzi, qolgani naqd; Z faqat naqd qismini ayiradi
  • /receipt chekida nasiya ulushi ham (summasi bilan) ko'rinadi
  • GOLDEN: yagona nasiya, naqd+karta split, sof naqd vozvrat — avvalgidek

Ishga tushirish:  cd backend && py -m pytest tests/test_split_credit.py -v
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
from models import (
    Cafe, Customer, CustomerDebt, Inventory, Order, OrderItem, Payment,
    Permission, Product, Return, Role, Shift, User,
)

ADMIN_PW,  ADMIN_PHONE  = "AdminSplit9", "+998900000091"
KASSIR_PW, KASSIR_PHONE = "KassirSpl9",  "+998900000092"

START_CASH = 100_000.0
UNIT       = 100_000.0
TOTAL      = 300_000.0          # 3 dona × 100 000
NAQD, NASIYA = 170_000.0, 130_000.0

NOW = utc_now()


# ══════════════════════════════════════════════════════════════════════════════
# FIXTURE'LAR
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def eng():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    Base.metadata.create_all(e)
    yield e
    Base.metadata.drop_all(e)
    e.dispose()


@pytest.fixture()
def db_session(eng, monkeypatch):
    Session = sessionmaker(bind=eng, autocommit=False, autoflush=False)
    monkeypatch.setattr(database, "SessionLocal", Session)   # audit log ham shu bazaga
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


def _role(db, name, perms):
    r = db.query(Role).filter(Role.name == name).first()
    if not r:
        r = Role(name=name, description=name)
        db.add(r)
        db.flush()
    r.permissions = perms
    db.flush()
    return r


@pytest.fixture()
def shop(db_session):
    """Do'kon + kassirning OCHIQ smenasi + mijoz + 300 000 lik KUTILAYOTGAN chek."""
    db = db_session
    p_pay, p_shift, p_rep, p_fin = (_perm(db, c) for c in
                                    ("process_payments", "manage_shifts", "view_reports", "view_finance"))
    r_admin  = _role(db, "admin",   [p_pay, p_shift, p_rep, p_fin])
    r_kassir = _role(db, "cashier", [p_pay, p_rep])

    cafe = Cafe(name="XOZMAG split", code="xsp", access_code="100.200.91",
                business_type="store", subscription_plan="pro", is_active=True)
    db.add(cafe)
    db.flush()
    admin = User(username="bosh91", email="a91@x.uz", full_name="Rahbar",
                 phone=ADMIN_PHONE, hashed_password=get_password_hash(ADMIN_PW),
                 is_active=True, tenant_id=cafe.id, role_id=r_admin.id)
    kassir = User(username="kassa91", email="k91@x.uz", full_name="Kassir",
                  phone=KASSIR_PHONE, hashed_password=get_password_hash(KASSIR_PW),
                  is_active=True, tenant_id=cafe.id, role_id=r_kassir.id)
    db.add_all([admin, kassir])
    db.flush()

    prod = Product(tenant_id=cafe.id, name="PLITKA", price=UNIT, cost_price=60_000.0)
    db.add(prod)
    db.flush()
    db.add(Inventory(tenant_id=cafe.id, product_id=prod.id, quantity=50.0, unit="dona"))

    shift = Shift(tenant_id=cafe.id, user_id=kassir.id,
                  start_time=NOW - timedelta(hours=3), starting_cash=START_CASH)
    db.add(shift)
    cust = Customer(tenant_id=cafe.id, name="Shuhrat aka", phone="+998901234591", total_debt=0.0)
    db.add(cust)
    db.flush()
    db.commit()
    ids = {"db": db, "cafe": cafe.id, "admin": admin.id, "kassir": kassir.id,
           "shift": shift.id, "customer": cust.id, "product": prod.id}
    ids["order"], ids["order_item"] = _new_order(db, ids, customer=True)
    return ids


def _new_order(db, s, *, customer=True, number="S-1"):
    o = Order(tenant_id=s["cafe"], order_number=number, daily_number=1, status="pending",
              total_amount=TOTAL, discount_amount=0.0, final_amount=TOTAL,
              waiter_id=s["kassir"], shift_id=s["shift"],
              customer_id=s["customer"] if customer else None,
              created_at=NOW - timedelta(minutes=30))
    db.add(o)
    db.flush()
    oi = OrderItem(tenant_id=s["cafe"], order_id=o.id, product_id=s["product"],
                   quantity=3, unit_price=UNIT, unit_cost=60_000.0, total_price=TOTAL)
    db.add(oi)
    db.commit()
    return o.id, oi.id


# ══════════════════════════════════════════════════════════════════════════════
# YORDAMCHILAR
# ══════════════════════════════════════════════════════════════════════════════

def _login(client, phone, pw):
    r = client.post("/api/v1/auth/login", data={"username": phone, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _pay(client, h, order_id, method, amount, customer_id=None, **q):
    body = {"order_id": order_id, "method": method, "amount": amount}
    if customer_id is not None:
        body["customer_id"] = customer_id
    url = "/api/v1/payments/" + ("?offline_sync=1" if q.get("offline") else "")
    return client.post(url, json=body, headers=h)


def _split(client, h, s):
    """POS tartibi: NASIYA BIRINCHI, keyin naqd."""
    r1 = _pay(client, h, s["order"], "credit", NASIYA, s["customer"])
    assert r1.status_code == 200, r1.text
    r2 = _pay(client, h, s["order"], "cash", NAQD)
    assert r2.status_code == 200, r2.text


def _close(client, h, shift_id):
    r = client.post(f"/api/v1/shifts/{shift_id}/close?counted_cash=0", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _debts(db, order_id):
    db.expire_all()
    return db.query(CustomerDebt).filter(CustomerDebt.order_id == order_id,
                                         CustomerDebt.amount > 0).all()


def _cust(db, cid):
    db.expire_all()
    return db.query(Customer).get(cid)


def _return(client, hk, ha, s, qty, method="cash"):
    r = client.post("/api/v1/returns/", headers=hk, json={
        "order_id": s["order"], "customer_id": s["customer"], "reason": "other",
        "refund_method": method,
        "items": [{"product_id": s["product"], "order_item_id": s["order_item"],
                   "quantity": qty, "unit_price": UNIT, "restore_to_inventory": True}],
    })
    assert r.status_code == 200, r.text
    a = client.post(f"/api/v1/returns/{r.json()['id']}/approve", headers=ha)
    assert a.status_code == 200, a.text
    return a.json()


# ══════════════════════════════════════════════════════════════════════════════
# 1) 170k naqd + 130k nasiya
# ══════════════════════════════════════════════════════════════════════════════

def test_split_naqd_nasiya_qarz_faqat_nasiya_qismi(client, shop):
    db = shop["db"]
    hk = _login(client, KASSIR_PHONE, KASSIR_PW)
    _split(client, hk, shop)

    db.expire_all()
    assert db.query(Order).get(shop["order"]).status == "completed"
    d = _debts(db, shop["order"])
    assert len(d) == 1
    assert d[0].amount == NASIYA and d[0].remaining == NASIYA and d[0].status == "open"
    assert d[0].customer_id == shop["customer"]
    assert _cust(db, shop["customer"]).total_debt == NASIYA


def test_split_z_hisobot_naqd_kiradi_nasiya_kirmaydi(client, shop):
    hk = _login(client, KASSIR_PHONE, KASSIR_PW)
    _split(client, hk, shop)
    z = _close(client, _login(client, ADMIN_PHONE, ADMIN_PW), shop["shift"])
    assert z["cash_sales"]    == NAQD
    assert z["credit_total"]  == NASIYA
    assert z["expected_cash"] == START_CASH + NAQD


def test_split_chekda_ikkala_qism_summasi_bilan(client, shop):
    hk = _login(client, KASSIR_PHONE, KASSIR_PW)
    _split(client, hk, shop)
    r = client.get(f"/api/v1/orders/{shop['order']}/receipt", headers=hk)
    assert r.status_code == 200, r.text
    pm = sorted((p["method"], p["amount"]) for p in r.json()["payment_methods"])
    assert pm == [("cash", NAQD), ("credit", NASIYA)]
    assert r.json()["paid"] == NAQD               # `paid` avvalgidek faqat to'langan


# ══════════════════════════════════════════════════════════════════════════════
# 2) Limit va mijoz
# ══════════════════════════════════════════════════════════════════════════════

def test_limit_oshsa_nasiya_rad_naqd_yozilmaydi(client, shop):
    db = shop["db"]
    c = db.query(Customer).get(shop["customer"])
    c.credit_limit = 100_000.0
    db.commit()
    hk = _login(client, KASSIR_PHONE, KASSIR_PW)

    r = _pay(client, hk, shop["order"], "credit", NASIYA, shop["customer"])
    assert r.status_code == 400
    assert "limit" in r.json()["detail"].lower()

    db.expire_all()
    assert db.query(Payment).filter(Payment.order_id == shop["order"]).count() == 0
    assert _debts(db, shop["order"]) == []
    assert db.query(Order).get(shop["order"]).status == "pending"
    assert _cust(db, shop["customer"]).total_debt == 0


def test_mijozsiz_nasiya_400(client, shop):
    db = shop["db"]
    oid, _ = _new_order(db, shop, customer=False, number="S-2")
    hk = _login(client, KASSIR_PHONE, KASSIR_PW)
    r = _pay(client, hk, oid, "credit", NASIYA)
    assert r.status_code == 400
    assert "mijoz" in r.json()["detail"].lower()
    db.expire_all()
    assert db.query(Payment).filter(Payment.order_id == oid).count() == 0


def test_payload_mijozi_buyurtmaga_ham_yoziladi(client, shop):
    db = shop["db"]
    oid, _ = _new_order(db, shop, customer=False, number="S-3")
    hk = _login(client, KASSIR_PHONE, KASSIR_PW)
    assert _pay(client, hk, oid, "credit", TOTAL, shop["customer"]).status_code == 200
    db.expire_all()
    assert db.query(Order).get(oid).customer_id == shop["customer"]
    assert [d.amount for d in _debts(db, oid)] == [TOTAL]


def test_offline_replay_limitdan_oshsa_ham_yoziladi(client, shop):
    """Offline sotuv do'konda ALLAQACHON bo'lgan — rad etilsa sync uni yutib yo'qotardi."""
    db = shop["db"]
    c = db.query(Customer).get(shop["customer"])
    c.credit_limit = 1_000.0
    db.commit()
    hk = _login(client, KASSIR_PHONE, KASSIR_PW)
    r = _pay(client, hk, shop["order"], "credit", TOTAL, offline=True)
    assert r.status_code == 200, r.text
    assert [d.amount for d in _debts(db, shop["order"])] == [TOTAL]


# ══════════════════════════════════════════════════════════════════════════════
# 3) POST /debts/ IDEMPOTENT (eski .exe sotuvdan keyin baribir chaqiradi)
# ══════════════════════════════════════════════════════════════════════════════

def test_debts_ikki_marta_bitta_qarz(client, shop):
    db = shop["db"]
    hk = _login(client, KASSIR_PHONE, KASSIR_PW)
    _split(client, hk, shop)
    first = _debts(db, shop["order"])[0].id

    body = {"customer_id": shop["customer"], "order_id": shop["order"],
            "amount": TOTAL, "notes": "POS dan nasiya"}            # eski .exe: t.total
    r1 = client.post("/api/v1/debts/", json=body, headers=hk)
    r2 = client.post("/api/v1/debts/", json=body, headers=hk)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"] == first

    assert len(_debts(db, shop["order"])) == 1
    assert _cust(db, shop["customer"]).total_debt == NASIYA


def test_debts_idempotent_limit_tekshiruvidan_oldin(client, shop):
    """Limit AYNAN qarzga teng: server yozgan qarzni ikkinchi marta sanab 400
    bersa, eski kassa "qarz yozilmadi" deb yolg'on ogohlantirardi."""
    db = shop["db"]
    c = db.query(Customer).get(shop["customer"])
    c.credit_limit = NASIYA
    db.commit()
    hk = _login(client, KASSIR_PHONE, KASSIR_PW)
    _split(client, hk, shop)
    r = client.post("/api/v1/debts/", headers=hk, json={
        "customer_id": shop["customer"], "order_id": shop["order"], "amount": TOTAL})
    assert r.status_code == 200, r.text


def test_GOLDEN_debts_order_siz_avvalgidek_yangi_qarz(client, shop):
    """Admin qo'lda qarz yozadi (order_id yo'q) — har chaqiruv YANGI qarz."""
    hk = _login(client, KASSIR_PHONE, KASSIR_PW)
    body = {"customer_id": shop["customer"], "amount": 5_000.0}
    a = client.post("/api/v1/debts/", json=body, headers=hk).json()["id"]
    b = client.post("/api/v1/debts/", json=body, headers=hk).json()["id"]
    assert a != b


# ══════════════════════════════════════════════════════════════════════════════
# 4) VOZVRAT: avval shu chek qarzi, keyin naqd
# ══════════════════════════════════════════════════════════════════════════════

def test_toliq_vozvrat_avval_qarz_keyin_naqd(client, shop):
    db = shop["db"]
    hk = _login(client, KASSIR_PHONE, KASSIR_PW)
    ha = _login(client, ADMIN_PHONE, ADMIN_PW)
    _split(client, hk, shop)

    ret = _return(client, hk, ha, shop, qty=3)
    assert ret["debt_offset"] == NASIYA

    d = _debts(db, shop["order"])[0]
    assert d.remaining == 0 and d.status == "paid"
    assert _cust(db, shop["customer"]).total_debt == 0
    naqd_qaytdi = -sum(p.amount for p in db.query(Payment).filter(
        Payment.order_id == shop["order"], Payment.amount < 0))
    assert naqd_qaytdi == NAQD

    z = _close(client, ha, shop["shift"])
    assert z["cash_refunds"]  == NAQD            # 300k EMAS — tuzatilgan nomuvofiqlik


def test_aralash_toliq_vozvrat_expected_cash_faqat_naqd_qismi(client, shop):
    """Ilgari strict xfail edi (ikki marta ayirish): naqd 170k to'lov to'liq
    qaytgach `refunded` bo'lib sotuvdan TUSHARDI va yana ayirilardi."""
    hk = _login(client, KASSIR_PHONE, KASSIR_PW)
    ha = _login(client, ADMIN_PHONE, ADMIN_PW)
    _split(client, hk, shop)
    _return(client, hk, ha, shop, qty=3)
    z = _close(client, ha, shop["shift"])
    assert z["cash_sales"]    == NAQD             # sotuv QOLADI
    assert z["cash_refunds"]  == NAQD             # bir marta ayiriladi
    assert z["expected_cash"] == START_CASH       # +170k sotuv −170k vozvrat


def test_qisman_vozvrat_faqat_qarz_kamayadi(client, shop):
    db = shop["db"]
    hk = _login(client, KASSIR_PHONE, KASSIR_PW)
    ha = _login(client, ADMIN_PHONE, ADMIN_PW)
    _split(client, hk, shop)

    ret = _return(client, hk, ha, shop, qty=1)          # 100k ≤ 130k qarz
    assert ret["debt_offset"] == UNIT
    assert _debts(db, shop["order"])[0].remaining == NASIYA - UNIT
    assert db.query(Payment).filter(Payment.order_id == shop["order"],
                                    Payment.amount < 0).count() == 0

    ret2 = _return(client, hk, ha, shop, qty=2)         # 200k: 30k qarz + 170k naqd
    assert ret2["debt_offset"] == NASIYA - UNIT
    assert _debts(db, shop["order"])[0].remaining == 0
    z = _close(client, ha, shop["shift"])
    assert z["cash_refunds"] == NAQD                    # 100k+200k EMAS


def test_boshqa_eski_qarzga_naqd_vozvrat_tegmaydi(client, shop):
    """Naqd vozvrat faqat SHU chek qarzini yopadi — mijozning boshqa qarzi qoladi."""
    db = shop["db"]
    db.add(CustomerDebt(tenant_id=shop["cafe"], customer_id=shop["customer"], order_id=None,
                        amount=50_000.0, paid_amount=0.0, remaining=50_000.0, status="open",
                        created_at=NOW - timedelta(days=10)))
    c = db.query(Customer).get(shop["customer"])
    c.total_debt = 50_000.0
    db.commit()
    hk = _login(client, KASSIR_PHONE, KASSIR_PW)
    ha = _login(client, ADMIN_PHONE, ADMIN_PW)
    _split(client, hk, shop)
    _return(client, hk, ha, shop, qty=3)
    assert _cust(db, shop["customer"]).total_debt == 50_000.0


# ══════════════════════════════════════════════════════════════════════════════
# 5) GOLDEN
# ══════════════════════════════════════════════════════════════════════════════

def test_GOLDEN_yagona_nasiya(client, shop):
    db = shop["db"]
    hk = _login(client, KASSIR_PHONE, KASSIR_PW)
    r = _pay(client, hk, shop["order"], "credit", TOTAL)    # eski .exe: customer_id yo'q
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending"
    db.expire_all()
    assert db.query(Order).get(shop["order"]).status == "completed"
    assert [d.amount for d in _debts(db, shop["order"])] == [TOTAL]
    assert _cust(db, shop["customer"]).total_debt == TOTAL

    z = _close(client, _login(client, ADMIN_PHONE, ADMIN_PW), shop["shift"])
    assert z["cash_sales"] == 0 and z["credit_total"] == TOTAL
    assert z["expected_cash"] == START_CASH


def test_GOLDEN_naqd_karta_split(client, shop):
    db = shop["db"]
    hk = _login(client, KASSIR_PHONE, KASSIR_PW)
    assert _pay(client, hk, shop["order"], "card", 100_000.0).status_code == 200
    assert _pay(client, hk, shop["order"], "cash", 200_000.0).status_code == 200
    db.expire_all()
    assert db.query(Order).get(shop["order"]).status == "completed"
    assert db.query(CustomerDebt).count() == 0
    z = _close(client, _login(client, ADMIN_PHONE, ADMIN_PW), shop["shift"])
    assert (z["cash_sales"], z["card_sales"], z["credit_total"]) == (200_000.0, 100_000.0, 0)
    assert z["expected_cash"] == START_CASH + 200_000.0


def test_GOLDEN_sof_naqd_vozvrat_total_amount(client, shop):
    """Qarzsiz chek: debt_offset NULL, Z avvalgidek total_amount ni ayiradi."""
    db = shop["db"]
    hk = _login(client, KASSIR_PHONE, KASSIR_PW)
    ha = _login(client, ADMIN_PHONE, ADMIN_PW)
    assert _pay(client, hk, shop["order"], "cash", TOTAL).status_code == 200
    ret = _return(client, hk, ha, shop, qty=1)
    assert ret["debt_offset"] is None
    db.expire_all()
    assert db.query(Return).get(ret["id"]).debt_offset is None
    z = _close(client, ha, shop["shift"])
    assert z["cash_refunds"]  == UNIT
    assert z["expected_cash"] == START_CASH + TOTAL - UNIT


# ══════════════════════════════════════════════════════════════════════════════
# 6) Z-HISOBOT: IKKI MARTA AYIRISH tuzatildi — sotuv qoladi, qaytarish bir marta
# ══════════════════════════════════════════════════════════════════════════════

def _zbuild(db, shift_id, user_id):
    """Z chekni qayta qurish yo'li (`print-z`) — yopish bilan bir xil bo'lishi SHART."""
    from routers.shift import _build_zreport_data
    db.expire_all()
    return _build_zreport_data(db.query(Shift).get(shift_id), db, db.query(User).get(user_id))


def test_sof_naqd_toliq_vozvrat_expected_cash_ozgarmaydi(client, shop):
    db = shop["db"]
    hk = _login(client, KASSIR_PHONE, KASSIR_PW)
    ha = _login(client, ADMIN_PHONE, ADMIN_PW)
    assert _pay(client, hk, shop["order"], "cash", TOTAL).status_code == 200
    _return(client, hk, ha, shop, qty=3)
    db.expire_all()
    asl = db.query(Payment).filter(Payment.order_id == shop["order"], Payment.amount > 0).one()
    assert asl.status == "refunded"               # ildiz: holat o'zgaradi

    zb = _zbuild(db, shop["shift"], shop["admin"])
    z = _close(client, ha, shop["shift"])
    for r in (z, zb):
        assert r["cash_sales"]    == TOTAL        # ilgari 0 edi
        assert r["cash_refunds"]  == TOTAL
        assert r["expected_cash"] == START_CASH   # ilgari START − 200k


def test_qisman_vozvrat_faqat_qaytgan_qism(client, shop):
    db = shop["db"]
    hk = _login(client, KASSIR_PHONE, KASSIR_PW)
    ha = _login(client, ADMIN_PHONE, ADMIN_PW)
    assert _pay(client, hk, shop["order"], "cash", TOTAL).status_code == 200
    _return(client, hk, ha, shop, qty=1)
    zb = _zbuild(db, shop["shift"], shop["admin"])
    z = _close(client, ha, shop["shift"])
    for r in (z, zb):
        assert (r["cash_sales"], r["cash_refunds"]) == (TOTAL, UNIT)
        assert r["expected_cash"] == START_CASH + TOTAL - UNIT


def test_ikki_qisman_vozvrat_oxirgisi_tolovni_yopadi(client, shop):
    """1 + 2 dona: ikkinchisida asl to'lov `refunded` bo'ladi — jami 300k bir marta."""
    hk = _login(client, KASSIR_PHONE, KASSIR_PW)
    ha = _login(client, ADMIN_PHONE, ADMIN_PW)
    assert _pay(client, hk, shop["order"], "cash", TOTAL).status_code == 200
    _return(client, hk, ha, shop, qty=1)
    _return(client, hk, ha, shop, qty=2)
    z = _close(client, ha, shop["shift"])
    assert (z["cash_sales"], z["cash_refunds"], z["expected_cash"]) == (TOTAL, TOTAL, START_CASH)


def test_naqd_karta_toliq_vozvrat_karta_kassaga_tegmaydi(client, shop):
    hk = _login(client, KASSIR_PHONE, KASSIR_PW)
    ha = _login(client, ADMIN_PHONE, ADMIN_PW)
    assert _pay(client, hk, shop["order"], "card", 100_000.0).status_code == 200
    assert _pay(client, hk, shop["order"], "cash", 200_000.0).status_code == 200
    _return(client, hk, ha, shop, qty=3)
    z = _close(client, ha, shop["shift"])
    assert (z["cash_sales"], z["card_sales"]) == (200_000.0, 100_000.0)
    # Vozvrat hujjati `cash` — kassir 300k naqd beradi (avvalgi qoida, total_amount)
    assert z["expected_cash"] == START_CASH + 200_000.0 - TOTAL


def test_tolov_yoli_toliq_qaytarish_bir_marta(client, shop):
    """`POST /payments/{id}/refund` (hujjatsiz) — ilgari faqat sotuv yo'qolishi
    bilan hisobga olinardi; endi sotuv qoladi, qaytarish bir marta ayiriladi."""
    db = shop["db"]
    hk = _login(client, KASSIR_PHONE, KASSIR_PW)
    ha = _login(client, ADMIN_PHONE, ADMIN_PW)
    pid = _pay(client, hk, shop["order"], "cash", TOTAL).json()["id"]
    assert client.post(f"/api/v1/payments/{pid}/refund", headers=hk).status_code == 200
    zb = _zbuild(db, shop["shift"], shop["admin"])
    z = _close(client, ha, shop["shift"])
    for r in (z, zb):
        assert (r["cash_sales"], r["cash_refunds"], r["expected_cash"]) == (TOTAL, TOTAL, START_CASH)


def test_tolov_yoli_qisman_qaytarish_endi_ayiriladi(client, shop):
    """Ilgari qisman qaytarishda pul UMUMAN ayirilmasdi (sotuv `paid` qolardi,
    hujjat yo'q) — kassada 100k kam chiqardi."""
    hk = _login(client, KASSIR_PHONE, KASSIR_PW)
    ha = _login(client, ADMIN_PHONE, ADMIN_PW)
    pid = _pay(client, hk, shop["order"], "cash", TOTAL).json()["id"]
    assert client.post(f"/api/v1/payments/{pid}/refund?amount={UNIT}", headers=hk).status_code == 200
    z = _close(client, ha, shop["shift"])
    assert (z["cash_sales"], z["cash_refunds"]) == (TOTAL, UNIT)
    assert z["expected_cash"] == START_CASH + TOTAL - UNIT


def test_GOLDEN_bekor_qilingan_nasiya_credit_totalga_qaytmaydi(client, shop):
    """Prod: MANHATTAN #4214 — `refunded` NASIYA (qo'lda bekor qilingan qarz).
    Tuzatish faqat naqd/kartaga tegadi; nasiya qatori avvalgidek."""
    db = shop["db"]
    hk = _login(client, KASSIR_PHONE, KASSIR_PW)
    assert _pay(client, hk, shop["order"], "credit", TOTAL).status_code == 200
    db.expire_all()
    p = db.query(Payment).filter(Payment.order_id == shop["order"]).one()
    p.status = "refunded"
    db.commit()
    zb = _zbuild(db, shop["shift"], shop["admin"])
    z = _close(client, _login(client, ADMIN_PHONE, ADMIN_PW), shop["shift"])
    for r in (z, zb):
        assert (r["cash_sales"], r["card_sales"], r["credit_total"]) == (0, 0, 0)
        assert r["sales_count"] == 0
        assert r["expected_cash"] == START_CASH


def test_otgan_smena_z_vozvratdan_keyin_ozgarmaydi(client, shop):
    """Kecha sotilib bugun qaytgan chek: kechagi (yopilgan) Z qayta qurilganda
    sotuv o'z joyida qoladi. Ilgari asl to'lov `refunded` bo'lib, kechagi
    `cash_sales` orqaga qarab kamayardi."""
    db = shop["db"]
    hk = _login(client, KASSIR_PHONE, KASSIR_PW)
    ha = _login(client, ADMIN_PHONE, ADMIN_PW)
    assert _pay(client, hk, shop["order"], "cash", TOTAL).status_code == 200
    kecha = _close(client, ha, shop["shift"])
    oldin = _zbuild(db, shop["shift"], shop["admin"])

    db.add(Shift(tenant_id=shop["cafe"], user_id=shop["kassir"], start_time=utc_now(),
                 starting_cash=START_CASH))
    db.commit()
    _return(client, hk, ha, shop, qty=3)
    keyin = _zbuild(db, shop["shift"], shop["admin"])
    assert keyin["cash_sales"]    == oldin["cash_sales"]    == kecha["cash_sales"] == TOTAL
    assert keyin["expected_cash"] == oldin["expected_cash"] == kecha["expected_cash"]


def test_GOLDEN_cash_refund_amount_eski_yozuv():
    from utils.cashflow import cash_refund_amount

    class R:                                     # eski vozvrat: ustun NULL
        refund_method, total_amount, debt_offset = "cash", 70_000.0, None
    assert cash_refund_amount(R) == 70_000.0
    R.refund_method = "card"
    assert cash_refund_amount(R) == 0.0
    R.refund_method, R.debt_offset = "cash", 30_000.0
    assert cash_refund_amount(R) == 40_000.0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
