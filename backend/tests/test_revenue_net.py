"""SOF TUSHUM (chegirma ayirilgan daromad) — utils/revenue.py matematikasi.

MUAMMO (audit 2026-08): hisobotlar daromadni OrderItem.total_price dan olardi —
bu chegirmagacha bo'lgan katalog summasi. Chegirma OrderItem'da saqlanmaydi
(maydon yo'q), faqat Order.discount_amount da. Natijada foyda chegirma summasiga
teng miqdorda OSHIRIB ko'rsatilardi.

Bu test HAQIQIY SQLite bazada, HAQIQIY so'rov ifodalari bilan tekshiradi:
  R1  chegirmasiz buyurtma  -> daromad AYNAN avvalgidek (REGRESSIYA YO'Q)
  R2  chegirmali buyurtma   -> daromad = subtotal - chegirma
  R3  mahsulot kesimidagi taqsimot AYNAN yig'iladi (ikki marta hisoblash YO'Q)
  R4  bepul aksiya qatori (total_price=0) -> 0 chegirma oladi
  R5  buzuq yozuv (chegirma > subtotal) -> manfiy daromad CHIQMAYDI (0 ga qisiladi)
  R6  soliq/xizmat haqi daromadga QO'SHILMAYDI (final_amount tuzog'i)
  R7  generate_profit_report() uchdan-uchiga to'g'ri foyda beradi

Ishga tushirish:  cd backend && py tests/test_revenue_net.py
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Category, Order, OrderItem, Product
from services.report_service import ReportService
from utils.revenue import net_revenue_expr, order_subtotal_subq

_fails = []


def check(name, got, want, tol=0.005):
    ok = abs(float(got) - float(want)) <= tol
    if not ok:
        _fails.append(name)
    print(f"[{'OK  ' if ok else 'FAIL'}] {name}: {round(float(got), 2)} (kutilgan {want})")


def _session():
    """Har ishga tushirishda toza in-memory baza."""
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    return sessionmaker(bind=eng)()


def _seed(db):
    """4 ta buyurtma — har biri bitta stsenariyni qoplaydi."""
    db.add(Category(id=1, name="Parfum", tenant_id=1))
    # cost_price: unit_cost snapshot bo'lmagan eski yozuvlar uchun zaxira
    db.add(Product(id=1, name="Shampun",   price=145000, cost_price=100000, category_id=1, tenant_id=1))
    db.add(Product(id=2, name="Sovun",     price=12000,  cost_price=8000,   category_id=1, tenant_id=1))
    db.add(Product(id=3, name="Atir",      price=400000, cost_price=250000, category_id=1, tenant_id=1))
    db.flush()

    when = datetime(2026, 8, 15, 12, 0, 0)

    def order(oid, discount, tax=0.0, service=0.0):
        sub = 0.0  # keyin to'ldiriladi
        o = Order(id=oid, order_number=f"T{oid}", tenant_id=1, status="completed",
                  created_at=when, discount_amount=discount, tax_amount=tax,
                  service_charge=service, total_amount=sub, final_amount=0.0)
        db.add(o)
        return o

    def item(oid, pid, qty, unit_price, unit_cost):
        db.add(OrderItem(order_id=oid, product_id=pid, tenant_id=1, quantity=qty,
                         unit_price=unit_price, unit_cost=unit_cost,
                         total_price=unit_price * qty))

    # A: CHEGIRMASIZ — regressiya nazorati (raqam o'zgarmasligi shart)
    order(1, discount=0)
    item(1, 1, 2, 145000, 100000)      # 290 000
    item(1, 2, 1, 12000, 8000)         #  12 000   subtotal = 302 000

    # B: CHEGIRMALI — Marg'ilon stsenariysi (145k->140k va 400k->390k = 15 000)
    order(2, discount=15000)
    item(2, 1, 1, 145000, 100000)      # 145 000
    item(2, 3, 1, 400000, 250000)      # 400 000   subtotal = 545 000

    # C: BEPUL AKSIYA qatori bilan (total_price = 0)
    order(3, discount=20000)
    item(3, 3, 1, 400000, 250000)      # 400 000
    item(3, 2, 1, 0, 8000)             #       0   subtotal = 400 000

    # D: BUZUQ yozuv — chegirma subtotaldan katta (eski/import ma'lumot)
    order(4, discount=500000)
    item(4, 2, 1, 12000, 8000)         #  12 000   subtotal =  12 000

    # E: SOLIQ + XIZMAT HAQI bor (final_amount tuzog'i uchun)
    order(5, discount=10000, tax=12000, service=10000)
    item(5, 1, 1, 100000, 60000)       # 100 000   subtotal = 100 000

    db.commit()


def _net_by_order(db):
    sq = order_subtotal_subq()
    rows = (
        db.query(OrderItem.order_id, func.sum(net_revenue_expr(sq)).label("net"))
        .join(Order, Order.id == OrderItem.order_id)
        .join(sq, sq.c.order_id == OrderItem.order_id)
        .group_by(OrderItem.order_id)
        .all()
    )
    return {r.order_id: float(r.net or 0) for r in rows}


def _net_by_product(db, order_id):
    sq = order_subtotal_subq()
    rows = (
        db.query(OrderItem.product_id, func.sum(net_revenue_expr(sq)).label("net"))
        .join(Order, Order.id == OrderItem.order_id)
        .join(sq, sq.c.order_id == OrderItem.order_id)
        .filter(OrderItem.order_id == order_id)
        .group_by(OrderItem.product_id)
        .all()
    )
    return {r.product_id: float(r.net or 0) for r in rows}


def main():
    db = _session()
    _seed(db)
    net = _net_by_order(db)

    # ── R1: CHEGIRMASIZ — eski xulq AYNAN saqlanadi ──────────────────────────
    gross_a = db.query(func.sum(OrderItem.total_price)).filter(OrderItem.order_id == 1).scalar()
    check("R1_chegirmasiz_regressiya_yoq", net[1], gross_a)
    check("R1_qiymat", net[1], 302000)

    # ── R2: CHEGIRMALI — subtotal - chegirma ─────────────────────────────────
    check("R2_chegirmali", net[2], 545000 - 15000)

    # ── R3: mahsulot kesimi AYNAN yig'iladi (ikki marta hisoblash yo'q) ──────
    per = _net_by_product(db, 2)
    #   shampun 145 000 * (1 - 15 000/545 000) = 141 009.17
    #   atir    400 000 * (1 - 15 000/545 000) = 388 990.83
    check("R3_ulush_shampun", per[1], 145000 * (1 - 15000 / 545000))
    check("R3_ulush_atir",    per[3], 400000 * (1 - 15000 / 545000))
    check("R3_yigindi_aynan", sum(per.values()), 530000)   # qoldiq ham, ortiqcha ham yo'q

    # ── R4: bepul aksiya qatori 0 chegirma oladi ─────────────────────────────
    per3 = _net_by_product(db, 3)
    check("R4_bepul_qator_0",   per3[2], 0)
    check("R4_haqiqiy_qator",   per3[3], 400000 - 20000)
    check("R4_buyurtma_jami",   net[3], 380000)

    # ── R5: buzuq yozuv — manfiy daromad chiqmaydi ───────────────────────────
    check("R5_manfiy_emas", net[4], 0)

    # ── R6: soliq/xizmat daromadga qo'shilmaydi (final_amount tuzogi) ────────
    #   final_amount bo'lsa: 100 000 - 10 000 + 12 000 + 10 000 = 112 000 (NOTO'G'RI)
    #   sof tushum:          100 000 - 10 000                   =  90 000 (TO'G'RI)
    check("R6_soliq_xizmat_qoshilmaydi", net[5], 90000)

    # ── R7: uchdan-uchiga — generate_profit_report() ─────────────────────────
    rep = ReportService(db).generate_profit_report(
        datetime(2026, 8, 1), datetime(2026, 8, 31), branch_id=None, current_user=None
    )
    #   sof tushum: 302 000 + 530 000 + 380 000 + 0 + 90 000 = 1 302 000
    check("R7_report_total_revenue", rep["total_revenue"], 1302000)
    #   tan narx (quantity * unit_cost): A 208 000 | B 350 000 | C 258 000
    #                                    D   8 000 | E  60 000  = 884 000
    check("R7_report_total_cost",   rep["total_cost"],   884000)
    check("R7_report_total_profit", rep["total_profit"], 1302000 - 884000)

    #   ESKI (buzuq) mantiq bo'yicha foyda: 1 359 000 - 884 000 = 475 000 bo'lardi,
    #   ya'ni chegirmalar (15k+20k+12k+10k = 57 000) chetlab o'tilardi.
    check("R7_eski_xato_qaytmagan", rep["total_profit"], 418000)

    db.close()
    print()
    total = 15
    if _fails:
        print(f"{total - len(_fails)}/{total} PASS — XATO: {', '.join(_fails)}")
        sys.exit(1)
    print(f"{total}/{total} PASS")


if __name__ == "__main__":
    main()
