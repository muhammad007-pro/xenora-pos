"""Z-HISOBOT VA KASSA NAZORATI (fix/shift-report, 2026-10).

PROD DALILLARI:
  • MANHATTAN #52 — smena sanalgan naqd = 0 bilan yopildi → −42 325 002 soxta
    kamomad (maydon sukut bo'yicha 0, waiter.js umuman yubormasdi).
  • Yopish oynasida "kutilgan naqd" "..." edi, "kamomad" = sanalgan − boshlang'ich.
  • Kassir hisoboti (`/report`) "Jami tushum" = Σfinal − chegirma: chegirma
    `final_amount` da ALLAQACHON ayrilgan → ikki marta (MANHATTAN: 9,43 mln kam).
  • Egasi yashikdan pul olsa yozadigan joy yo'q → kamomad (BARAKA: −20,7 mln/30 kun).
  • BARAKA order 4094: chek 177 000, naqd to'lov 247 000 qabul qilingan.

BU TESTLAR QULFLAYDI:
  • counted_cash yuborilmasa 400 (0 — qonuniy), manfiy 400
  • X-hisobot: smenani yopmaydi, kutilgan naqd Z bilan AYNAN bir xil
  • inkassatsiya/razmen expected_cash ni to'g'rilaydi, savdo va "kassaga tushgan" ga TEGMAYDI
  • PUL bloki: naqd + karta + qarz to'lovi − qaytarish (naqd+karta)
  • /report net_revenue = Σfinal (chegirma bir marta)
  • to'lov > chek → 400; aniq summa va eski .exe 0,5 so'm yaxlitlash — o'tadi
  • GOLDEN: harakatsiz smenada expected_cash eski 4 argumentli formula bilan bir xil

Ishga tushirish:  cd backend && py -m pytest tests/test_shift_report.py -v
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
    AuditLog, Cafe, CashMovement, Customer, CustomerDebt, DebtPayment, Inventory, Order,
    OrderItem, Payment, Permission, Product, Return, Role, Shift, User,
)
from utils.cashflow import expected_cash as _expected_cash

ADMIN_PW,  ADMIN_PHONE  = "AdminZrep9", "+998900000071"
KASSIR_PW, KASSIR_PHONE = "KassirZr9",  "+998900000072"
BOSHQA_PW, BOSHQA_PHONE = "BoshqaZr9",  "+998900000073"

START = 100_000.0
NOW = utc_now()

# Smena tarkibi (fixture): naqd chek 300k, karta chek 100k − 10k chegirma = 90k,
# qarz to'lovi naqd 20k + karta 5k, vozvrat naqd 10k + karta 15k.
CASH_SALE, CARD_SALE, DISCOUNT = 300_000.0, 90_000.0, 10_000.0
DEBT_CASH, DEBT_CARD = 20_000.0, 5_000.0
REF_CASH, REF_CARD = 10_000.0, 15_000.0
EXPECTED = START + CASH_SALE - REF_CASH + DEBT_CASH                       # 410 000
CASH_IN  = CASH_SALE + CARD_SALE + DEBT_CASH + DEBT_CARD - REF_CASH - REF_CARD  # 390 000


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


def _user(db, cafe, role, n, phone, pw):
    u = User(username=f"u{n}", email=f"u{n}@x.uz", full_name=f"Xodim {n}", phone=phone,
             hashed_password=get_password_hash(pw), is_active=True,
             tenant_id=cafe.id, role_id=role.id)
    db.add(u)
    db.flush()
    return u


def _order(db, s, number, total, discount=0.0, status="completed"):
    o = Order(tenant_id=s["cafe"], order_number=number, daily_number=1, status=status,
              total_amount=total, discount_amount=discount, final_amount=total - discount,
              waiter_id=s["kassir"], shift_id=s["shift"], created_at=NOW - timedelta(minutes=40))
    db.add(o)
    db.flush()
    db.add(OrderItem(tenant_id=s["cafe"], order_id=o.id, product_id=s["product"],
                     quantity=1, unit_price=total, unit_cost=1.0, total_price=total))
    db.flush()
    return o


@pytest.fixture()
def shop(db_session):
    db = db_session
    p_pay, p_shift, p_rep, p_fin = (_perm(db, c) for c in
                                    ("process_payments", "manage_shifts", "view_reports", "view_finance"))
    r_admin  = _role(db, "admin",   [p_pay, p_shift, p_rep, p_fin])
    r_kassir = _role(db, "cashier", [p_pay, p_rep])

    cafe = Cafe(name="ZREP do'kon", code="zrp", access_code="100.200.71",
                business_type="store", subscription_plan="pro", is_active=True)
    db.add(cafe)
    db.flush()
    admin  = _user(db, cafe, r_admin,  71, ADMIN_PHONE,  ADMIN_PW)
    kassir = _user(db, cafe, r_kassir, 72, KASSIR_PHONE, KASSIR_PW)
    boshqa = _user(db, cafe, r_kassir, 73, BOSHQA_PHONE, BOSHQA_PW)

    prod = Product(tenant_id=cafe.id, name="TOVAR", price=1000.0, cost_price=1.0)
    db.add(prod)
    db.flush()
    db.add(Inventory(tenant_id=cafe.id, product_id=prod.id, quantity=1000.0, unit="dona"))
    shift = Shift(tenant_id=cafe.id, user_id=kassir.id,
                  start_time=NOW - timedelta(hours=2), starting_cash=START)
    db.add(shift)
    cust = Customer(tenant_id=cafe.id, name="Qarzdor", phone="+998901234571", total_debt=0.0)
    db.add(cust)
    db.flush()
    s = {"db": db, "cafe": cafe.id, "admin": admin.id, "kassir": kassir.id, "boshqa": boshqa.id,
         "shift": shift.id, "product": prod.id, "customer": cust.id}

    # Sotuvlar (allaqachon to'langan)
    o1 = _order(db, s, "Z-1", CASH_SALE)
    o2 = _order(db, s, "Z-2", CARD_SALE + DISCOUNT, discount=DISCOUNT)
    db.add_all([
        Payment(tenant_id=cafe.id, order_id=o1.id, cashier_id=kassir.id, amount=CASH_SALE,
                method="cash", status="paid", transaction_id="T1"),
        Payment(tenant_id=cafe.id, order_id=o2.id, cashier_id=kassir.id, amount=CARD_SALE,
                method="card", status="paid", transaction_id="T2"),
    ])
    # Eski nasiya qarzi to'lovi (naqd + karta) — smena ichida
    debt = CustomerDebt(tenant_id=cafe.id, customer_id=cust.id, amount=100_000.0,
                        paid_amount=DEBT_CASH + DEBT_CARD, remaining=75_000.0, status="partial")
    db.add(debt)
    db.flush()
    db.add_all([
        DebtPayment(debt_id=debt.id, amount=DEBT_CASH, payment_method="cash",
                    created_at=NOW - timedelta(minutes=30)),
        DebtPayment(debt_id=debt.id, amount=DEBT_CARD, payment_method="card",
                    created_at=NOW - timedelta(minutes=29)),
    ])
    # Vozvratlar (tasdiqlangan) — naqd va karta
    db.add_all([
        Return(tenant_id=cafe.id, return_number="R-Z1", total_amount=REF_CASH, refund_method="cash",
               status="approved", approved_at=NOW - timedelta(minutes=20)),
        Return(tenant_id=cafe.id, return_number="R-Z2", total_amount=REF_CARD, refund_method="card",
               status="approved", approved_at=NOW - timedelta(minutes=19)),
    ])
    db.commit()
    return s


def _login(client, phone, pw):
    r = client.post("/api/v1/auth/login", data={"username": phone, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _kassir(client):
    return _login(client, KASSIR_PHONE, KASSIR_PW)


def _move(client, h, sid, kind, amount, reason="egasiga topshirildi"):
    return client.post(f"/api/v1/shifts/{sid}/cash-movements",
                       json={"kind": kind, "amount": amount, "reason": reason}, headers=h)


# ══════════════════════════════════════════════════════════════════════════════
# 1. SANALGAN NAQD MAJBURIY
# ══════════════════════════════════════════════════════════════════════════════

def test_sanalgan_naqdsiz_yopib_bolmaydi(client, shop):
    h = _kassir(client)
    r = client.post(f"/api/v1/shifts/{shop['shift']}/close", headers=h)
    assert r.status_code == 400, r.text
    assert "sanab" in r.json()["detail"]
    db = shop["db"]
    db.expire_all()
    assert db.query(Shift).get(shop["shift"]).end_time is None   # smena OCHIQ qoldi


def test_waiter_js_eski_tanasi_ham_rad_etiladi(client, shop):
    """waiter.js `ending_cash` ni TANADA yuborardi — server o'qimasdi → 0 kamomad."""
    h = _kassir(client)
    r = client.post(f"/api/v1/shifts/{shop['shift']}/close", json={"ending_cash": 5}, headers=h)
    assert r.status_code == 400


