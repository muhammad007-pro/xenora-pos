"""MIJOZ QARZ KARTOCHKASI — `GET /api/v1/customers/{id}/debt-card`.

Nima uchun bu testlar bor:

  1. **Qoldiq ikki joyda bir xil bo'lishi SHART.** Kartochka pul mantig'ini
     QAYTA HISOBLAMAYDI — `customers.total_debt` ni o'qiydi. Lekin xronologik
     oborotning oxirgi qatori (`balance`) ham shu raqamni bermasa, do'konchi
     ikki xil son ko'radi va ikkisiga ham ishonmaydi. Shu kafolat shu yerda
     qotirilgan (`suppliers.py` oborot varag'idagi bilan bir xil shartnoma).

  2. **Vozvrat tuzog'i.** `routers/returns.py` qarzni `paid_amount` orqali
     kamaytiradi, lekin `DebtPayment` qatori YARATMAYDI. Agar oborot faqat
     `DebtPayment` lardan yig'ilsa, qoldiq kartadagi raqamdan OSHIB ketadi.
     Shuning uchun "vozvrat bilan yopilgan" qatori bor — pastdagi test shuni
     tekshiradi.

  3. **`order_id IS NULL`** — qo'lda kiritilgan qarz (POS'siz, "+ Qarz yozish").
     Prodda bunday qatorlar bor edi (XOZMAG, 2026-10-02). Kartochka chek
     raqamini topolmay 500 bermasligi kerak.

  4. **Tenant izolyatsiyasi** — begona do'kon mijozining qarzi KO'RINMASIN.

Ishga tushirish:
    cd backend && py -m pytest tests/test_customer_debt_card.py -v
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

from database import Base, get_db
from main import app
from models import (
    Cafe, Customer, CustomerDebt, DebtPayment, Order, OrderItem, Product,
    User, Role, Permission,
)
from core.security import get_password_hash
from core.timeutils import utc_now

PW_A, PW_B = "AdminAlfa9x", "AdminBeta7y"
PHONE_A, PHONE_B = "+998900000031", "+998900000032"


@pytest.fixture()
def db_session():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,   # TestClient va test bir bazani ko'rsin
    )
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng, autocommit=False, autoflush=False)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        Base.metadata.drop_all(eng)
        eng.dispose()


@pytest.fixture()
def client(db_session):
    def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def seeded(db_session):
    """Ikki do'kon. A da to'liq qarz tarixi, B da begona mijoz."""
    db = db_session
    t0 = utc_now() - timedelta(days=10)

    p_rep = Permission(code="view_reports", description="Hisobotlar")
    db.add(p_rep)
    db.flush()
    role = Role(name="admin", description="Administrator")
    role.permissions = [p_rep]
    db.add(role)
    db.flush()

    cafe_a = Cafe(name="Do'kon A", code="dka", access_code="100.200.31",
                  business_type="store", subscription_plan="pro", is_active=True)
    cafe_b = Cafe(name="Do'kon B", code="dkb", access_code="100.200.32",
                  business_type="store", subscription_plan="pro", is_active=True)
    db.add_all([cafe_a, cafe_b])
    db.flush()

    db.add_all([
        User(username="admin_a", email="a@x.uz", full_name="Admin A", phone=PHONE_A,
             hashed_password=get_password_hash(PW_A), is_active=True,
             is_superuser=False, tenant_id=cafe_a.id, role_id=role.id),
        User(username="admin_b", email="b@x.uz", full_name="Admin B", phone=PHONE_B,
             hashed_password=get_password_hash(PW_B), is_active=True,
             is_superuser=False, tenant_id=cafe_b.id, role_id=role.id),
    ])
    db.flush()
    kassir = User(username="kassir_a", email="k@x.uz", full_name="Kassir Diyor",
                  phone="+998900000033", hashed_password=get_password_hash(PW_A),
                  is_active=True, is_superuser=False,
                  tenant_id=cafe_a.id, role_id=role.id)
    db.add(kassir)
    db.flush()

    # ── A do'kon: mijoz + 2 chekli qarz + 1 qo'lda qarz ────────────────────
    cust = Customer(tenant_id=cafe_a.id, name="Shuhrat aka", phone="+998905838778",
                    total_debt=0.0)
    db.add(cust)
    db.flush()

    prod = Product(tenant_id=cafe_a.id, name="HOFF Q38-E-004", price=250000.0)
    db.add(prod)
    db.flush()

    o1 = Order(tenant_id=cafe_a.id, order_number="A-1001", daily_number=5,
               customer_id=cust.id, status="completed", total_amount=250000.0,
               final_amount=240000.0, discount_amount=10000.0, created_at=t0)
    o2 = Order(tenant_id=cafe_a.id, order_number="A-1002", daily_number=6,
               customer_id=cust.id, status="completed", total_amount=60000.0,
               final_amount=60000.0, created_at=t0 + timedelta(days=1))
    db.add_all([o1, o2])
    db.flush()
    db.add_all([
        OrderItem(tenant_id=cafe_a.id, order_id=o1.id, product_id=prod.id,
                  quantity=1, unit_price=250000.0, total_price=250000.0),
        OrderItem(tenant_id=cafe_a.id, order_id=o2.id, product_id=prod.id,
                  quantity=2, unit_price=30000.0, total_price=60000.0),
    ])

    # 1) chekli qarz, qisman to'langan (240 000 − 40 000 = 200 000)
    d1 = CustomerDebt(tenant_id=cafe_a.id, customer_id=cust.id, order_id=o1.id,
                      amount=240000.0, paid_amount=40000.0, remaining=200000.0,
                      status="partial", notes="POS dan nasiya",
                      user_id=kassir.id, created_at=t0)
    # 2) chekli qarz, to'liq ochiq
    d2 = CustomerDebt(tenant_id=cafe_a.id, customer_id=cust.id, order_id=o2.id,
                      amount=60000.0, paid_amount=0.0, remaining=60000.0,
                      status="open", notes="POS dan nasiya",
                      user_id=kassir.id, created_at=t0 + timedelta(days=1))
    # 3) QO'LDA kiritilgan qarz — order_id YO'Q (prodda bor holat)
    d3 = CustomerDebt(tenant_id=cafe_a.id, customer_id=cust.id, order_id=None,
                      amount=15000.0, paid_amount=0.0, remaining=15000.0,
                      status="open", notes="Hoff smistitel",
                      user_id=kassir.id, created_at=t0 + timedelta(days=2))
    db.add_all([d1, d2, d3])
    db.flush()

    # d1 ga 40 000 naqd to'lov (kassir qabul qilgan)
    db.add(DebtPayment(debt_id=d1.id, amount=40000.0, payment_method="cash",
                       user_id=kassir.id, created_at=t0 + timedelta(days=3)))

    # `routers/debt.py::_recalc_customer_debt` qoidasi: ochiq+qisman remaining
    cust.total_debt = 200000.0 + 60000.0 + 15000.0   # 275 000
    db.commit()

    # ── B do'kon: begona mijoz (A ko'rmasligi kerak va aksincha) ───────────
    cust_b = Customer(tenant_id=cafe_b.id, name="Begona mijoz",
                      phone="+998901111111", total_debt=99000.0)
    db.add(cust_b)
    db.flush()
    db.add(CustomerDebt(tenant_id=cafe_b.id, customer_id=cust_b.id, order_id=None,
                        amount=99000.0, paid_amount=0.0, remaining=99000.0,
                        status="open", created_at=t0))
    db.commit()

    return {
        "db": db, "cafe_a": cafe_a.id, "cafe_b": cafe_b.id,
        "cust_a": cust.id, "cust_b": cust_b.id,
        "d1": d1.id, "d2": d2.id, "d3": d3.id,
        "o1": o1.id, "o2": o2.id,
    }


def _login(client, phone, password):
    r = client.post("/api/v1/auth/login", data={"username": phone, "password": password})
    assert r.status_code == 200, f"login yiqildi: {r.status_code} {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _card(client, headers, customer_id):
    return client.get(f"/api/v1/customers/{customer_id}/debt-card", headers=headers)


# ══════════════════════════════════════════════════════════════════════════════
# 1) QOLDIQ — karta va oborot bitta raqamni ko'rsatadi
# ══════════════════════════════════════════════════════════════════════════════

def test_kartochka_togri_qoldiq_korsatadi(client, seeded):
    hdr = _login(client, PHONE_A, PW_A)
    r = _card(client, hdr, seeded["cust_a"])
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    body = r.json()

    s = body["summary"]
    assert s["total_debt"] == 275000.0            # customers.total_debt
    assert s["ledger_balance"] == 275000.0        # oborotdan hisoblangani
    assert s["total_charged"] == 315000.0         # 240k + 60k + 15k
    assert s["total_paid"] == 40000.0
    assert s["debt_count"] == 3
    assert s["open_count"] == 2
    assert s["partial_count"] == 1
    assert s["manual_count"] == 1

    # KAFOLAT: oborotning OXIRGI qatori = kartadagi jami qoldiq
    assert body["ledger"], "oborot bo'sh"
    assert body["ledger"][-1]["balance"] == s["total_debt"], (
        "oborot qoldig'i karta raqamidan farq qiladi — do'konchi ikki xil son ko'radi")

    # Xronologiya: qarz → qarz → qarz → to'lov (sana bo'yicha)
    assert [e["kind"] for e in body["ledger"]] == ["debt", "debt", "debt", "payment"]
    # Yugurib boruvchi qoldiq: 240k → 300k → 315k → 275k
    assert [e["balance"] for e in body["ledger"]] == [240000.0, 300000.0, 315000.0, 275000.0]
    # To'lov MANFIY (qarzni kamaytiradi)
    assert body["ledger"][-1]["amount"] == -40000.0


def test_tolovlar_tarixi_kim_qabul_qilgani_bilan(client, seeded):
    hdr = _login(client, PHONE_A, PW_A)
    body = _card(client, hdr, seeded["cust_a"]).json()

    assert len(body["payments"]) == 1
    p = body["payments"][0]
    assert p["amount"] == 40000.0
    assert p["payment_method"] == "cash"
    assert p["user_name"] == "Kassir Diyor", "to'lovni kim qabul qilgani ko'rinmaydi"
    assert p["debt_id"] == seeded["d1"]


# ══════════════════════════════════════════════════════════════════════════════
# 2) CHEK RAQAMI + OLINGAN MAHSULOTLAR
# ══════════════════════════════════════════════════════════════════════════════

def test_chek_raqami_va_mahsulotlar_korinadi(client, seeded):
    hdr = _login(client, PHONE_A, PW_A)
    body = _card(client, hdr, seeded["cust_a"]).json()

    d1 = next(d for d in body["debts"] if d["id"] == seeded["d1"])
    assert d1["order_id"] == seeded["o1"]
    assert d1["order_number"] == "A-1001"
    assert d1["daily_number"] == 5
    assert d1["is_manual"] is False
    assert len(d1["items"]) == 1
    assert d1["items"][0]["name"] == "HOFF Q38-E-004"
    assert d1["items"][0]["quantity"] == 1
    assert d1["items"][0]["total_price"] == 250000.0

    d2 = next(d for d in body["debts"] if d["id"] == seeded["d2"])
    assert d2["order_number"] == "A-1002"
    assert d2["items"][0]["quantity"] == 2

    # Oborotda ham chek raqami bo'lishi kerak (qatorga bosib mahsulot ko'rish)
    led_d1 = next(e for e in body["ledger"] if e.get("debt_id") == seeded["d1"]
                  and e["kind"] == "debt")
    assert led_d1["order_number"] == "A-1001"
    assert "A-1001" in led_d1["label"]


# ══════════════════════════════════════════════════════════════════════════════
# 3) order_id NULL — "qo'lda kiritilgan", xato BERMAYDI
# ══════════════════════════════════════════════════════════════════════════════

def test_order_id_null_qarz_buzilmaydi(client, seeded):
    hdr = _login(client, PHONE_A, PW_A)
    r = _card(client, hdr, seeded["cust_a"])
    assert r.status_code == 200, f"order_id NULL da yiqildi: {r.status_code} {r.text}"

    d3 = next(d for d in r.json()["debts"] if d["id"] == seeded["d3"])
    assert d3["order_id"] is None
    assert d3["order_number"] is None
    assert d3["is_manual"] is True, "qo'lda kiritilgan qarz belgilanmagan"
    assert d3["items"] == []
    assert d3["amount"] == 15000.0

    led = next(e for e in r.json()["ledger"] if e.get("debt_id") == seeded["d3"])
    assert led["label"] == "Qo'lda kiritilgan qarz"
    assert led["order_number"] is None


def test_qarzsiz_mijoz_bosh_kartochka_beradi(client, seeded):
    """Qarzi yo'q mijoz ham 200 qaytarsin (bo'sh ro'yxat), 404/500 emas."""
    db = seeded["db"]
    yangi = Customer(tenant_id=seeded["cafe_a"], name="Qarzsiz mijoz",
                     phone="+998902222222", total_debt=0.0)
    db.add(yangi)
    db.commit()

    hdr = _login(client, PHONE_A, PW_A)
    r = _card(client, hdr, yangi.id)
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    body = r.json()
    assert body["debts"] == [] and body["payments"] == [] and body["ledger"] == []
    assert body["summary"]["total_debt"] == 0.0
    assert body["summary"]["ledger_balance"] == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# 4) VOZVRAT TUZOG'I — DebtPayment qatori YO'Q, lekin qarz kamaygan
