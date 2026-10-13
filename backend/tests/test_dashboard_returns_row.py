# -*- coding: utf-8 -*-
"""DASHBOARD: foyda blokida QAYTARISH qatori (feature/dashboard-returns-row).

Faqat KO'RSATISH — hisob o'zgarmaydi. `/profit/summary` da `revenue`/`cost`
allaqachon qaytarishdan keyin; endi ayirilgan summa ochiq beriladi:
    sales_gross − returns = revenue ("Sof savdo")

Qotiriladi:
  1) GOLDEN: profit_breakdown (yangi maydonlar ham) == /profit/summary
  2) zanjir aynan: sales_gross − returns == revenue; revenue − cost == gross_profit
  3) qaytarish — QAYTARILGAN kun bo'yicha: kechagi sotuvning bugungi vozvrati
     bugungi blokda; kechagi vozvrat va tasdiqlanmagan vozvrat kirmaydi
  4) qaytarish 0 → maydon 0, sales_gross == revenue == chap karta (total_revenue)
  5) GOLDEN: revenue/cost/net_profit qaytarishdan keyingi eski qiymat bilan bir xil

Fixture'lar `test_dashboard_net_profit.py` dan (soat qat'iy, SQLite zona = UTC).

Ishga tushirish:  cd backend && py -m pytest tests/test_dashboard_returns_row.py -v -p no:randomly
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import OrderItem, Product, Return, ReturnItem

from tests.test_dashboard_net_profit import (  # noqa: F401 — pytest fixture'lari
    _clock, db_session, seeded, client, _hdr, _dash, _summary, _at, TODAY, YESTERDAY,
)

NEW_KEYS = ("returns", "returns_count", "sales_gross")
KEYS = ("revenue", "cost", "gross_profit", "expenses", "net_profit") + NEW_KEYS


def _ret(db, cafe, ts, qty, status="approved", n=[0]):
    """P mahsulotdan qty dona qaytarish (1000 so'm, tan narx 600), sanasi ts."""
    n[0] += 1
    p = db.query(Product).first()
    oi = db.query(OrderItem).filter(OrderItem.product_id == p.id).first()
    r = Return(tenant_id=cafe, return_number=f"R{n[0]:04d}", order_id=oi.order_id,
               total_amount=1000 * qty, refund_method="cash", status=status,
               approved_at=ts if status == "approved" else None, created_at=ts)
    db.add(r); db.flush()
    db.add(ReturnItem(return_id=r.id, product_id=p.id, order_item_id=oi.id, quantity=qty,
                      unit_price=1000, total=1000 * qty))
    db.commit()


def test_GOLDEN_summary_bilan_aynan_qaytarish_bilan(db_session, seeded, client):
    _ret(db_session, seeded["cafe"], _at(TODAY, 9, 30), 2)
    h = _hdr(client)
    pb = _dash(client, h)["profit_breakdown"]
    s = _summary(client, h)
    assert {k: pb[k] for k in KEYS} == {k: s[k] for k in KEYS}


def test_zanjir_aynan_va_qaytarish_kuni(db_session, seeded, client):
    cafe = seeded["cafe"]
    _ret(db_session, cafe, _at(TODAY, 9, 30), 2)            # bugun — KIRADI
    _ret(db_session, cafe, _at(TODAY, 9, 40), 1)            # bugun — KIRADI
    _ret(db_session, cafe, _at(YESTERDAY, 16), 5)           # kecha — kirmaydi
    _ret(db_session, cafe, _at(TODAY, 9, 50), 4, "pending")  # tasdiqlanmagan — kirmaydi
    pb = _dash(client, _hdr(client))["profit_breakdown"]
    assert pb["returns"] == 3_000 and pb["returns_count"] == 2
    assert pb["sales_gross"] == 10_000                       # bugungi sotuv (2 chek)
    assert pb["sales_gross"] - pb["returns"] == pb["revenue"] == 7_000
    assert pb["cost"] == 6_000 - 3 * 600                     # qaytgan tovar tan narxi ham ayirilgan
    assert pb["revenue"] - pb["cost"] == pb["gross_profit"] == 2_800
    assert pb["net_profit"] == pb["gross_profit"] - pb["expenses"]


def test_kechagi_sotuvning_bugungi_qaytarishi_bugunga(db_session, seeded, client):
    """Izoh "kecha sotilgan tovar ham bo'lishi mumkin" — aynan shu holat."""
    _ret(db_session, seeded["cafe"], _at(TODAY, 8), 10)    # kechagi 50 donalik chekdan bo'lishi mumkin
    pb = _dash(client, _hdr(client))["profit_breakdown"]
    assert (pb["sales_gross"], pb["returns"], pb["revenue"]) == (10_000, 10_000, 0)


def test_qaytarish_nol_va_chap_karta_bilan_bir_xil(seeded, client):
    h = _hdr(client)
    pb = _dash(client, h)["profit_breakdown"]
    assert pb["returns"] == 0 and pb["returns_count"] == 0
    assert pb["sales_gross"] == pb["revenue"] == 10_000
    left = client.get("/api/v1/analytics/summary?period=today", headers=h).json()["total_revenue"]
    assert pb["sales_gross"] == left


def test_GOLDEN_eski_maydonlar_ozgarmagan(db_session, seeded, client):
    """revenue/cost/gross/net — qaytarish ayirilgan ESKI qiymatlar (hisob tegilmagan)."""
    _ret(db_session, seeded["cafe"], _at(TODAY, 9, 30), 2)
    h = _hdr(client)
    s = _summary(client, h)
    assert (s["revenue"], s["cost"], s["gross_profit"], s["net_profit"]) == (8_000, 4_800, 3_200, 3_200)
    d = _dash(client, h)
    assert d["net_profit"] == 3_200 and d["total_orders"] == 2
