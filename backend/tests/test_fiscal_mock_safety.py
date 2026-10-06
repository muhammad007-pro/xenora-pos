"""SOXTA FISKAL CHEK QO'RIQCHISI — `mode != "live"` chekka chiqmaydi.

═══ MUAMMO (2026-10-06, HUQUQIY XAVF) ═══
Prod `config/fiscal.json`: `{"enabled": true, "mode": "mock",
"inn": "123456789", "kassa_id": "TEST001"}`, `tenant_settings` da esa
`fiscal` yozuvi **birortasi ham yo'q** → beshta jonli do'kon ham shu
faylga tushardi.

`mock` rejim OFD ga HECH NARSA YUBORMAYDI, lekin:
  · fiskal raqam yasaydi: `int(time.time()*1000) % 10_000_000` ("№ 7114357")
  · QR yasaydi: `consumer.invoice.uz/check?...&fn=TEST001&i=<soxta>` —
    haqiqiy soliq portali manzili, yasama parametrlar bilan
  · chekka TEST INN `123456789` ni bosardi
Bazada 3323 ta buyurtmada shunday raqam bor.

⚠️ IKKI CHEK YO'LI IKKI XIL TEKSHIRARDI va aynan shu ajralish xatoni
yashirdi:
  · `/orders/{id}/receipt` → `ReceiptSettings.qr_enabled` (prodda faqat
    tenant 27 da yoniq → shu sabab faqat 1001 BARAKA da ko'rinardi)
  · ESC/POS yo'li          → faqat `fiscal_cfg["enabled"]` → `qr_enabled`
    o'chiq bo'lsa ham BESHTA do'konda soxta raqam bosilishi mumkin edi

QOIDA (shu test qulflaydi): fiskal element chekka faqat
`enabled=True` VA `mode=="live"` bo'lganda chiqadi. Ikki yo'l ham
`services/ofd_service.is_fiscal_live()` ni chaqiradi.

⚠️ Bazadagi `order.fiscal_number` TEGILMAYDI — faqat KO'RSATISH to'siladi.

Ishga tushirish:
    cd backend && py -m pytest tests/test_fiscal_mock_safety.py -v
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.security import get_password_hash
from core.tenant_config import set_tenant_config
from database import Base, get_db
from main import app
from models import (
    Cafe, Category, Order, OrderItem, Payment, Permission, Product,
    ReceiptSettings, Role, User,
)
from services.ofd_service import is_fiscal_live

ADMIN_PW = "AdminFisk9x"
PHONE = "+998900000091"

MOCK_FN = 7114357                      # jonli chekda ko'rilgan shakl
MOCK_QR = ("https://consumer.invoice.uz/check?t=20261006120000&s=1500000"
           "&fn=TEST001&i=7114357&fp=abc123&n=1")


# ══════════════════════════════════════════════════════════════════════════════
# 1) QO'RIQCHINING O'ZI (sof funksiya)
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("cfg,kutilgan", [
    # FAQAT shu holat True
    ({"enabled": True,  "mode": "live"},  True),
    ({"enabled": True,  "mode": "LIVE"},  True),      # katta harf
    ({"enabled": True,  "mode": " live "}, True),     # bo'shliq
    # mock va noma'lum rejimlar — CHIQMAYDI
    ({"enabled": True,  "mode": "mock"},  False),
    ({"enabled": True,  "mode": "test"},  False),
    ({"enabled": True,  "mode": ""},      False),
    ({"enabled": True},                   False),     # rejim ko'rsatilmagan → mock
    # o'chirilgan
    ({"enabled": False, "mode": "live"},  False),
    ({},                                  False),
    (None,                                False),
])
def test_qoriqchi(cfg, kutilgan):
    assert is_fiscal_live(cfg) is kutilgan


def test_prod_konfiguratsiyasi_endi_soxta_chek_bermaydi():
    """Repodagi standart `config/fiscal.json` — yangi soxta yozuv yozilmasin.

    ⚠️ ILGARI `enabled: true` + `mode: mock` edi: har to'lovda
    `send_to_ofd()` chaqirilib `order.fiscal_number` SOXTA raqam bilan
    to'lardi. Endi `enabled: false` → `send_to_ofd` "o'chirilgan" deb
    qaytadi va maydon bo'sh qoladi.
    """
    import json
    yol = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "config", "fiscal.json")
    cfg = json.load(open(yol, encoding="utf-8"))
    assert cfg.get("enabled") is False, (
        "config/fiscal.json da `enabled` yana yoqilgan — mock rejimda bu "
        "bazaga soxta fiskal raqam yozishni qaytaradi")
    assert not cfg.get("inn"), "test INN qaytib kelgan (123456789 kabi)"
    assert not cfg.get("kassa_id"), "test kassa_id qaytib kelgan (TEST001 kabi)"
    # Qo'riqchi ham shu konfiguratsiyada yopiq bo'lishi kerak
    assert is_fiscal_live(cfg) is False


# ══════════════════════════════════════════════════════════════════════════════
# FIXTURE
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def db():
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


@pytest.fixture()
def seeded(db):
    """1001 BARAKA holati: `qr_enabled=True` + bazada SOXTA fiskal raqam."""
    for code in ("process_orders", "view_reports", "process_payments",
                 "manage_settings", "manage_menu"):
        db.add(Permission(code=code, description=code))
    db.flush()
    r = Role(name="admin", description="Administrator")
    r.permissions = db.query(Permission).all()
    db.add(r)
    db.flush()

    db.add(Cafe(id=27, name="1001 BARAKA", code="brk", business_type="store",
                is_active=True, subscription_plan="pro"))
    db.add(Category(id=1, name="Oziq", tenant_id=27))
    db.flush()
    db.add(Product(id=1, name="SHAKAR", price=15000, cost_price=11000,
                   sale_unit="kg", category_id=1, tenant_id=27,
                   is_active=True, is_available=True))
    # Do'kon chekda QR ko'rsatishni TANLAGAN (prodda faqat shu tenantda true)
    db.add(ReceiptSettings(tenant_id=27, qr_enabled=True, paper_width=80,
                           store_name="1001 BARAKA"))
    o = Order(id=1, tenant_id=27, order_number="B-1", daily_number=1,
              status="completed", total_amount=15000.0, discount_amount=0.0,
              tax_amount=0.0, final_amount=15000.0,
              # ⚠️ SOXTA raqam — mock rejim yozib qo'ygan (3323 tadan biri)
              fiscal_number=MOCK_FN, fiscal_qr_url=MOCK_QR,
              fiscal_sent_at=datetime.now())
    db.add(o)
    db.flush()
    db.add(OrderItem(tenant_id=27, order_id=1, product_id=1, quantity=1,
                     unit_price=15000.0, unit_cost=11000.0, total_price=15000.0))
    db.add(Payment(tenant_id=27, order_id=1, amount=15000.0,
                   method="cash", status="paid"))
    db.add(User(id=1, username="a", email="a@x.uz", full_name="Admin",
                phone=PHONE, hashed_password=get_password_hash(ADMIN_PW),
                is_active=True, is_superuser=False, tenant_id=27, role_id=r.id))
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
    r = client.post("/api/v1/auth/login", data={"username": PHONE, "password": ADMIN_PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _receipt(client, h):
    r = client.get("/api/v1/orders/1/receipt", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


# ══════════════════════════════════════════════════════════════════════════════
# 2) /orders/{id}/receipt — ASOSIY TUZATISH
# ══════════════════════════════════════════════════════════════════════════════

def test_mock_rejimda_fiskal_chiqmaydi(seeded, client):
    """ASOSIY QULF: `qr_enabled=True` bo'lsa HAM mock rejimda QR/raqam yo'q."""
    set_tenant_config(seeded, 27, "fiscal",
                      {"enabled": True, "mode": "mock", "inn": "123456789",
                       "kassa_id": "TEST001"})
    d = _receipt(client, _h(client))

    assert d["fiscal_number"] is None, "SOXTA fiskal raqam chekka chiqdi"
    assert d["fiscal_qr_url"] is None, "SOXTA fiskal QR chekka chiqdi"
    assert d["qr_enabled"] is False, "QR bloki yoqilgan ko'rinadi"
    # Diagnostika: nega yo'q ekani AYTILADI (jim qolmaydi)
    assert d["fiscal_mode"] == "mock"
    assert d["fiscal_configured"] is True
    assert d["fiscal_suppressed"] is True, "to'silgani ko'rinmaydi"


def test_bazadagi_raqam_TEGILMAGAN(seeded, client):
    """⚠️ Faqat KO'RSATISH to'siladi — 3323 ta mavjud yozuv o'zgarmaydi."""
    set_tenant_config(seeded, 27, "fiscal", {"enabled": True, "mode": "mock"})
    _receipt(client, _h(client))

    seeded.expire_all()
    o = seeded.query(Order).filter(Order.id == 1).first()
    assert o.fiscal_number == MOCK_FN
    assert o.fiscal_qr_url == MOCK_QR
    assert o.fiscal_sent_at is not None


