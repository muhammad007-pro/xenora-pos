from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func as sqlfunc
from datetime import datetime
from typing import Optional

from database import get_db
from models import Shift, User, Order, Payment, OrderItem, CashRegister, Return, Cafe
from schemas import ShiftCreate, ShiftUpdate, ShiftInDB, MessageResponse
from deps import resolve_tenant_id, get_current_user, get_current_active_user, has_permission, apply_tenant_filter
from core.feature_flags import Feature, is_feature_enabled
from services import printer_service
from core.tenant_config import get_tenant_config  # BOSQICH 40 (3c): printer tenant-scoped
from core.audit import log_audit  # xodim harakatlarini yozish (audit)

router = APIRouter()

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
        target_date = datetime.strptime(date, "%Y-%m-%d")
        query = query.filter(
            Shift.start_time >= target_date,
            Shift.start_time < target_date.replace(hour=23, minute=59, second=59)
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

    # Faol smena mavjudligini tekshirish (foydalanuvchi bo'yicha — mavjud xatti-harakat)
    active_shift = db.query(Shift).filter(
        Shift.user_id == shift_data.user_id,
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
        user_id=shift_data.user_id,
        start_time=datetime.now(),
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
    counted_cash: float = 0.0,
    notes: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Smenani yopish — counted_cash=kassirdagi haqiqiy naqd pul"""
    shift = apply_tenant_filter(db.query(Shift), Shift, current_user).filter(Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Smena topilmadi")
    if shift.end_time:
        raise HTTPException(status_code=400, detail="Smena allaqachon yopilgan")

    now = datetime.now()

    # ── Smena buyurtmalari — Z-hisobot uchun aniq shift_id bog'lanishi ──────────
    # Bosqich 0 dan beri har buyurtma yaratilganda joriy smena id si yoziladi.
    orders = apply_tenant_filter(db.query(Order), Order, current_user).filter(
        Order.shift_id == shift.id
    ).all()

    legacy_fallback = False
    if not orders:
        # Orqaga moslik: shift_id biriktirilmagan eski smenalar — vaqt oralig'i bilan
        legacy_fallback = True
        orders = apply_tenant_filter(db.query(Order), Order, current_user).filter(
            Order.created_at >= shift.start_time,
            Order.created_at <= now,
        ).all()

    order_ids = [o.id for o in orders]

    # ── To'lovlar — smena buyurtmalariga tegishli (legacy: vaqt oralig'i) ───────
    if legacy_fallback:
        payments = apply_tenant_filter(db.query(Payment), Payment, current_user).filter(
            Payment.created_at >= shift.start_time,
            Payment.created_at <= now,
            Payment.status == "paid",
        ).all()
    elif order_ids:
        payments = apply_tenant_filter(db.query(Payment), Payment, current_user).filter(
            Payment.order_id.in_(order_ids),
            Payment.status == "paid",
        ).all()
    else:
        payments = []

    cash_sales   = sum(p.amount for p in payments if p.method == "cash")
    card_sales   = sum(p.amount for p in payments if p.method in ("card", "payme", "click"))
    credit_total = sum(p.amount for p in payments if p.method == "credit")
    total_sales  = cash_sales + card_sales + credit_total

    # Sotuvlar soni — to'langan cheklar (distinct order) soni
    paid_order_ids = {p.order_id for p in payments if p.order_id}
    sales_count    = len(paid_order_ids)

    # Chegirmalar jami — to'langan buyurtmalar bo'yicha
    discount_total = sum((o.discount_amount or 0) for o in orders if o.id in paid_order_ids)

    # ── Qaytarishlar — vaqt oralig'i bo'yicha (Return smenaga bog'lanmagan) ─────
    returns = apply_tenant_filter(db.query(Return), Return, current_user).filter(
        Return.created_at >= shift.start_time,
        Return.created_at <= now,
        Return.status != "rejected",
    ).all()
    returns_total = sum(r.total_amount or 0 for r in returns)
    cash_refunds  = sum((r.total_amount or 0) for r in returns if r.refund_method == "cash")

    # Naqd kassada bo'lishi kerak: boshlang'ich + naqd savdo − naqd qaytarishlar
    expected_cash = (shift.starting_cash or 0) + cash_sales - cash_refunds
    shortage      = counted_cash - expected_cash  # musbat=ortiqcha, manfiy=kamomad

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
    return {
        "id":             shift.id,
        "start_time":     shift.start_time.isoformat(),
        "end_time":       shift.end_time.isoformat(),
        "cashier":        shift.user.full_name if shift.user else None,
        "starting_cash":  shift.starting_cash,
        "cash_sales":     cash_sales,
        "card_sales":     card_sales,
        "credit_total":   credit_total,
        "total_sales":    total_sales,
        "sales_count":    sales_count,
        "discount_total": round(discount_total, 0),
        "returns_total":  round(returns_total, 0),
        "cash_refunds":   round(cash_refunds, 0),
        "expected_cash":  round(expected_cash, 0),
        "counted_cash":   counted_cash,
        "shortage":       round(shortage, 0),
        "shortage_type":  "ortiqcha" if shortage > 0 else ("kamomad" if shortage < 0 else "mos"),
        "notes":          notes,
    }

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

    start = shift.start_time
    end   = shift.end_time or datetime.now()

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

    order_ids = [o.id for o in orders]

    total_orders   = len(orders)
    total_revenue  = sum(o.final_amount for o in orders)
    discount_total = sum(o.discount_amount or 0 for o in orders)

    if legacy_fallback:
        payments = apply_tenant_filter(db.query(Payment), Payment, current_user).filter(
            Payment.created_at >= start,
            Payment.created_at <= end,
            Payment.status == "paid",
        ).all()
    elif order_ids:
        payments = apply_tenant_filter(db.query(Payment), Payment, current_user).filter(
            Payment.order_id.in_(order_ids),
            Payment.status == "paid",
        ).all()
    else:
        payments = []

    # Qaytarishlar jami — vaqt oralig'i bo'yicha
    returns = apply_tenant_filter(db.query(Return), Return, current_user).filter(
        Return.created_at >= start,
        Return.created_at <= end,
        Return.status != "rejected",
    ).all()
    returns_total = sum(r.total_amount or 0 for r in returns)

    by_method: dict = {}
    for p in payments:
        by_method[p.method] = by_method.get(p.method, 0) + p.amount

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
        "start_time":     start.strftime("%d.%m.%Y %H:%M"),
        "end_time":       end.strftime("%d.%m.%Y %H:%M"),
        "duration_hours": round((end - start).total_seconds() / 3600, 2),
        "summary": {
            "total_orders":   total_orders,
            "sales_count":    total_orders,
            "total_revenue":  total_revenue,
            "discount_total": discount_total,
            "returns_total":  round(returns_total, 0),
            "net_revenue":    total_revenue - discount_total,
            "avg_order":      round(total_revenue / total_orders, 0) if total_orders else 0,
        },
        "by_payment_method": [{"method": k, "amount": v} for k, v in by_method.items()],
        "by_source":         [{"source": k, "count": v} for k, v in by_source.items()],
        "top_products":      [{"name": n, "quantity": q} for n, q in top_products],
        "opening_cash":      shift.starting_cash or 0,
        "closing_cash":      (shift.starting_cash or 0) + by_method.get("cash", 0),
    }


def _require_z_report(db: Session, current_user: User) -> None:
    """z_report flagi shu tenant uchun yoqilganligini tekshiradi (super-admin bypass)."""
    if current_user.is_superuser:
        return
    cafe = db.query(Cafe).filter(Cafe.id == current_user.tenant_id).first()
    if not cafe or not is_feature_enabled(
        cafe.business_type, Feature.Z_REPORT,
        cafe.enabled_features, cafe.disabled_features,
    ):
        raise HTTPException(status_code=403, detail="Z-hisobot funksiyasi yoqilmagan")


def _build_zreport_data(shift: Shift, db: Session, current_user: User) -> dict:
    """Yopilgan (yoki ochiq) smenadan Z-hisobot chek ma'lumotlarini tayyorlaydi."""
    now = datetime.now()
    start = shift.start_time
    end   = shift.end_time or now

    orders = apply_tenant_filter(db.query(Order), Order, current_user).filter(
        Order.shift_id == shift.id
    ).all()
    legacy_fallback = not orders
    if legacy_fallback:
        orders = apply_tenant_filter(db.query(Order), Order, current_user).filter(
            Order.created_at >= start, Order.created_at <= end,
        ).all()
    order_ids = [o.id for o in orders]

    if legacy_fallback:
        payments = apply_tenant_filter(db.query(Payment), Payment, current_user).filter(
            Payment.created_at >= start, Payment.created_at <= end,
            Payment.status == "paid",
        ).all()
    elif order_ids:
        payments = apply_tenant_filter(db.query(Payment), Payment, current_user).filter(
            Payment.order_id.in_(order_ids), Payment.status == "paid",
        ).all()
    else:
        payments = []

    cash_sales   = sum(p.amount for p in payments if p.method == "cash")
    card_sales   = sum(p.amount for p in payments if p.method in ("card", "payme", "click"))
    credit_total = sum(p.amount for p in payments if p.method == "credit")
    paid_order_ids = {p.order_id for p in payments if p.order_id}
    sales_count    = len(paid_order_ids)
    discount_total = sum((o.discount_amount or 0) for o in orders if o.id in paid_order_ids)

    returns = apply_tenant_filter(db.query(Return), Return, current_user).filter(
        Return.created_at >= start, Return.created_at <= end,
        Return.status != "rejected",
    ).all()
    returns_total = sum(r.total_amount or 0 for r in returns)
    cash_refunds  = sum((r.total_amount or 0) for r in returns if r.refund_method == "cash")

    expected_cash = (shift.starting_cash or 0) + cash_sales - cash_refunds
    counted_cash  = shift.counted_cash if shift.counted_cash is not None else 0
    shortage      = (counted_cash - expected_cash) if shift.end_time else 0

    cafe = db.query(Cafe).filter(Cafe.id == shift.tenant_id).first()

    return {
        "store_name":     (cafe.name if cafe else None) or "RestoPOS",
        "datetime":       now.strftime("%d.%m.%Y %H:%M"),
        "shift_id":       shift.id,
        "cashier":        shift.user.full_name if shift.user else None,
        "register_name":  shift.register.name if shift.register else None,
        "start_time":     start.strftime("%d.%m.%Y %H:%M"),
        "end_time":       shift.end_time.strftime("%d.%m.%Y %H:%M") if shift.end_time else None,
        "starting_cash":  shift.starting_cash or 0,
        "cash_sales":     cash_sales,
        "card_sales":     card_sales,
        "credit_total":   credit_total,
        "total_sales":    cash_sales + card_sales + credit_total,
        "sales_count":    sales_count,
        "discount_total": round(discount_total, 0),
        "returns_total":  round(returns_total, 0),
        "cash_refunds":   round(cash_refunds, 0),
        "expected_cash":  round(expected_cash, 0),
        "counted_cash":   counted_cash,
        "shortage":       round(shortage, 0),
        "shortage_type":  "ortiqcha" if shortage > 0 else ("kamomad" if shortage < 0 else "mos"),
        "notes":          shift.notes,
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