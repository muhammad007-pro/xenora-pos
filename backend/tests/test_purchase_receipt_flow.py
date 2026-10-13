"""Priyomka (kirim) — to'liq API oqimi: purchase_receipts.html aynan shu yo'lni chaqiradi.

2026-10-13: sahifa api.js ning o'ralgan javobini xom o'qigani uchun ishlamasdi
(frontend tuzatildi). Bu testlar SERVER tomonini qulflaydi — sahifa nimaga
tayanadi va GOLDEN nima:

  1. ro'yxatlar (firmalar, mahsulotlar, priyomkalar) `items` bilan keladi;
  2. bir barkod bilan ikkinchi mahsulot yaratilmaydi (dublikat yo'q) va
     barkod lookup mavjudini qaytaradi (sahifaning dublikatga qarshi zaxirasi);
  3. tasdiqlash → ombor oshadi (brak ayriladi), tan narx yangilanadi,
     price_history ga 'receipt' sababi bilan yoziladi, StockMovement bor;
  4. firma qarzi = net − paid_now, FIFO o'zgarmagan; qayta tasdiqlash 400.

Ishga tushirish:  cd backend && py -m pytest tests/test_purchase_receipt_flow.py -v
"""
import os
import sys
from datetime import date as Date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models import (
    Cafe, Category, Inventory, PriceHistory, Product, StockMovement, Supplier,
)
from routers.price_history import REASON_RECEIPT
from services.supplier_debt import compute_debts


@pytest.fixture()
def api():
    from fastapi.testclient import TestClient
    from core.security import get_password_hash
    from database import get_db
    from main import app
    from models import Permission, Role, User

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng, autocommit=False, autoflush=False)()

    perms = [Permission(code=c, description=c) for c in ("view_finance", "manage_menu")]
    db.add_all(perms)
    db.flush()
    role = Role(name="admin", description="Administrator")
    role.permissions = perms
    db.add(role)
    db.flush()

    db.add(Cafe(id=1, name="Do'kon", code="d1", business_type="store", is_active=True))
    db.add(Category(id=1, name="Umumiy", tenant_id=1))
    db.add(Product(id=1, name="VERITA", price=10000, cost_price=7000,
                   category_id=1, tenant_id=1, is_active=True))
    db.add(Inventory(id=1, tenant_id=1, product_id=1, quantity=2, unit="dona"))
    db.add(Supplier(id=1, tenant_id=1, name="Ta'minot", phone="+998901112233",
                    is_active=True, payment_delay_days=0))
    db.add(User(username="a", email="a@x.uz", full_name="Admin", phone="+998900000001",
                hashed_password=get_password_hash("AdminAlfa9x"), is_active=True,
                is_superuser=False, tenant_id=1, role_id=role.id))
    db.commit()

    def _override():
        yield db
    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        r = c.post("/api/v1/auth/login",
                   data={"username": "+998900000001", "password": "AdminAlfa9x"})
        assert r.status_code == 200, r.text
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        yield c, db
    app.dependency_overrides.clear()
    db.close()
    Base.metadata.drop_all(eng)
    eng.dispose()


def _receipt(c, items, paid_now=0, discount=0):
    r = c.post("/api/v1/purchase-receipts/", json={
        "supplier_id": 1, "invoice_number": "NL-1", "receipt_date": "2026-10-13",
        "discount_amount": discount, "paid_now": paid_now, "items": items,
    })
    assert r.status_code == 200, r.text
    return r.json()


# ── 1) Ro'yxatlar — sahifa `apiData(res).items` ni o'qiydi ───────────────────
def test_royxatlar_items_bilan_keladi(api):
    c, _ = api
    sup = c.get("/api/v1/suppliers-b2b/?page_size=200&is_active=true").json()
    prod = c.get("/api/v1/products/?page_size=1000").json()
    assert [s["name"] for s in sup["items"]] == ["Ta'minot"]
    assert [p["name"] for p in prod["items"]] == ["VERITA"]

    _receipt(c, [{"product_id": 1, "quantity": 5, "unit_price": 7500}])
    lst = c.get("/api/v1/purchase-receipts/?page_size=100").json()
    assert lst["total"] == 1
    assert lst["items"][0]["supplier_name"] == "Ta'minot"
    assert lst["items"][0]["status"] == "draft"


# ── 2) Yangi tovar — dublikat yo'q ───────────────────────────────────────────
def test_yangi_tovar_bir_marta_yaratiladi(api):
    c, db = api
    body = {"name": "YANGI SOVUN", "price": 15000, "cost_price": 0,
            "barcode": "4780000000017", "category_id": 1}
    r1 = c.post("/api/v1/products/", json=body)
    assert r1.status_code == 200, r1.text
    pid = r1.json()["id"]

    # Qayta bosish (eski sahifa "yaratilmadi" deganda aynan shu bo'lardi)
    r2 = c.post("/api/v1/products/", json=body)
    assert r2.status_code == 400
    assert db.query(Product).filter(Product.barcode == "4780000000017").count() == 1

    # Sahifaning zaxira yo'li: lookup mavjud mahsulotni qaytaradi
    lk = c.get("/api/v1/barcodes/lookup/4780000000017")
    assert lk.status_code == 200 and lk.json()["id"] == pid

    # Yangi tovar 0 qoldiq bilan omborda (kirimdan oldin)
    assert db.query(Inventory).filter(Inventory.product_id == pid).one().quantity == 0


