"""MIQDOR CHEGARASI — shtrix-kod miqdor maydoniga tushib qolmasin (2026-10-13).

MUAMMO (prod): qoldiq kiritishda skaner fokus MIQDOR maydonida turgan —
omborga 508 681 002 822 184 dona kirim bo'lgan. 8 marta (XOZMAG 7, BARAKA 1).
Server faqat `> 0` ni tekshirardi, yuqori chegara yo'q edi.

Qotiriladigan qoidalar (`services/quantity_guard.py`):
  1) 1 000 000 dan katta miqdor -> 400 (422 EMAS) va aniq xabar
  2) 1 000 000 aynan — o'tadi (chegara ichida)
  3) Normal (10 000) va kasrli (0.566) miqdor — o'tadi (GOLDEN)
  4) Rad etilgan so'rov OMBORGA TEGMAYDI (qoldiq ham, harakat ham yo'q)
  5) Barcha ombor yo'llari: kirim, boshlang'ich qoldiq, chiqim, hisobdan
     chiqarish, inventarizatsiya, priyomka, spisaniye akti
  6) SOTUV tegilmagan (u yerda frontend faqat tasdiq so'raydi)

Ishga tushirish:
    cd backend && py -m pytest tests/test_quantity_limit.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.security import get_password_hash
from database import Base, get_db
from main import app
from models import (
    Cafe, Category, Inventory, InventoryCount, InventoryCountItem, Permission,
    Product, Role, StockMovement, Supplier, User,
)
from services.quantity_guard import MAX_QTY, check_qty

ADMIN_PW = "AdminMiqdor9x"
PHONE = "+998900000081"
BARCODE = 508681002822184          # prodda aynan shu son kirim bo'lgan
API = "/api/v1"


@pytest.fixture()
def db_session():
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
def seeded(db_session):
    db = db_session
    perms = [Permission(code=c, description=c)
             for c in ("manage_inventory", "view_finance", "manage_menu")]
    db.add_all(perms); db.flush()
    role = Role(name="admin", description="Administrator")
    role.permissions = perms
    db.add(role); db.flush()

    cafe = Cafe(name="SINOV", code="q", access_code="100.200.81",
                business_type="store", subscription_plan="pro", is_active=True)
    db.add(cafe); db.flush()
    kat = Category(name="KAT", tenant_id=cafe.id)
    db.add(kat); db.flush()

    p_dona = Product(name="SOVUN", price=5000, cost_price=3000, sale_unit="pcs",
                     category_id=kat.id, tenant_id=cafe.id, is_active=True)
    p_kg = Product(name="GURUCH", price=18000, cost_price=14000, sale_unit="kg",
                   category_id=kat.id, tenant_id=cafe.id, is_active=True)
    p_yangi = Product(name="YANGI", price=1000, sale_unit="pcs",
                      category_id=kat.id, tenant_id=cafe.id, is_active=True)
    db.add_all([p_dona, p_kg, p_yangi]); db.flush()

    inv_dona = Inventory(product_id=p_dona.id, quantity=50, unit="dona", tenant_id=cafe.id)
    inv_kg = Inventory(product_id=p_kg.id, quantity=20, unit="kg", tenant_id=cafe.id)
    db.add_all([inv_dona, inv_kg]); db.flush()

    sup = Supplier(name="FIRMA", tenant_id=cafe.id)
    db.add(sup); db.flush()

    db.add(User(username="uq", email="q@x.uz", full_name="Admin", phone=PHONE,
                hashed_password=get_password_hash(ADMIN_PW), is_active=True,
                is_superuser=False, tenant_id=cafe.id, role_id=role.id))
    db.commit()
    return {"db": db, "tid": cafe.id, "p_dona": p_dona.id, "p_kg": p_kg.id,
            "p_yangi": p_yangi.id, "inv_dona": inv_dona.id, "inv_kg": inv_kg.id,
            "sup": sup.id}


@pytest.fixture()
def client(db_session):
    def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def hdr(client, seeded):
    r = client.post(f"{API}/auth/login", data={"username": PHONE, "password": ADMIN_PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _qty(db, inv_id):
    db.expire_all()
    return db.query(Inventory).get(inv_id).quantity


def _moves(db):
    return db.query(StockMovement).count()


def _assert_rad(r):
    assert r.status_code == 400, r.text
    assert "shtrix-kod" in r.json()["detail"], r.text


# ══════════════════════════════════════════════════════════════════════════════
# 1) TALAB QILINGAN 4 HOL — ombor kirimi (add-stock)
# ══════════════════════════════════════════════════════════════════════════════

def test_kirim_1000001_rad(client, seeded, hdr):
    db = seeded["db"]
    before, mv = _qty(db, seeded["inv_dona"]), _moves(db)
    r = client.post(f"{API}/inventory/{seeded['inv_dona']}/add-stock",
                    json={"quantity": 1_000_001}, headers=hdr)
    _assert_rad(r)
    assert _qty(db, seeded["inv_dona"]) == before, "rad etilgan kirim omborga yozilgan"
    assert _moves(db) == mv, "rad etilgan kirim harakat yozgan"


def test_kirim_shtrix_kod_rad(client, seeded, hdr):
    db = seeded["db"]
    before = _qty(db, seeded["inv_dona"])
    r = client.post(f"{API}/inventory/{seeded['inv_dona']}/add-stock",
                    json={"quantity": BARCODE}, headers=hdr)
    _assert_rad(r)
    assert _qty(db, seeded["inv_dona"]) == before


def test_kirim_10000_otadi(client, seeded, hdr):
    db = seeded["db"]
    r = client.post(f"{API}/inventory/{seeded['inv_dona']}/add-stock",
                    json={"quantity": 10_000}, headers=hdr)
    assert r.status_code == 200, r.text
    assert _qty(db, seeded["inv_dona"]) == 50 + 10_000


def test_kirim_kasrli_0566_otadi(client, seeded, hdr):
    db = seeded["db"]
    r = client.post(f"{API}/inventory/{seeded['inv_kg']}/add-stock",
                    json={"quantity": 0.566}, headers=hdr)
    assert r.status_code == 200, r.text
    assert abs(_qty(db, seeded["inv_kg"]) - 20.566) < 1e-9


def test_kirim_aynan_chegara_otadi(client, seeded, hdr):
    """1 000 000 — chegara ICHIDA (`<=`), rad etilmasin."""
    r = client.post(f"{API}/inventory/{seeded['inv_dona']}/add-stock",
                    json={"quantity": MAX_QTY}, headers=hdr)
    assert r.status_code == 200, r.text


# ══════════════════════════════════════════════════════════════════════════════
# 2) QOLGAN OMBOR YO'LLARI
# ══════════════════════════════════════════════════════════════════════════════

def test_boshlangich_qoldiq_rad_va_otadi(client, seeded, hdr):
    db = seeded["db"]
    r = client.post(f"{API}/inventory/",
                    json={"product_id": seeded["p_yangi"], "quantity": BARCODE}, headers=hdr)
    _assert_rad(r)
    assert db.query(Inventory).filter_by(product_id=seeded["p_yangi"]).count() == 0

    r = client.post(f"{API}/inventory/",
                    json={"product_id": seeded["p_yangi"], "quantity": 120}, headers=hdr)
    assert r.status_code == 200, r.text
    assert r.json()["quantity"] == 120


def test_ombor_patch_rad(client, seeded, hdr):
    db = seeded["db"]
    r = client.patch(f"{API}/inventory/{seeded['inv_dona']}",
                     json={"quantity": BARCODE}, headers=hdr)
    _assert_rad(r)
    assert _qty(db, seeded["inv_dona"]) == 50


def test_chiqim_query_param_rad(client, seeded, hdr):
    r = client.post(f"{API}/inventory/{seeded['inv_dona']}/remove-stock",
                    params={"quantity": BARCODE}, headers=hdr)
    _assert_rad(r)


def test_hisobdan_chiqarish_rad_va_otadi(client, seeded, hdr):
    db = seeded["db"]
    r = client.post(f"{API}/inventory/writeoff",
                    json={"inventory_id": seeded["inv_dona"], "quantity": BARCODE,
                          "reason": "spoiled"}, headers=hdr)
    _assert_rad(r)
    r = client.post(f"{API}/inventory/writeoff",
                    json={"inventory_id": seeded["inv_kg"], "quantity": 0.566,
                          "reason": "spoiled"}, headers=hdr)
    assert r.status_code == 200, r.text
    assert abs(_qty(db, seeded["inv_kg"]) - 19.434) < 1e-9


def test_inventarizatsiya_rad_va_otadi(client, seeded, hdr):
    db = seeded["db"]
    cnt = InventoryCount(tenant_id=seeded["tid"], status="draft")
    db.add(cnt); db.flush()
    it = InventoryCountItem(count_id=cnt.id, inventory_id=seeded["inv_dona"],
                            product_id=seeded["p_dona"], product_name="SOVUN",
                            unit="dona", system_qty=50)
    db.add(it); db.commit()

    r = client.patch(f"{API}/inventory/count/{cnt.id}/items/{it.id}",
                     json={"actual_qty": BARCODE}, headers=hdr)
    _assert_rad(r)
    db.expire_all()
    assert db.query(InventoryCountItem).get(it.id).actual_qty is None

    r = client.patch(f"{API}/inventory/count/{cnt.id}/items/{it.id}",
                     json={"actual_qty": 48}, headers=hdr)
    assert r.status_code == 200, r.text
    assert r.json()["difference"] == -2


def test_priyomka_rad_va_otadi(client, seeded, hdr):
    base = {"supplier_id": seeded["sup"], "receipt_date": "2026-10-13"}
    r = client.post(f"{API}/purchase-receipts/", headers=hdr, json={**base, "items": [
        {"product_id": seeded["p_dona"], "quantity": 10, "unit_price": 3000},
        {"product_id": seeded["p_kg"], "quantity": BARCODE, "unit_price": 14000},
    ]})
    _assert_rad(r)
    assert "2-qator" in r.json()["detail"]

    r = client.post(f"{API}/purchase-receipts/", headers=hdr, json={**base, "items": [
        {"product_id": seeded["p_kg"], "quantity": 0.566, "unit_price": 14000},
    ]})
    assert r.status_code == 200, r.text


def test_spisaniye_akti_rad(client, seeded, hdr):
    r = client.post(f"{API}/write-offs/", headers=hdr, json={
        "reason": "damaged", "write_off_date": "2026-10-13",
        "items": [{"product_id": seeded["p_dona"], "quantity": BARCODE}],
    })
    _assert_rad(r)


# ══════════════════════════════════════════════════════════════════════════════
# 3) QO'RIQCHI FUNKSIYASI — chegaraviy qiymatlar
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("v", [None, 0, 0.001, 0.566, 1, 9999, 10_000, MAX_QTY, -5])
def test_check_qty_otadi(v):
    check_qty(v)


@pytest.mark.parametrize("v", [1_000_001, BARCODE, 4780000000001, -BARCODE,
                               float("inf"), float("nan")])
def test_check_qty_rad(v):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        check_qty(v)
    assert e.value.status_code == 400
