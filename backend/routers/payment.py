from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
import logging

from database import get_db
from models import Payment, Order, User, Table
from schemas import PaymentCreate, PaymentInDB, PaginatedResponse, MessageResponse
from deps import resolve_tenant_id, get_current_user, get_current_active_user, has_permission, apply_tenant_filter
from services.payment_service import PaymentService
from services.ofd_service import send_to_ofd
from websocket.manager import manager
from core.config_loader import config_loader
from core.tenant_config import get_tenant_config

log = logging.getLogger(__name__)

router = APIRouter()

@router.get("/", response_model=PaginatedResponse)
async def get_payments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    order_id: Optional[int] = None,
    method: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports"))
):
    """Barcha to'lovlarni olish"""
    query = db.query(Payment)
    # BOSQICH 1.5: tenant bo'yicha cheklash
    query = apply_tenant_filter(query, Payment, current_user)

    if order_id:
        query = query.filter(Payment.order_id == order_id)
    
    if method:
        query = query.filter(Payment.method == method)
    
    if status:
        query = query.filter(Payment.status == status)
    
    if date_from:
        query = query.filter(Payment.created_at >= date_from)
    
    if date_to:
        query = query.filter(Payment.created_at <= date_to)
    
    total = query.count()
    payments = query.order_by(Payment.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    
    return PaginatedResponse(
        items=[PaymentInDB.model_validate(p) for p in payments],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size
    )

@router.post("/", response_model=PaymentInDB)
async def create_payment(
    payment_data: PaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Yangi to'lov yaratish"""
    payment_service = PaymentService(db)

    # Buyurtmani tekshirish (BOSQICH 1.5: tenant bo'yicha cheklash)
    order = apply_tenant_filter(db.query(Order), Order, current_user).filter(Order.id == payment_data.order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")

    # To'lovni qayta ishlash
    payment = payment_service.process_payment(
        order=order,
        amount=payment_data.amount,
        method=payment_data.method,
        cashier_id=current_user.id,
        reference=payment_data.reference
    )
    # BOSQICH 1.5: to'lov yaratuvchi tenant'iga biriktiriladi
    payment.tenant_id = resolve_tenant_id(db, current_user)
    db.commit()
    db.refresh(payment)

    # Agar to'liq to'langan bo'lsa, buyurtmani yakunlash
    total_paid = sum(p.amount for p in order.payments if p.status == "paid")
    order_completed = False
    if total_paid >= order.final_amount:
        order.status = "completed"
        order.completed_at = datetime.now()
        if order.table:
            order.table.status = "free"
        db.commit()
        order_completed = True

        # ── Ombor chiqimi (sotuv = chiqim) — idempotent ──────────────────────────
        # Retseptli mahsulot → ingredientlar; retseptsiz (chakana tovar) → o'zi kamayadi.
        # `ingredients_deducted` guard: restoran kitchen-ready'da allaqachon chiqargan
        # bo'lsa qayta ayirmaydi; magazin sotuvida shu yerda birinchi marta ayiriladi.
        if not order.ingredients_deducted:
            try:
                from services.recipe_inventory_service import deduct_order_ingredients
                deduct_order_ingredients(
                    db, order.id,
                    tenant_id=resolve_tenant_id(db, current_user),
                    user_id=current_user.id,
                )
                order.ingredients_deducted = True
                db.commit()
            except Exception as exc:
                db.rollback()
                log.warning("[INVENTORY] order=%s chiqim xatosi: %s", order.id, exc)

    # ── OFD Fiskal integratsiya ───────────────────────────────────────────────
    if order_completed:
        # BOSQICH 40: fiskal sozlama tenant-scoped (INN/kassa_id/operator/api_key)
        # payment.tenant_id yuqorida resolve_tenant_id orqali aniqlangan.
        fiscal_config = get_tenant_config(db, payment.tenant_id, "fiscal") or {}
        if fiscal_config.get("enabled"):
            try:
                # payment metodini payload ga qo'shish
                fiscal_config = dict(fiscal_config)
                fiscal_config["payment_type"] = str(payment_data.method)

                ofd = send_to_ofd(order, fiscal_config)
                if ofd.success:
                    order.fiscal_number  = ofd.fiscal_number
                    order.fiscal_qr_url  = ofd.qr_url
                    order.fiscal_sent_at = datetime.now()
                    db.commit()
                    log.info(
                        "[OFD] order=%s fn=%s qr=%s",
                        order.id, ofd.fiscal_number, (ofd.qr_url or "")[:60]
                    )
                else:
                    # To'lov bekor bo'lmaydi — faqat loglash
                    log.warning("[OFD] order=%s yuborilmadi: %s", order.id, ofd.error)
            except Exception as exc:
                log.exception("[OFD] kutilmagan xato order=%s: %s", order.id, exc)

    # BOSQICH 2.6: to'lov haqida WebSocket xabari
    ws_payload = {
        "type": "payment_received",
        "order_id": order.id,
        "order_number": order.order_number,
        "table": order.table.number if order.table else None,
        "amount": payment_data.amount,
        "method": payment_data.method,
        "order_completed": order_completed,
    }
    await manager.broadcast_to_pos(ws_payload, tenant_id=resolve_tenant_id(db, current_user))
    if order_completed:
        # Oshxonaga ham xabar: bu buyurtma tugadi
        await manager.broadcast_to_kitchen({
            "type": "order_completed",
            "order_id": order.id,
            "order_number": order.order_number,
        }, tenant_id=resolve_tenant_id(db, current_user))

    return PaymentInDB.model_validate(payment)

@router.get("/{payment_id}", response_model=PaymentInDB)
async def get_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports"))
):
    """To'lov ma'lumotlarini olish"""
    payment = apply_tenant_filter(db.query(Payment), Payment, current_user).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="To'lov topilmadi")
    
    return PaymentInDB.model_validate(payment)

@router.post("/{payment_id}/refund", response_model=MessageResponse)
async def refund_payment(
    payment_id: int,
    amount: Optional[float] = None,
    reason: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("process_payments"))
):
    """To'lovni qaytarish"""
    payment_service = PaymentService(db)

    payment = apply_tenant_filter(db.query(Payment), Payment, current_user).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="To'lov topilmadi")
    
    if payment.status != "paid":
        raise HTTPException(status_code=400, detail="Faqat to'langan to'lovlarni qaytarish mumkin")
    
    refund_amount = amount or payment.amount
    
    if refund_amount > payment.amount:
        raise HTTPException(status_code=400, detail="Qaytarish summasi to'lov summasidan ko'p bo'lishi mumkin emas")
    
    success = payment_service.refund_payment(payment, refund_amount, reason)

    if success:
        # Buyurtma holatini yangilash
        order = payment.order
        if refund_amount == payment.amount:
            payment.status = "refunded"

        # Agar barcha to'lovlar qaytarilgan bo'lsa
        all_refunded = all(p.status == "refunded" for p in order.payments)
        if all_refunded and order.status == "completed":
            order.status = "cancelled"

        db.commit()

        # ── Ombor tiklash (refund = sotuv chiqimining teskarisi) ──────────────
        # Buyurtma to'liq qaytarilganda (barcha to'lov refund) va sotuvda ombor
        # chiqim qilingan bo'lsa (ingredients_deducted) — omborni bir marta tiklaymiz.
        # ingredients_restored guard: ikki marta refund bir xil zaxirani ikki marta
        # qaytarib qo'ymaydi (idempotent). StockMovement(type=return, reason=refund) izi.
        if all_refunded and order.ingredients_deducted and not order.ingredients_restored:
            try:
                from services.recipe_inventory_service import restore_order_ingredients
                restore_order_ingredients(
                    db, order.id,
                    tenant_id=order.tenant_id,
                    user_id=current_user.id,
                )
                order.ingredients_restored = True
                db.commit()
            except Exception as exc:
                db.rollback()
                log.warning("[INVENTORY] order=%s refund tiklash xatosi: %s", order.id, exc)

        return MessageResponse(message="To'lov qaytarildi")

    raise HTTPException(status_code=500, detail="To'lovni qaytarishda xatolik")