def test_manfiy_sanalgan_rad(client, shop):
    r = client.post(f"/api/v1/shifts/{shop['shift']}/close?counted_cash=-1", headers=_kassir(client))
    assert r.status_code == 400


def test_nol_qonuniy(client, shop):
    r = client.post(f"/api/v1/shifts/{shop['shift']}/close?counted_cash=0", headers=_kassir(client))
    assert r.status_code == 200, r.text
    assert r.json()["shortage"] == -EXPECTED


def test_begona_smena_403_qiymatdan_oldin(client, shop):
    """Ruxsat qiymat tekshiruvidan OLDIN — begona smena holati sizmasin."""
    h = _login(client, BOSHQA_PHONE, BOSHQA_PW)
    assert client.post(f"/api/v1/shifts/{shop['shift']}/close", headers=h).status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# 2. X-HISOBOT (yopishdan oldingi ko'rinish)
# ══════════════════════════════════════════════════════════════════════════════

def test_x_hisobot_haqiqiy_kutilgan_naqd(client, shop):
    h = _kassir(client)
    r = client.get(f"/api/v1/shifts/{shop['shift']}/x-report", headers=h)
    assert r.status_code == 200, r.text
    x = r.json()
    assert x["is_open"] is True
    assert x["expected_cash"] == EXPECTED
    assert x["cash_in_total"] == CASH_IN
    # yopmaydi
    db = shop["db"]
    db.expire_all()
    assert db.query(Shift).get(shop["shift"]).end_time is None
    # Yopilgandagi Z bilan AYNAN bir xil
    z = client.post(f"/api/v1/shifts/{shop['shift']}/close?counted_cash={EXPECTED}", headers=h).json()
    assert z["expected_cash"] == x["expected_cash"] and z["shortage"] == 0


