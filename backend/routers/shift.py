from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func as sqlfunc
from datetime import datetime, timedelta
from typing import Optional

from database import get_db
from models import Shift, User, Order, Payment, OrderItem, CashRegister, Return, Cafe, CashMovement
from schemas import ShiftCreate, ShiftUpdate, ShiftInDB, MessageResponse
from deps import (
    resolve_tenant_id, get_current_user, get_current_active_user,
    has_permission, apply_tenant_filter, user_has_permission,
)
from core.feature_flags import Feature, is_feature_enabled
from services import printer_service
from core.tenant_config import get_tenant_config  # BOSQICH 40 (3c): printer tenant-scoped
from core.audit import log_audit  # xodim harakatlarini yozish (audit)
# ⚠️ VAQT: naive `datetime.now()` server UTC'sini beradi va `shifts` ustunlari
# zona belgisiSIZ edi -> ekranda 5 soat orqada ko'rinardi (migratsiya
# c9f2a71d3e84). Endi yozishda `utc_now()` (aware UTC — SQLite'da ham to'g'ri),
# ko'rsatishda `to_local()`.
from core.timeutils import to_local, to_utc, utc_now
# Kassaga tushgan pul — YAGONA manba. Nasiya qarzi to'lovlari `Payment` yozuvi
# yaratmaydi, shuning uchun ular shu yerdan olinadi (tenant izolyatsiyasi
# CustomerDebt join'i orqali ta'minlanadi).
from utils.cashflow import (
    debt_payments_totals, expected_cash as _expected_cash, cash_refund_amount as _cash_refund_amount,
    refunded_sale_payments, payment_path_cash_refunds, CASH_METHODS, CARD_METHODS,
    card_refund_amount as _card_refund_amount, payment_path_refunds, cash_in_summary,
)

router = APIRouter()


def _shift_payment_query(db, current_user, legacy_fallback, order_ids, start, end):
    """Smenaning `Payment` so'rovi (status filtrisiz) — smena buyurtmalari, eski
    smenalarda vaqt oralig'i. Ikkala Z yo'li (yopish va chekni qayta qurish) shu
    bitta qoidadan foydalanadi. Buyurtma yo'q bo'lsa — None."""
    if legacy_fallback:
        return apply_tenant_filter(db.query(Payment), Payment, current_user).filter(
            Payment.created_at >= start, Payment.created_at <= end,
        )
    if order_ids:
        return apply_tenant_filter(db.query(Payment), Payment, current_user).filter(
            Payment.order_id.in_(order_ids),
        )
    return None


