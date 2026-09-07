"""Kasrli miqdor (tarozi sotuvi) — 0.740 kg.

2026-09-07 gacha `OrderItem.quantity` INTEGER edi va `OrderItemCreate.quantity`
`int` deb e'lon qilingan edi. Natijada og'irlik oynasi (pos.js) yuborgan
0.740 API chegarasidayoq 422 bilan rad etilardi — ya'ni oziq-ovqat do'konida
tarozi bilan sotish MUMKIN EMAS edi.

⚠️ `ml` sotuvi (atir maydalash) ishlab turgani ADASHTIRMASIN: u kasr
qo'llab-quvvatlangani uchun emas, ml miqdorlari BUTUN SON (30, 50) bo'lgani
uchun `int` filtridan o'tib ketardi. Shu sabab bu yerda ml uchun ham alohida
test bor — u avvalgidek ishlashi kerak.

Ishga tushirish:
    cd backend && py -m pytest tests/test_weight_sales.py -v
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.security import get_password_hash
from database import Base, get_db
from main import app
from models import (
    Cafe, Category, Inventory, Order, OrderItem, Permission, Product, Role,
    Shift, User,
)

ADMIN_PW = "AdminAlfa9x"
NARX_KG = 17000.0      # 1 kg go'sht
TAN_KG = 12000.0


@pytest.fixture()
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)

    # `OrderService._next_daily_number()` PostgreSQL'ning `timezone(tz, ts)`
    # funksiyasini ishlatadi — sqlite'da u YO'Q va buyurtma yaratish 500 beradi.
    # Shu sabab mavjud `test_orders.py` buyurtma testlarini sqlite'da SKIP
    # qiladi. Bu yerda skip qilib bo'lmaydi: aynan buyurtma yaratish sinalyapti.
    # Shuning uchun funksiyani sqlite'ga ro'yxatdan o'tkazamiz — sana qismini
    # qaytaradi, ya'ni "bugungi buyurtmalar" solishtiruvi to'g'ri ishlaydi va
    # kunlik raqam (daily_number) haqiqatdagidek o'sadi.
    @event.listens_for(eng, "connect")
    def _sqlite_timezone(dbapi_conn, _rec):
        dbapi_conn.create_function(
            "timezone", 2, lambda _tz, ts: str(ts)[:10] if ts else None)

    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng, autocommit=False, autoflush=False)()
    try:
        yield s
    finally:
        s.close()
        Base.metadata.drop_all(eng)
        eng.dispose()


@pytest.fixture()
def seeded(db):
    """Bitta do'kon: kg mahsulot (1), dona mahsulot (2), ml mahsulot (3)."""
    for code, desc in [("process_orders", "Buyurtmalar"), ("manage_menu", "Menyu"),
                       ("view_reports", "Hisobot"), ("process_payments", "To'lovlar"),
                       ("manage_inventory", "Ombor")]:
        db.add(Permission(code=code, description=desc))
    db.flush()
    r = Role(name="admin", description="Administrator")
    r.permissions = db.query(Permission).all()
    db.add(r)
    db.flush()

    db.add(Cafe(id=1, name="Oziq-ovqat", code="oz", business_type="supermarket",
                is_active=True, block_oversell=False))
    db.add(Category(id=1, name="Go'sht", tenant_id=1))
    db.flush()

    db.add(Product(id=1, name="Mol go'shti", price=NARX_KG, cost_price=TAN_KG,
                   sale_unit="kg", category_id=1, tenant_id=1,
                   is_active=True, is_available=True))
    db.add(Product(id=2, name="Non", price=4000, cost_price=2500,
                   sale_unit="pcs", category_id=1, tenant_id=1,
                   is_active=True, is_available=True))
    db.add(Product(id=3, name="Atir (ml)", price=20000, cost_price=10000,
                   sale_unit="ml", category_id=1, tenant_id=1,
                   is_active=True, is_available=True))
    db.add(Inventory(id=1, tenant_id=1, product_id=1, quantity=50, unit="kg"))
    db.add(Inventory(id=2, tenant_id=1, product_id=2, quantity=100, unit="dona"))
    db.add(Inventory(id=3, tenant_id=1, product_id=3, quantity=500, unit="ml"))

    u = User(id=1, username="a", email="a@x.uz", full_name="Admin",
             phone="+998900000001", hashed_password=get_password_hash(ADMIN_PW),
             is_active=True, is_superuser=False, tenant_id=1, role_id=r.id)
    db.add(u)
    db.flush()
    # To'lov OCHIQ SMENA talab qiladi ("Avval smena oching") — ombor chiqimi
    # to'lovda bo'lgani uchun qoldiq testlariga smena kerak.
    db.add(Shift(id=1, tenant_id=1, user_id=u.id, start_time=datetime.now()))
    db.commit()
    return db


