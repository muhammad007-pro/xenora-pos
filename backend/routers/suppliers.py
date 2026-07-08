"""
Yetkazib beruvchilar (Suppliers) router — BOSQICH 24 (B2B)
Firma kartochkasi: INN (tax_id), telefon, manzil, shartnoma, otsrochka, mas'ul shaxs.
Qarz summary hisoblash: priyomkalar - to'lovlar - vozvratlар.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date as Date
from typing import Optional

from database import get_db
from models import Supplier, PurchaseReceipt, SupplierPayment, SupplierReturn, User
from schemas import (
    SupplierCreate, SupplierUpdate, SupplierInDB,
    SupplierDebtSummary, PaginatedResponse, MessageResponse,
)
from deps import resolve_tenant_id, get_current_active_user, apply_tenant_filter, has_permission

router = APIRouter()


@router.get("/", response_model=PaginatedResponse)
async def list_suppliers(
    search:    Optional[str] = None,
    is_active: Optional[bool] = True,
    page:      int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    q = apply_tenant_filter(db.query(Supplier), Supplier, current_user)
    if is_active is not None:
        q = q.filter(Supplier.is_active == is_active)
    if search:
        q = q.filter(Supplier.name.ilike(f"%{search}%"))
    total = q.count()
    rows  = q.order_by(Supplier.name).offset((page - 1) * page_size).limit(page_size).all()
    items = [SupplierInDB.model_validate(r) for r in rows]
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size,
                             total_pages=(total + page_size - 1) // page_size)


@router.post("/", response_model=SupplierInDB)
async def create_supplier(
    data: SupplierCreate,
    db:   Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    s = Supplier(tenant_id=resolve_tenant_id(db, current_user), **data.model_dump())
    db.add(s)
    db.commit()
    db.refresh(s)
    return SupplierInDB.model_validate(s)


@router.get("/debt-summary", response_model=list)
async def debt_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports")),
):
    """Barcha firmalar qarz holati (qizil = muddati o'tgan)"""
    from datetime import timedelta
    suppliers = (
        apply_tenant_filter(db.query(Supplier), Supplier, current_user)
        .filter(Supplier.is_active == True)
        .order_by(Supplier.name)
        .all()
    )
    today = Date.today()
    result = []
    for s in suppliers:
        confirmed = [r for r in s.purchase_receipts if r.status in ("confirmed", "paid")]
        total_purchases = sum(r.net_amount for r in confirmed)
        last_purchase   = max((r.receipt_date for r in confirmed), default=None)

        # B2B to'lovlar: receipt_id bor to'lovlar
        b2b_pays = db.query(SupplierPayment).filter(
            SupplierPayment.supplier_id == s.id,
            SupplierPayment.receipt_id.isnot(None),
        ).all()
        total_paid     = sum(p.amount for p in b2b_pays)
        total_returned = sum(r.total_amount for r in s.supplier_returns)
        debt = max(0.0, total_purchases - total_paid - total_returned)

        # Muddati o'tgan
        overdue = 0.0
        for rec in confirmed:
            if rec.status != "paid":
                due = rec.receipt_date + timedelta(days=s.payment_delay_days or 0)
                if due < today:
                    paid_for_rec = sum(p.amount for p in b2b_pays if p.receipt_id == rec.id)
                    overdue += max(0.0, rec.net_amount - paid_for_rec)

        result.append(SupplierDebtSummary(
            supplier_id=s.id,
            supplier_name=s.name,
            phone=s.phone,
            total_purchases=total_purchases,
            total_paid=total_paid,
            total_returned=total_returned,
            debt=debt,
            overdue_amount=overdue,
            last_purchase=str(last_purchase) if last_purchase else None,
        ).model_dump())
    return result


@router.get("/{supplier_id}", response_model=SupplierInDB)
async def get_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    s = apply_tenant_filter(db.query(Supplier), Supplier, current_user) \
          .filter(Supplier.id == supplier_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Firma topilmadi")
    return SupplierInDB.model_validate(s)


@router.patch("/{supplier_id}", response_model=SupplierInDB)
async def update_supplier(
    supplier_id: int,
    data: SupplierUpdate,
    db:   Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    s = apply_tenant_filter(db.query(Supplier), Supplier, current_user) \
          .filter(Supplier.id == supplier_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Firma topilmadi")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(s, k, v)
    db.commit()
    db.refresh(s)
    return SupplierInDB.model_validate(s)


@router.delete("/{supplier_id}", response_model=MessageResponse)
async def delete_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    s = apply_tenant_filter(db.query(Supplier), Supplier, current_user) \
          .filter(Supplier.id == supplier_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Firma topilmadi")
    s.is_active = False
    db.commit()
    return MessageResponse(message="Firma arxivlandi")
