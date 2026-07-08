"""
Dori Partiyasi / Seriya Nazorati — BOSQICH 22 (Dorixona)
Har dori uchun alohida partiya: seriya, muddati, miqdori.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import date, timedelta
from typing import Optional, List

from database import get_db
from models import ProductBatch, Product, User
from schemas import (
    ProductBatchCreate, ProductBatchUpdate, ProductBatchInDB,
    PaginatedResponse, MessageResponse, ExpiryReportItem,
)
from deps import (
    get_current_active_user, apply_tenant_filter, resolve_tenant_id,
)

router = APIRouter()


def _get_batch(db: Session, batch_id: int, current_user: User) -> ProductBatch:
    b = (
        apply_tenant_filter(db.query(ProductBatch), ProductBatch, current_user)
        .filter(ProductBatch.id == batch_id)
        .first()
    )
    if not b:
        raise HTTPException(status_code=404, detail="Partiya topilmadi")
    return b


@router.get("/", response_model=PaginatedResponse)
async def list_batches(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    product_id: Optional[int] = None,
    expiring_in_days: Optional[int] = None,
    is_active: Optional[bool] = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    q = apply_tenant_filter(db.query(ProductBatch), ProductBatch, current_user)

    if product_id:
        q = q.filter(ProductBatch.product_id == product_id)
    if is_active is not None:
        q = q.filter(ProductBatch.is_active == is_active)
    if expiring_in_days is not None:
        cutoff = date.today() + timedelta(days=expiring_in_days)
        q = q.filter(ProductBatch.expiry_date <= cutoff)

    total = q.count()
    rows = q.order_by(ProductBatch.expiry_date.asc()).offset((page - 1) * page_size).limit(page_size).all()
    items = [ProductBatchInDB.model_validate(r) for r in rows]
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size,
                             total_pages=(total + page_size - 1) // page_size)


@router.post("/", response_model=ProductBatchInDB, status_code=201)
async def create_batch(
    data: ProductBatchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    tenant_id = resolve_tenant_id(db, current_user)

    product = (
        apply_tenant_filter(db.query(Product), Product, current_user)
        .filter(Product.id == data.product_id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")

    batch = ProductBatch(
        tenant_id=tenant_id,
        branch_id=data.branch_id or current_user.branch_id,
        product_id=data.product_id,
        batch_number=data.batch_number,
        manufacturer=data.manufacturer,
        manufacture_date=data.manufacture_date,
        expiry_date=data.expiry_date,
        quantity=data.quantity,
        initial_quantity=data.quantity,
        cost_price=data.cost_price,
        notes=data.notes,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


@router.get("/expiry-report", response_model=List[ExpiryReportItem])
async def expiry_report(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """30 kun ichida muddati tugaydigan va tugagan partiyalar ro'yxati"""
    today = date.today()
    cutoff = today + timedelta(days=days)

    batches = (
        apply_tenant_filter(db.query(ProductBatch), ProductBatch, current_user)
        .filter(
            ProductBatch.is_active == True,
            ProductBatch.expiry_date <= cutoff,
            ProductBatch.quantity > 0,
        )
        .order_by(ProductBatch.expiry_date.asc())
        .all()
    )

    result = []
    for b in batches:
        days_left = (b.expiry_date - today).days
        if days_left < 0:
            status = "expired"
        elif days_left <= 7:
            status = "critical"
        elif days_left <= 30:
            status = "warning"
        else:
            status = "ok"

        result.append(ExpiryReportItem(
            product_id=b.product_id,
            product_name=b.product.name if b.product else f"ID:{b.product_id}",
            batch_number=b.batch_number,
            expiry_date=b.expiry_date,
            days_left=days_left,
            quantity=b.quantity,
            status=status,
        ))
    return result


@router.get("/{batch_id}", response_model=ProductBatchInDB)
async def get_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return _get_batch(db, batch_id, current_user)


@router.put("/{batch_id}", response_model=ProductBatchInDB)
async def update_batch(
    batch_id: int,
    data: ProductBatchUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    batch = _get_batch(db, batch_id, current_user)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(batch, field, value)
    db.commit()
    db.refresh(batch)
    return batch


@router.delete("/{batch_id}", response_model=MessageResponse)
async def delete_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    batch = _get_batch(db, batch_id, current_user)
    batch.is_active = False
    db.commit()
    return {"message": "Partiya o'chirildi"}


@router.post("/check-and-disable-expired")
async def disable_expired_batches(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Muddati tugagan partiyalarni avtomatik o'chiradi (cron yoki qo'lda)"""
    today = date.today()
    expired = (
        apply_tenant_filter(db.query(ProductBatch), ProductBatch, current_user)
        .filter(ProductBatch.expiry_date < today, ProductBatch.is_active == True)
        .all()
    )
    count = 0
    for b in expired:
        b.is_active = False
        count += 1
    db.commit()
    return {"disabled_count": count, "message": f"{count} ta muddati tugagan partiya o'chirildi"}
