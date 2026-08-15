"""POS narx kelishuvi — SERVER tomoni (unit_price_override) xavfsizlik chegarasi.

QOIDA: server override'ni FAQAT katalog narxidan KATTA bo'lsa qabul qiladi.

NEGA ASIMMETRIK:
  OSHIRISH  — tanqis mahsulotga ustiga qo'yish. Bu chegirma emas, sotuv narxining
              o'zi oshadi. Client uchun xavf yo'q: u o'ziga ZARAR qiladi, foyda emas.
  TUSHIRISH — chegirma kanalidan (discount_type/discount_value) o'tadi, u yerda
              `min(dv, server_subtotal)` bilan cheklangan va Order.discount_amount
              ga yozilib hisobotlarga tushadi. Agar tushirish override'dan ham
              o'tsa edi, client narxni O'ZI UCHUN ARZONLASHTIRA olardi va
              "client narxiga ishonilmaydi" qoidasi buzilardi.

Bu test HAQIQIY create_order() ni haqiqiy SQLite bazada chaqiradi.

Ishga tushirish:  cd backend && py tests/test_price_override.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Category, OrderItem, Product
from schemas import OrderCreate, OrderItemCreate
from services.order_service import OrderService

_fails = []
_total = 0


def check(name, got, want):
    global _total
    _total += 1
    ok = got == want
    if not ok:
        _fails.append(name)
    print(f"[{'OK  ' if ok else 'FAIL'}] {name}: {got} (kutilgan {want})")


def _session():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    db = sessionmaker(bind=eng)()
    db.add(Category(id=1, name="Parfum", tenant_id=1))
    db.add(Product(id=1, name="Shampun", price=145000, cost_price=100000,
                   category_id=1, tenant_id=1, is_available=True))
    db.commit()
    return db


def _make(db, override, qty=1, discount_type=None, discount_value=None):
    svc = OrderService(db)
    # _next_daily_number PostgreSQL'ning timezone() funksiyasini ishlatadi — SQLite'da
    # yo'q (mavjud holat, narx mantig'iga aloqasi yo'q). Kunlik raqam bu testda
    # sinalmaydi, shuning uchun chetlab o'tamiz.
    svc._next_daily_number = lambda tenant_id: 1
    order = svc.create_order(
        OrderCreate(
            order_type="dine-in",
            items=[OrderItemCreate(product_id=1, quantity=qty,
                                   unit_price_override=override)],
            discount_type=discount_type,
            discount_value=discount_value,
        ),
        waiter_id=1, tenant_id=1,
    )
    it = db.query(OrderItem).filter(OrderItem.order_id == order.id).first()
    return order, it


def main():
    db = _session()

    # ── O1: override YO'Q -> katalog narxi (regressiya nazorati) ─────────────
    o, it = _make(db, None)
    check("O1_override_yoq_katalog", it.unit_price, 145000)
    check("O1_final", o.final_amount, 145000)

    # ── O2: OSHIRISH qabul qilinadi, chegirma yozilmaydi ────────────────────
    o, it = _make(db, 160000)
    check("O2_oshirish_qabul", it.unit_price, 160000)
    check("O2_total_price", it.total_price, 160000)
    check("O2_chegirma_yozilmadi", o.discount_amount, 0)
    check("O2_final", o.final_amount, 160000)

    # ── O3: ⚠️ TUSHIRISH RAD ETILADI — katalog narxi saqlanadi ──────────────
    #        Client narxni o'zi uchun arzonlashtira olmaydi.
    o, it = _make(db, 100000)
    check("O3_tushirish_RAD", it.unit_price, 145000)
    check("O3_final_katalogdan", o.final_amount, 145000)

    # ── O4: tushirish CHEGIRMA kanalidan o'tadi (to'g'ri yo'l) ──────────────
    o, it = _make(db, None, discount_type="fixed", discount_value=5000)
    check("O4_qator_katalogda", it.unit_price, 145000)
    check("O4_chegirma_yozildi", o.discount_amount, 5000)
    check("O4_final", o.final_amount, 140000)

    # ── O5: chegirma subtotaldan oshmaydi (mavjud himoya buzilmadi) ─────────
    o, it = _make(db, None, discount_type="fixed", discount_value=999999)
    check("O5_chegirma_cheklandi", o.discount_amount, 145000)
    check("O5_final_manfiy_emas", o.final_amount, 0)

    # ── O6: oshirish + chegirma birga — chegirma OSHGAN subtotaldan ─────────
    o, it = _make(db, 200000, discount_type="pct", discount_value=10)
    check("O6_narx_oshdi", it.unit_price, 200000)
    check("O6_chegirma_oshgan_subtotaldan", o.discount_amount, 20000)
    check("O6_final", o.final_amount, 180000)

    # ── O7: miqdor bilan ko'paytiriladi ─────────────────────────────────────
    o, it = _make(db, 160000, qty=3)
    check("O7_total_price", it.total_price, 480000)
    check("O7_tan_narx_tegilmadi", it.unit_cost, 100000)   # foyda to'g'ri oshadi

    # ── O8: schema chegarasi — manfiy/nol override umuman qabul qilinmaydi ──
    try:
        OrderItemCreate(product_id=1, quantity=1, unit_price_override=-5)
        check("O8_manfiy_rad", False, True)
    except Exception:
        check("O8_manfiy_rad", True, True)
    try:
        OrderItemCreate(product_id=1, quantity=1, unit_price_override=0)
        check("O8b_nol_rad", False, True)
    except Exception:
        check("O8b_nol_rad", True, True)

    db.close()
    print()
    if _fails:
        print(f"{_total - len(_fails)}/{_total} PASS — XATO: {', '.join(_fails)}")
        sys.exit(1)
    print(f"{_total}/{_total} PASS")


if __name__ == "__main__":
    main()
