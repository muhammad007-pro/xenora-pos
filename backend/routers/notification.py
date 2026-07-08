from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from database import get_db
from models import Notification, User
from schemas import NotificationCreate, NotificationInDB, PaginatedResponse, MessageResponse
from deps import resolve_tenant_id, get_current_user, get_current_active_user, apply_tenant_filter
from websocket.manager import manager

router = APIRouter()

@router.get("/", response_model=PaginatedResponse)
async def get_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    is_read: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Bildirishnomalarni olish"""
    query = db.query(Notification).filter(Notification.user_id == current_user.id)
    # BOSQICH 1.5: tenant bo'yicha cheklash (foydalanuvchi bo'yicha filtrga qo'shimcha)
    query = apply_tenant_filter(query, Notification, current_user)

    if is_read is not None:
        query = query.filter(Notification.is_read == is_read)
    
    total = query.count()
    notifications = query.order_by(Notification.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    
    return PaginatedResponse(
        items=[NotificationInDB.model_validate(n) for n in notifications],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size
    )

@router.get("/unread/count")
async def get_unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """O'qilmagan bildirishnomalar soni"""
    query = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False
    )
    # BOSQICH 1.5: tenant bo'yicha cheklash
    query = apply_tenant_filter(query, Notification, current_user)
    count = query.count()
    
    return {"count": count}

@router.post("/", response_model=NotificationInDB)
async def create_notification(
    notification_data: NotificationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Yangi bildirishnoma yaratish (admin uchun)"""
    # BOSQICH 1.5: yangi yozuv yaratuvchi tenant'iga biriktiriladi
    notification = Notification(**notification_data.model_dump(), tenant_id=resolve_tenant_id(db, current_user))
    db.add(notification)
    db.commit()
    db.refresh(notification)
    
    # WebSocket orqali yuborish
    await manager.send_to_user(notification.user_id, {
        "type": "new_notification",
        "data": NotificationInDB.model_validate(notification).model_dump()
    })
    
    return NotificationInDB.model_validate(notification)

@router.patch("/{notification_id}/read")
async def mark_as_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Bildirishnomani o'qilgan deb belgilash"""
    notification = apply_tenant_filter(db.query(Notification), Notification, current_user).filter(
        Notification.id == notification_id,
        Notification.user_id == current_user.id
    ).first()
    
    if not notification:
        raise HTTPException(status_code=404, detail="Bildirishnoma topilmadi")
    
    notification.is_read = True
    db.commit()
    
    return MessageResponse(message="O'qilgan deb belgilandi")

@router.post("/read-all")
async def mark_all_as_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Barcha bildirishnomalarni o'qilgan deb belgilash"""
    query = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False
    )
    # BOSQICH 1.5: tenant bo'yicha cheklash
    apply_tenant_filter(query, Notification, current_user).update({"is_read": True})
    
    db.commit()
    
    return MessageResponse(message="Barcha bildirishnomalar o'qilgan deb belgilandi")

@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Bildirishnomani o'chirish"""
    notification = apply_tenant_filter(db.query(Notification), Notification, current_user).filter(
        Notification.id == notification_id,
        Notification.user_id == current_user.id
    ).first()
    
    if not notification:
        raise HTTPException(status_code=404, detail="Bildirishnoma topilmadi")
    
    db.delete(notification)
    db.commit()
    
    return MessageResponse(message="Bildirishnoma o'chirildi")
