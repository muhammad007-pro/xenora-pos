"""FOYDA HISOBI BIRLASHTIRILDI — `utils/revenue.py:period_totals()` yagona manba.

MUAMMO: foyda TO'RT joyda TO'RT xil hisoblanardi. v1.9.7 dan keyin uchtasi
tenglashdi, lekin `/analytics/store-dashboard` ajralib turaverdi:
    tan narx = Product.cost_price (BUGUNGI narx) × miqdor
Bu O'TMISHGA NOTO'G'RI — priyomka `cost_price` ni qayta yozadi
(purchase_receipts.py:233), ya'ni eski sotuvlar foydasi ORQAGA o'zgarardi.
Jonli misol (Fazza, 2026-08-28): u yerda 503 970, boshqa uchtasida 405 320.

Bu fayl uchta narsani qotiradi:
  1) TO'G'RI TAN NARX — `unit_cost` snapshot ustun, `cost_price` faqat zaxira
  2) IKKI EKRAN BIR XIL — store-dashboard == /analytics/dashboard
  3) YALPI ≠ SOF — `period_totals` xarajatni HISOBGA OLMAYDI (bu ATAYIN)

Ishga tushirish:  cd backend && py -m pytest tests/test_unified_profit.py -v
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import (
    Cafe, Category, Expense, Inventory, Order, OrderItem, Product,
    Return, ReturnItem,
)
from utils.revenue import period_totals

TID = 1
T0 = datetime(2026, 8, 28, 12, 0)
START, END = datetime(2026, 8, 28, 0, 0), datetime(2026, 8, 28, 23, 59, 59)


class _User:
    is_superuser = False
    tenant_id = TID
    id = 1
    role = None


@pytest.fixture()
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    s = sessionmaker(bind=eng)()
    s.add(Cafe(id=TID, name="Fazza", code="FAZZA", business_type="store"))
    s.add(Category(id=1, name="Parfum", tenant_id=TID))
    s.commit()
    yield s
    s.close()


def _prod(db, pid, name, price, cost_price):
    db.add(Product(id=pid, name=name, price=price, cost_price=cost_price,
                   category_id=1, tenant_id=TID))
    db.commit()


def _order(db, oid, items, discount=0.0, status="completed", when=T0):
    """items: [(product_id, qty, unit_price, unit_cost)]"""
    sub = sum(q * up for _, q, up, _ in items)
    db.add(Order(id=oid, order_number=f"N{oid}", tenant_id=TID, status=status,
                 total_amount=sub, discount_amount=discount,
                 final_amount=sub - discount, created_at=when))
    db.flush()
    for pid, q, up, uc in items:
        db.add(OrderItem(order_id=oid, product_id=pid, quantity=q,
                         unit_price=up, unit_cost=uc, total_price=q * up,
                         tenant_id=TID))
    db.commit()


# ═══════════════════════════════════════════════════════════════════════════
# 1. TO'G'RI TAN NARX — snapshot, bugungi narx EMAS
# ═══════════════════════════════════════════════════════════════════════════
def test_snapshot_tan_narx_ustun(db):
    """JONLI HODISA: mahsulot sotilgandan KEYIN priyomka `cost_price` ni
    qayta yozadi. Foyda O'ZGARMASLIGI kerak."""
    _prod(db, 1, "Atir", price=100_000, cost_price=60_000)
    _order(db, 1, [(1, 1, 100_000, 60_000)])
    assert period_totals(db, _User(), START, END)["gross_profit"] == 40_000

    # priyomka keldi — bugungi tan narx ikki barobar oshdi
    db.query(Product).filter(Product.id == 1).update({"cost_price": 120_000})
    db.commit()
    t = period_totals(db, _User(), START, END)
    assert t["cost"] == 60_000                    # SNAPSHOT saqlandi
    assert t["gross_profit"] == 40_000            # o'tmish O'ZGARMADI
    # ESKI store-dashboard mantig'i bo'lsa: 100 000 − 120 000 = −20 000 bo'lardi


def test_unit_cost_yoq_bolsa_cost_price_zaxira(db):
    """Eski/import yozuv — `unit_cost` NULL. Zaxira: mahsulotning cost_price."""
    _prod(db, 1, "Atir", price=100_000, cost_price=70_000)
    _order(db, 1, [(1, 1, 100_000, None)])
    t = period_totals(db, _User(), START, END)
    assert t["cost"] == 70_000
    assert t["gross_profit"] == 30_000


def test_chegirma_daromaddan_ayiriladi(db):
    _prod(db, 1, "Atir", price=100_000, cost_price=60_000)
    _order(db, 1, [(1, 2, 100_000, 60_000)], discount=50_000)
    t = period_totals(db, _User(), START, END)
    assert t["revenue"] == 150_000                # 200 000 − 50 000
    assert t["cost"] == 120_000
    assert t["gross_profit"] == 30_000


# ═══════════════════════════════════════════════════════════════════════════
# 2. FILTRLAR
# ═══════════════════════════════════════════════════════════════════════════
def test_faqat_completed(db):
    _prod(db, 1, "Atir", price=100_000, cost_price=60_000)
    _order(db, 1, [(1, 1, 100_000, 60_000)], status="pending")
    _order(db, 2, [(1, 1, 100_000, 60_000)], status="cancelled")
    assert period_totals(db, _User(), START, END)["revenue"] == 0
    _order(db, 3, [(1, 1, 100_000, 60_000)], status="completed")
    assert period_totals(db, _User(), START, END)["revenue"] == 100_000


def test_davrdan_tashqari_hisobga_kirmaydi(db):
    _prod(db, 1, "Atir", price=100_000, cost_price=60_000)
    _order(db, 1, [(1, 1, 100_000, 60_000)], when=T0 - timedelta(days=3))
    assert period_totals(db, _User(), START, END)["revenue"] == 0


