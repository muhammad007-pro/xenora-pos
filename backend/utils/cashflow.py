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


# ══════════════════════════════════════════════════════════════════════════════
# QAYTARILGAN SOTUV — Z-hisobotda IKKI MARTA AYIRISH xatosi (2026-10-13)
# ══════════════════════════════════════════════════════════════════════════════
# `payment_service.refund_payment` to'liq qaytarishda ASL to'lovni
# `status="refunded"` qiladi (+ manfiy yozuv). Z esa sotuvni faqat `paid` dan
# yig'ardi → sotuv orqaga qarab YO'QOLARDI, vozvrat hujjati esa
# `cash_refunds` da YANA ayirilardi:
#     300k naqd chek to'liq qaytsa: expected = start + 0 − 300k  (−300k ortiqcha)
# Qisman qaytarishda asl to'lov `paid` qoladi → xato yo'q edi (shuning uchun
# sezilmagan).
#
# QAROR — SOTUV QOLADI, QAYTARISH O'Z VAQTIDA AYIRILADI (ikkalasi emas):
#   • pul kassaga sotuv paytida KIRGAN, qaytarish paytida CHIQQAN — kassa
#     daftari vaqt bo'yicha yuradi;
#   • sotuvni yo'qotish O'TGAN smenani o'zgartiradi: kecha sotilib bugun
#     qaytgan chek kechagi Z qayta qurilganda boshqa raqam berardi;
#   • qisman qaytarish bilan bir xil qoida (u yerda sotuv allaqachon qolardi).
# Shu sabab `refunded` bo'lgan ASL (amount > 0) naqd/karta to'lov sotuvda
# qoladi. NASIYA bunga KIRMAYDI: `refunded` nasiya = qo'lda bekor qilingan
# qarz (prod: MANHATTAN #4214), u `credit_total` da avvalgidek ko'rinmaydi.

# `routers/returns._refund_money` qaytarish sababi shu prefiks bilan yoziladi
# (`refund_payment` reference: "Refund for TRX..: Vozvrat RET.."). Shu belgi
# hujjat yo'li yozuvini `POST /payments/{id}/refund` yo'lidan ajratadi —
# hujjat yo'li `cash_refunds` da `Return` orqali ALLAQACHON ayiriladi.
RETURN_REFUND_REASON_PREFIX = "Vozvrat "
_RETURN_REFUND_MARK = ": " + RETURN_REFUND_REASON_PREFIX


def refunded_sales_totals(payment_query) -> dict:
    """`refunded` holatiga o'tgan ASL naqd/karta sotuv to'lovlari (amount > 0).

    `payment_query` — chaqiruvchi smena qoidasi bilan tayyorlagan `Payment`
    so'rovi (smena buyurtmalari yoki legacy vaqt oralig'i, tenant filtri bilan).
    Qaytaradi: {"cash": float, "card": float, "order_ids": set}
    """
    from models import Payment
    rows = payment_query.filter(Payment.status == "refunded", Payment.amount > 0).all()
    cash = sum(float(p.amount or 0) for p in rows if p.method in CASH_METHODS)
    card = sum(float(p.amount or 0) for p in rows if p.method in CARD_METHODS)
    return {"cash": cash, "card": card,
            "order_ids": {p.order_id for p in rows
                          if p.order_id and p.method in CASH_METHODS + CARD_METHODS}}


def payment_path_cash_refunds(db, current_user, start, end) -> float:
    """`POST /payments/{id}/refund` (hujjatsiz) yo'li bilan qaytarilgan NAQD.

    Sotuv endi qolgani uchun bu yo'lning naqdi ham ayirilishi SHART — aks
    holda u ilgari faqat "sotuv yo'qolishi" orqali hisobga olinardi (to'liq
    qaytarishda), qisman qaytarishda esa UMUMAN ayirilmasdi.
    Vaqt — manfiy yozuv yaratilgan payt (pul shunda chiqadi), `Return` bilan
    bir xil naqsh. Hujjat yo'li yozuvlari (`: Vozvrat ` belgisi) chiqariladi.
    """
    from deps import apply_tenant_filter
    from models import Order, Payment
    # ⚠️ Tenant BUYURTMA orqali: `refund_payment` manfiy yozuvga `tenant_id`
    # qo'ymaydi (NULL) — `Payment` ustidan filtr uni butunlay yashirardi.
    q = db.query(Payment).join(Order, Order.id == Payment.order_id)
    rows = apply_tenant_filter(q, Order, current_user).filter(
        Payment.amount < 0,
        Payment.status == "refunded",
        Payment.created_at >= start,
        Payment.created_at <= end,
    ).all()
    return sum(-float(p.amount or 0) for p in rows
               if p.method in CASH_METHODS and _RETURN_REFUND_MARK not in (p.reference or ""))


def cash_refund_amount(ret) -> float:
    """Vozvratda KASSADAN HAQIQATAN chiqqan naqd (faqat `refund_method == "cash"`).

    Aralash chekda (naqd + nasiya) avval shu chekning qarzi kamayadi
    (`Return.debt_offset`) — u qism yashikdan chiqmaydi. Ilgari Z-hisobot
    `total_amount` ni to'liq ayirardi: 170k naqd + 130k nasiya chek qaytsa
    `expected_cash` 300k ga tushardi, yashikdan esa 170k chiqqan.
    `debt_offset` NULL (eski yozuv, qarzsiz chek) → avvalgidek `total_amount`.
    """
    if ret.refund_method != "cash":       # avvalgi filtr bilan bit-bitiga bir xil
        return 0.0
    return max(0.0, float(ret.total_amount or 0) - float(getattr(ret, "debt_offset", None) or 0))


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
