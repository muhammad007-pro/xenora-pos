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


def refunded_sale_payments(payment_query) -> list:
    """`refunded` holatiga o'tgan ASL naqd/karta sotuv to'lovlari (amount > 0).

    `payment_query` — chaqiruvchi smena qoidasi bilan tayyorlagan `Payment`
    so'rovi (smena buyurtmalari yoki legacy vaqt oralig'i, tenant filtri bilan).
    Nasiya va boshqa usullar KIRMAYDI (yuqoridagi izoh).
    """
    from models import Payment
    rows = payment_query.filter(Payment.status == "refunded", Payment.amount > 0).all()
    return [p for p in rows if p.method in CASH_METHODS + CARD_METHODS]


def sale_tenders(payment_query) -> list:
    """SOTUV TENDERLARI — Z-hisobot (`routers/shift._shift_totals`) va dashboard
    savdo kartasi (`routers/analytics.get_summary`) uchun BITTA qoida:
      • `paid` to'lovlar + NASIYA (`credit`, pending) — tovar sotilgan;
      • tugallanmagan Click/Payme (pending) sotuv EMAS;
      • to'liq qaytarilgan ASL naqd/karta to'lov sotuvda QOLADI
        (`refunded_sale_payments` izohi) — qaytarish alohida ayiriladi.
    `payment_query` — chaqiruvchining `Payment` so'rovi (status filtrisiz).
    """
    from models import Payment
    live = payment_query.filter(Payment.status.in_(("paid", "pending"))).all()

    # PaymentStatus — str-enum; eski yozuvlarda oddiy matn bo'lishi mumkin.
    def _paid(p):
        return str(getattr(p.status, "value", p.status)) == "paid"

    return [p for p in live if _paid(p) or p.method == "credit"] + refunded_sale_payments(payment_query)


def payment_path_cash_refunds(db, current_user, start, end) -> float:
    """`POST /payments/{id}/refund` (hujjatsiz) yo'li bilan qaytarilgan NAQD."""
    return payment_path_refunds(db, current_user, start, end, CASH_METHODS)


