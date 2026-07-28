"""Aksiya / Murakkab chegirmalar — buy_x_get_y, flash narx, min summa, vaqt"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional

from database import get_db
from models import Promotion, Product, Category, User
from deps import resolve_tenant_id, get_current_active_user, has_permission, apply_tenant_filter

router = APIRouter()


@router.get("/")
async def get_promotions(
    is_active: Optional[bool] = None,
    promo_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Barcha aksiyalar"""
    q = apply_tenant_filter(db.query(Promotion), Promotion, current_user)
    if is_active is not None:
        q = q.filter(Promotion.is_active == is_active)
    if promo_type:
        q = q.filter(Promotion.promo_type == promo_type)
    total = q.count()
    items = q.order_by(Promotion.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [_promo_dict(p) for p in items], "total": total}


@router.post("/")
async def create_promotion(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_discounts")),
):
    """Yangi aksiya yaratish"""
    tid = resolve_tenant_id(db, current_user)
    allowed = {"name", "promo_type", "product_id", "category_id", "buy_qty",
               "get_qty", "discount_type", "discount_value", "min_purchase_amount",
               "min_purchase_qty", "flash_price", "start_date", "end_date",
               "days_of_week", "time_from", "time_to", "is_active", "usage_limit",
               "free_product_id", "free_qty_per_set"}   # FAZA 3b
    clean = {k: v for k, v in data.items() if k in allowed}

    for field in ("start_date", "end_date"):
        if isinstance(clean.get(field), str):
            try:
                clean[field] = datetime.fromisoformat(clean[field])
            except Exception:
                clean.pop(field, None)

    promo = Promotion(tenant_id=tid, **clean)
    db.add(promo)
    db.commit()
    db.refresh(promo)
    return _promo_dict(promo)


@router.put("/{promo_id}")
async def update_promotion(
    promo_id: int,
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_discounts")),
):
    tid = resolve_tenant_id(db, current_user)
    promo = db.query(Promotion).filter(Promotion.id == promo_id, Promotion.tenant_id == tid).first()
    if not promo:
        raise HTTPException(status_code=404, detail="Aksiya topilmadi")

    allowed = {"name", "is_active", "discount_value", "flash_price", "start_date",
               "end_date", "days_of_week", "time_from", "time_to", "usage_limit",
               "buy_qty", "get_qty", "discount_type", "min_purchase_amount", "min_purchase_qty",
               "free_product_id", "free_qty_per_set"}   # FAZA 3b
    for k, v in data.items():
        if k in allowed:
            if k in ("start_date", "end_date") and isinstance(v, str):
                try:
                    v = datetime.fromisoformat(v)
                except Exception:
                    continue
            setattr(promo, k, v)
    db.commit()
    db.refresh(promo)
    return _promo_dict(promo)


@router.delete("/{promo_id}")
async def delete_promotion(
    promo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_discounts")),
):
    tid = resolve_tenant_id(db, current_user)
    promo = db.query(Promotion).filter(Promotion.id == promo_id, Promotion.tenant_id == tid).first()
    if not promo:
        raise HTTPException(status_code=404, detail="Aksiya topilmadi")
    db.delete(promo)
    db.commit()
    return {"ok": True}


