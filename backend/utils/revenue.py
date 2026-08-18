"""Sof tushum (net revenue) — CHEGIRMA AYIRILGAN daromad. Yagona manba.

═══ MUAMMO (audit, 2026-08) ═══
Hisobotlar daromadni `OrderItem.total_price` dan olardi — bu CHEGIRMAGACHA bo'lgan
katalog summasi (`unit_price × quantity`). Chegirma esa OrderItem darajasida
UMUMAN saqlanmaydi (bunday maydon yo'q), faqat `Order.discount_amount` da —
u yerda qo'lda + mijoz + avtomatik aksiya chegirmalari serverda BITTA songa
yig'ilgan (order_service.create_order).

Natija: foyda chegirma summasiga TENG miqdorda oshirib ko'rsatilardi. Marg'ilon
amaliyotida deyarli har sotuvda narx tushiriladi → xato tizimli va katta edi.

═══ FORMULA ═══
    sof_tushum(buyurtma) = Σ(OrderItem.total_price) − Order.discount_amount

⚠️ `Order.final_amount` ATAYIN ISHLATILMAYDI — bu tuzoq:
       final_amount = subtotal − chegirma + soliq + xizmat_haqi
   Soliq va xizmat haqi mahsulot daromadi EMAS (restoran rejimida 12% + 10%).
   Uni daromad deb olsak foyda ~22% ga shishardi — mavjud xatoni almashtirgan
   bo'lardik, xolos.

═══ MAHSULOT/KATEGORIYA KESIMI (proporsional taqsimlash) ═══
Buyurtma chegirmasi qatorlar orasida ULUSHGA QARAB bo'linadi:

    koef(order) = 1 − discount_amount / Σ(o'sha order items.total_price)
    item_sof    = OrderItem.total_price × koef

  • Kafolat: Σ item_sof = subtotal − chegirma  → qoldiq ham, ortiqcha ham yo'q,
    ya'ni chegirma ANIQ BIR MARTA ayiriladi (ikki marta hisoblash mumkin emas).
  • Bepul aksiya qatori (total_price = 0) → 0 chegirma oladi ✓ to'g'ri.
  • NULLIF(sub, 0) — nolga bo'lishdan himoya (butunlay bepul buyurtma).
  • GREATEST(koef, 0) — eski/import qilingan yozuvlarda discount_amount > subtotal
    bo'lib qolsa manfiy daromad chiqmasin. (Yangi yozuvlarda bunday bo'lmaydi:
    order_service `total_disc = min(..., server_subtotal)` bilan cheklaydi.)

═══ TAN NARX (o'zgarmadi, faqat izchillik uchun) ═══
`cost_expr()` — sotuv paytidagi SNAPSHOT (`OrderItem.unit_cost`) ustun, u bo'lmasa
mahsulotning bugungi `cost_price` ga tushadi. Ilgari ba'zi hisobotlar to'g'ridan
`Product.cost_price` (BUGUNGI narx) ni olardi — eski sotuvlar uchun noto'g'ri.

═══ TEGILMAGAN — ALOHIDA ISH SIFATIDA QAYD ETILDI ═══
  1) Sodiqlik balli: ball bilan to'lov `Order.discount_amount` ga TUSHMAYDI —
     u to'lov (Payment) summasini kamaytiradi, buyurtmani emas. Ball ishlatilgan
     sotuvlarda daromad hamon ozgina oshiq ko'rinadi. Mavjud xato, bu tuzatishdan
     mustaqil.
  2) Qaytarish (Return): foyda hisobotlaridan ayirilmaydi.
Ikkalasi ham SHU tuzatish doirasidan tashqarida — ataylab tegilmadi.
"""
from sqlalchemy import case, func, select

from models import Order, OrderItem, Product


def order_subtotal_subq():
    """order_id → o'sha buyurtmaning chegirmagacha subtotali (Σ items.total_price).

    Chegirmani qatorlar orasida proporsional taqsimlash uchun MAXRAJ.
    Ishlatish:
        sq = order_subtotal_subq()
        q = q.join(sq, sq.c.order_id == OrderItem.order_id)
        ... net_revenue_expr(sq) ...
    """
    return (
        select(
            OrderItem.order_id.label("order_id"),
            func.sum(OrderItem.total_price).label("sub"),
        )
        .group_by(OrderItem.order_id)
        .subquery()
    )


def discount_factor_expr(sq):
    """Buyurtmaning "chegirmadan keyin qolgan ulushi" koeffitsiyenti (0..1).

    `func.greatest` ATAYIN ishlatilmadi — u SQLite'da YO'Q (testlar SQLite'da,
    prod PostgreSQL'da ishlaydi). `case()` ikkalasida ham bir xil kompilyatsiya
    bo'ladi.
    """
    raw = 1.0 - func.coalesce(Order.discount_amount, 0.0) / func.nullif(sq.c.sub, 0.0)
    return case((raw < 0.0, 0.0), else_=func.coalesce(raw, 1.0))


def net_revenue_expr(sq):
    """Bitta OrderItem qatorining SOF tushumi (chegirma ulushi ayirilgan)."""
    return OrderItem.total_price * discount_factor_expr(sq)


def cost_expr():
    """Tan narx: sotuv paytidagi snapshot ustun, bo'lmasa mahsulotning cost_price.

    profit.py:_COST_EXPR bilan AYNAN bir xil — hisobotlar orasida raqam ajralmasin.
    DIQQAT: OrderItem.quantity ga KO'PAYTIRILMAGAN — chaqiruvchi o'zi ko'paytiradi
    (ba'zi so'rovlarda quantity boshqacha yig'iladi).
    """
    return func.coalesce(
        func.nullif(OrderItem.unit_cost, 0.0),
        Product.cost_price,
        0.0,
    )
