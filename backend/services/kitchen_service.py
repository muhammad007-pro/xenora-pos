from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime

from models import Order, OrderItem, Product

class KitchenService:
    def __init__(self, db: Session):
        self.db = db
    
    def get_kitchen_orders(
        self,
        station_id: Optional[int] = None,
        status: Optional[str] = None,
        current_user=None
    ) -> List[dict]:
        """Oshxona uchun faol buyurtmalarni stansiya bo'yicha olish.

        station_id=None  → barcha displayli stansiyalar (yoki stansiyasiz)
        station_id=0     → stansiyaga biriktirilmagan itemlar
        station_id=N     → faqat shu stansiya itemlari
        """
        from models import Product, Station

        query = self.db.query(Order).filter(
            Order.status.in_(["pending", "confirmed", "preparing", "ready"])
        )
        if current_user is not None:
            from deps import apply_tenant_filter
            query = apply_tenant_filter(query, Order, current_user)
        if status:
            query = query.filter(Order.status == status)

        orders = query.order_by(Order.created_at).all()

        result = []
        for order in orders:
            # Item filtratsiya
            if station_id is None:
                # Barcha display stansiyali + stansiyasiz itemlar
                filtered_items = [
                    i for i in order.items
                    if not i.product.station_id or
                    (i.product.station and i.product.station.has_display)
                ]
            elif station_id == 0:
                filtered_items = [i for i in order.items if not i.product.station_id]
            else:
                filtered_items = [
                    i for i in order.items
                    if i.product.station_id == station_id
                ]

            if not filtered_items:
                continue

            result.append({
                "order":          order,
                "filtered_items": filtered_items,
            })

        return result
    
    def send_order_to_kitchen(self, order: Order) -> bool:
        """Buyurtmani oshxonaga yuborish"""
        # Buyurtma holatini yangilash
        order.status = "confirmed"
        self.db.commit()
        
        # TODO: Printerga yuborish logikasi
        
        return True
    
    def start_preparing(self, order_id: int) -> Optional[Order]:
        """Buyurtmani tayyorlashni boshlash"""
        order = self.db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return None
        
        if order.status not in ["pending", "confirmed"]:
            return None
        
        order.status = "preparing"
        self.db.commit()
        self.db.refresh(order)
        
        return order
    
    def mark_ready(self, order_id: int) -> Optional[Order]:
        """Buyurtmani tayyor deb belgilash"""
        order = self.db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return None
        
        if order.status != "preparing":
            return None
        
        order.status = "ready"
        self.db.commit()
        self.db.refresh(order)
        
        return order
    
    def mark_served(self, order_id: int) -> Optional[Order]:
        """Buyurtmani xizmat qilingan deb belgilash"""
        order = self.db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return None
        
        if order.status != "ready":
            return None
        
        order.status = "served"
        self.db.commit()
        self.db.refresh(order)
        
        return order
    
    def update_item_status(self, item_id: int, status: str) -> Optional[OrderItem]:
        """Buyurtma elementi holatini yangilash"""
        item = self.db.query(OrderItem).filter(OrderItem.id == item_id).first()
        if not item:
            return None
        
        valid_statuses = ["pending", "preparing", "ready", "served"]
        if status not in valid_statuses:
            return None
        
        item.status = status
        self.db.commit()
        self.db.refresh(item)
        
        # Agar barcha itemlar tayyor bo'lsa, buyurtmani avtomatik tayyor qilish
        order = item.order
        if order.status == "preparing":
            all_ready = all(i.status == "ready" for i in order.items)
            if all_ready:
                order.status = "ready"
                self.db.commit()
        
        return item
    
    def get_order_items_by_station(self, order_id: int, station: str) -> List[OrderItem]:
        """Stansiya bo'yicha buyurtma elementlarini olish"""
        order = self.db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return []
        
        items = []
        for item in order.items:
            if item.product.category and item.product.category.name.lower() == station.lower():
                items.append(item)
        
        return items
    
    def get_kitchen_stats(self, date: Optional[datetime] = None):
        """Oshxona statistikasi"""
        from sqlalchemy import func
        
        target_date = date or datetime.now().date()
        
        query = self.db.query(Order).filter(
            func.date(Order.created_at) == target_date
        )
        
        total_orders = query.count()
        completed = query.filter(Order.status == "completed").count()
        cancelled = query.filter(Order.status == "cancelled").count()
        
        # O'rtacha tayyorlash vaqti
        completed_orders = query.filter(Order.status == "completed").all()
        prep_times = []
        
        for order in completed_orders:
            if order.completed_at and order.created_at:
                delta = order.completed_at - order.created_at
                prep_times.append(delta.total_seconds() / 60)
        
        avg_time = sum(prep_times) / len(prep_times) if prep_times else 0
        
        return {
            "date": target_date.isoformat(),
            "total_orders": total_orders,
            "completed": completed,
            "cancelled": cancelled,
            "completion_rate": (completed / total_orders * 100) if total_orders > 0 else 0,
            "average_preparation_time": round(avg_time, 1)
        }