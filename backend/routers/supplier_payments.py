"""
Firmaga to'lovlar router — BOSQICH 24 (B2B)
To'lov qilinganда qarz kamayadi.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date as Date
from typing import Optional

from database import get_db
from models import SupplierPayment, Supplier, PurchaseReceipt, User  # User: to'lovni kim kiritgani
from schemas import (
    SupplierPaymentCreate, SupplierPaymentInDB,
    PaginatedResponse, MessageResponse,
)
from deps import resolve_tenant_id, get_current_active_user, apply_tenant_filter, has_permission
from core.audit import log_audit   # kim qancha to'lov kiritgani keyin tekshirilsin

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

    # FAZA 2: to'lov turi + kim kiritgani. Ikkalasi ham bazada BOR edi, lekin
    # javobga chiqmasdi — do'konchi "tovar bilan berilganmi yoki alohida pulmi"
    # va "kim kiritdi" degan savolga javob topa olmasdi.
    # N+1 bo'lmasin: sahifadagi nakladnoy va foydalanuvchilar 2 ta so'rovda olinadi.
    rec_ids  = {r.receipt_id for r in rows if r.receipt_id}
    user_ids = {r.created_by or r.user_id for r in rows if (r.created_by or r.user_id)}
    receipts = {rec.id: rec for rec in db.query(PurchaseReceipt)
                .filter(PurchaseReceipt.id.in_(rec_ids)).all()} if rec_ids else {}
    users    = {u.id: u for u in db.query(User)
                .filter(User.id.in_(user_ids)).all()} if user_ids else {}

    items = []
    for r in rows:
        m = SupplierPaymentInDB.model_validate(r)
        if r.receipt_id:
            m.payment_type = "receipt"
            rec = receipts.get(r.receipt_id)
            inv = f" · {rec.invoice_number}" if (rec and rec.invoice_number) else ""
            m.receipt_label = f"Nakladnoy #{r.receipt_id}{inv}"
        else:
            m.payment_type  = "general"
            m.receipt_label = None
        u = users.get(r.created_by or r.user_id)
        if u:
            m.created_by_name = u.full_name or u.username or u.phone
        items.append(m)

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size,
                             total_pages=(total + page_size - 1) // page_size)


@router.post("/", response_model=SupplierPaymentInDB)
async def create_payment(
    data: SupplierPaymentCreate,
    db:   Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_finance")),
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

    # AUDIT: firmaga to'lov — sof pul harakati. "Kim qancha to'lov kiritdi"
    # degan savolga keyin javob topilsin (ilgari hech qanday iz qolmasdi).
    log_audit(current_user, "supplier_payments", "CREATE", p.id,
              tenant_id=p.tenant_id,
              detail={"supplier_id": p.supplier_id, "amount": float(p.amount or 0),
                      "receipt_id": p.receipt_id, "method": p.payment_method,
                      "payment_date": str(p.payment_date) if p.payment_date else None})
    return SupplierPaymentInDB.model_validate(p)


@router.delete("/{payment_id}", response_model=MessageResponse)
async def delete_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_finance")),
):
    p = apply_tenant_filter(db.query(SupplierPayment), SupplierPayment, current_user) \
          .filter(SupplierPayment.id == payment_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="To'lov topilmadi")

    _rec_id, _amount, _sup_id = p.receipt_id, float(p.amount or 0), p.supplier_id
    db.delete(p)
    db.flush()

    # B5 TUZATISH: to'lov o'chirilsa nakladnoy holati QAYTA HISOBLANADI.
    # Ilgari yozuv o'chirilar, `status` esa "paid" bo'lib QOLAVERARDI — natijada
    # o'sha nakladnoy "muddati o'tgan" hisobidan abadiy chiqib ketardi va
    # do'konchi to'lanmagan qarzni ko'rmasdi.
    if _rec_id:
        rec = db.query(PurchaseReceipt).filter(PurchaseReceipt.id == _rec_id).first()
        if rec and rec.status in ("confirmed", "paid"):
            qolgan = db.query(func.coalesce(func.sum(SupplierPayment.amount), 0.0)).filter(
                SupplierPayment.receipt_id == rec.id
            ).scalar() or 0.0
            rec.status = "paid" if qolgan >= float(rec.net_amount or 0) else "confirmed"

    db.commit()

    log_audit(current_user, "supplier_payments", "DELETE", payment_id,
              tenant_id=resolve_tenant_id(db, current_user),
              detail={"supplier_id": _sup_id, "amount": _amount, "receipt_id": _rec_id})
    return MessageResponse(message="To'lov o'chirildi")
