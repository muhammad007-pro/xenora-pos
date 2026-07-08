"""
Firmaga to'lovlar router — BOSQICH 24 (B2B)
To'lov qilinganда qarz kamayadi.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date as Date
from typing import Optional

from database import get_db
from models import SupplierPayment, Supplier, PurchaseReceipt, User
from schemas import (
    SupplierPaymentCreate, SupplierPaymentInDB,
    PaginatedResponse, MessageResponse,
)
from deps import resolve_tenant_id, get_current_active_user, apply_tenant_filter, has_permission

router = APIRouter()


@router.get("/", response_model=PaginatedResponse)
async def list_payments(
    supplier_id: Optional[int] = None,
    receipt_id:  Optional[int] = None,
    date_from:   Optional[str] = None,
    date_to:     Optional[str] = None,
    page:        int = Query(1, ge=1),
    page_size:   int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports")),
):
    q = apply_tenant_filter(db.query(SupplierPayment), SupplierPayment, current_user)
    if supplier_id:
        q = q.filter(SupplierPayment.supplier_id == supplier_id)
    if receipt_id:
        q = q.filter(SupplierPayment.receipt_id == receipt_id)
    if date_from:
        q = q.filter(SupplierPayment.payment_date >= date_from)
    if date_to:
        q = q.filter(SupplierPayment.payment_date <= date_to)
    total = q.count()
    rows  = q.order_by(SupplierPayment.payment_date.desc()).offset((page - 1) * page_size).limit(page_size).all()
    items = [SupplierPaymentInDB.model_validate(r) for r in rows]
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size,
                             total_pages=(total + page_size - 1) // page_size)


@router.post("/", response_model=SupplierPaymentInDB)
async def create_payment(
    data: SupplierPaymentCreate,
    db:   Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Firmaga to'lov qilish"""
    supplier = apply_tenant_filter(db.query(Supplier), Supplier, current_user) \
                   .filter(Supplier.id == data.supplier_id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Firma topilmadi")

    if data.receipt_id:
        rec = apply_tenant_filter(db.query(PurchaseReceipt), PurchaseReceipt, current_user) \
                  .filter(PurchaseReceipt.id == data.receipt_id).first()
        if not rec:
            raise HTTPException(status_code=404, detail="Priyomka topilmadi")

    p = SupplierPayment(
        tenant_id=resolve_tenant_id(db, current_user),
        user_id=current_user.id,
        created_by=current_user.id,
        supplier_id=data.supplier_id,
        receipt_id=data.receipt_id,
        amount=data.amount,
        payment_date=Date.fromisoformat(data.payment_date),
        payment_method=data.payment_method,
        notes=data.notes,
    )
    db.add(p)

    # Agar to'lov nakladnoy uchun bo'lsa, holатini yangilash
    if data.receipt_id:
        rec = db.query(PurchaseReceipt).filter(PurchaseReceipt.id == data.receipt_id).first()
        if rec and rec.status == "confirmed":
            total_paid = sum(pay.amount for pay in rec.b2b_payments) + data.amount
            if total_paid >= rec.net_amount:
                rec.status = "paid"

    db.commit()
    db.refresh(p)
    return SupplierPaymentInDB.model_validate(p)


@router.delete("/{payment_id}", response_model=MessageResponse)
async def delete_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    p = apply_tenant_filter(db.query(SupplierPayment), SupplierPayment, current_user) \
          .filter(SupplierPayment.id == payment_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="To'lov topilmadi")
    db.delete(p)
    db.commit()
    return MessageResponse(message="To'lov o'chirildi")
