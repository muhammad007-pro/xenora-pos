"""MIJOZ QARZI (nasiya) — FIFO taqsimlash va qoldiq hisobining YAGONA MANBASI.

═══ NEGA BU FAYL PAYDO BO'LDI ═══
Ikki muammo bir vaqtda:

  1) `_recalc_customer_debt` IKKI NUSXADA edi — `routers/debt.py` va
     `routers/returns.py`. Ikkisi ham bir xil edi, lekin BIRINI tuzatib
     ikkinchisini unutish — bu loyihada allaqachon bo'lgan xato sinfi
     (foyda to'rt joyda to'rt xil hisoblanardi, utils/revenue.py izohi).

  2) FIFO taqsimlash FAQAT vozvrat yo'lida bor edi
     (`routers/returns.py:_refund_money`, `method == "credit"`). Mijoz
     500 000 so'm keltirib 3 ta qarzi bo'lsa, kassir uchtasiga ALOHIDA
     to'lashga majbur edi. Firmalarda (`supplier_payments`) FIFO bor,
     mijozlarda yo'q edi.

═══ ⚠️ VOZVRAT XULQI BIT-BITIGA SAQLANGAN ═══
Bu yerdagi `pick_debts_fifo` + `apply_payment_to_debts` — vozvrat yo'lidagi
AYNAN o'sha kod (tartib, dopusk `0.009`, `round(..., 2)`, `status` o'tishlari,
`min()` ulushi). `_refund_money` endi faqat SHU funksiyalarni chaqiradi.
Yangi mantiq O'YLAB TOPILMADI — ko'chirildi, chunki u prodda sinalgan.
Agar bu yerda biror shart o'zgarsa, vozvrat ham o'zgaradi: shuning uchun
`tests/test_returns_validation.py` va `tests/test_customer_return.py`
GOLDEN sifatida ushlab turiladi.

═══ AVANS (ortiqcha to'lov) ═══
Qarzdan oshgan summa MANFIY `remaining` li `CustomerDebt` qatori bo'ladi —
`recalc_customer_debt` manfiyni ham qo'shgani uchun `Customer.total_debt`
minusga tushadi, ya'ni "do'kon mijozga qarzdor". Bu naqsh vozvratdan keladi
va firma qarzidagi avans bilan izchil.
"""
from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Customer, CustomerDebt, DebtPayment

# Qarz "ochiq" deb sanaladigan holatlar — uchala yo'l (yaratish, to'lash,
# vozvrat) bitta ro'yxatdan foydalanadi.
OPEN_STATUSES = ("open", "partial")

# Pul dopuski: 1 tiyindan kichik qoldiq "yopilgan" deb hisoblanadi.
# `0.009` / `0.01` qiymatlari vozvrat yo'lidan KO'CHIRILGAN — o'zgartirilsa
# vozvratning yopish chegarasi ham siljiydi.
_EPS_LEFT   = 0.009   # bundan kichik qoldiq bilan taqsimlash to'xtaydi
_EPS_CLOSED = 0.01    # bundan kichik `remaining` → qarz to'liq yopilgan


def recalc_customer_debt(db: Session, customer_id: int) -> float:
    """`customers.total_debt` ni ochiq/qisman qarzlardan qayta hisoblaydi.

    MANFIY `remaining` (avans) ham qo'shiladi — natija minus bo'lsa do'kon
    mijozga qarzdor. `routers/debt.py` va `routers/returns.py` dagi ikki
    nusxaning O'RNIGA shu funksiya turadi.

    Qaytaradi: yangi `total_debt` (chaqiruvchi javobda ko'rsatishi uchun).

    ⚠️ `db.flush()` BIRINCHI QATORDA — TASODIFIY EMAS. Bu funksiya XOM SQL
    yig'indisi bilan o'qiydi: chaqiruvchi `remaining`/`status` ni o'zgartirgan
    bo'lsa-yu o'zgarish hali bazaga yuborilmagan bo'lsa, SUM ESKI qiymatlarni
    sanaydi va `total_debt` yolg'on qoladi. Ilgari bu faqat `autoflush=True`
    sessiyada (so'rov oqimi) ishlardi — ya'ni xato LATENT edi va
    `autoflush=False` sessiyada (skript, zaxira, test) jimgina yuzaga chiqardi.
    `routers/returns.py` buni bilib qo'lda `db.flush()` chaqirardi; endi himoya
    yagona joyda. Flush — COMMIT EMAS, tranzaksiya chaqiruvchida qoladi.
    """
    db.flush()
    total = (
        db.query(func.coalesce(func.sum(CustomerDebt.remaining), 0.0))
        .filter(
            CustomerDebt.customer_id == customer_id,
            CustomerDebt.status.in_(OPEN_STATUSES),
        )
        .scalar()
    )
    db.query(Customer).filter(Customer.id == customer_id).update({"total_debt": total})
    return float(total or 0.0)


def pick_debts_fifo(db: Session, customer_id: int, *, prefer_order_id=None) -> list:
    """Yopish uchun qarzlar ketma-ketligi: avval ANIQ bog'langan chek, keyin FIFO.

    ⚠️ Tartib `routers/returns.py:_refund_money` dan ko'chirilgan:
      1) `prefer_order_id` berilsa — SHU buyurtmaning qarzi birinchi
         (vozvratda aniq bog'lanish bor, taxmin qilmaymiz)
      2) qolgani — `created_at`, keyin `id` bo'yicha eng eskidan (FIFO)

    `if d not in debts` — bir qator ikki marta tushmasin. Bitta sessiya
    ichida ORM identity map bir xil obyektni qaytaradi, shuning uchun bu
    solishtirish ishonchli (vozvrat yo'li ham aynan shunga tayanadi).
    """
    q = db.query(CustomerDebt).filter(
        CustomerDebt.customer_id == customer_id,
        CustomerDebt.status.in_(OPEN_STATUSES),
    )
    debts = []
    if prefer_order_id:
        debts = q.filter(CustomerDebt.order_id == prefer_order_id).all()
    debts += [d for d in q.order_by(CustomerDebt.created_at, CustomerDebt.id).all()
              if d not in debts]
    return debts


