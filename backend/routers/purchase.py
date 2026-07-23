from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional

from database import get_db
from models import User, Inventory
from schemas import MessageResponse
from deps import get_current_user, has_permission, apply_tenant_filter

router = APIRouter()

# Sotib olish tarixi (real loyihada database da)
purchases = []

@router.get("/")
async def get_purchases(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    current_user: User = Depends(has_permission("manage_inventory"))
):
    """Sotib olishlar tarixi"""
    start = (page - 1) * page_size
    end = start + page_size
    
    return {
        "items": purchases[start:end],
        "total": len(purchases),
        "page": page,
        "page_size": page_size
    }

@router.post("/")
async def create_purchase(
    product_id: int,
    quantity: float,
    unit_price: float,
    supplier: Optional[str] = None,
    invoice_number: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_inventory"))
):
    """Yangi sotib olish"""
    # Omborni yangilash (BOSQICH 1.5: tenant bo'yicha cheklash)
    inventory = apply_tenant_filter(db.query(Inventory), Inventory, current_user).filter(
        Inventory.product_id == product_id
    ).with_for_update().first()   # ROW-LOCK: kirim atomik (o'qi→qo'sh→yoz)
    if not inventory:
        # Yangi ombor elementi yaratish
        from models import Product
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail="Mahsulot topilmadi")
        
        inventory = Inventory(
            product_id=product_id,
            quantity=0,
            unit="kg"
        )
        db.add(inventory)
        db.flush()
    
    inventory.quantity += quantity
    inventory.last_restock = datetime.now()
    
    # Sotib olish yozuvi
    purchase = {
        "id": len(purchases) + 1,
        "product_id": product_id,
        "quantity": quantity,
        "unit_price": unit_price,
        "total_price": quantity * unit_price,
        "supplier": supplier,
        "invoice_number": invoice_number,
        "user_id": current_user.id,
        "created_at": datetime.now().isoformat()
    }
    purchases.append(purchase)
    
    db.commit()
    
    return {"success": True, "purchase": purchase}

@router.get("/suppliers")
async def get_suppliers(
    current_user: User = Depends(get_current_user)
):
    """Yetkazib beruvchilar ro'yxati"""
    suppliers = list(set(p.get("supplier") for p in purchases if p.get("supplier")))
    return suppliers
