"""VOZVRAT — SOTUVNI RO'YXATDAN TANLASH (`GET /returns/orders`).

NEGA KERAK: `GET /returns/lookup` chek raqamini BILISHNI talab qiladi. Mijoz
chekni yo'qotgan bo'lsa kassir yana qo'lda kiritishga qaytardi — `order_item_id`
yuborilmasdi, miqdor cheklovi tekshirilmasdi (XOZMAG `RET261002001` aynan
shunday paydo bo'lgan: `order_id IS NULL`).

Bu endpoint FAQAT RO'YXAT beradi. Tanlangandan keyin UI avvalgidek `/lookup`
ga boradi — qaytarish mantig'i o'zgarmaydi.

Ishga tushirish:
    cd backend && py -m pytest tests/test_returns_order_picker.py -v
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
    Cafe, Customer, Order, OrderItem, Payment, Product, Return, ReturnItem,
    Role, Permission, User,
)
from core.security import get_password_hash
from core.timeutils import utc_now

PW_A, PHONE_A = "AdminAlfa9x", "+998900000051"
PW_B, PHONE_B = "AdminBeta7y", "+998900000052"


@pytest.fixture()
def db_session():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
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


def _perm(db, code):
    p = db.query(Permission).filter(Permission.code == code).first()
    if not p:
        p = Permission(code=code, description=code)
        db.add(p)
        db.flush()
    return p


@pytest.fixture()
def seeded(db_session):
    """A do'kon: 4 sotuv (biri to'liq, biri qisman qaytarilgan) + B do'kon."""
    db = db_session
    now = utc_now()

    perms = [_perm(db, c) for c in ("process_payments", "view_reports", "manage_shifts")]
    role = db.query(Role).filter(Role.name == "admin").first()
    if not role:
        role = Role(name="admin", description="Administrator")
        db.add(role)
        db.flush()
    role.permissions = perms
    db.flush()

    cafe_a = Cafe(name="Do'kon A", code="dka", access_code="100.200.51",
                  business_type="store", subscription_plan="pro", is_active=True)
    cafe_b = Cafe(name="Do'kon B", code="dkb", access_code="100.200.52",
                  business_type="store", subscription_plan="pro", is_active=True)
    db.add_all([cafe_a, cafe_b])
    db.flush()

    db.add_all([
        User(username="a", email="a@x.uz", full_name="Admin A", phone=PHONE_A,
             hashed_password=get_password_hash(PW_A), is_active=True,
             is_superuser=False, tenant_id=cafe_a.id, role_id=role.id),
        User(username="b", email="b@x.uz", full_name="Admin B", phone=PHONE_B,
             hashed_password=get_password_hash(PW_B), is_active=True,
             is_superuser=False, tenant_id=cafe_b.id, role_id=role.id),
    ])
    db.flush()

    cust = Customer(tenant_id=cafe_a.id, name="Dilnoza Karimova",
                    phone="+998901234567")
    db.add(cust)
    prod = Product(tenant_id=cafe_a.id, name="EMULTSA BALANCE", price=9000.0,
                   cost_price=7000.0)
    db.add(prod)
    db.flush()

    def _sotuv(cafe_id, nomer, summa, kun, *, mijoz=None, soat=1, qty=2, usul="cash"):
        o = Order(tenant_id=cafe_id, order_number=nomer, daily_number=kun,
                  status="completed", total_amount=summa, final_amount=summa,
                  customer_id=mijoz, created_at=now - timedelta(hours=soat))
        db.add(o)
        db.flush()
        oi = OrderItem(tenant_id=cafe_id, order_id=o.id, product_id=prod.id,
                       quantity=qty, unit_price=summa / qty, unit_cost=7000.0,
                       total_price=summa)
        db.add(oi)
        db.add(Payment(tenant_id=cafe_id, order_id=o.id, amount=summa,
                       method=usul, status="paid"))
        db.flush()
        return o, oi

    # A: aniq 360 000 · taxminiy 359 500 · uzoq 350 000 · mijozli 120 000
    o_exact, oi_exact = _sotuv(cafe_a.id, "A-1001", 360000.0, 1, soat=1)
    o_near,  oi_near  = _sotuv(cafe_a.id, "A-1002", 359500.0, 2, soat=2)
    o_far,   oi_far   = _sotuv(cafe_a.id, "A-1003", 350000.0, 3, soat=3)
    o_cust,  oi_cust  = _sotuv(cafe_a.id, "A-1004", 120000.0, 4, soat=4, mijoz=cust.id)

    # `o_far` TO'LIQ qaytarilgan (2 dona sotildi, 2 dona qaytdi)
    r_full = Return(tenant_id=cafe_a.id, return_number="RET-A-1", order_id=o_far.id,
                    reason="dislike", total_amount=350000.0, refund_method="cash",
                    status="approved", created_at=now)
    db.add(r_full)
    db.flush()
    db.add(ReturnItem(return_id=r_full.id, product_id=prod.id,
                      order_item_id=oi_far.id, quantity=2, base_qty=2,
                      unit_price=175000.0, total=350000.0))

    # `o_cust` QISMAN qaytarilgan (2 dan 1 tasi)
    r_part = Return(tenant_id=cafe_a.id, return_number="RET-A-2", order_id=o_cust.id,
                    reason="broken", total_amount=60000.0, refund_method="cash",
                    status="approved", created_at=now)
    db.add(r_part)
    db.flush()
    db.add(ReturnItem(return_id=r_part.id, product_id=prod.id,
                      order_item_id=oi_cust.id, quantity=1, base_qty=1,
                      unit_price=60000.0, total=60000.0))

    # B do'kon sotuvi — A ko'rmasligi kerak
    o_b, _ = _sotuv(cafe_b.id, "B-9001", 999000.0, 1, soat=1)

    # Bekor qilingan sotuv — ro'yxatga TUSHMASLIGI kerak
    db.add(Order(tenant_id=cafe_a.id, order_number="A-1099", daily_number=9,
                 status="cancelled", total_amount=77000.0, final_amount=77000.0,
                 created_at=now - timedelta(hours=1)))
    db.commit()

    return {"db": db, "cafe_a": cafe_a.id, "cafe_b": cafe_b.id,
            "exact": o_exact.id, "near": o_near.id, "far": o_far.id,
            "cust": o_cust.id, "b": o_b.id, "customer": cust.id}