@router.get("/methods/summary")
async def get_payment_methods_summary(
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports"))
):
    """To'lov usullari bo'yicha xulosa"""
    from sqlalchemy import func

    query = db.query(
        Payment.method,
        func.sum(Payment.amount).label('total'),
        func.count(Payment.id).label('count')
    ).filter(Payment.status == "paid")
    # BOSQICH 1.5: tenant bo'yicha cheklash
    query = apply_tenant_filter(query, Payment, current_user)

    if date_from:
        query = query.filter(Payment.created_at >= date_from)
    
    if date_to:
        query = query.filter(Payment.created_at <= date_to)
    
    results = query.group_by(Payment.method).all()

    return [
        {
            "method": r.method,
            "total": float(r.total or 0),
            "count": r.count
        }
        for r in results
    ]


@router.post("/{payment_id}/tip")
async def add_tip(
    payment_id: int,
    tip_amount: float,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Choy puli (tips) qo'shish (BOSQICH 9.11).
    Ofitsiantga to'lovdan alohida qo'shilgan summa.
    """
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(404, "To'lov topilmadi")
    if tip_amount < 0:
        raise HTTPException(400, "Choy puli manfiy bo'lishi mumkin emas")
    payment.tip_amount = tip_amount
    db.commit()
    return {"success": True, "tip_amount": tip_amount, "payment_id": payment_id}


@router.get("/tips/summary")
async def get_tips_summary(
    date_from: str = None,
    date_to: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports"))
):
    """Choy puli umumiy hisoboti вЂ” ofitsiant bo'yicha"""
    from sqlalchemy import func as sqlfunc
    from datetime import datetime as dt
    q = db.query(
        Payment.cashier_id,
        sqlfunc.sum(Payment.tip_amount).label("total_tips"),
        sqlfunc.count(Payment.id).label("payments_count")
    ).filter(Payment.tip_amount > 0)

    if date_from:
        try:
            q = q.filter(Payment.created_at >= dt.fromisoformat(date_from))
        except Exception:
            pass
    if date_to:
        try:
            q = q.filter(Payment.created_at <= dt.fromisoformat(date_to))
        except Exception:
            pass

    results = q.group_by(Payment.cashier_id).all()
    return [{"cashier_id": r.cashier_id, "total_tips": float(r.total_tips or 0), "payments_count": r.payments_count}
            for r in results]
