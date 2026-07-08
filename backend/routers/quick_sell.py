"""Tez sotuv paneli — eng ko'p sotiladigan mahsulotlar bir bosishda"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from database import get_db
from models import QuickSellItem, Product, User, Order, OrderItem
from deps import resolve_tenant_id, get_current_active_user, has_permission, apply_tenant_filter
from sqlalchemy import func as sqlfunc

router = APIRouter()


@router.get("/")
async def get_quick_sell_items(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Tez sotuv paneli mahsulotlari"""
    tid = resolve_tenant_id(db, current_user)
    items = db.query(QuickSellItem).filter(
        QuickSellItem.tenant_id == tid,
        QuickSellItem.is_active == True,
    ).order_by(QuickSellItem.display_order.asc()).all()

    result = []
    for item in items:
        d = _item_dict(item)
        if item.product:
            d["price"] = item.product.price
            # Ombor qoldig'i — Inventory jadvalidan (Product'da stock ustuni yo'q)
            d["stock_quantity"] = sum((inv.quantity or 0) for inv in (item.product.inventory_items or []))
            d["image_url"] = item.product.image_url
            d["barcode"] = item.product.barcode
            d["unit"] = item.product.sale_unit
        result.append(d)
    return result


@router.get("/suggestions")
async def get_top_selling(
    limit: int = Query(12, ge=1, le=30),
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Oxirgi N kunda eng ko'p sotilgan mahsulotlar (tez sotuv uchun taklif)"""
    tid = resolve_tenant_id(db, current_user)
    from datetime import datetime, timedelta
    since = datetime.now() - timedelta(days=days)

    rows = (
        db.query(OrderItem.product_id, sqlfunc.sum(OrderItem.quantity).label("total_qty"))
        .join(OrderItem.order)
        .filter(
            OrderItem.order.has(tenant_id=tid),
            OrderItem.order.has(created_at=None) | True,
        )
        .group_by(OrderItem.product_id)
        .order_by(sqlfunc.sum(OrderItem.quantity).desc())
        .limit(limit)
        .all()
    )

    result = []
    for row in rows:
        product = db.query(Product).filter(Product.id == row.product_id).first()
        if product:
            result.append({
                "product_id": product.id,
                "name": product.name,
                "price": product.price,
                "image_url": product.image_url,
                "total_sold": float(row.total_qty or 0),
                "already_added": db.query(QuickSellItem).filter(
                    QuickSellItem.product_id == product.id,
                    QuickSellItem.tenant_id == tid,
                ).first() is not None,
            })
    return result


@router.post("/")
async def add_quick_sell_item(
    product_id: int,
    display_name: Optional[str] = None,
    display_order: int = 0,
    color: str = "#4CAF50",
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu")),
):
    """Tez sotuv paneliga mahsulot qo'shish"""
    tid = resolve_tenant_id(db, current_user)

    existing = db.query(QuickSellItem).filter(
        QuickSellItem.product_id == product_id,
        QuickSellItem.tenant_id == tid,
    ).first()
    if existing:
        existing.is_active = True
        db.commit()
        return _item_dict(existing)

    item = QuickSellItem(
        tenant_id=tid,
        product_id=product_id,
        display_name=display_name,
        display_order=display_order,
        color=color,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _item_dict(item)


@router.put("/{item_id}")
async def update_quick_sell_item(
    item_id: int,
    display_name: Optional[str] = None,
    display_order: Optional[int] = None,
    color: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu")),
):
    tid = resolve_tenant_id(db, current_user)
    item = db.query(QuickSellItem).filter(
        QuickSellItem.id == item_id, QuickSellItem.tenant_id == tid,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Element topilmadi")
    if display_name is not None:
        item.display_name = display_name
    if display_order is not None:
        item.display_order = display_order
    if color is not None:
        item.color = color
    if is_active is not None:
        item.is_active = is_active
    db.commit()
    return _item_dict(item)


@router.delete("/{item_id}")
async def remove_quick_sell_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu")),
):
    tid = resolve_tenant_id(db, current_user)
    item = db.query(QuickSellItem).filter(
        QuickSellItem.id == item_id, QuickSellItem.tenant_id == tid,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Element topilmadi")
    db.delete(item)
    db.commit()
    return {"ok": True}


@router.post("/reorder")
async def reorder_items(
    order: list,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu")),
):
    """Tartibni qayta belgilash. order = [{"id": 1, "display_order": 0}, ...]"""
    tid = resolve_tenant_id(db, current_user)
    for entry in order:
        db.query(QuickSellItem).filter(
            QuickSellItem.id == entry["id"],
            QuickSellItem.tenant_id == tid,
        ).update({"display_order": entry["display_order"]})
    db.commit()
    return {"ok": True}


def _item_dict(item: QuickSellItem) -> dict:
    return {
        "id": item.id,
        "product_id": item.product_id,
        "display_name": item.display_name or (item.product.name if item.product else ""),
        "display_order": item.display_order,
        "color": item.color,
        "is_active": item.is_active,
    }