def _login(client, phone, pw):
    r = client.post("/api/v1/auth/login", data={"username": phone, "password": pw})
    assert r.status_code == 200, f"login yiqildi: {r.status_code} {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _orders(client, hdr, **params):
    r = client.get("/api/v1/returns/orders", params=params, headers=hdr)
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    return r.json()


# ══════════════════════════════════════════════════════════════════════════════
# 1) RO'YXAT
# ══════════════════════════════════════════════════════════════════════════════

def test_royxat_togri_qaytadi(client, seeded):
    hdr = _login(client, PHONE_A, PW_A)
    rows = _orders(client, hdr)

    nomerlar = [r["order_number"] for r in rows]
    assert "A-1001" in nomerlar and "A-1004" in nomerlar
    # Bekor qilingan sotuv ro'yxatda YO'Q
    assert "A-1099" not in nomerlar, "cancelled sotuv ro'yxatga tushdi"
    # Eng yangisi tepada (created_at desc)
    assert nomerlar[0] == "A-1001"

    r1 = next(r for r in rows if r["order_number"] == "A-1001")
    assert r1["order_id"] == seeded["exact"]
    assert r1["daily_number"] == 1
    assert r1["final_amount"] == 360000.0
    assert r1["payment_methods"] == ["cash"]
    assert r1["customer_name"] is None

    r4 = next(r for r in rows if r["order_number"] == "A-1004")
    assert r4["customer_name"] == "Dilnoza Karimova"


def test_marshrut_return_id_dan_oldin(client, seeded):
    """`/orders` `/{return_id}` dan OLDIN turishi SHART — aks holda 422."""
    hdr = _login(client, PHONE_A, PW_A)
    r = client.get("/api/v1/returns/orders", headers=hdr)
    assert r.status_code == 200, (
        f"/orders marshrut sifatida o'qilmadi ({r.status_code}) — "
        f"`/{{return_id}}` dan keyin qolib ketgan bo'lishi mumkin: {r.text}")
    assert isinstance(r.json(), list)


# ══════════════════════════════════════════════════════════════════════════════
# 2) QAYTARISH BELGILARI
# ══════════════════════════════════════════════════════════════════════════════

def test_has_returns_va_fully_returned(client, seeded):
    hdr = _login(client, PHONE_A, PW_A)
    rows = {r["order_number"]: r for r in _orders(client, hdr)}

    # Hech narsa qaytarilmagan
    assert rows["A-1001"]["has_returns"] is False
    assert rows["A-1001"]["fully_returned"] is False

    # TO'LIQ qaytarilgan (2 dan 2)
    assert rows["A-1003"]["has_returns"] is True
    assert rows["A-1003"]["fully_returned"] is True, "to'liq qaytarilgan sotuv belgilanmadi"

    # QISMAN qaytarilgan (2 dan 1) — tanlash mumkin bo'lib qolsin
    assert rows["A-1004"]["has_returns"] is True
    assert rows["A-1004"]["fully_returned"] is False, "qisman qaytarilgan to'liq deb belgilandi"


