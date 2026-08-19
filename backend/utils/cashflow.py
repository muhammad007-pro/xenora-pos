"""KASSAGA TUSHGAN PUL (cash flow) — yagona manba.

═══ NEGA ALOHIDA FAYL (utils/revenue.py ga QO'SHILMADI) ═══
Tizimda IKKI XIL o'lchov bor va ularni aralashtirish — pul hisobidagi eng
qimmat xato turi:

  1) SOTUV (accrual) — tovar chiqqan KUNDA daromad. Manba: `utils/revenue.py`
     (OrderItem sof tushumi). Nasiyaga berilgan tovar ham shu yerda, chunki
     sotuv sodir bo'lgan. Qarz keyin to'lansa — YANGI sotuv emas.
  2) KASSAGA TUSHGAN PUL (cash flow) — pul KELGAN KUNDA. Manba: shu fayl.
     Nasiya sotuvi bu yerga sotuv kunida KIRMAYDI (pul kelmagan), lekin qarz
     to'langan kunda KIRADI.

Bir o'lchovni ikkinchisiga qo'shish = ikki marta hisoblash. Aynan shu xato
2026-08 auditida topilgan edi (vozvrat foydadan ayirilmasdi) — takrorlamaymiz.
Shuning uchun `revenue.py` GA TEGILMAYDI, cash flow shu yerda alohida turadi.

═══ MUAMMO (2026-08-19) ═══
Mijoz nasiya qarzini to'laganda `debt_payments` ga yozuv tushardi, LEKIN:
  • `Payment` yozuvi yaratilmasdi (`routers/debt.py` faqat DebtPayment yozadi)
  • demak Z-hisobotdagi `cash_sales` ga kirmasdi
  • demak `expected_cash` kam chiqardi va kassadagi ortiqcha naqd "ortiqcha"
    (shortage > 0) bo'lib ko'rinardi — kassir asossiz ayblanardi
Ya'ni bu "ko'rinmaydi" emas, kassa farqini FAOL ravishda buzadigan xato edi.

═══ TENANT IZOLYATSIYASI — MAJBURIY JOIN ═══
`DebtPayment` da `tenant_id` ustuni YO'Q (`models.py:1296`). Tenant faqat
`debt_id -> CustomerDebt.tenant_id` orqali aniqlanadi. Shu sabab bu yerdagi
HAR BIR so'rov `join(CustomerDebt)` + `apply_tenant_filter(..., CustomerDebt)`
bilan ketadi. To'g'ridan-to'g'ri `db.query(DebtPayment)` YOZMANG — u BOSHQA
do'konning pulini hisobotga qo'shib yuboradi.

`shift_id` ham yo'q, shuning uchun smenaga bog'lash VAQT ORALIG'I bilan
bo'ladi — bu loyihada allaqachon ishlatiladigan naqsh (`Return` ham Z-hisobotda
shunday olinadi, `routers/shift.py`).
"""
from models import CustomerDebt, DebtPayment

# Naqd deb hisoblanadigan usul(lar) — kassa yashigiga JISMONAN tushadigan pul.
# Faqat shular `expected_cash` ga qo'shiladi.
CASH_METHODS = ("cash",)
# Karta/online — pul keladi, lekin kassa yashigiga EMAS (terminal/hisob raqam).
CARD_METHODS = ("card", "click", "payme")


def debt_payments_totals(db, current_user, start, end) -> dict:
    """Berilgan vaqt oralig'ida TO'LANGAN nasiya qarzlari.

    Vaqt — `DebtPayment.created_at`, ya'ni TO'LOV kuni (sotuv kuni EMAS).
    Pul aynan shunda keladi; sotuv esa o'z kunida accrual hisobotda turadi.

    Qaytaradi:
        {"cash": float, "card": float, "total": float, "count": int}

    `cash` — `expected_cash` ga qo'shiladigan yagona qism.
    """
    from deps import apply_tenant_filter          # aylanma import bo'lmasin

    q = (
        db.query(DebtPayment)
        .join(CustomerDebt, CustomerDebt.id == DebtPayment.debt_id)
        .filter(
            DebtPayment.created_at >= start,
            DebtPayment.created_at <= end,
        )
    )
    # ⚠️ Tenant filtri CustomerDebt ustidan — DebtPayment da tenant_id yo'q.
    q = apply_tenant_filter(q, CustomerDebt, current_user)

    rows = q.all()
    cash = sum(float(p.amount or 0) for p in rows if (p.payment_method or "cash") in CASH_METHODS)
    card = sum(float(p.amount or 0) for p in rows if (p.payment_method or "") in CARD_METHODS)
    return {
        "cash":  round(cash, 2),
        "card":  round(card, 2),
        "total": round(cash + card, 2),
        "count": len(rows),
    }


def expected_cash(starting_cash, cash_sales, cash_refunds, debt_cash) -> float:
    """Smena oxirida kassa yashigida BO'LISHI KERAK bo'lgan naqd.

        boshlang'ich + naqd sotuv − naqd qaytarish + naqd qarz to'lovlari

    Karta/online (sotuv ham, qarz to'lovi ham) bu yerga KIRMAYDI — ular kassa
    yashigiga tushmaydi. Nasiya SOTUVI ham kirmaydi (pul kelmagan).
    """
    return (
        float(starting_cash or 0)
        + float(cash_sales or 0)
        - float(cash_refunds or 0)
        + float(debt_cash or 0)
    )


def cash_in_totals(db, current_user, start, end, cash_sales, card_sales, cash_refunds) -> dict:
    """"Kassaga tushgan pul" ko'rsatkichi — hisobot/dashboard uchun to'liq manzara.

    Sotuv (accrual) ko'rsatkichi bilan ATAYLAB aralashtirilmaydi: bu "bugun
    qancha PUL keldi" degan savolga javob, "bugun qancha SOTDIK" ga emas.
    """
    debts = debt_payments_totals(db, current_user, start, end)
    return {
        "cash_sales":    round(float(cash_sales or 0), 2),
        "card_sales":    round(float(card_sales or 0), 2),
        "cash_refunds":  round(float(cash_refunds or 0), 2),
        "debt_cash":     debts["cash"],
        "debt_card":     debts["card"],
        "debt_total":    debts["total"],
        "debt_count":    debts["count"],
        "total_cash_in": round(
            float(cash_sales or 0) + float(card_sales or 0)
            - float(cash_refunds or 0) + debts["total"], 2
        ),
    }