def test_x_hisobot_begona_kassirga_403(client, shop):
    h = _login(client, BOSHQA_PHONE, BOSHQA_PW)
    assert client.get(f"/api/v1/shifts/{shop['shift']}/x-report", headers=h).status_code == 403


def test_x_hisobot_admin_istalganini_koradi(client, shop):
    h = _login(client, ADMIN_PHONE, ADMIN_PW)
    assert client.get(f"/api/v1/shifts/{shop['shift']}/x-report", headers=h).status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# 3. PUL BLOKI (variant A)
# ══════════════════════════════════════════════════════════════════════════════

def test_pul_bloki_va_savdo_ajratilgan(client, shop):
    z = client.post(f"/api/v1/shifts/{shop['shift']}/close?counted_cash={EXPECTED}",
                    headers=_kassir(client)).json()
    # SAVDO — o'zgarmagan (GOLDEN)
    assert z["total_sales"] == CASH_SALE + CARD_SALE
    # PUL — naqd + karta + qarz to'lovi − qaytarish (naqd + karta)
    assert z["cash_in_total"] == CASH_IN
    assert z["card_refunds"] == REF_CARD
    assert z["money_refunds"] == REF_CASH + REF_CARD
    # YASHIK — karta qaytarish yashikka TEGMAYDI
    assert z["expected_cash"] == EXPECTED


def test_print_z_ma_lumoti_ham_pul_blokida(client, shop):
    """print-z (ESC/POS) yo'li — matnda SAVDO/PUL/YASHIK bloklari."""
    from services import escpos_service
    from routers.shift import _build_zreport_data
    db = shop["db"]
    shift = db.query(Shift).get(shop["shift"])
    user = db.query(User).get(shop["kassir"])
    data = _build_zreport_data(shift, db, user)
    txt = escpos_service.render_z_report(data, 80)
    for frag in ("JAMI SAVDO", "KASSAGA TUSHGAN", "YASHIK (NAQD)", "Bo'lishi kerak"):
        assert frag in txt, frag
    assert "390 000" in txt or "390000" in txt.replace(" ", "")
    escpos_service.build_z_report(data, 58)        # bayt quruvchi ham yiqilmaydi