# ══════════════════════════════════════════════════════════════════════════════

def test_vozvrat_bilan_yopilgan_qism_oborotga_tushadi(client, seeded):
    """`returns.py` paid_amount ni oshiradi, DebtPayment yozmaydi.

    Shu qator bo'lmasa oborot qoldig'i `total_debt` dan OSHIB ketadi.
    """
    db = seeded["db"]
    d2 = db.query(CustomerDebt).get(seeded["d2"])
    d2.paid_amount = 20000.0      # vozvrat 20 000 ni yopdi
    d2.remaining = 40000.0
    d2.status = "partial"
    cust = db.query(Customer).get(seeded["cust_a"])
    cust.total_debt = 200000.0 + 40000.0 + 15000.0   # 255 000
    db.commit()

    hdr = _login(client, PHONE_A, PW_A)
    body = _card(client, hdr, seeded["cust_a"]).json()

    kinds = [e["kind"] for e in body["ledger"]]
    assert "return" in kinds, "vozvrat bilan yopilgan qism oborotda ko'rinmaydi"
    ret = next(e for e in body["ledger"] if e["kind"] == "return")
    assert ret["amount"] == -20000.0
    assert ret["debt_id"] == seeded["d2"]

    assert body["summary"]["ledger_balance"] == 255000.0
    assert body["ledger"][-1]["balance"] == body["summary"]["total_debt"]


