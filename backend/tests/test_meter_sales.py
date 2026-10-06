"""METR (m) BO'YICHA KASRLI SOTUV — 3.5 m kabel/mato.

═══ MUAMMO (jonli, XOZMAG / tenant 28) ═══
`m` birligi POS'ning `isWeightUnit` ro'yxatida YO'Q edi: "necha metr?" oynasi
ochilmas, mato/kabel BUTUN songa majburlanardi. Prodda 30 ta `m` mahsulot
bor (9 tasida pachka narxi — kabel o'rami) va 13 ta sotuvning HAMMASI butun
son — ya'ni kassir 3.5 m sotolmagan.

⚠️ ENG MUHIM FAKT: **TO'SIQ FAQAT FRONTENDDA EDI.** Backend `quantity` ni
`float = Field(gt=0)` deb oladi va birlikka QARAB hech qanday butun-son
qoidasi YO'Q (`schemas.py`). Shu sabab bu fayl "tuzatishni" sinamaydi —
u backend xulqini QULFLAYDI: metr kasri avval ham, keyin ham o'tadi, va
frontend tuzatilgach u yo'l amalda ishlaydi.

⚠️ BILIB TURILGAN BO'SHLIQ (atayin qoldirilgan): server `pcs` mahsulotga
ham kasr qabul qiladi (pastdagi `test_bosliq_...`). Himoya FAQAT POS UI'da
(dona mahsulotda og'irlik oynasi ochilmaydi, miqdor `++` bilan o'sadi).
Serverga birlik bo'yicha qoida qo'shish — 5 jonli do'konning pul yo'liga
tegish, bu vazifa doirasidan tashqarida; test bo'shliqni KO'RINADIGAN qiladi.

Ishga tushirish:
    cd backend && py -m pytest tests/test_meter_sales.py -v
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

ADMIN_PW = "AdminMetr9x"
# XOZMAG'dagi haqiqiy mahsulot: "JILVIR 400 METRAJ" — 4 000 so'm/m
NARX_M = 4000.0
TAN_M  = 2800.0
# "2*6 SALID KABEL ALUMIN" — 150 m o'ram / 570 000 (pachka narxi)
PACK_SIZE_M  = 150
PACK_PRICE_M = 570_000.0


@pytest.fixture()
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)

    # `OrderService._next_daily_number()` PostgreSQL `timezone(tz, ts)` ni
    # ishlatadi — sqlite'da yo'q (test_weight_sales.py dagi ayni naqsh).
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
    """Do'kon: metr mahsulot (1), metr+o'ram (2), dona mahsulot (3)."""
    for code, desc in [("process_orders", "Buyurtmalar"), ("manage_menu", "Menyu"),
                       ("view_reports", "Hisobot"), ("process_payments", "To'lovlar"),
                       ("manage_inventory", "Ombor")]:
        db.add(Permission(code=code, description=desc))
    db.flush()
    r = Role(name="admin", description="Administrator")
    r.permissions = db.query(Permission).all()
    db.add(r)
    db.flush()

    db.add(Cafe(id=1, name="XOZMAG test", code="xz", business_type="store",
                is_active=True, block_oversell=False, subscription_plan="pro"))
    db.add(Category(id=1, name="Kabel", tenant_id=1))
    db.flush()

    db.add(Product(id=1, name="JILVIR 400 METRAJ", price=NARX_M, cost_price=TAN_M,
                   sale_unit="m", category_id=1, tenant_id=1,
                   is_active=True, is_available=True))
    db.add(Product(id=2, name="2*6 SALID KABEL ALUMIN", price=4200.0, cost_price=3000.0,
                   sale_unit="m", category_id=1, tenant_id=1,
                   pack_size=PACK_SIZE_M, pack_price=PACK_PRICE_M,
                   is_active=True, is_available=True))
    db.add(Product(id=3, name="ROZETKA", price=15000, cost_price=9000,
                   sale_unit="pcs", category_id=1, tenant_id=1,
                   is_active=True, is_available=True))
    db.add(Inventory(id=1, tenant_id=1, product_id=1, quantity=400, unit="m"))
    db.add(Inventory(id=2, tenant_id=1, product_id=2, quantity=600, unit="m"))
    db.add(Inventory(id=3, tenant_id=1, product_id=3, quantity=50, unit="dona"))

    u = User(id=1, username="a", email="a@x.uz", full_name="Admin",
             phone="+998900000011", hashed_password=get_password_hash(ADMIN_PW),
             is_active=True, is_superuser=False, tenant_id=1, role_id=r.id)
    db.add(u)
    db.flush()
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
                    data={"username": "+998900000011", "password": ADMIN_PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _sotuv(client, h, items):
    return client.post("/api/v1/orders/", headers=h,
                       json={"items": items, "order_type": "takeaway", "source": "pos"})


def _tolov(client, h, order):
    """Ombor chiqimi TO'LOVDA bo'ladi (routers/payment.py), buyurtmada emas."""
    r = client.post("/api/v1/payments/", headers=h, json={
        "order_id": order["id"], "amount": order["total_amount"], "method": "cash",
    })
    assert r.status_code == 200, r.text
    return r


def _inv(db, pid):
    db.expire_all()
    return db.query(Inventory).filter(Inventory.product_id == pid).first()


# ══════════════════════════════════════════════════════════════════════════════
# 1) 3.5 METR SOTUV
# ══════════════════════════════════════════════════════════════════════════════

def test_3_5_metr_sotuv_qabul_qilinadi(seeded, client):
    """3.5 m × 4 000 = 14 000."""
    h = _h(client)
    r = _sotuv(client, h, [{"product_id": 1, "quantity": 3.5}])
    assert r.status_code == 200, r.text
    o = r.json()
    assert o["items"][0]["quantity"] == 3.5
    assert o["total_amount"] == 14_000


def test_ombordan_3_5_ayriladi(seeded, client):
    """400 m − 3.5 = 396.5 (butun songa yaxlitlanmasligi SHART)."""
    h = _h(client)
    r = _sotuv(client, h, [{"product_id": 1, "quantity": 3.5}])
    assert r.status_code == 200, r.text
    _tolov(client, h, r.json())
    assert _inv(seeded, 1).quantity == 396.5


def test_kasr_3_xonagacha_yaxlitlanadi(seeded, client):
    """Metr ham og'irlik bilan bir xil qoida: 3 xona (`_yaxlitla_miqdor`)."""
    h = _h(client)
    r = _sotuv(client, h, [{"product_id": 1, "quantity": 2.8571428}])
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["quantity"] == 2.857