def test_live_rejimda_fiskal_CHIQADI(seeded, client):
    """Haqiqiy OFD ulanganda (mode=live) chek fiskal bo'ladi."""
    set_tenant_config(seeded, 27, "fiscal",
                      {"enabled": True, "mode": "live", "operator": "soliquz",
                       "inn": "301234567", "kassa_id": "KASSA-01",
                       "api_key": "real-token"})
    d = _receipt(client, _h(client))

    assert d["fiscal_number"] == MOCK_FN     # bazadagi raqam (live da OFD beradi)
    assert d["fiscal_qr_url"] == MOCK_QR
    assert d["qr_enabled"] is True
    assert d["fiscal_mode"] == "live"
    assert d["fiscal_suppressed"] is False


def test_live_lekin_qr_enabled_ochiq(seeded, client):
    """GOLDEN: do'kon QR ko'rsatishni tanlamagan bo'lsa — live da ham yo'q."""
    seeded.query(ReceiptSettings).filter(
        ReceiptSettings.tenant_id == 27).update({"qr_enabled": False})
    seeded.commit()
    set_tenant_config(seeded, 27, "fiscal", {"enabled": True, "mode": "live"})
    d = _receipt(client, _h(client))
    assert d["fiscal_number"] is None
    assert d["qr_enabled"] is False


