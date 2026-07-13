"""
Modifikatorlar routeri (BOSQICH 9.3)
Mahsulot o'lchami, o'tkirlik, qo'shimcha ingredientlar uchun.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel

from database import get_db
from models import ProductModifierGroup, ProductModifier, User
from deps import resolve_tenant_id, get_current_active_user, apply_tenant_filter, has_permission

router = APIRouter()


class ModifierCreate(BaseModel):
    name: str
    price_delta: float = 0.0
    is_default: bool = False
    display_order: int = 0


class ModifierGroupCreate(BaseModel):
    name: str
    product_id: Optional[int] = None
    type: str = "single"           # single | multiple
    is_required: bool = False
    min_select: int = 0
    max_select: int = 1
    display_order: int = 0
    modifiers: List[ModifierCreate] = []


class ModifierOut(BaseModel):
    id: int
    name: str
    price_delta: float
    is_default: bool
    is_active: bool
    display_order: int
    model_config = {"from_attributes": True}


class ModifierGroupOut(BaseModel):
    id: int
    name: str
    product_id: Optional[int]
    type: str
    is_required: bool
    min_select: int
    max_select: int
    is_active: bool
    display_order: int
    modifiers: List[ModifierOut] = []
    model_config = {"from_attributes": True}


@router.get("/groups", response_model=List[ModifierGroupOut])
async def get_modifier_groups(
    product_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Modifikator guruhlarini olish (mahsulotga yoki umumiy)"""
    q = db.query(ProductModifierGroup).filter(ProductModifierGroup.is_active == True)
    q = apply_tenant_filter(q, ProductModifierGroup, current_user)
    if product_id:
        q = q.filter(
            (ProductModifierGroup.product_id == product_id) |
            (ProductModifierGroup.product_id == None)
        )
    return q.order_by(ProductModifierGroup.display_order).all()


@router.post("/groups", response_model=ModifierGroupOut)
async def create_modifier_group(
    data: ModifierGroupCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu"))
):
    """Yangi modifikator guruhi yaratish"""
    group = ProductModifierGroup(
        tenant_id=resolve_tenant_id(db, current_user),
        product_id=data.product_id,
        name=data.name,
        type=data.type,
        is_required=data.is_required,
        min_select=data.min_select,
        max_select=data.max_select,
        display_order=data.display_order,
    )
    db.add(group)
    db.flush()
    for m in data.modifiers:
        mod = ProductModifier(
            tenant_id=resolve_tenant_id(db, current_user),
            group_id=group.id,
            name=m.name,
            price_delta=m.price_delta,
            is_default=m.is_default,
            display_order=m.display_order,
        )
        db.add(mod)
    db.commit()
    db.refresh(group)
    return group


@router.patch("/groups/{group_id}", response_model=ModifierGroupOut)
async def update_modifier_group(
    group_id: int,
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu"))
):
    group = db.query(ProductModifierGroup).filter(ProductModifierGroup.id == group_id).first()
    if not group:
        raise HTTPException(404, "Guruh topilmadi")
    for k, v in data.items():
        if hasattr(group, k):
            setattr(group, k, v)
    db.commit()
    db.refresh(group)
    return group


@router.delete("/groups/{group_id}")
async def delete_modifier_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu"))
):
    group = db.query(ProductModifierGroup).filter(ProductModifierGroup.id == group_id).first()
    if not group:
        raise HTTPException(404, "Guruh topilmadi")
    group.is_active = False
    db.commit()
    return {"success": True}


@router.post("/groups/{group_id}/modifiers", response_model=ModifierOut)
async def add_modifier(
    group_id: int,
    data: ModifierCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu"))
):
    group = db.query(ProductModifierGroup).filter(ProductModifierGroup.id == group_id).first()
    if not group:
        raise HTTPException(404, "Guruh topilmadi")
    mod = ProductModifier(
        tenant_id=resolve_tenant_id(db, current_user),
        group_id=group_id,
        name=data.name,
        price_delta=data.price_delta,
        is_default=data.is_default,
        display_order=data.display_order,
    )
    db.add(mod)
    db.commit()
    db.refresh(mod)
    return mod


@router.patch("/modifiers/{modifier_id}", response_model=ModifierOut)
async def update_modifier(
    modifier_id: int,
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu"))
):
    mod = db.query(ProductModifier).filter(ProductModifier.id == modifier_id).first()
    if not mod:
        raise HTTPException(404, "Modifikator topilmadi")
    for k, v in data.items():
        if hasattr(mod, k):
            setattr(mod, k, v)
    db.commit()
    db.refresh(mod)
    return mod


@router.delete("/modifiers/{modifier_id}")
async def delete_modifier(
    modifier_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu"))
):
    mod = db.query(ProductModifier).filter(ProductModifier.id == modifier_id).first()
    if not mod:
        raise HTTPException(404, "Modifikator topilmadi")
    mod.is_active = False
    db.commit()
    return {"success": True}
