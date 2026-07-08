from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, List, Dict, Any

from models import Notification, User
from websocket.manager import manager

class NotificationService:
    def __init__(self, db: Session):
        self.db = db
    
    async def send_notification(
        self,
        user_id: int,
        title: str,
        message: str,
        notification_type: str = "system",
        data: Optional[Dict[str, Any]] = None
    ) -> Notification:
        """Bildirishnoma yuborish"""
        notification = Notification(
            user_id=user_id,
            title=title,
            message=message,
            type=notification_type,
            data=data
        )
        
        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)
        
        # WebSocket orqali yuborish
        await manager.send_to_user(user_id, {
            "type": "new_notification",
            "data": {
                "id": notification.id,
                "title": title,
                "message": message,
                "type": notification_type,
                "data": data,
                "created_at": notification.created_at.isoformat()
            }
        })
        
        return notification
    
    async def send_to_role(
        self,
        role_name: str,
        title: str,
        message: str,
        notification_type: str = "system",
        data: Optional[Dict[str, Any]] = None
    ):
        """Rol bo'yicha barcha foydalanuvchilarga yuborish"""
        users = self.db.query(User).join(User.role).filter(
            User.role.has(name=role_name),
            User.is_active == True
        ).all()
        
        notifications = []
        for user in users:
            notification = await self.send_notification(
                user.id, title, message, notification_type, data
            )
            notifications.append(notification)
        
        return notifications
    
    async def send_to_all(
        self,
        title: str,
        message: str,
        notification_type: str = "system",
        data: Optional[Dict[str, Any]] = None
    ):
        """Barcha faol foydalanuvchilarga yuborish"""
        users = self.db.query(User).filter(User.is_active == True).all()
        
        notifications = []
        for user in users:
            notification = await self.send_notification(
                user.id, title, message, notification_type, data
            )
            notifications.append(notification)
        
        return notifications
    
    async def notify_order_ready(self, order_id: int, table_number: str, waiter_id: int):
        """Buyurtma tayyorligi haqida xabar"""
        await self.send_notification(
            user_id=waiter_id,
            title="Buyurtma tayyor",
            message=f"Stol #{table_number} uchun buyurtma tayyor",
            notification_type="order",
            data={"order_id": order_id, "table_number": table_number}
        )
    
    async def notify_low_stock(self, product_name: str, quantity: float, unit: str):
        """Kam qolgan mahsulot haqida xabar (adminlarga)"""
        await self.send_to_role(
            role_name="admin",
            title="Ombor ogohlantirishi",
            message=f"{product_name} kam qolgan: {quantity} {unit}",
            notification_type="inventory",
            data={"product_name": product_name, "quantity": quantity, "unit": unit}
        )
    
    async def notify_new_order(self, order_number: str, table_number: str):
        """Yangi buyurtma haqida xabar (oshxona uchun)"""
        await self.send_to_role(
            role_name="kitchen",
            title="Yangi buyurtma",
            message=f"#{order_number} - Stol #{table_number}",
            notification_type="order",
            data={"order_number": order_number, "table_number": table_number}
        )
    
    async def notify_payment_received(self, order_number: str, amount: float):
        """To'lov qabul qilingani haqida xabar"""
        await self.send_to_role(
            role_name="admin",
            title="To'lov qabul qilindi",
            message=f"#{order_number} - {amount:,.0f} UZS",
            notification_type="payment",
            data={"order_number": order_number, "amount": amount}
        )
    
    def get_unread_count(self, user_id: int) -> int:
        """O'qilmagan bildirishnomalar soni"""
        return self.db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.is_read == False
        ).count()
    
    def mark_as_read(self, notification_id: int, user_id: int) -> bool:
        """Bildirishnomani o'qilgan deb belgilash"""
        notification = self.db.query(Notification).filter(
            Notification.id == notification_id,
            Notification.user_id == user_id
        ).first()
        
        if not notification:
            return False
        
        notification.is_read = True
        self.db.commit()
        return True
    
    def mark_all_as_read(self, user_id: int) -> int:
        """Barcha bildirishnomalarni o'qilgan deb belgilash"""
        result = self.db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.is_read == False
        ).update({"is_read": True})
        
        self.db.commit()
        return result
    
    def delete_old_notifications(self, days: int = 30) -> int:
        """Eski bildirishnomalarni o'chirish"""
        cutoff = datetime.now() - datetime.timedelta(days=days)
        
        result = self.db.query(Notification).filter(
            Notification.created_at < cutoff,
            Notification.is_read == True
        ).delete()
        
        self.db.commit()
        return result