# ══════════════════════════════════════════════════════════════════════════════
# 4. INKASSATSIYA
# ══════════════════════════════════════════════════════════════════════════════

def test_inkassatsiya_kutilgan_naqdni_tuzatadi(client, shop):
    h = _kassir(client)
    assert _move(client, h, shop["shift"], "withdrawal", 200_000).status_code == 200
    assert _move(client, h, shop["shift"], "deposit", 50_000, "razmen").status_code == 200
    want = EXPECTED - 200_000 + 50_000
    x = client.get(f"/api/v1/shifts/{shop['shift']}/x-report", headers=h).json()
    assert x["expected_cash"] == want
    assert x["withdrawals"] == 200_000 and x["deposits"] == 50_000
    assert len(x["cash_movements"]) == 2
    # Savdo va pul oqimi O'ZGARMAYDI — inkassatsiya tushum ham, xarajat ham emas
    assert x["total_sales"] == CASH_SALE + CARD_SALE
    assert x["cash_in_total"] == CASH_IN
    # Egasi olgan pul endi kamomad EMAS
    z = client.post(f"/api/v1/shifts/{shop['shift']}/close?counted_cash={want}", headers=h).json()
    assert z["shortage"] == 0


def test_inkassatsiya_xarajat_emas(client, shop):
    """Foyda hisobotiga tegmaydi: expenses jadvaliga yozilmaydi."""
    from models import Expense
    _move(client, _kassir(client), shop["shift"], "withdrawal", 100_000)
    assert shop["db"].query(Expense).count() == 0


def test_inkassatsiya_audit(client, shop):
    r = _move(client, _kassir(client), shop["shift"], "withdrawal", 70_000)
    mid = r.json()["id"]
    db = shop["db"]
    db.expire_all()
    a = db.query(AuditLog).filter(AuditLog.resource == "cash_movements",
                                  AuditLog.resource_id == str(mid)).first()
    assert a is not None


@pytest.mark.parametrize("body,code", [
    ({"kind": "steal", "amount": 1, "reason": "xx"}, 400),
    ({"kind": "withdrawal", "amount": 0, "reason": "xx"}, 400),
    ({"kind": "withdrawal", "amount": -5, "reason": "xx"}, 400),
    ({"kind": "withdrawal", "amount": "abc", "reason": "xx"}, 400),
    ({"kind": "withdrawal", "amount": 5}, 400),          # sababsiz
])
def test_inkassatsiya_validatsiya(client, shop, body, code):
    r = client.post(f"/api/v1/shifts/{shop['shift']}/cash-movements", json=body, headers=_kassir(client))
    assert r.status_code == code, r.text


def test_inkassatsiya_yopilgan_smenaga_yoq(client, shop):
    h = _kassir(client)
    client.post(f"/api/v1/shifts/{shop['shift']}/close?counted_cash=0", headers=h)
    assert _move(client, h, shop["shift"], "withdrawal", 10).status_code == 400


def test_inkassatsiya_begona_kassir_403(client, shop):
    h = _login(client, BOSHQA_PHONE, BOSHQA_PW)
    assert _move(client, h, shop["shift"], "withdrawal", 10).status_code == 403
    assert shop["db"].query(CashMovement).count() == 0