def test_fiscal_sozlamasi_yoq_bolsa_global_faylga_tushadi(seeded, client):
    """`tenant_settings` da yozuv yo'q (prodda aynan shunday) → global fayl.

    Repodagi fayl endi `enabled: false`, ya'ni fiskal blok CHIQMAYDI.
    """
    d = _receipt(client, _h(client))   # set_tenant_config CHAQIRILMAYDI
    assert d["fiscal_number"] is None
    assert d["fiscal_qr_url"] is None
    assert d["fiscal_configured"] is False
    assert d["fiscal_suppressed"] is True   # raqam bor, lekin ko'rsatilmaydi


def test_chek_qolgan_qismi_OZGARMAGAN(seeded, client):
    """GOLDEN: chek formati tegilmagan — faqat fiskal blok to'sildi."""
    set_tenant_config(seeded, 27, "fiscal", {"enabled": True, "mode": "mock"})
    d = _receipt(client, _h(client))
    assert d["order_number"] == "B-1"
    assert d["order_id"] == 1
    assert d["status"] == "completed"
    assert d["total"] == 15000.0
    assert d["subtotal"] == 15000.0
    assert len(d["items"]) == 1
    assert d["items"][0]["name"] == "SHAKAR"
    assert d["payment_methods"][0]["method"] == "cash"
    assert d["cafe_name"] == "1001 BARAKA"


# ══════════════════════════════════════════════════════════════════════════════
# 3) IKKI YO'L BIR XIL QO'RIQCHI (ajralish qaytmasin)
# ══════════════════════════════════════════════════════════════════════════════

def test_ikki_yol_ham_is_fiscal_live_chaqiradi():
    """⚠️ Ajralish xatoni yashirgan edi — manbada ikkisi ham qulflanadi.

    `/receipt` yo'li `qr_enabled AND is_fiscal_live`, ESC/POS yo'li esa
    `is_fiscal_live`. Birortasi yana `cfg.get("enabled")` ga qaytsa — yiqiladi.
    """
    yol = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "routers", "order.py")
    src = open(yol, encoding="utf-8").read()

    assert "from services.ofd_service import is_fiscal_live" in src
    # Ikki chaqiruv: /receipt va escpos
    assert src.count("is_fiscal_live(") == 2, (
        f"is_fiscal_live chaqiruvlari soni {src.count('is_fiscal_live(')} — "
        f"ikki chek yo'lining biri qo'riqchini yo'qotgan bo'lishi mumkin")
    # Eski (xavfli) shart qaytmasin
    assert 'fiscal_on = bool(fiscal_cfg.get("enabled"))' not in src, (
        "ESC/POS yo'li yana faqat `enabled` ni tekshiryapti — mock rejim "
        "soxta raqam bosib chiqaradi")
