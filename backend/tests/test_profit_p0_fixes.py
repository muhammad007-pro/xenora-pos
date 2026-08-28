"""P0 FOYDA TUZATISHLARI — regressiya qulfi (Fazza Parfum tashxisi, 2026-08-28).

Bu testlar `fix/profit-calculation` branchidagi TO'RT tuzatishni qulflaydi.
Har biri JONLI bazadan topilgan aniq holatdan kelib chiqqan.

  P0-1  report_service: tan narxda COALESCE yo'q edi -> `unit_cost` NULL bo'lgan
        qator SUM dan jimgina tushib qolardi (tan narx kam, foyda oshiq).
        Vozvrat tomonida COALESCE bor edi -> assimetriya.

  P0-2  revenue.py: vozvrat tan narxi `base_qty(DONA) * unit_cost(PACHKA)` deb
        hisoblanardi -> `pack_size` marta shishardi.
        Jonli isbot (tenant 26): BVLGARI AQUA, pack_size=100, unit_cost=1 000 000
          eski  -> 100 * 1 000 000 = 100 000 000  (100 MLN!)
          to'g'ri->   1 * 1 000 000 =   1 000 000
        Bu `cost` dan AYIRILGANI uchun foydani ~99 mln ga OSHIRGAN bo'lardi.

  P0-3  report.py `_dates`: ikkala chegara ham 00:00 edi -> `created_at <= to`
        tugash kunini QAMRAMASDI. report.html standarti from=to=bugun ->
        "Bugun" hisoboti HAR DOIM 0 so'm chiqardi.

  P0-4  profit.py: `returns_totals()` ga `date` uzatilardi -> TIMESTAMP bilan
        solishtirilganda kun 00:00 ga qisilardi -> "Bugun" davrida vozvrat
        AMALDA HECH QACHON ayirilmasdi.

Ishga tushirish:  cd backend && py tests/test_profit_p0_fixes.py
"""
import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Category, Order, OrderItem, Product, Return, ReturnItem
from services.report_service import ReportService
from utils.revenue import returns_totals

_fails = []
_total = 0


def check(name, got, want, tol=0.005):
    global _total
    _total += 1
    ok = abs(float(got) - float(want)) <= tol
    if not ok:
        _fails.append(name)
    print(f"[{'OK  ' if ok else 'FAIL'}] {name}: {round(float(got), 2)} (kutilgan {want})")


def _session():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    return sessionmaker(bind=eng)()


# ═══════════════════════════════════════════════════════════════════════════
# P0-1 — tan narxda COALESCE
# ═══════════════════════════════════════════════════════════════════════════
def t_p0_1(db):
    db.add(Category(id=1, name="Parfum", tenant_id=1))
    # cost_price = 60 000 — `unit_cost` yo'q qatorda ZAXIRA sifatida ishlatilishi kerak
    db.add(Product(id=1, name="Atir", price=100000, cost_price=60000, category_id=1, tenant_id=1))
    db.flush()

    o = Order(id=1, order_number="P1", tenant_id=1, total_amount=200000,
              discount_amount=0, final_amount=200000, status="completed",
              created_at=datetime(2026, 8, 10, 12, 0))
    db.add(o)
    db.flush()
    # 1-qator: unit_cost SNAPSHOT bor -> o'sha ishlatiladi
    db.add(OrderItem(order_id=1, product_id=1, quantity=1,
                     unit_price=100000, unit_cost=55000, total_price=100000, tenant_id=1))
    # 2-qator: unit_cost YO'Q (eski/import qilingan sotuv) -> cost_price ga tushishi kerak
    db.add(OrderItem(order_id=1, product_id=1, quantity=1,
                     unit_price=100000, unit_cost=None, total_price=100000, tenant_id=1))
    db.commit()

    rep = ReportService(db).generate_profit_report(
        datetime(2026, 8, 1), datetime(2026, 8, 31), branch_id=None, current_user=None
    )
    check("P0-1_revenue", rep["total_revenue"], 200000)
    # YANGI: 55 000 + 60 000 = 115 000.  ESKI (buzuq) mantiq 55 000 berardi.
    check("P0-1_cost_coalesce_bilan", rep["total_cost"], 115000)
    check("P0-1_eski_xato_qaytmagan", rep["total_profit"], 200000 - 115000)


