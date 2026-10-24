"""NARX CHEGARASI — shtrix-kod narx maydoniga tushmasin (fix/weight-qty-and-price-limit).

MUAMMO (prod): skaner shtrix-kodni narx/tan narx maydoniga QO'SHIB yuboradi —
"12000" + "4780019480…" = 1.2000478e17. audit_logs: 11 marta, 3 do'kon.
BARAKA RIZQ 200 GR tannarxi 4 780 045 170 147 → "Ombor qiymati" 95,6 trln.

Qotiriladi (`services/price_guard.py`, MAX_PRICE = 1 000 000 000):
  1) mahsulot yaratish: narx / tan narx / ulgurji / pachka > 1 mlrd → 400, mahsulot YARATILMAYDI
  2) tahrirlash: tan narx = shtrix-kod → 400, narx va narx tarixi O'ZGARMAYDI
  3) ombor kirimi unit_cost shtrix-kod → 400, qoldiq ham tan narx ham o'zgarmaydi
  4) priyomka qatori unit_price → 400
  5) POS narx kelishuvi — avvaldan schema `le=1e9` (422); test_weight_qty.py da qulflangan
  6) GOLDEN: aynan 1 mlrd, 5 500 000 (prod eng qimmati), kasrli narx — o'tadi

Ishga tushirish:  cd backend && py -m pytest tests/test_price_limit.py -v -p no:randomly
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi import HTTPException

from models import Inventory, PriceHistory, Product, PurchaseReceipt
from services.price_guard import MAX_PRICE, check_price

from tests.test_quantity_limit import (  # noqa: F401 — pytest fixture'lari
    db_session, seeded, client, hdr, _qty, API,
)

BARCODE_COST = 4_780_045_170_147.0           # prod: RIZQ 200 GR tannarxi
APPENDED = float("12000" + "4780019480030")  # "12000" + EAN-13 = 1.2000478e17


def _assert_rad(r):
    assert r.status_code == 400, r.text
    assert "shtrix-kod" in r.json()["detail"]


def _kat(db, tid):
    from models import Category
    return db.query(Category).filter(Category.tenant_id == tid).first().id


@pytest.mark.parametrize("field", ["price", "cost_price", "wholesale_price", "pack_price"])
def test_yaratish_rad(seeded, client, hdr, field):
    db = seeded["db"]
    n0 = db.query(Product).count()
    body = {"name": "RIZQ 200 GR", "price": 12_000, "category_id": _kat(db, seeded["tid"]), "sale_unit": "pcs"}
    body[field] = APPENDED
    if field == "pack_price":
        body["pack_size"] = 10
    _assert_rad(client.post(f"{API}/products/", json=body, headers=hdr))
    db.expire_all()
    assert db.query(Product).count() == n0


def test_tahrir_tan_narx_shtrix_kod(seeded, client, hdr):
    db, pid = seeded["db"], seeded["p_dona"]
    h0 = db.query(PriceHistory).count()
    _assert_rad(client.patch(f"{API}/products/{pid}", json={"cost_price": BARCODE_COST}, headers=hdr))
    db.expire_all()
    p = db.query(Product).get(pid)
    assert (p.cost_price, p.price) == (3000, 5000)
    assert db.query(PriceHistory).count() == h0          # narx tarixi ham yozilmagan


def test_ombor_kirimi_unit_cost(seeded, client, hdr):
    db, inv = seeded["db"], seeded["inv_dona"]
    _assert_rad(client.post(f"{API}/inventory/{inv}/add-stock",
                            json={"quantity": 20, "unit_cost": BARCODE_COST}, headers=hdr))
    assert _qty(db, inv) == 50
    assert db.query(Product).get(seeded["p_dona"]).cost_price == 3000


def test_priyomka_unit_price(seeded, client, hdr):
    db = seeded["db"]
    r = client.post(f"{API}/purchase-receipts/", headers=hdr, json={
        "supplier_id": seeded["sup"], "receipt_date": "2026-10-14",
        "items": [{"product_id": seeded["p_dona"], "quantity": 10, "unit_price": BARCODE_COST}],
    })
    _assert_rad(r)
    db.expire_all()
    assert db.query(PurchaseReceipt).count() == 0


def test_GOLDEN_chegara_ichida(seeded, client, hdr):
    db, kat = seeded["db"], _kat(seeded["db"], seeded["tid"])
    for price in (MAX_PRICE, 5_500_000, 12_500.5):
        r = client.post(f"{API}/products/", headers=hdr, json={
            "name": f"T{price}", "price": price, "cost_price": min(price, 5_040_000),
            "category_id": kat, "sale_unit": "pcs"})
        assert r.status_code == 200, r.text
    r = client.patch(f"{API}/products/{seeded['p_dona']}", json={"cost_price": 3_200}, headers=hdr)
    assert r.status_code == 200, r.text
    r = client.post(f"{API}/inventory/{seeded['inv_dona']}/add-stock",
                    json={"quantity": 5, "unit_cost": 3_300}, headers=hdr)
    assert r.status_code == 200, r.text


def test_check_price_birlik():
    check_price(MAX_PRICE)
    check_price(None)
    for bad in (MAX_PRICE + 1, -APPENDED, float("nan"), float("inf")):
        with pytest.raises(HTTPException) as e:
            check_price(bad, "Narx")
        assert e.value.status_code == 400
