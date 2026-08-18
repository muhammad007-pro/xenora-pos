"""
Yetkazib beruvchilar (Suppliers) router — BOSQICH 24 (B2B)
Firma kartochkasi: INN (tax_id), telefon, manzil, shartnoma, otsrochka, mas'ul shaxs.
Qarz summary hisoblash: priyomkalar - to'lovlar - vozvratlар.
FAZA 1: hisobning O'ZI services/supplier_debt.py ga ko'chirildi (yagona manba).
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from database import get_db
from models import Supplier, User
from schemas import (
    SupplierCreate, SupplierUpdate, SupplierInDB,
    SupplierDebtSummary, PaginatedResponse, MessageResponse,
)
from deps import resolve_tenant_id, get_current_active_user, apply_tenant_filter, has_permission
from services.supplier_debt import compute_debts

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
    current_user: User = Depends(has_permission("manage_inventory")),
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
    """Barcha firmalar qarz holati (qizil = muddati o'tgan)

    Hisob services/supplier_debt.py da — /store-dashboard ham SHU servisni
    chaqiradi, ya'ni ikki ekran endi bir xil son ko'rsatadi.
    """
    suppliers = (
        apply_tenant_filter(db.query(Supplier), Supplier, current_user)
        .filter(Supplier.is_active == True)
        .order_by(Supplier.name)
        .all()
    )
    debts = compute_debts(db, suppliers)
    result = []
    for s in suppliers:
        d = debts[s.id]
        result.append(SupplierDebtSummary(
            supplier_id=d.supplier_id,
            supplier_name=d.supplier_name,
            phone=d.phone,
            total_purchases=d.total_purchases,
            total_paid=d.total_paid,
            total_returned=d.total_returned,
            debt=d.debt,
            advance=d.advance,
            balance=d.balance,
            opening_debt=d.opening_debt,
            overdue_amount=d.overdue_amount,
            last_purchase=str(d.last_purchase) if d.last_purchase else None,
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
    current_user: User = Depends(has_permission("manage_inventory")),
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
    current_user: User = Depends(has_permission("manage_inventory")),
):
    s = apply_tenant_filter(db.query(Supplier), Supplier, current_user) \
          .filter(Supplier.id == supplier_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Firma topilmadi")
    s.is_active = False
    db.commit()
    return MessageResponse(message="Firma arxivlandi")