def test_boshqa_tenant_kirmaydi(db):
    db.add(Cafe(id=2, name="Eco", code="ECO")); db.commit()
    _prod(db, 1, "Atir", price=100_000, cost_price=60_000)
    db.add(Order(id=9, order_number="N9", tenant_id=2, status="completed",
                 total_amount=100_000, discount_amount=0, final_amount=100_000,
                 created_at=T0))
    db.flush()
    db.add(OrderItem(order_id=9, product_id=1, quantity=1, unit_price=100_000,
                     unit_cost=60_000, total_price=100_000, tenant_id=2))
    db.commit()
    assert period_totals(db, _User(), START, END)["revenue"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# 3. VOZVRAT
# ═══════════════════════════════════════════════════════════════════════════
def test_vozvrat_ayiriladi(db):
    _prod(db, 1, "Atir", price=100_000, cost_price=60_000)
    _order(db, 1, [(1, 2, 100_000, 60_000)])
    oi = db.query(OrderItem).first()

    r = Return(id=1, return_number="R1", tenant_id=TID, order_id=1,
               status="approved", total_amount=100_000, refund_method="cash",
               created_at=T0, approved_at=T0)
    db.add(r); db.flush()
    db.add(ReturnItem(return_id=1, product_id=1, order_item_id=oi.id,
                      quantity=1, base_qty=1, unit_price=100_000, total=100_000))
    db.commit()

    t = period_totals(db, _User(), START, END)
    assert t["revenue"] == 100_000                # 200 000 − 100 000
    assert t["cost"] == 60_000                    # 120 000 − 60 000
    assert t["gross_profit"] == 40_000
    assert t["returns_count"] == 1


def test_tasdiqlanmagan_vozvrat_ayirilmaydi(db):
    _prod(db, 1, "Atir", price=100_000, cost_price=60_000)
    _order(db, 1, [(1, 1, 100_000, 60_000)])
    oi = db.query(OrderItem).first()
    r = Return(id=1, return_number="R1", tenant_id=TID, order_id=1,
               status="pending", total_amount=100_000, refund_method="cash",
               created_at=T0)
    db.add(r); db.flush()
    db.add(ReturnItem(return_id=1, product_id=1, order_item_id=oi.id,
                      quantity=1, base_qty=1, unit_price=100_000, total=100_000))
    db.commit()
    assert period_totals(db, _User(), START, END)["gross_profit"] == 40_000


# ═══════════════════════════════════════════════════════════════════════════
# 4. YALPI ≠ SOF — xarajat ATAYIN kirmaydi
# ═══════════════════════════════════════════════════════════════════════════
def test_xarajat_hisobga_OLINMAYDI(db):
    """`period_totals` YALPI foyda beradi. Xarajat faqat `/profit/summary` da
    ayiriladi ("sof foyda"). Bu FARQ ataylab — ular turli ko'rsatkichlar."""
    _prod(db, 1, "Atir", price=100_000, cost_price=60_000)
    _order(db, 1, [(1, 1, 100_000, 60_000)])
    db.add(Expense(tenant_id=TID, category="rent", name="ARENDA",
                   amount=5_800_000, expense_date=T0.date()))
    db.commit()
    assert period_totals(db, _User(), START, END)["gross_profit"] == 40_000


# ═══════════════════════════════════════════════════════════════════════════
# 5. IKKI EKRAN BIR XIL RAQAM (asosiy maqsad)
# ═══════════════════════════════════════════════════════════════════════════
def test_GOLDEN_store_dashboard_va_dashboard_bir_xil(db):
    """Fazza 08-28 naqshi: mahsulot sotilgach `cost_price` o'zgargan.
    ESKI store-dashboard boshqa raqam berardi (503 970 / 405 320)."""
    import routers.analytics as an
    from core.timeutils import tenant_now

    bugun = tenant_now()
    _prod(db, 1, "BVLGARI AQUA", price=17_000, cost_price=10_000)
    _prod(db, 2, "Gupka", price=1_000, cost_price=700)
    _order(db, 1, [(1, 1, 1_400_000, 1_000_000), (2, 4, 1_000, 700)],
           when=bugun.replace(tzinfo=None) if bugun.tzinfo else bugun)
    db.add(Inventory(tenant_id=TID, product_id=1, quantity=5, unit="ml"))
    db.commit()

    # Sotuvdan KEYIN tan narx o'zgardi (priyomka) — eski formulani "chalg'itadi"
    db.query(Product).filter(Product.id == 1).update({"cost_price": 3_000})
    db.commit()

    sd = asyncio.run(an.get_store_dashboard(db=db, current_user=_User()))

    s = bugun.replace(hour=0, minute=0, second=0, microsecond=0)
    kutilgan = period_totals(db, _User(), s, bugun)["gross_profit"]

    assert sd["today_profit"] == kutilgan

    # Tushum = 1 400 000 (flakon) + 4×1 000 (gupka) = 1 404 000
    # YANGI tan narx (snapshot): 1 000 000 + 4×700 = 1 002 800 -> foyda 401 200
    # ESKI  tan narx (bugungi cost_price): 3 000×1 + 700×4 = 5 800 -> 1 398 200
    assert sd["today_profit"] == 1_404_000 - 1_002_800 == 401_200
    assert sd["today_profit"] != 1_404_000 - 5_800      # eski xato QAYTMADI


def test_bosh_davr_nol_qaytaradi(db):
    t = period_totals(db, _User(), START, END)
    assert t == {"revenue": 0.0, "cost": 0.0, "gross_profit": 0.0,
                 "returns_revenue": 0.0, "returns_cost": 0.0, "returns_count": 0}
