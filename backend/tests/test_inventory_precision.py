"""MIQDOR ANIQLIGI — float chiqindisi omborga yozilmasin (fix/inventory-precision).

MUAMMO (prod, BARAKA 2026-10-14): 0.265 + 8.4 = 8.665000000000001; frontend
"qoldiqni X ga tenglash" farqini float'da yuborib, bir kunda 12 ta iflos harakat
(`writeoff 0.665000000000001`, `in 9e-15`). Qoldiq 20+ joyda yangilanadi,
faqat 4 tasi yaxlitlardi.

Qotiriladi (`models.round_qty` + atribut tinglovchilari):
  1) API: kirim 0.265 → 8.4 qo'shilsa qoldiq AYNAN 8.665
  2) API: hisobdan chiqarish 0.665000000000001 → qoldiq 8.0, harakat 0.665
  3) API: chiqim (remove-stock) va 9e-15 kirim — qoldiq iflos bo'lmaydi
  4) ORM: har yo'l (=, +=, konstruktor) — inventory 3 xona, harakat 6 xona
  5) GOLDEN: butun sonlar, 0.566, retseptning 6 xonali harakati o'zgarmaydi;
     bazadan O'QISH qiymatni o'zgartirmaydi (eski qatorlar faqat yozilganda tozalanadi)

Ishga tushirish:  cd backend && py -m pytest tests/test_inventory_precision.py -v -p no:randomly
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from models import Inventory, StockMovement, round_qty, QTY_DECIMALS, MOVEMENT_QTY_DECIMALS

from tests.test_quantity_limit import (  # noqa: F401 — pytest fixture'lari
    db_session, seeded, client, hdr, _qty, API,
)


def _moves(db, inv_id):
    db.expire_all()
    return [(m.movement_type, m.quantity)
            for m in db.query(StockMovement).filter(StockMovement.inventory_id == inv_id)
                                            .order_by(StockMovement.id).all()]


def test_kirim_0265_plus_84_aynan_8665(seeded, client, hdr):
    db, inv = seeded["db"], seeded["inv_kg"]
    db.query(Inventory).get(inv).quantity = 0.265
    db.commit()
    r = client.post(f"{API}/inventory/{inv}/add-stock", json={"quantity": 8.4}, headers=hdr)
    assert r.status_code == 200, r.text
    q = _qty(db, inv)
    assert q == 8.665 and repr(q) == "8.665"


def test_hisobdan_chiqarish_float_farq(seeded, client, hdr):
    db, inv = seeded["db"], seeded["inv_kg"]
    db.query(Inventory).get(inv).quantity = 8.665
    db.commit()
    # frontend 8.665 − 8 ni float'da hisoblab yuboradi
    r = client.post(f"{API}/inventory/writeoff",
                    json={"inventory_id": inv, "quantity": 8.665 - 8, "reason": "other"}, headers=hdr)
    assert r.status_code == 200, r.text
    assert repr(_qty(db, inv)) == "8.0"
    assert _moves(db, inv)[-1] == ("writeoff", 0.665)


def test_chiqim_va_mayda_kirim(seeded, client, hdr):
    db, inv = seeded["db"], seeded["inv_kg"]
    db.query(Inventory).get(inv).quantity = 5.687
    db.commit()
    r = client.post(f"{API}/inventory/{inv}/remove-stock", params={"quantity": 5.687 - 0.001}, headers=hdr)
    assert r.status_code == 200, r.text
    assert repr(_qty(db, inv)) == "0.001"
    # prodda: `in 9e-15` — endi qoldiq va harakat iflos bo'lmaydi
    client.post(f"{API}/inventory/{inv}/add-stock", json={"quantity": 0.1 + 0.2 - 0.3}, headers=hdr)
    assert repr(_qty(db, inv)) == "0.001"


def test_orm_har_yol():
    i = Inventory(quantity=0.265)
    i.quantity += 8.4
    assert repr(i.quantity) == "8.665"
    i.quantity = 0.1 + 0.2
    assert repr(i.quantity) == "0.3"
    i.quantity = -0.0001
    assert repr(i.quantity) == "0.0"                        # -0.0 ham emas
    m = StockMovement(movement_type="writeoff", quantity=0.665000000000001)
    assert repr(m.quantity) == "0.665"
    m.quantity = 9e-15
    assert m.quantity == 0.0


def test_GOLDEN_qiymatlar_ozgarmaydi():
    for v in (0, 1, 50, 10_000, 1_000_000, 0.566, 0.656, 2.5, 182.0):
        assert round_qty(v) == v
    # retsept yo'li: harakat 6 xonada (gramm ulushi saqlanadi)
    assert StockMovement(movement_type="sale", quantity=0.0004).quantity == 0.0004
    assert StockMovement(movement_type="sale", quantity=0.000125).quantity == 0.000125
    assert (QTY_DECIMALS, MOVEMENT_QTY_DECIMALS) == (3, 6)
    # son bo'lmagan qiymatlar tegilmaydi
    assert round_qty(None) is None and round_qty(True) is True


def test_GOLDEN_bazadan_oqish_ozgartirmaydi(seeded):
    """Eski iflos qator FAQAT o'qilganda o'zgarmaydi (tozalash — alohida SQL)."""
    db, inv = seeded["db"], seeded["inv_kg"]
    db.execute(text("UPDATE inventory SET quantity = :q WHERE id = :i"), {"q": 0.265 + 8.4, "i": inv})
    db.commit()
    db.expire_all()
    row = db.query(Inventory).get(inv)
    assert row.quantity == 0.265 + 8.4               # o'qish — tegilmagan
    assert db.is_modified(row) is False
