"""
Utilizatsiya / Spisaniye router — BOSQICH 25
Tovarni hisobdan chiqarish: buzilgan, muddati tugagan, o'g'irlik, brak.
Confirm bo'lganda inventory kamayadi, zarar hisobotga tushadi.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date as Date, datetime
from typing import Optional

from database import get_db
from models import WriteOff, WriteOffItem, Inventory, Product, User
from schemas import WriteOffCreate, WriteOffInDB, WriteOffItemInDB, PaginatedResponse, MessageResponse
from deps import resolve_tenant_id, get_current_active_user, apply_tenant_filter, has_permission

from deps import require_feature  # funksiya-flag himoyasi (O'ZGARISH 3)
router = APIRouter(dependencies=[Depends(require_feature("write_off"))])


def _gen_act_number(db: Session) -> str:
    count = db.query(WriteOff).count()
    return f"WO-{count + 1:05d}"


def _enrich_item(item: WriteOffItem) -> WriteOffItemInDB:
    d = WriteOffItemInDB.model_validate(item)
    d.product_name = item.product.name if item.product else None
    return d


def _enrich(wo: WriteOff) -> WriteOffInDB:
    d = WriteOffInDB.model_validate(wo)
    d.items = [_enrich_item(i) for i in wo.items]
    return d


@router.get("/", response_model=PaginatedResponse)
async def list_write_offs(
    reason:    Optional[str] = None,
    status:    Optional[str] = None,
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    page:      int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    q = apply_tenant_filter(db.query(WriteOff), WriteOff, current_user)
    if reason:    q = q.filter(WriteOff.reason == reason)
    if status:    q = q.filter(WriteOff.status == status)
    if date_from: q = q.filter(WriteOff.write_off_date >= date_from)
    if date_to:   q = q.filter(WriteOff.write_off_date <= date_to)
    total = q.count()
    rows  = q.order_by(WriteOff.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    return PaginatedResponse(items=[_enrich(r) for r in rows], total=total,
                             page=page, page_size=page_size,
                             total_pages=(total+page_size-1)//page_size)


@router.post("/", response_model=WriteOffInDB)
async def create_write_off(
    data: WriteOffCreate,
    db:   Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_inventory")),
):
    if not data.items:
        raise HTTPException(status_code=400, detail="Kamida 1 ta tovar kiritilsin")
    wo = WriteOff(
        tenant_id      = resolve_tenant_id(db, current_user),
        act_number     = _gen_act_number(db),
        reason         = data.reason,
        write_off_date = Date.fromisoformat(data.write_off_date),
        notes          = data.notes,
        created_by     = current_user.id,
    )
    db.add(wo)
    db.flush()
    total = 0.0
    for it in data.items:
        loss = it.quantity * it.cost_price
        total += loss
        db.add(WriteOffItem(
            write_off_id = wo.id,
            product_id   = it.product_id,
            quantity     = it.quantity,
            cost_price   = it.cost_price,
            total_loss   = loss,
            notes        = it.notes,
        ))
    wo.total_loss = total
    db.commit()
    db.refresh(wo)
    return _enrich(wo)


@router.get("/{write_off_id}", response_model=WriteOffInDB)
async def get_write_off(
    write_off_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    wo = apply_tenant_filter(db.query(WriteOff), WriteOff, current_user) \
             .filter(WriteOff.id == write_off_id).first()
    if not wo:
        raise HTTPException(status_code=404, detail="Akt topilmadi")
    return _enrich(wo)


@router.post("/{write_off_id}/confirm", response_model=WriteOffInDB)
async def confirm_write_off(
    write_off_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_inventory")),
):
    """Aktni tasdiqlash: inventory'dan chiqarish"""
    wo = apply_tenant_filter(db.query(WriteOff), WriteOff, current_user) \
             .filter(WriteOff.id == write_off_id).first()
    if not wo:
        raise HTTPException(status_code=404, detail="Akt topilmadi")
    if wo.status == "confirmed":
        raise HTTPException(status_code=400, detail="Akt allaqachon tasdiqlangan")

    for item in wo.items:
        inv = apply_tenant_filter(db.query(Inventory), Inventory, current_user) \
                  .filter(Inventory.product_id == item.product_id).first()
        if inv:
            inv.quantity = max(0, inv.quantity - item.quantity)

    wo.status       = "confirmed"
    wo.confirmed_by = current_user.id
    wo.confirmed_at = datetime.utcnow()
    db.commit()
    db.refresh(wo)
    return _enrich(wo)


@router.delete("/{write_off_id}", response_model=MessageResponse)
async def delete_write_off(
    write_off_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_inventory")),
):
    wo = apply_tenant_filter(db.query(WriteOff), WriteOff, current_user) \
             .filter(WriteOff.id == write_off_id).first()
    if not wo:
        raise HTTPException(status_code=404, detail="Akt topilmadi")
    if wo.status == "confirmed":
        raise HTTPException(status_code=400, detail="Tasdiqlangan aktni o'chirish mumkin emas")
    db.delete(wo)
    db.commit()
    return MessageResponse(message="Akt o'chirildi")
