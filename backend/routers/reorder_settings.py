"""Minimal qoldiq va avto-zakaz sozlamalari — BOSQICH 27"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from database import get_db
from models import ProductReorderSetting, Product, Supplier
from deps import get_current_active_user
from models import User

router = APIRouter()


@router.get("/")
async def list_reorder_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Barcha minimal qoldiq sozlamalarini ro'yxatdan olish"""
    rows = db.query(ProductReorderSetting).filter(
        ProductReorderSetting.tenant_id == current_user.tenant_id
    ).all()

    result = []
    for rs in rows:
        prod = db.query(Product).filter(Product.id == rs.product_id).first()
        sup  = db.query(Supplier).filter(Supplier.id == rs.preferred_supplier_id).first() if rs.preferred_supplier_id else None
        result.append({
            "id":             rs.id,
            "product_id":     rs.product_id,
            "product_name":   prod.name if prod else "—",
            "min_qty":        rs.min_qty,
            "reorder_qty":    rs.reorder_qty,
            "supplier_id":    rs.preferred_supplier_id,
            "supplier_name":  sup.name if sup else None,
            "notes":          rs.notes,
            "created_at":     rs.created_at.isoformat() if rs.created_at else None,
        })
    return result


@router.post("/")
async def create_reorder_setting(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Yangi minimal qoldiq sozlamasini yaratish"""
    product_id = data.get("product_id")
    if not product_id:
        raise HTTPException(status_code=422, detail="product_id majburiy")

    existing = db.query(ProductReorderSetting).filter(
        ProductReorderSetting.tenant_id == current_user.tenant_id,
        ProductReorderSetting.product_id == product_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Bu mahsulot uchun sozlama allaqachon mavjud")

    rs = ProductReorderSetting(
        tenant_id             = current_user.tenant_id,
        product_id            = product_id,
        min_qty               = float(data.get("min_qty", 10)),
        reorder_qty           = float(data.get("reorder_qty", 50)),
        preferred_supplier_id = data.get("supplier_id"),
        notes                 = data.get("notes"),
    )
    db.add(rs)
    db.commit()
    db.refresh(rs)
    return {"id": rs.id, "product_id": rs.product_id, "min_qty": rs.min_qty, "reorder_qty": rs.reorder_qty}


@router.patch("/{setting_id}")
async def update_reorder_setting(
    setting_id: int,
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Minimal qoldiq sozlamasini yangilash"""
    rs = db.query(ProductReorderSetting).filter(
        ProductReorderSetting.id == setting_id,
        ProductReorderSetting.tenant_id == current_user.tenant_id,
    ).first()
    if not rs:
        raise HTTPException(status_code=404, detail="Sozlama topilmadi")

    if "min_qty"    in data: rs.min_qty    = float(data["min_qty"])
    if "reorder_qty" in data: rs.reorder_qty = float(data["reorder_qty"])
    if "supplier_id" in data: rs.preferred_supplier_id = data["supplier_id"]
    if "notes"       in data: rs.notes = data["notes"]

    db.commit()
    return {"ok": True, "id": rs.id}


@router.delete("/{setting_id}")
async def delete_reorder_setting(
    setting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Minimal qoldiq sozlamasini o'chirish"""
    rs = db.query(ProductReorderSetting).filter(
        ProductReorderSetting.id == setting_id,
        ProductReorderSetting.tenant_id == current_user.tenant_id,
    ).first()
    if not rs:
        raise HTTPException(status_code=404, detail="Sozlama topilmadi")
    db.delete(rs)
    db.commit()
    return {"ok": True}