# ══════════════════════════════════════════════════════════════════════════════
# 5) TENANT IZOLYATSIYASI
# ══════════════════════════════════════════════════════════════════════════════

def test_begona_tenant_mijozini_korib_bolmaydi(client, seeded):
    """B do'kon admini A do'kon mijozining kartochkasini OLMAYDI."""
    hdr_b = _login(client, PHONE_B, PW_B)
    r = _card(client, hdr_b, seeded["cust_a"])
    assert r.status_code == 404, (
        f"TENANT TESHIGI — begona mijoz kartochkasi ochildi: {r.status_code} {r.text}")

    # Teskari tomon ham yopiq
    hdr_a = _login(client, PHONE_A, PW_A)
    assert _card(client, hdr_a, seeded["cust_b"]).status_code == 404


def test_nasiya_royxati_qidiruv_tenant_ichida(client, seeded):
    """`/debts/?search=` — ism/telefon bo'yicha, faqat o'z do'koni ichida."""
    hdr_a = _login(client, PHONE_A, PW_A)

    r = client.get("/api/v1/debts/?search=Shuhrat", headers=hdr_a)
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    assert len(r.json()) == 3, "ism bo'yicha qidiruv qarzlarni topmadi"

    r = client.get("/api/v1/debts/?search=5838778", headers=hdr_a)
    assert len(r.json()) == 3, "telefon bo'yicha qidiruv ishlamadi"

    r = client.get("/api/v1/debts/?search=yo%27q-bunday", headers=hdr_a)
    assert r.json() == []

    # Begona do'kon mijozi nomi bilan qidirilsa — hech narsa chiqmasin
    r = client.get("/api/v1/debts/?search=Begona", headers=hdr_a)
    assert r.json() == [], "qidiruv begona tenant qarzini ko'rsatdi"
