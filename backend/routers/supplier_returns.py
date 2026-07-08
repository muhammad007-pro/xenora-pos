"""
Firmaga qaytarish (vozvrat) router — BOSQICH 24 (B2B)
Qaytarilganда: ombor -qty, firma qarzidan -summa.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from database import get_db
from models import SupplierReturn, Supplier, Product, Inventory, User
from schemas import (
    SupplierReturnCreate, SupplierReturnInDB,
    PaginatedResponse, MessageResponse,
)
from deps import resolve_tenant_id, get_current_active_user, apply_tenant_filter

router = APIRouter()


def _enrich_return(r: SupplierReturn) -> dict:
    return {
        "id":           r.id,
        "tenant_id":    r.tenant_id,
        "supplier_id":  r.supplier_id,
        "product_id":   r.product_id,
        "product_name": r.product.name if r.product else None,
        "quantity":     r.quantity,
        "unit_price":   r.unit_price,
        "total_amount": r.total_amount,
        "return_date":  str(r.return_date),
        "reason":       r.reason,
        "notes":        r.notes,
        "created_at":   r.created_at,
    }


@router.get("/")
async def list_returns(
    supplier_id: Optional[int] = None,
    date_from:   Optional[str] = None,
    date_to:     Optional[str] = None,
    page:        int = Query(1, ge=1),
    page_size:   int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    q = apply_tenant_filter(db.query(SupplierReturn), SupplierReturn, current_user)
    if supplier_id:
        q = q.filter(SupplierReturn.supplier_id == supplier_id)
    if date_from:
        q = q.filter(SupplierReturn.return_date >= date_from)
    if date_to:
        q = q.filter(SupplierReturn.return_date <= date_to)
    total = q.count()
    rows  = q.order_by(SupplierReturn.return_date.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items":       [_enrich_return(r) for r in rows],
        "total":       total,
        "page":        page,
        "page_size":   page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.post("/")
async def create_return(
    data: SupplierReturnCreate,
    db:   Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Firmaga vozvrat: ombor kamayadi, firma qarzidan ayriladi"""
    supplier = apply_tenant_filter(db.query(Supplier), Supplier, current_user) \
                   .filter(Supplier.id == data.supplier_id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Firma topilmadi")

    product = db.query(Product).filter(Product.id == data.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")

    tid = resolve_tenant_id(db, current_user)

    # Ombordan kamaytirish
    inv = db.query(Inventory).filter(
        Inventory.product_id == data.product_id,
        Inventory.tenant_id == tid,
    ).first()
    if inv:
        if inv.quantity < data.quantity:
            raise HTTPException(status_code=400, detail=f"Omborda yetarli miqdor yo'q (mavjud: {inv.quantity})")
        inv.quantity -= data.quantity

    ret = SupplierReturn(
        tenant_id=tid,
        created_by=current_user.id,
        total_amount=data.quantity * data.unit_price,
        **data.model_dump(),
    )
    db.add(ret)
    db.commit()
    db.refresh(ret)
    return _enrich_return(ret)


@router.get("/{return_id}")
async def get_return(
    return_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    r = apply_tenant_filter(db.query(SupplierReturn), SupplierReturn, current_user) \
          .filter(SupplierReturn.id == return_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Vozvrat topilmadi")
    return _enrich_return(r)


@router.delete("/{return_id}", response_model=MessageResponse)
async def delete_return(
    return_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    r = apply_tenant_filter(db.query(SupplierReturn), SupplierReturn, current_user) \
          .filter(SupplierReturn.id == return_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Vozvrat topilmadi")
    db.delete(r)
    db.commit()
    return MessageResponse(message="Vozvrat o'chirildi")
