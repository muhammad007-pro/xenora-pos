"""
Naценka siyosati router — BOSQICH 26
Tan narxга markup foizi qo'yib sotuv narxini avtomatik hisoblash.
Apply qilinganda Product.price yangilanadi + PriceHistory yoziladi.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from database import get_db
from models import MarkupPolicy, Product, Category, PriceHistory, User
from schemas import (
    MarkupPolicyCreate, MarkupPolicyUpdate, MarkupPolicyInDB,
    MarkupApplyRequest, PaginatedResponse, MessageResponse,
)
from deps import resolve_tenant_id, get_current_active_user, apply_tenant_filter

router = APIRouter()


def _enrich(p: MarkupPolicy) -> MarkupPolicyInDB:
    d = MarkupPolicyInDB.model_validate(p)
    d.category_name = p.category.name if p.category else None
    d.product_name  = p.product.name  if p.product  else None
    return d


@router.get("/", response_model=PaginatedResponse)
async def list_policies(
    scope:     Optional[str]  = None,
    is_active: Optional[bool] = None,
    page:      int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    q = apply_tenant_filter(db.query(MarkupPolicy), MarkupPolicy, current_user)
    if scope:              q = q.filter(MarkupPolicy.scope == scope)
    if is_active is not None: q = q.filter(MarkupPolicy.is_active == is_active)
    total = q.count()
    rows  = q.order_by(MarkupPolicy.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    return PaginatedResponse(items=[_enrich(r) for r in rows], total=total,
                             page=page, page_size=page_size,
                             total_pages=(total+page_size-1)//page_size)


@router.post("/", response_model=MarkupPolicyInDB)
async def create_policy(
    data: MarkupPolicyCreate,
    db:   Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    mp = MarkupPolicy(
        tenant_id   = resolve_tenant_id(db, current_user),
        name        = data.name,
        scope       = data.scope,
        category_id = data.category_id,
        product_id  = data.product_id,
        markup_pct  = data.markup_pct,
        min_price   = data.min_price,
        is_active   = data.is_active,
        created_by  = current_user.id,
    )
    db.add(mp); db.commit(); db.refresh(mp)
    return _enrich(mp)


@router.patch("/{policy_id}", response_model=MarkupPolicyInDB)
async def update_policy(
    policy_id: int,
    data: MarkupPolicyUpdate,
    db:   Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    mp = apply_tenant_filter(db.query(MarkupPolicy), MarkupPolicy, current_user) \
             .filter(MarkupPolicy.id == policy_id).first()
    if not mp:
        raise HTTPException(status_code=404, detail="Siyosat topilmadi")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(mp, k, v)
    db.commit(); db.refresh(mp)
    return _enrich(mp)


@router.delete("/{policy_id}", response_model=MessageResponse)
async def delete_policy(
    policy_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    mp = apply_tenant_filter(db.query(MarkupPolicy), MarkupPolicy, current_user) \
             .filter(MarkupPolicy.id == policy_id).first()
    if not mp:
        raise HTTPException(status_code=404, detail="Siyosat topilmadi")
    db.delete(mp); db.commit()
    return MessageResponse(message="Siyosat o'chirildi")


@router.post("/apply", response_model=MessageResponse)
async def apply_markup(
    data: MarkupApplyRequest,
    db:   Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Naценka siyosatini mahsulotlarga qo'llash:
    price = cost_price * (1 + markup_pct/100), lekin min_price dan past bo'lmaydi.
    Har o'zgarish PriceHistory ga yoziladi.
    """
    mp = apply_tenant_filter(db.query(MarkupPolicy), MarkupPolicy, current_user) \
             .filter(MarkupPolicy.id == data.policy_id).first()
    if not mp:
        raise HTTPException(status_code=404, detail="Siyosat topilmadi")

    tid = resolve_tenant_id(db, current_user)
    q   = apply_tenant_filter(db.query(Product), Product, current_user)

    if data.product_ids:
        q = q.filter(Product.id.in_(data.product_ids))
    elif mp.scope == "product" and mp.product_id:
        q = q.filter(Product.id == mp.product_id)
    elif mp.scope == "category" and mp.category_id:
        q = q.filter(Product.category_id == mp.category_id)
    # global → hammasi

    products = q.all()
    updated  = 0
    for prod in products:
        cost = getattr(prod, "cost_price", None) or 0
        if not cost:
            continue
        new_price = round(cost * (1 + mp.markup_pct / 100), 0)
        if mp.min_price and new_price < mp.min_price:
            new_price = mp.min_price
        if new_price == prod.price:
            continue
        db.add(PriceHistory(
            tenant_id  = tid,
            product_id = prod.id,
            old_price  = prod.price,
            new_price  = new_price,
            old_cost   = cost,
            new_cost   = cost,
            reason     = f"Markup siyosati: {mp.name} ({mp.markup_pct}%)",
            changed_by = current_user.id,
        ))
        prod.price = new_price
        updated += 1

    db.commit()
    return MessageResponse(message=f"{updated} ta tovar narxi yangilandi")


@router.get("/preview/{policy_id}")
async def preview_markup(
    policy_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Apply qilmasdan narx hisoblashni ko'rish"""
    mp = apply_tenant_filter(db.query(MarkupPolicy), MarkupPolicy, current_user) \
             .filter(MarkupPolicy.id == policy_id).first()
    if not mp:
        raise HTTPException(status_code=404, detail="Siyosat topilmadi")

    q = apply_tenant_filter(db.query(Product), Product, current_user)
    if mp.scope == "product" and mp.product_id:
        q = q.filter(Product.id == mp.product_id)
    elif mp.scope == "category" and mp.category_id:
        q = q.filter(Product.category_id == mp.category_id)

    result = []
    for prod in q.limit(100).all():
        cost = getattr(prod, "cost_price", None) or 0
        new_price = round(cost * (1 + mp.markup_pct / 100), 0) if cost else prod.price
        if mp.min_price and new_price < mp.min_price:
            new_price = mp.min_price
        result.append({
            "id":          prod.id,
            "name":        prod.name,
            "cost_price":  cost,
            "old_price":   prod.price,
            "new_price":   new_price,
            "diff":        round(new_price - prod.price, 0),
            "will_change": new_price != prod.price,
        })
    return result