# ── 3) Tasdiqlash: ombor + tan narx + price_history ──────────────────────────
def test_tasdiqlash_ombor_tan_narx_tarix(api):
    c, db = api
    rec = _receipt(c, [{"product_id": 1, "quantity": 10, "unit_price": 7500, "brak_qty": 1}])
    assert rec["net_amount"] == 9 * 7500

    # Draft omborga tegmaydi
    assert db.query(Inventory).get(1).quantity == 2

    r = c.post(f"/api/v1/purchase-receipts/{rec['id']}/confirm")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "confirmed"      # sahifa `apiData(res).status` ni tekshiradi

    db.expire_all()
    assert db.query(Inventory).get(1).quantity == 2 + 9     # brak ayrilgan
    assert db.query(Product).get(1).cost_price == 7500

    hist = db.query(PriceHistory).filter(PriceHistory.product_id == 1).all()
    assert [(h.reason, h.old_cost, h.new_cost) for h in hist] == [(REASON_RECEIPT, 7000, 7500)]

    mv = db.query(StockMovement).filter(StockMovement.reference_type == "purchase_receipt").one()
    assert (mv.quantity, mv.unit_cost, mv.reference_id) == (9, 7500, rec["id"])

    # Qayta tasdiqlash — ikki marta kirim bo'lmasin
    assert c.post(f"/api/v1/purchase-receipts/{rec['id']}/confirm").status_code == 400
    db.expire_all()
    assert db.query(Inventory).get(1).quantity == 11


def test_yangi_tovar_kirimi_yangi_ombor(api):
    """Skaner → yangi tovar → kirim: yangi mahsulot qoldig'i 0 dan oshadi."""
    c, db = api
    pid = c.post("/api/v1/products/", json={
        "name": "YANGI", "price": 5000, "cost_price": 0,
        "barcode": "4780000000024", "category_id": 1}).json()["id"]
    rec = _receipt(c, [{"product_id": pid, "quantity": 6, "unit_price": 3000}])
    assert c.post(f"/api/v1/purchase-receipts/{rec['id']}/confirm").status_code == 200
    db.expire_all()
    assert db.query(Inventory).filter(Inventory.product_id == pid).one().quantity == 6
    assert db.query(Product).get(pid).cost_price == 3000


# ── 4) Firma qarzi ───────────────────────────────────────────────────────────
def _debt(db):
    return compute_debts(db, [db.query(Supplier).get(1)], today=Date(2026, 10, 13))[1]


def test_qarz_tasdiqlangandan_keyin_paydo_boladi(api):
    c, db = api
    rec = _receipt(c, [{"product_id": 1, "quantity": 10, "unit_price": 1000}],
                   paid_now=4000, discount=1000)
    assert _debt(db).debt == 0                        # draft — hali qarz emas
    r = c.post(f"/api/v1/purchase-receipts/{rec['id']}/confirm")
    assert r.json()["status"] == "confirmed"
    db.expire_all()
    d = _debt(db)
    assert d.total_purchases == 9000                  # 10 000 − 1 000 chegirma
    assert d.total_paid == 4000
    assert d.debt == 5000


def test_toliq_tolangan_kirim_paid(api):
    """paid_now ≥ net → server darhol `paid` beradi (sahifa buni ham muvaffaqiyat deb oladi)."""
    c, db = api
    rec = _receipt(c, [{"product_id": 1, "quantity": 2, "unit_price": 1000}], paid_now=2000)
    r = c.post(f"/api/v1/purchase-receipts/{rec['id']}/confirm")
    assert r.json()["status"] == "paid"
    db.expire_all()
    assert _debt(db).debt == 0
    assert db.query(Inventory).get(1).quantity == 4


def test_fifo_eski_nakladnoy_avval_yopiladi(api):
    """Ikki kirim + umumiy to'lov: pul eng eski nakladnoyni yopadi (GOLDEN FIFO)."""
    c, db = api
    from models import SupplierPayment
    a = _receipt(c, [{"product_id": 1, "quantity": 1, "unit_price": 3000}])
    c.post(f"/api/v1/purchase-receipts/{a['id']}/confirm")
    b = _receipt(c, [{"product_id": 1, "quantity": 1, "unit_price": 5000}])
    c.post(f"/api/v1/purchase-receipts/{b['id']}/confirm")
    db.add(SupplierPayment(tenant_id=1, supplier_id=1, amount=4000,
                           payment_date=Date(2026, 10, 13), payment_method="cash"))
    db.commit()
    d = _debt(db)
    left = {r.receipt_id: r.remaining for r in d.receipts}
    assert left == {a["id"]: 0, b["id"]: 4000}
    assert d.debt == 4000