def apply_payment_to_debts(debts: list, amount: float) -> tuple:
    """`amount` ni `debts` ketma-ketligiga FIFO bo'yicha yopadi (YOZADI).

    Qaytaradi: `(allocations, qoldiq)`
      allocations — [{"debt_id", "amount", "remaining_after", "status"}, ...]
                    faqat HAQIQATAN pul tushgan qarzlar
      qoldiq      — taqsimlanmagan ortiqcha summa (avans uchun)

    ⚠️ Qator holatini o'zgartiradi, lekin COMMIT QILMAYDI va `DebtPayment`
    yozmaydi — ularni chaqiruvchi hal qiladi (vozvratda `DebtPayment` YO'Q,
    chunki pul kelmagan; qarz to'lovida esa BOR).
    """
    qoldiq = float(amount or 0)
    allocations = []
    for d in debts:
        if qoldiq <= _EPS_LEFT:
            break
        ulush = min(qoldiq, float(d.remaining or 0))
        if ulush <= 0:
            continue                      # avans qatori (manfiy remaining) — o'tkazib yuboriladi
        d.remaining    = round(float(d.remaining) - ulush, 2)
        d.paid_amount  = round(float(d.paid_amount or 0) + ulush, 2)
        if d.remaining < _EPS_CLOSED:
            d.remaining = 0.0
            d.status    = "paid"
        elif d.paid_amount > 0:
            d.status    = "partial"
        qoldiq -= ulush
        allocations.append({
            "debt_id":         d.id,
            "amount":          round(ulush, 2),
            "remaining_after": d.remaining,
            "status":          d.status,
        })
    return allocations, qoldiq


def preview_allocation(db: Session, customer_id: int, amount: float,
                       *, prefer_order_id=None) -> dict:
    """Taqsimlashni HECH NARSA YOZMASDAN hisoblaydi (UI oldindan ko'rsatish uchun).

    `apply_payment_to_debts` bilan BIR XIL tartib va bir xil dopusk — ya'ni
    "500 000 → #5 ga 240 000, #7 ga 260 000" yozuvi haqiqatan sodir bo'ladigan
    narsani ko'rsatadi. Frontendda ikkinchi nusxa hisob YOZILMASIN.
    """
    debts  = pick_debts_fifo(db, customer_id, prefer_order_id=prefer_order_id)
    qoldiq = float(amount or 0)
    rows   = []
    for d in debts:
        if qoldiq <= _EPS_LEFT:
            break
        ulush = min(qoldiq, float(d.remaining or 0))
        if ulush <= 0:
            continue
        _after = round(float(d.remaining) - ulush, 2)
        if _after < _EPS_CLOSED:
            _after = 0.0
        rows.append({
            "debt_id":         d.id,
            "order_id":        d.order_id,
            "debt_remaining":  round(float(d.remaining or 0), 2),
            "amount":          round(ulush, 2),
            "remaining_after": _after,
            "closes":          _after == 0.0,
            "created_at":      d.created_at,
            "due_date":        d.due_date,
        })
        qoldiq -= ulush
    return {
        "allocations": rows,
        "applied":     round(float(amount or 0) - qoldiq, 2),
        "advance":     round(qoldiq, 2) if qoldiq > _EPS_LEFT else 0.0,
        "debts_count": len(rows),
    }


def add_advance(db: Session, *, tenant_id, branch_id, customer_id, order_id,
                amount: float, notes: str, user_id=None) -> CustomerDebt:
    """Qarzdan OSHGAN summa — manfiy qoldiqli qator (AVANS). Naqd qaytarilmaydi.

    ⚠️ `remaining` MANFIY: `recalc_customer_debt` uni ham qo'shadi, shuning
    uchun `total_debt` minusga tushadi = do'kon mijozga qarzdor. Vozvrat
    yo'lidagi avans naqshi aynan shu (firma qarzi bilan ham izchil).
    """
    adv = CustomerDebt(
        tenant_id=tenant_id,
        branch_id=branch_id,
        customer_id=customer_id,
        order_id=order_id,
        amount=-amount,
        paid_amount=0.0,
        remaining=-amount,
        status="open",
        notes=notes,
        user_id=user_id,
    )
    db.add(adv)
    return adv


def record_debt_payment(db: Session, *, debt_id: int, amount: float,
                        payment_method: str, notes: str = None,
                        user_id=None) -> DebtPayment:
    """`DebtPayment` yozuvi — KASSAGA TUSHGAN PULNING izi.

    ⚠️ BU YOZUV PUL YO'LIDA MAJBURIY: `utils/cashflow.debt_payments_totals`
    aynan `DebtPayment` dan o'qiydi va `expected_cash` ni shundan to'ldiradi
    (`routers/shift.py`). Yozuv qoldirilsa kassadagi haqiqiy naqd "ortiqcha"
    bo'lib ko'rinadi va kassir asossiz ayblanadi — 2026-08-19 da aynan shu
    xato bo'lgan (`utils/cashflow.py` fayl boshidagi izoh).

    Shu sabab qoida: QABUL QILINGAN SUMMA = Σ(`DebtPayment.amount`), avans
    qismi ham qo'shilgan holda.
    """
    p = DebtPayment(
        debt_id=debt_id,
        amount=round(float(amount), 2),
        payment_method=payment_method,
        notes=notes,
        user_id=user_id,
    )
    db.add(p)
    return p