@router.post("/validate")
async def validate_promotions(
    cart: list,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Savat uchun qo'llaniladigan aksiyalarni hisoblash.
    cart = [{"product_id": 1, "qty": 3, "price": 5000}, ...]
    Qaytaradi: applied_promos va har satr uchun free_qty / discount_amount
    """
    tid = resolve_tenant_id(db, current_user)
    now = datetime.now()

    active_promos = db.query(Promotion).filter(
        Promotion.tenant_id == tid,
        Promotion.is_active == True,
    ).all()

    # Vaqt filtri
    def _is_valid(p: Promotion) -> bool:
        if p.start_date and now < p.start_date:
            return False
        if p.end_date and now > p.end_date:
            return False
        if p.time_from and p.time_to:
            cur_time = now.strftime("%H:%M")
            if not (p.time_from <= cur_time <= p.time_to):
                return False
        if p.days_of_week:
            # 1=dushanba ... 7=yakshanba
            allowed_days = p.days_of_week.split(",")
            if str(now.isoweekday()) not in allowed_days:
                return False
        return True

    valid_promos = [p for p in active_promos if _is_valid(p)]

    total_amount = sum(item.get("qty", 1) * item.get("price", 0) for item in cart)
    applied = []
    cart_result = [dict(item) for item in cart]

    for promo in valid_promos:
        if promo.usage_limit and promo.used_count >= promo.usage_limit:
            continue

        if promo.promo_type == "buy_x_get_y":
            for item in cart_result:
                if promo.product_id and item["product_id"] != promo.product_id:
                    continue
                sets = item.get("qty", 1) // (promo.buy_qty + promo.get_qty)
                if sets > 0:
                    free = sets * promo.get_qty
                    item["free_qty"] = item.get("free_qty", 0) + free
                    item["discount_amount"] = item.get("discount_amount", 0) + free * item["price"]
                    applied.append({"promo_id": promo.id, "name": promo.name,
                                    "type": "buy_x_get_y", "free_qty": free})

        elif promo.promo_type == "flash_price" and promo.flash_price is not None:
            for item in cart_result:
                if promo.product_id and item["product_id"] != promo.product_id:
                    continue
                old_price = item["price"]
                diff = (old_price - promo.flash_price) * item.get("qty", 1)
                if diff > 0:
                    item["flash_price"] = promo.flash_price
                    item["discount_amount"] = item.get("discount_amount", 0) + diff
                    applied.append({"promo_id": promo.id, "name": promo.name,
                                    "type": "flash_price", "flash_price": promo.flash_price})

        elif promo.promo_type == "min_amount" and total_amount >= promo.min_purchase_amount:
            for item in cart_result:
                if promo.product_id and item["product_id"] != promo.product_id:
                    continue
                if promo.category_id:
                    pass  # category check requires product lookup
                qty = item.get("qty", 1)
                if promo.discount_type == "percentage":
                    disc = item["price"] * qty * promo.discount_value / 100
                else:
                    disc = promo.discount_value * qty
                item["discount_amount"] = item.get("discount_amount", 0) + disc
            applied.append({"promo_id": promo.id, "name": promo.name,
                            "type": "min_amount", "discount": promo.discount_value})

        elif promo.promo_type == "min_qty_discount":
            for item in cart_result:
                if promo.product_id and item["product_id"] != promo.product_id:
                    continue
                qty = item.get("qty", 1)
                if qty >= promo.min_purchase_qty:
                    if promo.discount_type == "percentage":
                        disc = item["price"] * qty * promo.discount_value / 100
                    else:
                        disc = promo.discount_value * qty
                    item["discount_amount"] = item.get("discount_amount", 0) + disc
                    applied.append({"promo_id": promo.id, "name": promo.name,
                                    "type": "min_qty_discount"})

    total_discount = sum(item.get("discount_amount", 0) for item in cart_result)
    return {
        "cart": cart_result,
        "applied_promos": applied,
        "total_discount": round(total_discount, 0),
        "final_amount": round(total_amount - total_discount, 0),
    }


@router.post("/gift-suggestions")
async def gift_suggestions(
    cart: list,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """FAZA 3b: savat uchun "boshqa mahsulot bepul" (buy_x_get_y + free_product_id) takliflari.
    SERVER-AUTHORITATIVE — X yetarli + Y ombor DB'dan tekshiriladi (tested helperlar).
    cart = [{"product_id": 1, "quantity": 3}]. Qaytaradi: available (taklif) + unavailable (Y yo'q)."""
    from services.order_service import OrderService
    tid = resolve_tenant_id(db, current_user)
    now = datetime.now()
    svc = OrderService(db)
    active = svc._fetch_active_promotions(tid, now)
    valid = [p for p in active if p.promo_type == "buy_x_get_y" and getattr(p, "free_product_id", None)]

    cart_qty = {}
    for it in cart:
        pid = it.get("product_id")
        cart_qty[pid] = cart_qty.get(pid, 0) + (it.get("quantity") or 0)

    stock_map = svc._gift_stock_map([p.free_product_id for p in valid], tid)
    gifts = svc._compute_gift_items(valid, cart_qty, stock_map)
    available_ids = {g["promo_id"] for g in gifts}

    # Y nomi
    yids = [g["product_id"] for g in gifts]
    names = {}
    if yids:
        for pid, name in db.query(Product.id, Product.name).filter(Product.id.in_(yids)).all():
            names[pid] = name
    for g in gifts:
        g["free_product_name"] = names.get(g["product_id"], "")

    # unavailable: X yetarli, lekin Y ombor yetmadi → kassirга ogohlantirish
    unavailable = []
    for p in valid:
        if p.id in available_ids:
            continue
        if (p.buy_qty or 0) > 0 and cart_qty.get(p.product_id, 0) >= p.buy_qty:
            unavailable.append({"promo_id": p.id, "name": p.name, "reason": "Bepul mahsulot omborда yetarli emas"})

    return {"available": gifts, "unavailable": unavailable}


def _promo_dict(p: Promotion) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "promo_type": p.promo_type,
        "product_id": p.product_id,
        "category_id": p.category_id,
        "buy_qty": p.buy_qty,
        "get_qty": p.get_qty,
        "discount_type": p.discount_type,
        "discount_value": p.discount_value,
        "min_purchase_amount": p.min_purchase_amount,
        "min_purchase_qty": p.min_purchase_qty,
        "flash_price": p.flash_price,
        "start_date": p.start_date.isoformat() if p.start_date else None,
        "end_date": p.end_date.isoformat() if p.end_date else None,
        "days_of_week": p.days_of_week,
        "time_from": p.time_from,
        "time_to": p.time_to,
        "is_active": p.is_active,
        "usage_limit": p.usage_limit,
        "used_count": p.used_count,
        "product_name": p.product.name if p.product else None,
        "free_product_id": getattr(p, "free_product_id", None),           # FAZA 3b
        "free_qty_per_set": getattr(p, "free_qty_per_set", None),
        "free_product_name": p.free_product.name if getattr(p, "free_product", None) else None,
    }