def test_inkassatsiya_boshqa_smenaga_tushmaydi(client, shop):
    """Vaqt oralig'i emas, shift_id — parallel ochiq smena ta'sirlanmaydi."""
    db = shop["db"]
    other = Shift(tenant_id=shop["cafe"], user_id=shop["boshqa"],
                  start_time=NOW - timedelta(hours=3), starting_cash=0.0)
    db.add(other)
    db.commit()
    _move(client, _kassir(client), shop["shift"], "withdrawal", 100_000)
    h2 = _login(client, BOSHQA_PHONE, BOSHQA_PW)
    x2 = client.get(f"/api/v1/shifts/{other.id}/x-report", headers=h2).json()
    assert x2["withdrawals"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# 5. KASSIR HISOBOTI — chegirma bir marta
# ══════════════════════════════════════════════════════════════════════════════

def test_report_chegirma_ikki_marta_ayirilmaydi(client, shop):
    h = _kassir(client)
    client.post(f"/api/v1/shifts/{shop['shift']}/close?counted_cash={EXPECTED - 5000}", headers=h)
    r = client.get(f"/api/v1/shifts/{shop['shift']}/report", headers=h).json()
    assert r["summary"]["net_revenue"] == CASH_SALE + CARD_SALE     # 390 000, 380 000 EMAS
    assert r["summary"]["discount_total"] == DISCOUNT
    # Kassir endi kutilgan naqd va kamomadni ko'radi
    assert r["expected_cash"] == EXPECTED
    assert r["counted_cash"] == EXPECTED - 5000
    assert r["shortage"] == -5000
    assert r["cash_in_total"] == CASH_IN


# ══════════════════════════════════════════════════════════════════════════════
# 6. ORTIQCHA TO'LOV
# ══════════════════════════════════════════════════════════════════════════════

def _pending(db, s, number, total):
    o = _order(db, s, number, total, status="pending")
    db.commit()
    return o.id


def _pay(client, h, oid, amount, method="cash", offline=False):
    url = "/api/v1/payments/" + ("?offline_sync=1" if offline else "")
    return client.post(url, json={"order_id": oid, "method": method, "amount": amount}, headers=h)


def test_ortiqcha_tolov_rad(client, shop):
    """BARAKA 4094: chek 177 000, to'lov 247 000."""
    oid = _pending(shop["db"], shop, "P-1", 177_000.0)
    r = _pay(client, _kassir(client), oid, 247_000.0)
    assert r.status_code == 400, r.text
    assert "ko'p" in r.json()["detail"]
    assert shop["db"].query(Payment).filter(Payment.order_id == oid).count() == 0


def test_aniq_tolov_otadi(client, shop):
    oid = _pending(shop["db"], shop, "P-2", 177_000.0)
    assert _pay(client, _kassir(client), oid, 177_000.0).status_code == 200


def test_eski_exe_yarim_som_yaxlitlash_otadi(client, shop):
    """Eski .exe aralash to'lovda Math.round(total) — kg chekda +0,5 so'm."""
    oid = _pending(shop["db"], shop, "P-3", 14_998.6)
    assert _pay(client, _kassir(client), oid, 14_999.0).status_code == 200


def test_tolangan_chekka_yana_tolov_rad(client, shop):
    h = _kassir(client)
    oid = _pending(shop["db"], shop, "P-4", 50_000.0)
    assert _pay(client, h, oid, 50_000.0).status_code == 200
    assert _pay(client, h, oid, 50_000.0).status_code == 400


def test_split_qismlar_otadi_oshgani_rad(client, shop):
    h = _kassir(client)
    oid = _pending(shop["db"], shop, "P-5", 100_000.0)
    assert _pay(client, h, oid, 60_000.0, "card").status_code == 200
    assert _pay(client, h, oid, 50_000.0).status_code == 400          # 110k > 100k
    assert _pay(client, h, oid, 40_000.0).status_code == 200


def test_offline_sync_istisno(client, shop):
    """Offline navbat replay — rad etilsa sync.js sotuvni yo'qotardi (log bilan qabul)."""
    oid = _pending(shop["db"], shop, "P-6", 10_000.0)
    assert _pay(client, _kassir(client), oid, 12_000.0, offline=True).status_code == 200


def test_manfiy_tolov_rad(client, shop):
    oid = _pending(shop["db"], shop, "P-7", 10_000.0)
    assert _pay(client, _kassir(client), oid, -5.0).status_code in (400, 422)   # sxema yoki server


# ══════════════════════════════════════════════════════════════════════════════
# 7. GOLDEN
# ══════════════════════════════════════════════════════════════════════════════

def test_golden_harakatsiz_eski_formula(client, shop):
    z = client.post(f"/api/v1/shifts/{shop['shift']}/close?counted_cash=1",
                    headers=_kassir(client)).json()
    old = _expected_cash(START, z["cash_sales"], z["cash_refunds"], z["debt_paid_cash"])
    assert z["expected_cash"] == round(old, 0)
    assert z["withdrawals"] == 0 and z["deposits"] == 0
    for k in ("cash_sales", "card_sales", "credit_total", "total_sales", "sales_count",
              "discount_total", "returns_total", "cash_refunds", "debt_paid_cash", "debt_paid_card"):
        assert k in z, k
