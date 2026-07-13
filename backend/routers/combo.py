"""
Kombo/Set menyu routeri (BOSQICH 9.4)
Bir nechta mahsulot bitta narxda.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel

from database import get_db
from models import ComboSet, ComboSetItem, Product, User
from deps import resolve_tenant_id, get_current_active_user, apply_tenant_filter, has_permission

router = APIRouter()


class ComboItemIn(BaseModel):
    product_id: int
    quantity: int = 1
    is_replaceable: bool = False


class ComboCreate(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    image_url: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    items: List[ComboItemIn] = []


class ComboItemOut(BaseModel):
    id: int
    product_id: int
    quantity: int
    is_replaceable: bool
    product_name: Optional[str] = None
    product_price: Optional[float] = None
    model_config = {"from_attributes": True}


class ComboOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    price: float
    image_url: Optional[str]
    is_active: bool
    valid_from: Optional[datetime]
    valid_to: Optional[datetime]
    items: List[ComboItemOut] = []
    savings: float = 0.0      # Vычисляется на лету
    model_config = {"from_attributes": True}


def _combo_out(combo: ComboSet) -> dict:
    items_out = []
    total_individual = 0.0
    for ci in combo.items:
        p = ci.product
        items_out.append({
            "id": ci.id,
            "product_id": ci.product_id,
            "quantity": ci.quantity,
            "is_replaceable": ci.is_replaceable,
            "product_name": p.name if p else None,
            "product_price": p.price if p else None,
        })
        if p:
            total_individual += p.price * ci.quantity
    return {
        "id": combo.id,
        "name": combo.name,
        "description": combo.description,
        "price": combo.price,
        "image_url": combo.image_url,
        "is_active": combo.is_active,
        "valid_from": combo.valid_from,
        "valid_to": combo.valid_to,
        "items": items_out,
        "savings": max(0, total_individual - combo.price),
    }


@router.get("/")
async def get_combos(
    is_active: Optional[bool] = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Barcha kombo menyularni olish"""
    q = db.query(ComboSet)
    q = apply_tenant_filter(q, ComboSet, current_user)
    if is_active is not None:
        q = q.filter(ComboSet.is_active == is_active)
    now = datetime.now()
    combos = q.all()
    result = []
    for c in combos:
        if c.valid_from and c.valid_from > now:
            continue
        if c.valid_to and c.valid_to < now:
            continue
        result.append(_combo_out(c))
    return result


@router.post("/")
async def create_combo(
    data: ComboCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu"))
):
    combo = ComboSet(
        tenant_id=resolve_tenant_id(db, current_user),
        name=data.name,
        description=data.description,
        price=data.price,
        image_url=data.image_url,
        valid_from=data.valid_from,
        valid_to=data.valid_to,
    )
    db.add(combo)
    db.flush()
    for item in data.items:
        ci = ComboSetItem(
            combo_id=combo.id,
            product_id=item.product_id,
            quantity=item.quantity,
            is_replaceable=item.is_replaceable,
        )
        db.add(ci)
    db.commit()
    db.refresh(combo)
    return _combo_out(combo)


@router.get("/{combo_id}")
async def get_combo(
    combo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    combo = db.query(ComboSet).filter(ComboSet.id == combo_id).first()
    if not combo:
        raise HTTPException(404, "Kombo topilmadi")
    return _combo_out(combo)


@router.patch("/{combo_id}")
async def update_combo(
    combo_id: int,
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu"))
):
    combo = db.query(ComboSet).filter(ComboSet.id == combo_id).first()
    if not combo:
        raise HTTPException(404, "Kombo topilmadi")
    allowed = {"name", "description", "price", "image_url", "is_active", "valid_from", "valid_to"}
    for k, v in data.items():
        if k in allowed:
            setattr(combo, k, v)
    db.commit()
    db.refresh(combo)
    return _combo_out(combo)


@router.delete("/{combo_id}")
async def delete_combo(
    combo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu"))
):
    combo = db.query(ComboSet).filter(ComboSet.id == combo_id).first()
    if not combo:
        raise HTTPException(404, "Kombo topilmadi")
    combo.is_active = False
    db.commit()
    return {"success": True}