def test_summa_rejimi_natijasi_otadi(seeded, client):
    """POS "Summa" rejimi: 9 500 so'm / 4 000 = 2.375 m — server qabul qilsin.

    (Hisob FRONTENDDA: `_weightFromSum`. Server tayyor miqdorni oladi, shu
    sabab bu yerda aynan o'sha natija yuboriladi.)
    """
    h = _h(client)
    r = _sotuv(client, h, [{"product_id": 1, "quantity": 2.375}])
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["quantity"] == 2.375
    assert r.json()["total_amount"] == 9_500


def test_bir_nechta_kasrli_metr_qator(seeded, client):
    h = _h(client)
    r = _sotuv(client, h, [
        {"product_id": 1, "quantity": 3.5},
        {"product_id": 2, "quantity": 12.25},
    ])
    assert r.status_code == 200, r.text
    qlar = sorted(i["quantity"] for i in r.json()["items"])
    assert qlar == [3.5, 12.25]
    # 3.5×4000 + 12.25×4200 = 14 000 + 51 450
    assert r.json()["total_amount"] == 65_450


@pytest.mark.parametrize("q", [0, -1, -0.5])
def test_nol_va_manfiy_422(seeded, client, q):
    h = _h(client)
    assert _sotuv(client, h, [{"product_id": 1, "quantity": q}]).status_code == 422


def test_eng_kichik_metr_0_001(seeded, client):
    h = _h(client)
    r = _sotuv(client, h, [{"product_id": 1, "quantity": 0.001}])
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["quantity"] == 0.001