# ═══════════════════════════════════════════════════════════════════════════
# P0-2 — vozvrat tan narxi: birlik mosligi (pachka)
# ═══════════════════════════════════════════════════════════════════════════
def t_p0_2(db):
    db.add(Category(id=2, name="Atirlar", tenant_id=2))
    # Jonli holat: atir 100 ml flakon. cost_price = 1 ml tan narxi (10 000),
    # pachka (butun flakon) unit_cost = 10 000 * 100 = 1 000 000.
    db.add(Product(id=2, name="BVLGARI AQUA", price=17000, cost_price=10000,
                   pack_size=100, pack_price=1400000, category_id=2, tenant_id=2))
    db.flush()

    o = Order(id=2, order_number="P2", tenant_id=2, total_amount=1400000,
              discount_amount=0, final_amount=1400000, status="completed",
              created_at=datetime(2026, 8, 10, 12, 0))
    db.add(o)
    db.flush()
    oi = OrderItem(id=100, order_id=2, product_id=2, quantity=1, unit_sold="pachka",
                   base_qty=100, unit_price=1400000, unit_cost=1000000,
                   total_price=1400000, tenant_id=2)
    db.add(oi)

    r = Return(id=2, return_number="RET2", tenant_id=2, order_id=2, status="approved",
               total_amount=1400000, refund_method="cash",
               created_at=datetime(2026, 8, 11, 12, 0),
               approved_at=datetime(2026, 8, 11, 12, 0))
    db.add(r)
    db.flush()
    # Bitta FLAKON qaytarildi: quantity=1 (pachka), base_qty=100 (ml)
    db.add(ReturnItem(return_id=2, product_id=2, order_item_id=100,
                      quantity=1, base_qty=100, unit_price=1400000, total=1400000))
    db.commit()

    ret = returns_totals(db, None, datetime(2026, 8, 1), datetime(2026, 8, 31))
    check("P0-2_vozvrat_tushumi", ret["revenue"], 1400000)
    # YANGI: 1 pachka * 1 000 000 = 1 000 000
    # ESKI:  100 (ml) * 1 000 000 = 100 000 000  <- 100 BAROBAR shishgan
    check("P0-2_vozvrat_tan_narxi", ret["cost"], 1000000)
    if ret["cost"] > 2000000:
        print("      !! ESKI 100x XATO QAYTDI — foyda ~99 mln ga oshib ketadi")


def t_p0_2_fallback(db):
    """`unit_cost` yo'q vozvrat -> `cost_price` BAZA birligida -> base_qty ga ko'paytiriladi."""
    db.add(Product(id=3, name="Atir 2", price=17000, cost_price=10000,
                   pack_size=100, pack_price=1400000, category_id=2, tenant_id=3))
    r = Return(id=3, return_number="RET3", tenant_id=3, order_id=None, status="approved",
               total_amount=1400000, refund_method="cash",
               created_at=datetime(2026, 8, 11, 12, 0),
               approved_at=datetime(2026, 8, 11, 12, 0))
    db.add(r)
    db.flush()
    # order_item_id YO'Q -> unit_cost yo'q -> cost_price(1 ml) * base_qty(100 ml)
    db.add(ReturnItem(return_id=3, product_id=3, order_item_id=None,
                      quantity=1, base_qty=100, unit_price=1400000, total=1400000))
    db.commit()

    ret = returns_totals(db, None, datetime(2026, 8, 1), datetime(2026, 8, 31))
    # tenant filtri yo'q -> t_p0_2 dagi 1 000 000 ham qo'shiladi
    check("P0-2_fallback_cost_price_base_birlikda", ret["cost"], 1000000 + 100 * 10000)


# ═══════════════════════════════════════════════════════════════════════════
# P0-3 / P0-4 — sana chegaralari
# ═══════════════════════════════════════════════════════════════════════════
def t_p0_3():
    from routers.report import _dates
    df, dt = _dates("2026-08-28", "2026-08-28")
    check("P0-3_boshlanish_soati", df.hour, 0)
    check("P0-3_tugash_soati",     dt.hour, 23)
    check("P0-3_tugash_daqiqasi",  dt.minute, 59)
    check("P0-3_tugash_mikrosoniya", dt.microsecond, 999999)
    # ESKI: dt == df (ikkalasi 00:00) -> oraliq BO'SH edi. Endi ~1 kun (1 mks kam).
    check("P0-3_oraliq_bir_kun", (dt - df).total_seconds(), 86400 - 1e-6, tol=1e-3)


def t_p0_4():
    from routers.profit import _dt_bounds
    s, e = _dt_bounds(date(2026, 8, 28), date(2026, 8, 28))
    check("P0-4_boshlanish_soati", s.hour, 0)
    check("P0-4_tugash_soati",     e.hour, 23)
    check("P0-4_oraliq_bir_kun", (e - s).total_seconds(), 86400 - 1e-6, tol=1e-3)


def main():
    print("=== P0 FOYDA TUZATISHLARI ===\n")
    db = _session()
    t_p0_1(db)
    print()
    t_p0_2(db)
    t_p0_2_fallback(db)
    print()
    t_p0_3()
    t_p0_4()
    db.close()

    print()
    if _fails:
        print(f"{_total - len(_fails)}/{_total} PASS — XATO: {', '.join(_fails)}")
        sys.exit(1)
    print(f"{_total}/{_total} PASS")


def test_p0_fixes():
    """pytest kirish nuqtasi."""
    main()


if __name__ == "__main__":
    main()