def payment_path_refunds(db, current_user, start, end, methods) -> float:
    """`POST /payments/{id}/refund` (hujjatsiz) yo'li bilan qaytarilgan pul (`methods` usulida).

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
               if p.method in methods and _RETURN_REFUND_MARK not in (p.reference or ""))


def card_refund_amount(ret) -> float:
    """Vozvratda KARTA orqali qaytarilgan pul — `cash_refund_amount` bilan bir
    qoida (aralash chekda qarz qismi `debt_offset` chiqmaydi). Yashikka
    tegmaydi, faqat "Kassaga tushgan" (pul oqimi) dan ayiriladi."""
    if ret.refund_method != "card":
        return 0.0
    return max(0.0, float(ret.total_amount or 0) - float(getattr(ret, "debt_offset", None) or 0))


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


# ══════════════════════════════════════════════════════════════════════════════
# DAVR TENDERLARI — /reports/sales, /analytics/summary (by_payment_method) va
# AnalyticsService.get_period_data uchun YAGONA QOIDA (2026-10-21)
# ══════════════════════════════════════════════════════════════════════════════
# MUAMMO (MANHATTAN shikoyati): uchala joy `Payment.status == "paid"` dan
# o'qirdi. To'liq vozvratda asl to'lov `refunded` bo'ladi → sotuv O'TGAN
# kundan yo'qolardi (16.10: 6 865 000 → 5 965 000), bugungi manfiy yozuv ham
# `refunded` → vozvrat HECH QAYSI kunda ko'rinmasdi. Qisman vozvratda asl
# to'lov `paid` qolardi → vozvrat umuman ko'rinmasdi.
#
# QOIDA — Z-hisobot bilan bir xil (`sale_tenders` izohi):
#   • sotuv o'z kunida qoladi (`sale_tenders`: refunded asl to'lov ham);
#   • qaytarish QAYTARILGAN kunda ayiriladi: Return hujjati (`approved`,
#     `return_date_expr` — Moliya/Z bilan bir sana) + hujjatsiz
#     `POST /payments/{id}/refund` yo'li (manfiy yozuv vaqti).
# Qaysi qism pul (naqd/karta) — `cash_refund_amount`/`card_refund_amount`
# (Z bilan bir formula); qolgani (nasiya qarzidan yopilgan, eski `exchange`)
# pul EMAS: faqat sotuv hisobotida ko'rinadi, "kassaga tushgan"dan ayirilmaydi.

def return_tender_rows(db, current_user, start, end, branch_id=None) -> list:
    """[start, end] da QAYTARILGAN summalar, usul kesimida.

    Har qator: SimpleNamespace(at, method, amount, money). `money=False` —
    kassadan pul chiqmagan qism (nasiya qarzi kamaygan va h.k.).
    """
    from types import SimpleNamespace
    from deps import apply_tenant_filter
    from models import Order, Payment, Return
    from utils.revenue import RETURN_COUNTED_STATUSES, return_date_expr

    dt = return_date_expr()
    q = db.query(Return, dt.label("at")).filter(
        Return.status.in_(RETURN_COUNTED_STATUSES), dt >= start, dt <= end,
    )
    if current_user is not None:
        q = apply_tenant_filter(q, Return, current_user)
    if branch_id:
        q = q.filter(Return.branch_id == branch_id)

    rows = []
    for ret, at in q.all():
        total = float(ret.total_amount or 0)
        cash, card = cash_refund_amount(ret), card_refund_amount(ret)
        if cash:
            rows.append(SimpleNamespace(at=at, method="cash", amount=cash, money=True))
        if card:
            rows.append(SimpleNamespace(at=at, method="card", amount=card, money=True))
        rest = round(total - cash - card, 2)
        if rest > 0.009:
            method = "credit" if (ret.refund_method == "credit" or ret.debt_offset) else (ret.refund_method or "other")
            rows.append(SimpleNamespace(at=at, method=method, amount=rest, money=False))

    # Hujjatsiz yo'l — `payment_path_refunds` bilan bir qoida (tenant buyurtma orqali).
    pq = db.query(Payment).join(Order, Order.id == Payment.order_id).filter(
        Payment.amount < 0, Payment.status == "refunded",
        Payment.created_at >= start, Payment.created_at <= end,
    )
    if current_user is not None:
        pq = apply_tenant_filter(pq, Order, current_user)
    if branch_id:
        pq = pq.filter(Order.branch_id == branch_id)
    for p in pq.all():
        method = str(getattr(p.method, "value", p.method))
        if method in CASH_METHODS + CARD_METHODS and _RETURN_REFUND_MARK not in (p.reference or ""):
            rows.append(SimpleNamespace(at=p.created_at, method=method, amount=-float(p.amount or 0), money=True))
    return rows


def period_tenders(db, current_user, payment_query, start, end, *, money_only=False, branch_id=None) -> dict:
    """Davr tenderlari: {"sales": [Payment], "refunds": [return_tender_rows qatori]}.

    `payment_query` — chaqiruvchining `Payment` so'rovi (davr oynasi + tenant,
    status filtrisiz). `start`/`end` — qaytarish oralig'i.
    `money_only=True` — "kassaga tushgan pul": nasiya tenderi (pending) va
    pul bo'lmagan qaytarish qismi chiqariladi (avvalgi `status == "paid"` ma'nosi).
    """
    sales = sale_tenders(payment_query)
    refunds = return_tender_rows(db, current_user, start, end, branch_id=branch_id)
    if money_only:
        sales = [p for p in sales if str(getattr(p.status, "value", p.status)) != "pending"]
        refunds = [r for r in refunds if r.money]
    return {"sales": sales, "refunds": refunds}


def tenders_by_method(t: dict) -> dict:
    """`period_tenders` natijasi → {usul: {"sales", "count", "refunds", "net"}}
    (tartib: avval sotuv usullari, keyin faqat qaytarishi bor usullar)."""
    out: dict = {}
    for p in t["sales"]:
        m = out.setdefault(str(getattr(p.method, "value", p.method)),
                           {"sales": 0.0, "count": 0, "refunds": 0.0})
        m["sales"] += float(p.amount or 0)
        m["count"] += 1
    for r in t["refunds"]:
        out.setdefault(r.method, {"sales": 0.0, "count": 0, "refunds": 0.0})["refunds"] += r.amount
    for m in out.values():
        m["net"] = m["sales"] - m["refunds"]
    return out


def expected_cash(starting_cash, cash_sales, cash_refunds, debt_cash,
                  withdrawals=0.0, deposits=0.0) -> float:
    """Smena oxirida kassa yashigida BO'LISHI KERAK bo'lgan naqd.

        boshlang'ich + naqd sotuv − naqd qaytarish + naqd qarz to'lovlari
                     − olingan (inkassatsiya) + qo'shilgan (razmen)

    Karta/online (sotuv ham, qarz to'lovi ham) bu yerga KIRMAYDI — ular kassa
    yashigiga tushmaydi. Nasiya SOTUVI ham kirmaydi (pul kelmagan).
    `withdrawals`/`deposits` — `cash_movements` (sukut 0 → avvalgi formula
    bit-bitiga).
    """
    return (
        float(starting_cash or 0)
        + float(cash_sales or 0)
        - float(cash_refunds or 0)
        + float(debt_cash or 0)
        - float(withdrawals or 0)
        + float(deposits or 0)
    )


def cash_in_summary(cash_sales, card_sales, debt_pay, cash_refunds, card_refunds=0.0) -> dict:
    """"KASSAGA TUSHGAN" — pul oqimi (sotuv EMAS). Hisob shu yerda, ma'lumot
    chaqiruvchida (Z: `_shift_totals` allaqachon yig'gan qiymatlar).

        naqd sotuv + karta sotuv + qarz to'lovi (naqd+karta) − qaytarish (naqd+karta)

    Nasiya SOTUVI kirmaydi (pul kelmagan), boshlang'ich naqd va inkassatsiya
    ham kirmaydi (ular tushum emas, yashik ichidagi harakat).
    """
    cash_refunds = float(cash_refunds or 0)
    card_refunds = float(card_refunds or 0)
    debt_cash, debt_card = float(debt_pay.get("cash") or 0), float(debt_pay.get("card") or 0)
    return {
        "cash_sales":    round(float(cash_sales or 0), 2),
        "card_sales":    round(float(card_sales or 0), 2),
        "cash_refunds":  round(cash_refunds, 2),
        "card_refunds":  round(card_refunds, 2),
        "debt_cash":     round(debt_cash, 2),
        "debt_card":     round(debt_card, 2),
        "debt_total":    round(debt_cash + debt_card, 2),
        "debt_count":    debt_pay.get("count", 0),
        "total_cash_in": round(
            float(cash_sales or 0) + float(card_sales or 0)
            + debt_cash + debt_card - cash_refunds - card_refunds, 2
        ),
    }


def cash_in_totals(db, current_user, start, end, cash_sales, card_sales, cash_refunds,
                   card_refunds=0.0) -> dict:
    """"Kassaga tushgan pul" ko'rsatkichi — hisobot/dashboard uchun to'liq manzara.

    Sotuv (accrual) ko'rsatkichi bilan ATAYLAB aralashtirilmaydi: bu "bugun
    qancha PUL keldi" degan savolga javob, "bugun qancha SOTDIK" ga emas.
    """
    debts = debt_payments_totals(db, current_user, start, end)
    return cash_in_summary(cash_sales, card_sales, debts, cash_refunds, card_refunds)
