"""
Qaytarish / Almashtirish router — BOSQICH 19

Endpointlar:
  POST /returns/              — yangi qaytarish yaratish
  GET  /returns/              — ro'yxat (filter bilan)
  GET  /returns/report        — hisobot (sabab, usul bo'yicha)
  GET  /returns/{id}          — bitta tafsilot
  POST /returns/{id}/approve  — tasdiqlash (pul + ombor)
  POST /returns/{id}/reject   — rad etish
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, date
from typing import Optional, List

from database import get_db
from models import Return, ReturnItem, Product, Order, OrderItem, Inventory, StockMovement
from schemas import ReturnCreate, ReturnInDB, ReturnReport, MessageResponse
from deps import get_current_active_user, apply_tenant_filter, has_permission
from core.audit import log_audit  # xodim harakatlarini yozish (audit)

router = APIRouter()


def _next_return_number(db: Session, tenant_id: Optional[int]) -> str:
    today = date.today()
    prefix = f"RET{today.strftime('%y%m%d')}"
    count = (
        db.query(func.count(Return.id))
        .filter(Return.return_number.like(f"{prefix}%"))
        .scalar()
        or 0
    )
    return f"{prefix}{count + 1:03d}"


def _restore_inventory(db: Session, product_id: int, quantity: float, tenant_id, branch_id, user_id):
    """Omborga tovarni qaytarish — Inventory miqdorini oshirish + StockMovement yozish"""
    inv = (
        db.query(Inventory)
        .filter(
            Inventory.product_id == product_id,
            Inventory.tenant_id == tenant_id,
        )
        .first()
    )
    if inv:
        inv.quantity += quantity

    product = db.query(Product).filter(Product.id == product_id).first()
    unit_cost = product.cost_price if product else 0.0

    movement = StockMovement(
        tenant_id=tenant_id,
        branch_id=branch_id,
        product_id=product_id,
        inventory_id=inv.id if inv else None,
        movement_type="return",
        quantity=quantity,
        unit_cost=unit_cost,
        total_cost=quantity * unit_cost,
        reason="customer_return",
        reference_type="return",
        user_id=user_id,
    )
    db.add(movement)


# ── POST /returns/ ───────────────────────────────────────────────────────────
@router.post("/", response_model=ReturnInDB)
def create_return(
    data: ReturnCreate,
    db: Session = Depends(get_db),
    # RBAC: qaytarish = to'lov amali → admin + kassir. Ofitsiant/oshpaz QILA OLMAYDI.
    current_user=Depends(has_permission("process_payments")),
):
    if not data.items:
        raise HTTPException(400, "Kamida bitta mahsulot ko'rsatilishi kerak")

    # Original buyurtmani tekshirish (ixtiyoriy)
    if data.order_id:
        order = (
            apply_tenant_filter(db.query(Order), Order, current_user)
            .filter(Order.id == data.order_id)
            .first()
        )
        if not order:
            raise HTTPException(404, "Buyurtma topilmadi")

    total_amount = sum(item.quantity * item.unit_price for item in data.items)

    ret = Return(
        tenant_id=current_user.tenant_id,
        branch_id=getattr(current_user, "_active_branch_id", None),
        return_number=_next_return_number(db, current_user.tenant_id),
        order_id=data.order_id,
        customer_id=data.customer_id,
        reason=data.reason,
        total_amount=total_amount,
        refund_method=data.refund_method,
        status="pending",
        notes=data.notes,
        user_id=current_user.id,
    )
    db.add(ret)
    db.flush()

    for item_data in data.items:
        product = db.query(Product).filter(Product.id == item_data.product_id).first()
        if not product:
            raise HTTPException(404, f"Mahsulot {item_data.product_id} topilmadi")

        ri = ReturnItem(
            return_id=ret.id,
            product_id=item_data.product_id,
            order_item_id=item_data.order_item_id,
            quantity=item_data.quantity,
            unit_price=item_data.unit_price,
            total=item_data.quantity * item_data.unit_price,
            restore_to_inventory=item_data.restore_to_inventory,
        )
        db.add(ri)

    db.commit()
    db.refresh(ret)

    # Audit: KIM qaytarish qildi — summa, sabab, mahsulot soni
    log_audit(current_user, "returns", "RETURN", ret.id, tenant_id=ret.tenant_id, detail={
        "return_number": ret.return_number,
        "total_amount": total_amount,
        "reason": data.reason,
        "refund_method": data.refund_method,
        "order_id": data.order_id,
        "items_count": len(data.items),
    })
    return ret


# ── GET /returns/ ────────────────────────────────────────────────────────────
@router.get("/", response_model=List[ReturnInDB])
def list_returns(
    status: Optional[str] = None,
    customer_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    q = apply_tenant_filter(db.query(Return), Return, current_user)

    if status:
        q = q.filter(Return.status == status)
    if customer_id:
        q = q.filter(Return.customer_id == customer_id)
    if date_from:
        q = q.filter(Return.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        q = q.filter(Return.created_at <= datetime.combine(date_to, datetime.max.time()))

    q = q.order_by(Return.created_at.desc())
    return q.offset((page - 1) * page_size).limit(page_size).all()


# ── GET /returns/report ──────────────────────────────────────────────────────
@router.get("/report", response_model=ReturnReport)
def returns_report(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user=Depends(has_permission("view_reports")),
):
    q = apply_tenant_filter(db.query(Return), Return, current_user).filter(
        Return.status == "approved"
    )
    if date_from:
        q = q.filter(Return.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        q = q.filter(Return.created_at <= datetime.combine(date_to, datetime.max.time()))

    returns = q.all()
    total_amount = sum(r.total_amount for r in returns)

    by_reason: dict = {}
    by_refund: dict = {}
    for r in returns:
        by_reason[r.reason] = by_reason.get(r.reason, 0) + 1
        by_refund[r.refund_method] = by_refund.get(r.refund_method, 0.0) + r.total_amount

    return ReturnReport(
        total_returns=len(returns),
        total_amount=total_amount,
        by_reason=by_reason,
        by_refund_method=by_refund,
    )


# ── GET /returns/{id} ────────────────────────────────────────────────────────
@router.get("/{return_id}", response_model=ReturnInDB)
def get_return(
    return_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    ret = (
        apply_tenant_filter(db.query(Return), Return, current_user)
        .filter(Return.id == return_id)
        .first()
    )
    if not ret:
        raise HTTPException(404, "Qaytarish topilmadi")
    return ret


# ── POST /returns/{id}/approve ───────────────────────────────────────────────
@router.post("/{return_id}/approve", response_model=ReturnInDB)
def approve_return(
    return_id: int,
    db: Session = Depends(get_db),
    # RBAC: tasdiqlash ham admin + kassir (ofitsiant/oshpaz emas)
    current_user=Depends(has_permission("process_payments")),
):
    ret = (
        apply_tenant_filter(db.query(Return), Return, current_user)
        .filter(Return.id == return_id)
        .first()
    )
    if not ret:
        raise HTTPException(404, "Qaytarish topilmadi")
    if ret.status != "pending":
        raise HTTPException(400, f"Bu qaytarish allaqachon '{ret.status}' holatida")

    # Omborga qaytarish (faqat restore_to_inventory=True bo'lganlar)
    for item in ret.items:
        if item.restore_to_inventory:
            _restore_inventory(
                db,
                item.product_id,
                item.quantity,
                ret.tenant_id,
                ret.branch_id,
                current_user.id,
            )

    ret.status = "approved"
    ret.approved_by = current_user.id
    ret.approved_at = datetime.utcnow()

    db.commit()
    db.refresh(ret)
    return ret


# ── POST /returns/{id}/reject ────────────────────────────────────────────────
@router.post("/{return_id}/reject", response_model=ReturnInDB)
def reject_return(
    return_id: int,
    db: Session = Depends(get_db),
    # RBAC: rad etish ham admin + kassir (ofitsiant/oshpaz emas)
    current_user=Depends(has_permission("process_payments")),
):
    ret = (
        apply_tenant_filter(db.query(Return), Return, current_user)
        .filter(Return.id == return_id)
        .first()
    )
    if not ret:
        raise HTTPException(404, "Qaytarish topilmadi")
    if ret.status != "pending":
        raise HTTPException(400, f"Bu qaytarish allaqachon '{ret.status}' holatida")

    ret.status = "rejected"
    ret.approved_by = current_user.id
    ret.approved_at = datetime.utcnow()

    db.commit()
    db.refresh(ret)
    return ret