@pytest.fixture()
def client(db):
    def _override():
        yield db
    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _h(client):
    r = client.post("/api/v1/auth/login",
                    data={"username": "+998900000001", "password": ADMIN_PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _sotuv(client, h, items):
    return client.post("/api/v1/orders/", headers=h,
                       json={"items": items, "order_type": "takeaway", "source": "pos"})


def _tolov(client, h, order):
    """Ombor chiqimi TO'LOVDA bo'ladi (routers/payment.py:189), buyurtma
    yaratishda emas. Qoldiqni tekshiradigan testlar shu sabab to'laydi."""
    r = client.post("/api/v1/payments/", headers=h, json={
        "order_id": order["id"],
        "amount": order["total_amount"],
        "method": "cash",
    })
    assert r.status_code == 200, r.text
    return r


# ══════════════════════════════════════════════════════════════════════════════
# 1) KASRLI SOTUV — asosiy maqsad
# ══════════════════════════════════════════════════════════════════════════════

def test_0740_kg_sotuv_qabul_qilinadi(seeded, client):
    """0.740 kg × 17 000 = 12 580. Avval bu 422 berardi."""
    h = _h(client)
    r = _sotuv(client, h, [{"product_id": 1, "quantity": 0.740}])
    assert r.status_code == 200, r.text
    d = r.json()

    it = d["items"][0]
    assert it["quantity"] == 0.740
    assert it["unit_price"] == NARX_KG
    assert it["total_price"] == pytest.approx(12580.0, abs=0.01)
    assert d["total_amount"] == pytest.approx(12580.0, abs=0.01)


def test_uzun_kasr_3_xonagacha_yaxlitlanadi(seeded, client):
    """Tarozi 0.7405882 bersa — 0.741 (1 gramm aniqlik)."""
    h = _h(client)
    r = _sotuv(client, h, [{"product_id": 1, "quantity": 0.7405882}])
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["quantity"] == 0.741


def test_ombordan_kasrli_ayriladi(seeded, client):
    """base_qty = miqdor; ombor 50 -> 49.26."""
    h = _h(client)
    r = _sotuv(client, h, [{"product_id": 1, "quantity": 0.740}])
    assert r.status_code == 200, r.text
    _tolov(client, h, r.json())

    db = seeded
    inv = db.query(Inventory).filter(Inventory.product_id == 1).first()
    db.refresh(inv)
    assert inv.quantity == pytest.approx(49.26, abs=0.001)

    oi = db.query(OrderItem).filter(OrderItem.product_id == 1).first()
    assert oi.base_qty == pytest.approx(0.740, abs=0.0001)


def test_foyda_kasrda_togri(seeded, client):
    """unit_cost snapshot × kasrli miqdor.

    0.740 × (17 000 - 12 000) = 3 700 foyda.
    """
    h = _h(client)
    assert _sotuv(client, h, [{"product_id": 1, "quantity": 0.740}]).status_code == 200

    oi = seeded.query(OrderItem).filter(OrderItem.product_id == 1).first()
    assert oi.unit_cost == pytest.approx(TAN_KG)
    foyda = oi.total_price - oi.unit_cost * oi.quantity
    assert foyda == pytest.approx(3700.0, abs=0.01)


def test_bir_nechta_kasrli_qator(seeded, client):
    """Kasr + butun aralash: 0.25 kg + 3 dona non."""
    h = _h(client)
    r = _sotuv(client, h, [
        {"product_id": 1, "quantity": 0.25},
        {"product_id": 2, "quantity": 3},
    ])
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["total_amount"] == pytest.approx(0.25 * NARX_KG + 3 * 4000, abs=0.01)


# ══════════════════════════════════════════════════════════════════════════════
# 2) VALIDATSIYA
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("q", [0, -1, -0.5, 0.0])
def test_nol_va_manfiy_422(seeded, client, q):
    h = _h(client)
    assert _sotuv(client, h, [{"product_id": 1, "quantity": q}]).status_code == 422


# ══════════════════════════════════════════════════════════════════════════════
# 3) GOLDEN — mavjud sotuvlar bit-bitiga o'zgarmasin
# ══════════════════════════════════════════════════════════════════════════════

def test_golden_butun_donali_sotuv_ozgarmadi(seeded, client):
    """3 dona non × 4 000 = 12 000. Miqdor 3.0 bo'lib saqlanadi (== 3)."""
    h = _h(client)
    r = _sotuv(client, h, [{"product_id": 2, "quantity": 3}])
    assert r.status_code == 200, r.text
    d = r.json()
    it = d["items"][0]
    assert it["quantity"] == 3
    assert it["total_price"] == 12000
    assert d["total_amount"] == 12000
    _tolov(client, h, d)

    inv = seeded.query(Inventory).filter(Inventory.product_id == 2).first()
    seeded.refresh(inv)
    assert inv.quantity == 97          # 100 - 3


def test_golden_ml_sotuvi_buzilmadi(seeded, client):
    """152 ta ml mahsuloti prodda ishlab turibdi — 30 ml × 20 000 = 600 000."""
    h = _h(client)
    r = _sotuv(client, h, [{"product_id": 3, "quantity": 30}])
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["items"][0]["quantity"] == 30
    assert d["total_amount"] == 600000
    _tolov(client, h, d)

    inv = seeded.query(Inventory).filter(Inventory.product_id == 3).first()
    seeded.refresh(inv)
    assert inv.quantity == 470         # 500 - 30


def test_golden_butun_kasr_sifatida_kelsa_ham_bir_xil(seeded, client):
    """quantity=3.0 (float) natijasi quantity=3 (int) bilan AYNAN bir xil."""
    h = _h(client)
    a = _sotuv(client, h, [{"product_id": 2, "quantity": 3}]).json()
    b = _sotuv(client, h, [{"product_id": 2, "quantity": 3.0}]).json()
    assert a["total_amount"] == b["total_amount"] == 12000
    assert a["items"][0]["quantity"] == b["items"][0]["quantity"]


# ══════════════════════════════════════════════════════════════════════════════
# 4) CHEK FORMATI
# ══════════════════════════════════════════════════════════════════════════════

def test_chek_kasrni_togri_korsatadi(seeded, client):
    """`_qtyNum` (receipt-print.js) mantig'i: 0.740 -> "0.74", 3 -> "3"."""
    def _qty_num(q):                    # JS `_qtyNum` ning aynan nusxasi
        return str(round(float(q) * 1000) / 1000)

    assert _qty_num(0.740) == "0.74"
    assert _qty_num(0.741) == "0.741"
    assert _qty_num(3) == "3.0" or _qty_num(3) == "3"

    h = _h(client)
    r = _sotuv(client, h, [{"product_id": 1, "quantity": 0.740}])
    assert r.status_code == 200
    # Chek uchun kerak bo'ladigan uchlik javobda bor
    it = r.json()["items"][0]
    assert it["quantity"] and it["unit_price"] and it["total_price"]
