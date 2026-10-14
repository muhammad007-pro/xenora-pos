"""OG'IRLIK × MIQDOR — chek #4094 (fix/weight-qty-and-price-limit).

MUAMMO (prod, BARAKA 09.10): POS savatida og'irlik qatori `qty: 2, _weight: 1 kg`
(−/+ tugmasi og'irlik qatoriga ham ishlaydi). Ekranda 2 × 70 000 = 140 000,
mijoz shuni to'ladi; serverga esa `quantity = _weight` (1 kg) ketdi →
chek 70 000, ombordan 1 kg ayirildi.

QAROR: tuzatish KLIENTDA (`pos.js:_lineQty` — quantity = JAMI og'irlik). Server
`qty` ni olmaydi; `quantity` = sotilgan kg — server narx×miqdor, ombor, vozvrat
o'zgarishsiz to'g'ri hisoblaydi. Bu test serverning shu shartnomasini qulflaydi:
  1) quantity 2 kg → chek to'liq (2 × narx), ombordan 2 kg, harakat 2
  2) ESKI klient (quantity 1 kg, to'lov 2 × narx) → 400 "chek summasidan ko'p",
     hech narsa yozilmaydi — jimgina kam yozish endi mumkin emas (onlayn)
  3) summa rejimi qty 2: quantity = round3(summa×2/narx) → qabul;
     round3(w)×2 esa yaxlitlash xatosini ikki baravar qilib 400 berardi (nega
     klient summadan hisoblaydi — isbot)
  4) GOLDEN: qty 1 og'irlik sotuvi avvalgidek

Ishga tushirish:  cd backend && py -m pytest tests/test_weight_qty.py -v -p no:randomly
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Order, Payment, StockMovement

from tests.test_payment_rounding import (  # noqa: F401 — pytest fixture'lari
    eng, db_session, client, shop, _h, _order, _pay, _status, _stock, KG_PRICE,
)


def test_qty2_x_1kg_toliq_summa_va_2kg(client, shop):
    db, h = shop["db"], _h(client)
    r = _order(client, h, [{"product_id": shop["kg"], "quantity": 2.0}])   # yangi klient: 1 kg × 2
    assert r.status_code == 200, r.text
    o = r.json()
    assert o["final_amount"] == 2 * KG_PRICE
    _pay(client, h, o["id"], 2 * KG_PRICE)
    assert _status(db, o["id"]) == "completed"
    assert _stock(db, shop["kg"]) == 8.0
    mv = db.query(StockMovement).filter(StockMovement.reference_id == o["id"]).one()
    assert mv.quantity == 2.0


def test_eski_klient_kam_yozish_endi_400(client, shop):
    """#4094 aynan: chek 1 kg, kassa 2 kg narxini oladi → server rad etadi."""
    db, h = shop["db"], _h(client)
    o = _order(client, h, [{"product_id": shop["kg"], "quantity": 1.0}]).json()
    assert o["final_amount"] == KG_PRICE
    r = client.post("/api/v1/payments/", headers=h,
                    json={"order_id": o["id"], "amount": 2 * KG_PRICE, "method": "cash"})
    assert r.status_code == 400, r.text
    assert "ko'p" in r.json()["detail"]
    assert _status(db, o["id"]) == "pending"
    assert _stock(db, shop["kg"]) == 10.0
    assert db.query(Payment).filter(Payment.order_id == o["id"]).count() == 0


def test_summa_rejimi_qty2(client, shop):
    db, h = shop["db"], _h(client)
    T = 15_010.0                                   # T/narx = 0.566415… → round3 0.566 (xato 0.000415)
    w = round(T / KG_PRICE, 3)
    # Klient (`_lineQty`): summadan — xato ≤ 0.0005
    good = round(T * 2 / KG_PRICE, 3)
    r = _order(client, h, [{"product_id": shop["kg"], "quantity": good, "line_total": T * 2}])
    assert r.status_code == 200, r.text
    assert r.json()["final_amount"] == T * 2
    # Oddiy round3(w) × 2 — xato ikki baravar (0.00083 > 0.0005) → server rad etardi
    naive = round(w * 2, 3)
    assert naive != good
    r2 = _order(client, h, [{"product_id": shop["kg"], "quantity": naive, "line_total": T * 2}])
    assert r2.status_code == 400, r2.text


def test_GOLDEN_qty1_ogirlik(client, shop):
    db, h = shop["db"], _h(client)
    o = _order(client, h, [{"product_id": shop["kg"], "quantity": 0.656}]).json()
    assert o["final_amount"] == round(0.656 * KG_PRICE, 0) or o["final_amount"] == round(0.656 * KG_PRICE, 2)
    _pay(client, h, o["id"], o["final_amount"])
    assert _status(db, o["id"]) == "completed"
    assert _stock(db, shop["kg"]) == 10.0 - 0.656 or abs(_stock(db, shop["kg"]) - 9.344) < 1e-9
    assert db.query(Order).get(o["id"]).items[0].quantity == 0.656


def test_pos_narx_kelishuvi_shtrix_kod(client, shop):
    """Kassa narx maydoni (narx kelishuvi) avvaldan himoyalangan:
    schemas.OrderItemCreate.unit_price_override le=1 000 000 000 — price_guard bilan
    BIR chegara. Shtrix-kod qo'shilgan narx → 422 (rad), oddiy oshirish → o'tadi."""
    from schemas import OrderItemCreate
    from services.price_guard import MAX_PRICE
    assert OrderItemCreate.model_fields["unit_price_override"].metadata[-1].le == MAX_PRICE
    h = _h(client)
    r = _order(client, h, [{"product_id": shop["dona"], "quantity": 1,
                            "unit_price_override": float("12000" + "4780019480030")}])
    assert r.status_code == 422, r.text
    ok = _order(client, h, [{"product_id": shop["dona"], "quantity": 1, "unit_price_override": 6_000}])
    assert ok.status_code == 200, ok.text
    assert ok.json()["final_amount"] == 6_000
