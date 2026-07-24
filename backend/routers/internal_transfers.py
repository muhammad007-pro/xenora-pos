"""
Ichki ko'chirish router — BOSQICH 25
Filiallar orasida tovar harakati.
Confirm bo'lganda: from_branch inventorydan chiqadi, to_branch inventoryga kiradi.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date as Date, datetime
from typing import Optional

from database import get_db
from models import InternalTransfer, InternalTransferItem, Inventory, Branch, User
from schemas import (
    InternalTransferCreate, InternalTransferInDB, InternalTransferItemInDB,
    PaginatedResponse, MessageResponse,
)
from deps import resolve_tenant_id, get_current_active_user, apply_tenant_filter, has_permission

from deps import require_feature  # funksiya-flag himoyasi (O'ZGARISH 3)
router = APIRouter(dependencies=[Depends(require_feature("internal_transfer"))])


def _enrich_item(item: InternalTransferItem) -> InternalTransferItemInDB:
    d = InternalTransferItemInDB.model_validate(item)
    d.product_name = item.product.name if item.product else None
    return d


def _enrich(tr: InternalTransfer) -> InternalTransferInDB:
    d = InternalTransferInDB.model_validate(tr)
    d.items = [_enrich_item(i) for i in tr.items]
    d.from_branch_name = tr.from_branch.name if tr.from_branch else None
    d.to_branch_name   = tr.to_branch.name   if tr.to_branch   else None
    return d


@router.get("/", response_model=PaginatedResponse)
async def list_transfers(
    status:         Optional[str] = None,
    from_branch_id: Optional[int] = None,
    to_branch_id:   Optional[int] = None,
    date_from:      Optional[str] = None,
    date_to:        Optional[str] = None,
    page:           int = Query(1, ge=1),
    page_size:      int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    q = apply_tenant_filter(db.query(InternalTransfer), InternalTransfer, current_user)
    if status:         q = q.filter(InternalTransfer.status == status)
    if from_branch_id: q = q.filter(InternalTransfer.from_branch_id == from_branch_id)
    if to_branch_id:   q = q.filter(InternalTransfer.to_branch_id == to_branch_id)
    if date_from:      q = q.filter(InternalTransfer.transfer_date >= date_from)
    if date_to:        q = q.filter(InternalTransfer.transfer_date <= date_to)
    total = q.count()
    rows  = q.order_by(InternalTransfer.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    return PaginatedResponse(items=[_enrich(r) for r in rows], total=total,
                             page=page, page_size=page_size,
                             total_pages=(total+page_size-1)//page_size)


@router.post("/", response_model=InternalTransferInDB)
async def create_transfer(
    data: InternalTransferCreate,
    db:   Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_inventory")),
):
    if not data.items:
        raise HTTPException(status_code=400, detail="Kamida 1 ta tovar kiritilsin")
    if data.from_branch_id and data.to_branch_id and data.from_branch_id == data.to_branch_id:
        raise HTTPException(status_code=400, detail="Bir xil filiallar orasida ko'chirish mumkin emas")

    tr = InternalTransfer(
        tenant_id      = resolve_tenant_id(db, current_user),
        from_branch_id = data.from_branch_id,
        to_branch_id   = data.to_branch_id,
        transfer_date  = Date.fromisoformat(data.transfer_date),
        notes          = data.notes,
        created_by     = current_user.id,
    )
    db.add(tr)
    db.flush()
    for it in data.items:
        db.add(InternalTransferItem(
            transfer_id = tr.id,
            product_id  = it.product_id,
            quantity    = it.quantity,
            cost_price  = it.cost_price,
        ))
    db.commit()
    db.refresh(tr)
    return _enrich(tr)


@router.get("/{transfer_id}", response_model=InternalTransferInDB)
async def get_transfer(
    transfer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    tr = apply_tenant_filter(db.query(InternalTransfer), InternalTransfer, current_user) \
             .filter(InternalTransfer.id == transfer_id).first()
    if not tr:
        raise HTTPException(status_code=404, detail="Ko'chirma topilmadi")
    return _enrich(tr)


@router.post("/{transfer_id}/confirm", response_model=InternalTransferInDB)
async def confirm_transfer(
    transfer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_inventory")),
):
    """Ko'chirmani tasdiqlash: from_branch → to_branch inventory yangilanadi"""
    tr = apply_tenant_filter(db.query(InternalTransfer), InternalTransfer, current_user) \
             .filter(InternalTransfer.id == transfer_id).first()
    if not tr:
        raise HTTPException(status_code=404, detail="Ko'chirma topilmadi")
    if tr.status == "confirmed":
        raise HTTPException(status_code=400, detail="Allaqachon tasdiqlangan")

    tid = resolve_tenant_id(db, current_user)

    for item in tr.items:
        # From branch — tovar chiqadi
        if tr.from_branch_id:
            inv_from = db.query(Inventory).filter(
                Inventory.product_id == item.product_id,
                Inventory.branch_id  == tr.from_branch_id,
            ).with_for_update().first()   # ROW-LOCK
            if not inv_from:
                inv_from = db.query(Inventory).filter(
                    Inventory.product_id == item.product_id,
                    Inventory.tenant_id  == tid,
                ).with_for_update().first()   # ROW-LOCK
            if inv_from:
                inv_from.quantity = max(0, inv_from.quantity - item.quantity)

        # To branch — tovar kiradi
        if tr.to_branch_id:
            inv_to = db.query(Inventory).filter(
                Inventory.product_id == item.product_id,
                Inventory.branch_id  == tr.to_branch_id,
            ).with_for_update().first()   # ROW-LOCK
            if inv_to:
                inv_to.quantity += item.quantity
            else:
                db.add(Inventory(
                    tenant_id  = tid,
                    branch_id  = tr.to_branch_id,
                    product_id = item.product_id,
                    quantity   = item.quantity,
                ))

    tr.status       = "confirmed"
    tr.confirmed_by = current_user.id
    tr.confirmed_at = datetime.utcnow()
    db.commit()
    db.refresh(tr)
    return _enrich(tr)


@router.delete("/{transfer_id}", response_model=MessageResponse)
async def delete_transfer(
    transfer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_inventory")),
):
    tr = apply_tenant_filter(db.query(InternalTransfer), InternalTransfer, current_user) \
             .filter(InternalTransfer.id == transfer_id).first()
    if not tr:
        raise HTTPException(status_code=404, detail="Ko'chirma topilmadi")
    if tr.status == "confirmed":
        raise HTTPException(status_code=400, detail="Tasdiqlangan ko'chirmani o'chirish mumkin emas")
    db.delete(tr)
    db.commit()
    return MessageResponse(message="Ko'chirma o'chirildi")