def _shift_totals(db, current_user, shift: Shift, end) -> dict:
    """SMENA PUL HISOBINING YAGONA MANBASI — close_shift, print-z va /report.

    ═══ NEGA (2026-10-13) ═══
    Uch joy uch xil hisoblardi va ajralib ketgan edi:
      • print-z faqat `paid` olardi → NASIYA (pending) Z chekida doim 0
        (XOZMAG'da nasiya bor, chekda yo'q edi), close_shift esa to'g'ri;
      • /report usullar taqsimoti to'liq qaytarilgan sotuvni tashlab yuborardi
        va "Yakuniy kassa" = start + naqd edi (qaytarish va qarz to'lovisiz) —
        Z'dagi `expected_cash` bilan mos emas edi.
    Endi uchalasi SHU funksiyani chaqiradi; qoida bir joyda o'zgaradi.

    QOIDALAR:
      • to'lovlar — smena buyurtmalaridan (legacy: vaqt oralig'i);
      • sotuv tenderi = `paid` + NASIYA (pending); tugallanmagan Click/Payme
        (pending) sotuv emas;
      • to'liq qaytarilgan ASL naqd/karta to'lov sotuvda QOLADI, qaytarish
        `cash_refunds` da bir marta ayiriladi (utils/cashflow izohi);
      • qaytarish va qarz to'lovlari — vaqt oralig'i [start, end].
    """
    start = to_utc(shift.start_time)
    end   = to_utc(end)

    orders = apply_tenant_filter(db.query(Order), Order, current_user).filter(
        Order.shift_id == shift.id
    ).all()
    legacy_fallback = not orders
    if legacy_fallback:
        # Orqaga moslik: shift_id biriktirilmagan eski smenalar — vaqt oralig'i bilan
        orders = apply_tenant_filter(db.query(Order), Order, current_user).filter(
            Order.created_at >= start, Order.created_at <= end,
        ).all()
    order_ids = [o.id for o in orders]

    pay_q = _shift_payment_query(db, current_user, legacy_fallback, order_ids, start, end)
    if pay_q is not None:
        live = pay_q.filter(Payment.status.in_(("paid", "pending"))).all()
        refunded = refunded_sale_payments(pay_q)
    else:
        live, refunded = [], []

    # PaymentStatus — str-enum; eski yozuvlarda oddiy matn bo'lishi mumkin.
    def _paid(p):
        return str(getattr(p.status, "value", p.status)) == "paid"

    tenders = [p for p in live if _paid(p) or p.method == "credit"]
    sales = tenders + refunded           # sotuv tenderlari (qaytarilgani ham)

    cash_sales   = sum(p.amount for p in sales if p.method in CASH_METHODS)
    card_sales   = sum(p.amount for p in sales if p.method in CARD_METHODS)
    # Nasiya — pul kelmagan, lekin TOVAR SOTILGAN: alohida qator, kassaga KIRMAYDI
    credit_total = sum(p.amount for p in sales if p.method == "credit")

    by_method: dict = {}
    for p in sales:
        k = str(getattr(p.method, "value", p.method))
        by_method[k] = by_method.get(k, 0) + p.amount

    paid_order_ids = {p.order_id for p in sales if p.order_id}
    discount_total = sum((o.discount_amount or 0) for o in orders if o.id in paid_order_ids)

    returns = _returns_in_range(db, current_user, start, end)
    returns_total = sum(r.total_amount or 0 for r in returns)
    cash_refunds  = (sum(_cash_refund_amount(r) for r in returns)   # aralash chek: qarz qismi chiqmaydi
                     + payment_path_cash_refunds(db, current_user, start, end))
    # Karta qaytarish — yashikka TEGMAYDI, faqat "Kassaga tushgan" dan ayiriladi
    card_refunds  = (sum(_card_refund_amount(r) for r in returns)
                     + payment_path_refunds(db, current_user, start, end, CARD_METHODS))

    # Nasiya qarzi to'lovlari — pul KASSAGA tushadi (Payment yozuvi yo'q)
    debt_pay = debt_payments_totals(db, current_user, start, end)

    # Inkassatsiya / razmen — smenaga `shift_id` bilan QATTIQ bog'langan
    moves = _cash_movements(db, shift)
    withdrawals = sum(m.amount or 0 for m in moves if m.kind == "withdrawal")
    deposits    = sum(m.amount or 0 for m in moves if m.kind == "deposit")

    expected_cash = _expected_cash(shift.starting_cash, cash_sales, cash_refunds, debt_pay["cash"],
                                   withdrawals, deposits)

    return {
        "start": start, "end": end, "orders": orders,
        "cash_sales": cash_sales, "card_sales": card_sales, "credit_total": credit_total,
        "total_sales": cash_sales + card_sales + credit_total,
        "by_method": by_method,
        "paid_order_ids": paid_order_ids, "sales_count": len(paid_order_ids),
        "discount_total": discount_total,
        "returns_total": returns_total, "cash_refunds": cash_refunds, "card_refunds": card_refunds,
        "debt_pay": debt_pay, "expected_cash": expected_cash,
        "withdrawals": withdrawals, "deposits": deposits, "movements": moves,
        "cash_in": cash_in_summary(cash_sales, card_sales, debt_pay, cash_refunds, card_refunds),
    }


def _cash_movements(db, shift: Shift) -> list:
    """Smenaning inkassatsiya/razmen yozuvlari (vaqt tartibida). Tenant smena
    orqali kafolatlangan — `shift` allaqachon tenant filtri bilan olingan."""
    return (db.query(CashMovement)
            .filter(CashMovement.shift_id == shift.id)
            .order_by(CashMovement.created_at, CashMovement.id)
            .all())


def _z_money_fields(t: dict) -> dict:
    """Z-hisobotning PUL bloki (variant A) — close / print-z / report / x-report
    hammasi shu bitta shakldan. SAVDO bloki (naqd/karta/nasiya → jami savdo)
    eski maydonlarda qoladi (`total_sales` GOLDEN)."""
    ci = t["cash_in"]
    return {
        "card_refunds":     round(t["card_refunds"], 0),
        "money_refunds":    round(t["cash_refunds"] + t["card_refunds"], 0),
        "cash_in_total":    round(ci["total_cash_in"], 0),
        "withdrawals":      round(t["withdrawals"], 0),
        "deposits":         round(t["deposits"], 0),
        "cash_movements":   [_movement_out(m) for m in t["movements"]],
    }


def _movement_out(m) -> dict:
    return {
        "id": m.id, "kind": m.kind, "amount": m.amount, "reason": m.reason,
        "user_id": m.user_id,
        "created_at": to_utc(m.created_at).isoformat() if m.created_at else None,
    }