def test_rad_etilgan_vozvrat_sanalmaydi(client, seeded):
    """`rejected` vozvrat miqdorni band QILMAYDI (`_returned_qty_map` qoidasi)."""
    db = seeded["db"]
    r = Return(tenant_id=seeded["cafe_a"], return_number="RET-A-3",
               order_id=seeded["exact"], reason="other", total_amount=360000.0,
               refund_method="cash", status="rejected", created_at=utc_now())
    db.add(r)
    db.flush()
    oi = db.query(OrderItem).filter(OrderItem.order_id == seeded["exact"]).first()
    db.add(ReturnItem(return_id=r.id, product_id=oi.product_id,
                      order_item_id=oi.id, quantity=2, base_qty=2,
                      unit_price=180000.0, total=360000.0))
    db.commit()

    hdr = _login(client, PHONE_A, PW_A)
    row = next(r for r in _orders(client, hdr) if r["order_number"] == "A-1001")
    assert row["has_returns"] is False, "rad etilgan vozvrat sanalib ketdi"
    assert row["fully_returned"] is False


# ══════════════════════════════════════════════════════════════════════════════
# 3) QIDIRUV
# ══════════════════════════════════════════════════════════════════════════════

def test_qidiruv_chek_raqami(client, seeded):
    hdr = _login(client, PHONE_A, PW_A)
    rows = _orders(client, hdr, search="A-1002")
    assert [r["order_number"] for r in rows] == ["A-1002"]

    # Qismli moslik ham ishlaydi (kassir oxirini yozgan)
    rows = _orders(client, hdr, search="1004")
    assert any(r["order_number"] == "A-1004" for r in rows)


def test_qidiruv_mijoz_ismi(client, seeded):
    hdr = _login(client, PHONE_A, PW_A)
    rows = _orders(client, hdr, search="Dilnoza")
    assert [r["order_number"] for r in rows] == ["A-1004"]
    assert rows[0]["customer_name"] == "Dilnoza Karimova"


def test_qidiruv_summa_aniq_moslik_birinchi(client, seeded):
    """"360000" → aniq moslik BIRINCHI, keyin taxminiy (±1000)."""
    hdr = _login(client, PHONE_A, PW_A)
    rows = _orders(client, hdr, search="360000")
    nomerlar = [r["order_number"] for r in rows]

    assert nomerlar[0] == "A-1001", f"aniq moslik birinchi turmadi: {nomerlar}"
    assert "A-1002" in nomerlar, "taxminiy moslik (359 500) chiqmadi"
    assert "A-1003" not in nomerlar, "oraliqdan tashqari summa (350 000) chiqdi"


def test_qidiruv_natijasiz_bosh_royxat(client, seeded):
    hdr = _login(client, PHONE_A, PW_A)
    assert _orders(client, hdr, search="yo'q-bunday-chek") == []


def test_sana_filtri(client, seeded):
    """Kelajakdagi oraliq — bo'sh (period_dates kelajakni kesadi)."""
    hdr = _login(client, PHONE_A, PW_A)
    ertaga = (utc_now() + timedelta(days=5)).date().isoformat()
    assert _orders(client, hdr, date_from=ertaga, date_to=ertaga) == []

    # Buzuq sana — 400 (500 EMAS)
    r = client.get("/api/v1/returns/orders", params={"date_from": "02-10-2026"}, headers=hdr)
    assert r.status_code == 400, f"buzuq sana 400 bermadi: {r.status_code} {r.text}"


# ══════════════════════════════════════════════════════════════════════════════
# 4) TENANT IZOLYATSIYASI
# ══════════════════════════════════════════════════════════════════════════════

def test_begona_tenant_sotuvi_korinmaydi(client, seeded):
    hdr_a = _login(client, PHONE_A, PW_A)
    nomerlar = [r["order_number"] for r in _orders(client, hdr_a)]
    assert "B-9001" not in nomerlar, "TENANT TESHIGI — begona sotuv ro'yxatda"

    # Qidiruv orqali ham chiqmasin
    assert _orders(client, hdr_a, search="B-9001") == []
    assert _orders(client, hdr_a, search="999000") == []

    # B faqat o'zini ko'radi
    hdr_b = _login(client, PHONE_B, PW_B)
    nomerlar_b = [r["order_number"] for r in _orders(client, hdr_b)]
    assert nomerlar_b == ["B-9001"]


def test_lookup_oqimi_buzilmagan(client, seeded):
    """GOLDEN: ro'yxatdan tanlangan chek raqami `/lookup` ga tushadi."""
    hdr = _login(client, PHONE_A, PW_A)
    nomer = _orders(client, hdr, search="A-1001")[0]["order_number"]

    r = client.get("/api/v1/returns/lookup", params={"q": nomer}, headers=hdr)
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    body = r.json()
    assert body["order_id"] == seeded["exact"]
    assert body["items"], "lookup qatorlarni qaytarmadi"
    assert body["items"][0]["returnable_qty"] == 2.0
    assert body["items"][0]["order_item_id"] is not None