# ══════════════════════════════════════════════════════════════════════════════
# 2) O'RAM (pachka) — metr mahsulotda
# ══════════════════════════════════════════════════════════════════════════════

def test_oram_narxi_boyicha_sotuv(seeded, client):
    """150 m o'ram = 570 000 (metr narxi × 150 EMAS — o'ram o'z narxida).

    ⚠️ `base_qty` = pack_size × quantity → ombordan 150 m ayriladi.
    """
    h = _h(client)
    r = client.post("/api/v1/orders/", headers=h, json={
        "items": [{"product_id": 2, "quantity": 1, "unit_sold": "pachka",
                   "base_qty": PACK_SIZE_M, "unit_price": PACK_PRICE_M}],
        "order_type": "takeaway", "source": "pos",
    })
    assert r.status_code == 200, r.text
    it = r.json()["items"][0]
    assert it["unit_price"] == PACK_PRICE_M
    _tolov(client, h, r.json())
    assert _inv(seeded, 2).quantity == 600 - PACK_SIZE_M


def test_oram_va_metr_birga(seeded, client):
    """Bitta chekda o'ram ham, kesib sotilgan metr ham bo'lishi mumkin."""
    h = _h(client)
    r = client.post("/api/v1/orders/", headers=h, json={
        "items": [
            {"product_id": 2, "quantity": 1, "unit_sold": "pachka",
             "base_qty": PACK_SIZE_M, "unit_price": PACK_PRICE_M},
            {"product_id": 2, "quantity": 7.5, "unit_price": 4200.0},
        ],
        "order_type": "takeaway", "source": "pos",
    })
    assert r.status_code == 200, r.text
    _tolov(client, h, r.json())
    # 600 − 150 (o'ram) − 7.5 (kesilgan) = 442.5
    assert _inv(seeded, 2).quantity == 442.5


# ══════════════════════════════════════════════════════════════════════════════
# 3) GOLDEN — dona mahsulot va mavjud oqimlar
# ══════════════════════════════════════════════════════════════════════════════

def test_dona_butun_son_ishlaydi(seeded, client):
    h = _h(client)
    r = _sotuv(client, h, [{"product_id": 3, "quantity": 3}])
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["quantity"] == 3
    _tolov(client, h, r.json())
    assert _inv(seeded, 3).quantity == 47


def test_bosliq_server_dona_mahsulotga_ham_kasr_qabul_qiladi(seeded, client):
    """⚠️ BILIB TURILGAN BO'SHLIQ — tuzatish EMAS, HOLATNI QULFLASH.

    `schemas.py`: `quantity: float = Field(gt=0)` — birlik bo'yicha
    butun-son qoidasi YO'Q. Ya'ni server `pcs` mahsulotga 3.5 ni ham oladi.

    Himoya FAQAT POS UI'da: dona mahsulotda og'irlik/uzunlik oynasi
    ochilmaydi (`isFractionalUnit('pcs') === false`) va miqdor `++` bilan
    o'sadi — `frontend/tests/test_meter_sales.mjs` shuni qulflaydi.

    Agar kelajakda serverga qoida qo'shilsa, SHU test yiqiladi va qaror
    ataylab qayta ko'riladi (jimgina o'zgarmaydi).
    """
    h = _h(client)
    r = _sotuv(client, h, [{"product_id": 3, "quantity": 3.5}])
    assert r.status_code == 200, (
        "server xulqi o'zgargan — endi dona mahsulotda kasr rad etiladi. "
        "Bu YAXSHILANISH bo'lishi mumkin, lekin ATAYLAB qilinganini "
        "tasdiqlang va testni yangilang.")
    assert r.json()["items"][0]["quantity"] == 3.5


def test_metr_mahsulot_birligi_saqlanadi(seeded, client):
    """Ombor birligi `m` bo'lib qolsin (kg/dona ga aylanmasin)."""
    h = _h(client)
    r = _sotuv(client, h, [{"product_id": 1, "quantity": 3.5}])
    assert r.status_code == 200, r.text
    _tolov(client, h, r.json())
    assert _inv(seeded, 1).unit == "m"
    assert seeded.query(Product).filter(Product.id == 1).first().sale_unit == "m"