def _returns_in_range(db, current_user, start, end):
    """Smena/Z-hisobot uchun vozvratlar — FOYDA HISOBOTI BILAN BIR XIL QOIDA.

    ═══ NEGA O'ZGARTIRILDI (2026-10-01) ═══
    Ilgari bu yerda `Return.status != "rejected"` turardi, ya'ni TASDIQLANMAGAN
    (`pending`) vozvrat ham sanalardi. Natijada kassadan pul CHIQMAGAN bo'lsa
    ham `expected_cash` kamayardi va yashikdagi haqiqiy naqd "ortiqcha" bo'lib
    ko'rinardi — kassir asossiz ayblanardi (`utils/cashflow.py` da tasvirlangan
    xato sinfining aynan o'zi).

    Ikki qoida bir vaqtda to'g'rilanadi — ikkinchisisiz birinchisi yangi teshik
    ochadi:
      1) FAQAT `approved` — `utils/revenue.py:RETURN_COUNTED_STATUSES` bilan bir xil.
      2) VAQT — `approved_at` (fallback `created_at`), `utils/revenue.py:
         return_date_expr()` bilan bir xil. Pul aynan TASDIQLANGANDA chiqadi.
         Faqat (1) qilinsa: kecha yaratilgan, bugun tasdiqlangan vozvrat
         kechaning (yopilgan) hisobotiga tushib, bugungi yashikdan pul
         sababsiz kam chiqardi.
    Bir smena ichida yaratilib tasdiqlangan vozvratda (odatiy hol) natija
    O'ZGARMAYDI: `approved_at` ~ `created_at`.
    """
    from utils.revenue import RETURN_COUNTED_STATUSES, return_date_expr

    dt = return_date_expr()
    q = db.query(Return).filter(
        Return.status.in_(RETURN_COUNTED_STATUSES),
        dt >= start,
        dt <= end,
    )
    return apply_tenant_filter(q, Return, current_user).all()


def _fmt_local(dt):
    """Ko'rsatish uchun vaqt — TENANT zonasida (Toshkent), "dd.mm.yyyy HH:MM".

    ⚠️ To'g'ridan `dt.strftime(...)` QILINMAYDI: `strftime` zona haqida hech
    narsa bilmaydi va aware UTC qiymatdan UTC DEVOR VAQTINI chiqaradi. Chek va
    Z-hisobotda aynan shu sabab 5 soat orqada ko'rinardi — satr serverda
    tayyorlangani uchun frontend uni tuzata ham olmasdi.
    """
    return to_local(dt).strftime("%d.%m.%Y %H:%M") if dt else None

@router.get("/", response_model=list[ShiftInDB])
async def get_shifts(
    user_id: Optional[int] = None,
    date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Smenalarni olish"""
    query = db.query(Shift)
    # BOSQICH 1.5: tenant bo'yicha cheklash
    query = apply_tenant_filter(query, Shift, current_user)

    if user_id:
        query = query.filter(Shift.user_id == user_id)
    
    if date:
        # Toshkent kuni (2026-10): naive sana UTC deb solishtirilardi (kun 05:00
        # dan boshlanardi) va 23:59:59 dan keyingi oxirgi soniya tushib qolardi.
        from core.timeutils import day_bounds
        d_start, d_end = day_bounds(datetime.strptime(date, "%Y-%m-%d").date())
        query = query.filter(
            Shift.start_time >= d_start,
            Shift.start_time < d_end,
        )
    
    shifts = query.order_by(Shift.start_time.desc()).all()
    return [ShiftInDB.model_validate(s) for s in shifts]

@router.post("/", response_model=ShiftInDB)
async def create_shift(
    shift_data: ShiftCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Yangi smena ochish.

    cash_register flagi yoqilgan bo'lsa — smena kassaga (register_id) bog'lanadi
    va bir kassada bir vaqtda bitta faol smena bo'ladi. Flag o'chiq (register_id
    yuborilmagan) bo'lsa — eski oddiy smena ishlaydi (orqaga moslik).
    """
    tenant_id = resolve_tenant_id(db, current_user)

    # ── SMENA EGASI — KLIENTGA ISHONILMAYDI ───────────────────────────────────
    # `ShiftCreate.user_id` klient tanasidan keladi va ILGARI umuman
    # tekshirilmasdi: istalgan xodim istalgan `user_id` yozib, BOSHQA kassir
    # nomiga smena ocha olardi. Bu shunchaki noto'g'ri yozuv emas — sotuv aynan
    # shu bog'lanish bo'yicha taqsimlanadi (`order_service`:
    # `Shift.user_id == waiter_id`), ya'ni pul boshqa odamning Z-hisobotiga
    # tushardi va kamomad ham o'shanga yozilardi.
    #
    # Endi smena HAR DOIM so'rov yuborgan xodimga ochiladi. Klient boshqa
    # `user_id` yuborsa — jimgina almashtirilmaydi, ANIQ xato qaytariladi
    # (aks holda admin panelidagi xodim tanlash ro'yxati "ishlayotgandek"
    # ko'rinib, aslida noto'g'ri egali smena yaratardi).
    #
    # Admin boshqa xodimga smena ochishi HOZIRCHA yo'q. Kerak bo'lsa alohida,
    # aniq niyatli endpoint bilan qilinadi (`manage_shifts` + audit bilan).
    if shift_data.user_id and shift_data.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Smena faqat o'zingizga ochiladi. Boshqa xodim smenani o'zi ochishi kerak.",
        )
    owner_id = current_user.id

    # Faol smena mavjudligini tekshirish (foydalanuvchi bo'yicha — mavjud xatti-harakat)
    active_shift = db.query(Shift).filter(
        Shift.user_id == owner_id,
        Shift.end_time.is_(None)
    ).first()

    if active_shift:
        raise HTTPException(status_code=400, detail="Bu foydalanuvchida faol smena mavjud")

    # ── Kassa (multi-register) tekshiruvi ──────────────────────────────────────
    register_id = shift_data.register_id
    branch_id = None
    if register_id is not None:
        reg = db.query(CashRegister).filter(CashRegister.id == register_id).first()
        if not reg or not reg.is_active:
            raise HTTPException(status_code=400, detail="Kassa topilmadi yoki nofaol")
        if not current_user.is_superuser and reg.tenant_id != tenant_id:
            raise HTTPException(status_code=403, detail="Kassa boshqa tenantga tegishli")
        branch_id = reg.branch_id
        # Bir kassada bir vaqtda bitta faol smena
        open_on_reg = db.query(Shift).filter(
            Shift.register_id == register_id,
            Shift.end_time.is_(None)
        ).first()
        if open_on_reg:
            raise HTTPException(status_code=400, detail="Bu kassada faol smena ochiq")

    # BOSQICH 1.5: yangi smena yaratuvchi tenant'iga biriktiriladi
    shift = Shift(
        user_id=owner_id,           # ⚠️ klient bergan `user_id` EMAS
        start_time=utc_now(),         # aware UTC — zona belgisi bilan saqlanadi
        starting_cash=shift_data.starting_cash,
        tenant_id=tenant_id,
        register_id=register_id,
        branch_id=branch_id,
    )

    db.add(shift)
    db.commit()
    db.refresh(shift)

    # Audit: smena ochildi
    log_audit(current_user, "shifts", "CREATE", shift.id, tenant_id=tenant_id, detail={
        "user_id": shift.user_id, "starting_cash": shift.starting_cash, "register_id": register_id,
    })
    return ShiftInDB.model_validate(shift)

