from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import OrderItem, User
from schemas import OrderItemUpdate, OrderItemInDB, MessageResponse
from deps import get_current_active_user, apply_tenant_filter

router = APIRouter()

@router.get("/{item_id}", response_model=OrderItemInDB)
async def get_order_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Buyurtma elementi ma'lumotlarini olish"""
    # BOSQICH 1.5: tenant bo'yicha cheklash
    item = apply_tenant_filter(db.query(OrderItem), OrderItem, current_user).filter(OrderItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Buyurtma elementi topilmadi")
    
    return OrderItemInDB.model_validate(item)

@router.patch("/{item_id}", response_model=OrderItemInDB)
async def update_order_item(
    item_id: int,
    item_data: OrderItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Buyurtma elementini yangilash"""
    # BOSQICH 1.5: tenant bo'yicha cheklash
    item = apply_tenant_filter(db.query(OrderItem), OrderItem, current_user).filter(OrderItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Buyurtma elementi topilmadi")
    
    update_data = item_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(item, field, value)
    
    # Jami summani qayta hisoblash
    if 'quantity' in update_data:
        item.total_price = item.unit_price * item.quantity
    
    db.commit()
    db.refresh(item)
    
    return OrderItemInDB.model_validate(item)

@router.patch("/{item_id}/status")
async def update_item_status(
    item_id: int,
    status: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Buyurtma elementi holatini yangilash"""
    # BOSQICH 1.5: tenant bo'yicha cheklash
    item = apply_tenant_filter(db.query(OrderItem), OrderItem, current_user).filter(OrderItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Buyurtma elementi topilmadi")
    
    valid_statuses = ["pending", "preparing", "ready", "served"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Noto'g'ri holat. Ruxsat etilgan: {valid_statuses}")
    
    item.status = status
    db.commit()
    
    return MessageResponse(message=f"Holat yangilandi: {status}")

@router.delete("/{item_id}")
async def delete_order_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Buyurtma elementini o'chirish"""
    # BOSQICH 1.5: tenant bo'yicha cheklash
    item = apply_tenant_filter(db.query(OrderItem), OrderItem, current_user).filter(OrderItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Buyurtma elementi topilmadi")
    
    order_id = item.order_id
    db.delete(item)
    db.commit()
    
    return MessageResponse(message="Buyurtma elementi o'chirildi")