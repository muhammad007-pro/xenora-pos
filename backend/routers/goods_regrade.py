"""
Peresort router — BOSQICH 25
Xato kirimni tuzatish: A tovarni B tovarga o'zgartirish.
Confirm bo'lganda: A inventory kamayadi, B inventory ortadi.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date as Date, datetime
from typing import Optional

from database import get_db
from models import GoodsRegrade, GoodsRegradeItem, Inventory, User
from schemas import (
    GoodsRegradeCreate, GoodsRegradeInDB, GoodsRegradeItemInDB,
    PaginatedResponse, MessageResponse,
)
from deps import resolve_tenant_id, get_current_active_user, apply_tenant_filter

from deps import require_feature  # funksiya-flag himoyasi (O'ZGARISH 3)
router = APIRouter(dependencies=[Depends(require_feature("goods_regrade"))])


def _enrich_item(item: GoodsRegradeItem) -> GoodsRegradeItemInDB:
    d = GoodsRegradeItemInDB.model_validate(item)
    d.from_product_name = item.from_product.name if item.from_product else None
    d.to_product_name   = item.to_product.name   if item.to_product   else None
    return d


def _enrich(gr: GoodsRegrade) -> GoodsRegradeInDB:
    d = GoodsRegradeInDB.model_validate(gr)
    d.items = [_enrich_item(i) for i in gr.items]
    return d


@router.get("/", response_model=PaginatedResponse)
async def list_regrades(
    status:    Optional[str] = None,
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    page:      int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    q = apply_tenant_filter(db.query(GoodsRegrade), GoodsRegrade, current_user)
    if status:    q = q.filter(GoodsRegrade.status == status)
    if date_from: q = q.filter(GoodsRegrade.regrade_date >= date_from)
    if date_to:   q = q.filter(GoodsRegrade.regrade_date <= date_to)
    total = q.count()
    rows  = q.order_by(GoodsRegrade.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    return PaginatedResponse(items=[_enrich(r) for r in rows], total=total,
                             page=page, page_size=page_size,
                             total_pages=(total+page_size-1)//page_size)


@router.post("/", response_model=GoodsRegradeInDB)
async def create_regrade(
    data: GoodsRegradeCreate,
    db:   Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not data.items:
        raise HTTPException(status_code=400, detail="Kamida 1 ta qator kiritilsin")
    for it in data.items:
        if it.from_product_id == it.to_product_id:
            raise HTTPException(status_code=400, detail="Bir xil tovarlar o'rtasida peresort bo'lmaydi")

    gr = GoodsRegrade(
        tenant_id    = resolve_tenant_id(db, current_user),
        regrade_date = Date.fromisoformat(data.regrade_date),
        notes        = data.notes,
        created_by   = current_user.id,
    )
    db.add(gr)
    db.flush()
    for it in data.items:
        db.add(GoodsRegradeItem(
            regrade_id      = gr.id,
            from_product_id = it.from_product_id,
            to_product_id   = it.to_product_id,
            quantity        = it.quantity,
            notes           = it.notes,
        ))
    db.commit()
    db.refresh(gr)
    return _enrich(gr)


@router.get("/{regrade_id}", response_model=GoodsRegradeInDB)
async def get_regrade(
    regrade_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    gr = apply_tenant_filter(db.query(GoodsRegrade), GoodsRegrade, current_user) \
             .filter(GoodsRegrade.id == regrade_id).first()
    if not gr:
        raise HTTPException(status_code=404, detail="Peresort topilmadi")
    return _enrich(gr)


@router.post("/{regrade_id}/confirm", response_model=GoodsRegradeInDB)
async def confirm_regrade(
    regrade_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Peresortni tasdiqlash: A inventorydan ayir, B inventoryga qo'sh"""
    gr = apply_tenant_filter(db.query(GoodsRegrade), GoodsRegrade, current_user) \
             .filter(GoodsRegrade.id == regrade_id).first()
    if not gr:
        raise HTTPException(status_code=404, detail="Peresort topilmadi")
    if gr.status == "confirmed":
        raise HTTPException(status_code=400, detail="Allaqachon tasdiqlangan")

    for item in gr.items:
        # A tovardan ayir
        inv_from = apply_tenant_filter(db.query(Inventory), Inventory, current_user) \
                       .filter(Inventory.product_id == item.from_product_id).first()
        if inv_from:
            inv_from.quantity = max(0, inv_from.quantity - item.quantity)

        # B tovarga qo'sh
        inv_to = apply_tenant_filter(db.query(Inventory), Inventory, current_user) \
                     .filter(Inventory.product_id == item.to_product_id).first()
        if inv_to:
            inv_to.quantity += item.quantity
        else:
            tid = resolve_tenant_id(db, current_user)
            db.add(Inventory(
                tenant_id  = tid,
                product_id = item.to_product_id,
                quantity   = item.quantity,
            ))

    gr.status       = "confirmed"
    gr.confirmed_by = current_user.id
    gr.confirmed_at = datetime.utcnow()
    db.commit()
    db.refresh(gr)
    return _enrich(gr)


@router.delete("/{regrade_id}", response_model=MessageResponse)
async def delete_regrade(
    regrade_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    gr = apply_tenant_filter(db.query(GoodsRegrade), GoodsRegrade, current_user) \
             .filter(GoodsRegrade.id == regrade_id).first()
    if not gr:
        raise HTTPException(status_code=404, detail="Peresort topilmadi")
    if gr.status == "confirmed":
        raise HTTPException(status_code=400, detail="Tasdiqlangan peresortni o'chirish mumkin emas")
    db.delete(gr)
    db.commit()
    return MessageResponse(message="Peresort o'chirildi")