@router.post("/{shift_id}/close")
async def close_shift(
    shift_id: int,
    # ⛔ MAJBURIY (2026-10). Ilgari sukut 0.0 edi: kassir maydonni bo'sh
    # qoldirsa (yoki klient umuman yubormasa — waiter.js tanada `ending_cash`
    # yuborardi, server uni o'qimasdi) butun naqd KAMOMAD bo'lib yozilardi.
    # Prod: MANHATTAN #52 — 0 bilan yopildi → −42 325 002 soxta kamomad.
    counted_cash: Optional[float] = None,
    notes: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Smenani yopish — counted_cash=kassirdagi haqiqiy naqd pul (majburiy)"""
    shift = _get_shift_for_cashier(db, current_user, shift_id, action="yopa")

    if shift.end_time:
        raise HTTPException(status_code=400, detail="Smena allaqachon yopilgan")

    # Qiymat tekshiruvi ruxsatdan KEYIN — begona smena haqida ma'lumot sizmasin.
    # 0 — QONUNIY qiymat (yashik haqiqatan bo'sh), faqat "kiritilmagan" rad etiladi.
    if counted_cash is None:
        raise HTTPException(
            status_code=400,
            detail="Kassadagi naqd pulni sanab kiriting. Bo'sh qoldirib smenani yopib bo'lmaydi "
                   "(yashik bo'sh bo'lsa — 0 yozing).",
        )
    if counted_cash < 0 or counted_cash > 1e12:
        raise HTTPException(status_code=400, detail="Sanalgan naqd noto'g'ri")

    now   = utc_now()                # aware UTC — `end_time` timestamptz ga yoziladi
    # ⚠️ `shift.start_time` bazadan naive ham kelishi mumkin (SQLite, yoki
    # migratsiya hali qo'llanmagan prod) — `_shift_totals` uni `to_utc` qiladi.

    # ── Pul hisobi — YAGONA MANBA (print-z va /report bilan bir xil) ─────────
    # Qoidalar `_shift_totals` izohida: nasiya alohida qator, qaytarilgan sotuv
    # qoladi, naqd qarz to'lovlari kassaga qo'shiladi.
    t = _shift_totals(db, current_user, shift, now)
    cash_sales, card_sales, credit_total = t["cash_sales"], t["card_sales"], t["credit_total"]
    total_sales    = t["total_sales"]
    sales_count    = t["sales_count"]
    discount_total = t["discount_total"]
    returns_total, cash_refunds = t["returns_total"], t["cash_refunds"]
    debt_pay       = t["debt_pay"]
    expected_cash  = t["expected_cash"]
    shortage       = counted_cash - expected_cash  # musbat=ortiqcha, manfiy=kamomad

    shift.end_time     = now
    shift.ending_cash  = counted_cash
    shift.counted_cash = counted_cash
    shift.total_sales  = total_sales
    shift.cash_sales   = cash_sales
    shift.card_sales   = card_sales
    shift.credit_total = credit_total
    shift.shortage     = shortage
    shift.notes        = notes

    db.commit()
    db.refresh(shift)

    # Audit: smena yopildi (savdo + kamomad/ortiqcha)
    log_audit(current_user, "shifts", "UPDATE", shift.id, tenant_id=shift.tenant_id, detail={
        "action": "close",
        "total_sales": total_sales,
        "counted_cash": counted_cash,
        "expected_cash": round(expected_cash, 0),
        "shortage": round(shortage, 0),
    })
    cafe = db.query(Cafe).filter(Cafe.id == shift.tenant_id).first()
    return {
        "id":             shift.id,
        "store_name":     (cafe.name if cafe else None) or "XENORA",
        "start_time":     to_utc(shift.start_time).isoformat(),
        "end_time":       to_utc(shift.end_time).isoformat(),
        "cashier":        shift.user.full_name if shift.user else None,
        "starting_cash":  shift.starting_cash,
        "cash_sales":     cash_sales,
        "card_sales":     card_sales,
        "credit_total":   credit_total,
        "total_sales":    total_sales,
        "sales_count":    sales_count,
        "avg_order":      round(total_sales / sales_count, 0) if sales_count else 0,
        "discount_total": round(discount_total, 0),
        "returns_total":  round(returns_total, 0),
        "cash_refunds":   round(cash_refunds, 0),
        # Nasiya to'lovlari — ALOHIDA qator. Bu SOTUV EMAS (sotuv o'z kunida
        # hisoblangan), shuning uchun `total_sales` ga QO'SHILMAYDI — faqat
        # kassaga tushgan pul sifatida ko'rsatiladi.
        "debt_paid_cash": round(debt_pay["cash"], 0),
        "debt_paid_card": round(debt_pay["card"], 0),
        "debt_paid_total": round(debt_pay["total"], 0),
        "debt_paid_count": debt_pay["count"],
        "expected_cash":  round(expected_cash, 0),
        "counted_cash":   counted_cash,
        "shortage":       round(shortage, 0),
        "shortage_type":  "ortiqcha" if shortage > 0 else ("kamomad" if shortage < 0 else "mos"),
        # Z-hisobot: SOTILGAN MAHSULOTLAR (nima nechta, summa) — faqat to'langan
        "products":       _shift_products(t["orders"], t["paid_order_ids"]),
        "notes":          notes,
        **_z_money_fields(t),
    }


def _get_shift_for_cashier(db, current_user, shift_id: int, action: str = "ko'ra") -> Shift:
    """Smena + egalik tekshiruvi (yopish, X-hisobot, inkassatsiya — bitta qoida).

    ILGARI (yopish): tenant ichidagi HAR KIM har kimning smenasini yopa olardi —
    bir kassir ikkinchisining Z-hisobotini yakunlab, kamomadni o'sha odam
    nomiga yozishi mumkin edi. Endi: kassir FAQAT o'z smenasini; `manage_shifts`
    (admin, menejer) — istalganini (kassir yopmay ketsa, kunni kimdir yopadi).
    Tekshiruv 404 dan KEYIN, holat tekshiruvlaridan OLDIN — begona smena
    holati (ochiq/yopiq) sizib chiqmasin.
    """
    shift = apply_tenant_filter(db.query(Shift), Shift, current_user).filter(Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Smena topilmadi")
    if shift.user_id != current_user.id and not user_has_permission(current_user, "manage_shifts"):
        raise HTTPException(
            status_code=403,
            detail=f"Faqat o'z smenangizni {action} olasiz. Boshqa xodimning smenasini "
                   "administrator yoki menejer boshqaradi.",
        )
    return shift


@router.get("/{shift_id}/x-report")
async def get_shift_x_report(
    shift_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """X-hisobot — smenani YOPMASDAN joriy holat (Z bilan aynan bir xil hisob).

    Yopish oynasi shundan HAQIQIY "kutilgan naqd" ni oladi: ilgari u "..."
    bo'lib turardi va "kamomad" = sanalgan − boshlang'ich deb ko'rsatilardi.
    Hech narsa yozmaydi. Ruxsat — yopish bilan bir xil (o'z smenasi yoki
    `manage_shifts`).
    """
    shift = _get_shift_for_cashier(db, current_user, shift_id, action="ko'ra")
    data = _build_zreport_data(shift, db, current_user)
    data["is_open"] = shift.end_time is None
    return data


_MOVE_KINDS = {"withdrawal": "Kassadan olindi", "deposit": "Kassaga qo'shildi"}


@router.get("/{shift_id}/cash-movements")
async def list_cash_movements(
    shift_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Smenaning inkassatsiya/razmen yozuvlari."""
    shift = _get_shift_for_cashier(db, current_user, shift_id, action="ko'ra")
    return [_movement_out(m) for m in _cash_movements(db, shift)]


@router.post("/{shift_id}/cash-movements")
async def create_cash_movement(
    shift_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Smena ichida yashikdan pul olish (inkassatsiya) yoki qo'shish (razmen).

    FOYDAGA TEGMAYDI (xarajat emas) — faqat `expected_cash` ni to'g'rilaydi.
    O'chirish/tahrir YO'Q: xato yozuv teskari yozuv bilan tuzatiladi; har biri
    auditga tushadi. Faqat OCHIQ smenaga.
    """
    shift = _get_shift_for_cashier(db, current_user, shift_id, action="boshqara")
    if shift.end_time:
        raise HTTPException(status_code=400, detail="Smena yopilgan — kassa harakati qo'shib bo'lmaydi")

    kind = str(payload.get("kind") or "").strip().lower()
    if kind not in _MOVE_KINDS:
        raise HTTPException(status_code=400, detail="Tur noto'g'ri: withdrawal (olish) yoki deposit (qo'shish)")
    try:
        amount = round(float(payload.get("amount")), 2)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Summa noto'g'ri")
    if not (0 < amount <= 1e12):
        raise HTTPException(status_code=400, detail="Summa musbat bo'lishi kerak")
    reason = str(payload.get("reason") or "").strip()[:255]
    if len(reason) < 2:
        # Kim, nima uchun — keyin "kamomad"ni tushuntiradigan yagona iz
        raise HTTPException(status_code=400, detail="Sababini yozing (masalan: egasiga topshirildi)")

    m = CashMovement(
        tenant_id=shift.tenant_id, shift_id=shift.id, user_id=current_user.id,
        kind=kind, amount=amount, reason=reason, created_at=utc_now(),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    log_audit(current_user, "cash_movements", "CREATE", m.id, tenant_id=shift.tenant_id, detail={
        "shift_id": shift.id, "kind": kind, "amount": amount, "reason": reason,
    })
    return _movement_out(m)

@router.get("/active")
async def get_active_shift(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Joriy foydalanuvchining faol smenasini olish"""
    shift = db.query(Shift).filter(
        Shift.user_id == current_user.id,
        Shift.end_time.is_(None)
    ).first()
    
    if not shift:
        return None

    return ShiftInDB.model_validate(shift)


#: Smena shundan uzoq ochiq tursa — admin panelda ogohlantirish.
STALE_SHIFT_HOURS = 24


@router.get("/open-alerts")
async def get_open_shift_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_analytics")),
):
    """Uzoq (24 soatdan ortiq) ochiq qolgan smenalar — egasiga ogohlantirish.

    NEGA (jonli, 2026-10): MANHATTAN'da smena 8 kun, 1001 BARAKA'da 4 kun
    yopilmay turgan — egasi bilmagan. Ochiq smena Z-hisobotni buzadi va
    "smena bo'yicha" hisobot kunida (core/business_day.py) himoya tufayli
    tungi savdo smena kuniga TUSHMAYDI (06:00 dan keyin kalendar kuni).
    Faqat o'qish; hech narsa yopilmaydi.
    """
    now = utc_now()
    cutoff = now - timedelta(hours=STALE_SHIFT_HOURS)
    q = db.query(Shift).filter(Shift.end_time.is_(None), Shift.start_time < cutoff)
    shifts = apply_tenant_filter(q, Shift, current_user).order_by(Shift.start_time).all()
    alerts = []
    for s in shifts:
        hours = (now - to_utc(s.start_time)).total_seconds() / 3600
        days = int(hours // 24)
        user = db.query(User.full_name).filter(User.id == s.user_id).first() if s.user_id else None
        alerts.append({
            "shift_id":   s.id,
            "user_name":  (user[0] if user else None) or "—",
            "start_time": to_local(s.start_time).isoformat(),
            "opened_at":  _fmt_local(s.start_time),
            "hours_open": round(hours, 1),
            "days_open":  days,
            "message":    f"Smena {days} kundan beri ochiq",
        })
    return {"threshold_hours": STALE_SHIFT_HOURS, "alerts": alerts}


@router.get("/{shift_id}/report")
async def get_shift_report(
    shift_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports")),
):
    """Smena yakuni hisoboti (BOSQICH 5.5)"""
    shift = apply_tenant_filter(db.query(Shift), Shift, current_user) \
        .filter(Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Smena topilmadi")

    # ⚠️ UTC ga normallashtiriladi: bazadan naive ham kelishi mumkin (SQLite,
    # yoki migratsiya hali qo'llanmagan prod) -> aware `utc_now()` bilan ayirish
    # TypeError berardi. Ko'rsatish `_fmt_local` orqali mahalliyga o'giriladi.
    start = to_utc(shift.start_time)
    end   = to_utc(shift.end_time) or utc_now()

    # Buyurtmalar — aniq shift_id bog'lanishi (legacy smenalarda vaqt oralig'i)
    orders = apply_tenant_filter(db.query(Order), Order, current_user).filter(
        Order.shift_id == shift.id,
        Order.status == "completed",
    ).all()
    legacy_fallback = not orders
    if legacy_fallback:
        orders = apply_tenant_filter(db.query(Order), Order, current_user).filter(
            Order.created_at >= start,
            Order.created_at <= end,
            Order.status == "completed",
        ).all()

    # Buyurtma ko'rsatkichlari (soni, tushum, top mahsulot) — YAKUNLANGAN
    # buyurtmalardan, avvalgidek (bu "nima sotildi" o'lchovi).
    total_orders   = len(orders)
    total_revenue  = sum(o.final_amount for o in orders)
    discount_total = sum(o.discount_amount or 0 for o in orders)

    # PUL ko'rsatkichlari — Z bilan YAGONA MANBA (`_shift_totals`). Ilgari bu
    # yerda alohida hisob bor edi: to'liq qaytarilgan sotuv taqsimotdan
    # tushardi va "Yakuniy kassa" = start + naqd edi (qaytarish va naqd qarz
    # to'lovisiz) — Z'dagi `expected_cash` bilan mos emasdi.
    t = _shift_totals(db, current_user, shift, end)
    by_method     = t["by_method"]
    returns_total = t["returns_total"]

    item_counts: dict = {}
    for o in orders:
        for item in o.items:
            name = item.product.name if item.product else f"#{item.product_id}"
            item_counts[name] = item_counts.get(name, 0) + item.quantity

    top_products = sorted(item_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    by_source: dict = {}
    for o in orders:
        src = o.source or "pos"
        by_source[src] = by_source.get(src, 0) + 1

    return {
        "shift_id":       shift.id,
        "cashier":        shift.user.full_name if shift.user else None,
        "start_time":     _fmt_local(start),
        "end_time":       _fmt_local(end),
        "duration_hours": round((end - start).total_seconds() / 3600, 2),
        "summary": {
            "total_orders":   total_orders,
            "sales_count":    total_orders,
            "total_revenue":  total_revenue,
            "discount_total": discount_total,
            "returns_total":  round(returns_total, 0),
            # ⚠️ `final_amount` = subtotal − chegirma (+ soliq/xizmat), ya'ni
            # chegirma ALLAQACHON ayrilgan. Ilgari bu yerda yana ayirilardi —
            # kassir hisobotidagi "Jami tushum" chegirma summasiga kam chiqardi
            # (prod MANHATTAN #52: 39 166 006, aslida 48 595 006).
            "net_revenue":    total_revenue,
            "avg_order":      round(total_revenue / total_orders, 0) if total_orders else 0,
        },
        "by_payment_method": [{"method": k, "amount": v} for k, v in by_method.items()],
        "by_source":         [{"source": k, "count": v} for k, v in by_source.items()],
        "top_products":      [{"name": n, "quantity": q} for n, q in top_products],
        "opening_cash":      shift.starting_cash or 0,
        # "Yakuniy kassa" = Z'dagi `expected_cash` (naqd qaytarish va naqd qarz
        # to'lovlari bilan). Ilgari start + naqd edi.
        "closing_cash":      round(t["expected_cash"], 0),
        # Z bilan bir xil pul qatorlari (yagona manba) — solishtirish uchun
        "cash_sales":        t["cash_sales"],
        "card_sales":        t["card_sales"],
        "credit_total":      t["credit_total"],
        "cash_refunds":      round(t["cash_refunds"], 0),
        "debt_paid_cash":    round(t["debt_pay"]["cash"], 0),
        "expected_cash":     round(t["expected_cash"], 0),
        # Kassir hisobotida ham Z'ning SAVDO/PUL bloklari + kamomad (ilgari
        # kassir yopgandan keyin kamomadni umuman ko'rmasdi).
        "total_sales":       t["total_sales"],
        "debt_paid_card":    round(t["debt_pay"]["card"], 0),
        "counted_cash":      shift.counted_cash,
        "shortage":          round(shift.shortage or 0, 0) if shift.end_time else None,
        "is_open":           shift.end_time is None,
        **_z_money_fields(t),
    }


def _require_z_report(db: Session, current_user: User) -> None:
    """z_report flagi shu tenant uchun yoqilganligini tekshiradi (super-admin bypass)."""
    if current_user.is_superuser:
        return
    cafe = db.query(Cafe).filter(Cafe.id == current_user.tenant_id).first()
    if not cafe or not is_feature_enabled(
        cafe.business_type, Feature.Z_REPORT,
        cafe.enabled_features, cafe.disabled_features,
        cafe.subscription_plan,
    ):
        raise HTTPException(status_code=403, detail="Z-hisobot funksiyasi yoqilmagan")


def _shift_products(orders, paid_order_ids) -> list:
    """Smenada SOTILGAN mahsulotlar breakdown — nom, soni, summa (faqat to'langan
    buyurtmalar). Z-hisobot 'nima nechta sotildi' uchun. Summa bo'yicha kamayadi."""
    agg: dict = {}
    for o in orders:
        if o.id not in paid_order_ids:
            continue
        for it in (o.items or []):
            name = it.product.name if it.product else f"#{it.product_id}"
            e = agg.get(name)
            if not e:
                e = {"name": name, "quantity": 0, "revenue": 0.0}
                agg[name] = e
            e["quantity"] += it.quantity or 0
            e["revenue"]  += it.total_price or 0
    return sorted(agg.values(), key=lambda x: x["revenue"], reverse=True)


def _build_zreport_data(shift: Shift, db: Session, current_user: User) -> dict:
    """Yopilgan (yoki ochiq) smenadan Z-hisobot chek ma'lumotlarini tayyorlaydi."""
    now = utc_now()
    # ── YAGONA MANBA (close_shift va /report bilan bir xil) ──────────────────
    # ⚠️ Ilgari bu yerda faqat `paid` olinardi → NASIYA (pending) Z chekida
    # DOIM 0 edi, smena yopilganda esa to'g'ri ko'rinardi.
    t = _shift_totals(db, current_user, shift, to_utc(shift.end_time) or now)
    start = t["start"]
    orders, paid_order_ids = t["orders"], t["paid_order_ids"]
    cash_sales, card_sales, credit_total = t["cash_sales"], t["card_sales"], t["credit_total"]
    sales_count    = t["sales_count"]
    discount_total = t["discount_total"]
    returns_total, cash_refunds = t["returns_total"], t["cash_refunds"]
    debt_pay       = t["debt_pay"]
    expected_cash  = t["expected_cash"]
    counted_cash  = shift.counted_cash if shift.counted_cash is not None else 0
    shortage      = (counted_cash - expected_cash) if shift.end_time else 0

    cafe = db.query(Cafe).filter(Cafe.id == shift.tenant_id).first()

    return {
        "store_name":     (cafe.name if cafe else None) or "RestoPOS",
        "datetime":       _fmt_local(now),
        "shift_id":       shift.id,
        "cashier":        shift.user.full_name if shift.user else None,
        "register_name":  shift.register.name if shift.register else None,
        "start_time":     _fmt_local(start),
        "end_time":       _fmt_local(to_utc(shift.end_time)),
        "starting_cash":  shift.starting_cash or 0,
        "cash_sales":     cash_sales,
        "card_sales":     card_sales,
        "credit_total":   credit_total,
        "total_sales":    cash_sales + card_sales + credit_total,
        "sales_count":    sales_count,
        "avg_order":      round((cash_sales + card_sales + credit_total) / sales_count, 0) if sales_count else 0,
        "discount_total": round(discount_total, 0),
        "returns_total":  round(returns_total, 0),
        "cash_refunds":   round(cash_refunds, 0),
        # Nasiya to'lovlari — SOTUV EMAS, `total_sales` ga qo'shilmaydi
        "debt_paid_cash": round(debt_pay["cash"], 0),
        "debt_paid_card": round(debt_pay["card"], 0),
        "debt_paid_total": round(debt_pay["total"], 0),
        "debt_paid_count": debt_pay["count"],
        "expected_cash":  round(expected_cash, 0),
        "counted_cash":   counted_cash,
        "shortage":       round(shortage, 0),
        "shortage_type":  "ortiqcha" if shortage > 0 else ("kamomad" if shortage < 0 else "mos"),
        "products":       _shift_products(orders, paid_order_ids),
        "notes":          shift.notes,
        **_z_money_fields(t),
    }


@router.post("/{shift_id}/print-z")
async def print_z_report(
    shift_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Z-hisobotni ESC/POS printerga chiqarish (z_report flagi talab qilinadi)."""
    _require_z_report(db, current_user)

    shift = apply_tenant_filter(db.query(Shift), Shift, current_user) \
        .filter(Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Smena topilmadi")

    data = _build_zreport_data(shift, db, current_user)
    # BOSQICH 40: tenant printer config bilan chop etish
    _printer_cfg = get_tenant_config(db, shift.tenant_id or resolve_tenant_id(db, current_user), "printer")
    result = printer_service.print_z_report(data, cfg=_printer_cfg)
    return {"printed": bool(result.get("ok")), "printer": result, "data": data}