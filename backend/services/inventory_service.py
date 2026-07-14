from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from typing import Optional, List, Dict, Any

from models import Inventory, Product, OrderItem, Order

class InventoryService:
    def __init__(self, db: Session):
        self.db = db
    
    def get_inventory_status(self, product_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Ombor holatini olish"""
        query = self.db.query(
            Inventory,
            Product.name,
            Product.is_active
        ).join(Product, Product.id == Inventory.product_id)
        
        if product_id:
            query = query.filter(Inventory.product_id == product_id)
        
        results = query.all()
        
        inventory_data = []
        for inv, name, is_active in results:
            status = "ok"
            if inv.quantity <= 0:
                status = "out_of_stock"
            elif inv.quantity <= inv.min_threshold:
                status = "low_stock"
            elif inv.quantity >= inv.max_threshold:
                status = "overstock"
            
            inventory_data.append({
                "id": inv.id,
                "product_id": inv.product_id,
                "product_name": name,
                "quantity": inv.quantity,
                "unit": inv.unit,
                "min_threshold": inv.min_threshold,
                "max_threshold": inv.max_threshold,
                "status": status,
                "is_active": is_active,
                "last_restock": inv.last_restock.isoformat() if inv.last_restock else None
            })
        
        return inventory_data
    
    def adjust_stock(self, product_id: int, quantity_change: float, reason: str) -> bool:
        """Omborni sozlash"""
        inventory = self.db.query(Inventory).filter(
            Inventory.product_id == product_id
        ).first()
        
        if not inventory:
            return False
        
        new_quantity = inventory.quantity + quantity_change
        
        if new_quantity < 0:
            return False
        
        inventory.quantity = new_quantity
        
        if quantity_change > 0:
            inventory.last_restock = datetime.now()
        
        inventory.updated_at = datetime.now()
        
        # TODO: O'zgarish tarixini saqlash
        
        self.db.commit()
        return True
    
    # OLIB TASHLANDI (B6): sync_inventory_from_orders — ikkinchi, xavfli chiqim yo'li edi.
    # Retseptni hisobga olmasdan xom item.quantity ni ayirar, tenant filtri YO'Q edi
    # (product_id bo'yicha birinchi Inventory ni olardi — cross-tenant). Endi yagona,
    # to'g'ri chiqim yo'li: to'lov paytida services.recipe_inventory_service.
    # deduct_order_ingredients (Order.ingredients_deducted bilan idempotent, tenant-scoped).
    # Ikki yo'l birga ishlasa ombor ikki marta kamayardi — shu bois butunlay olib tashlandi.

    def get_low_stock_alerts(self) -> List[Dict[str, Any]]:
        """Kam qolgan mahsulotlar haqida ogohlantirish"""
        results = self.db.query(
            Inventory,
            Product.name
        ).join(Product, Product.id == Inventory.product_id).filter(
            Inventory.quantity <= Inventory.min_threshold,
            Product.is_active == True
        ).all()
        
        alerts = []
        for inv, name in results:
            alerts.append({
                "product_id": inv.product_id,
                "product_name": name,
                "current_quantity": inv.quantity,
                "min_threshold": inv.min_threshold,
                "unit": inv.unit,
                "deficit": inv.min_threshold - inv.quantity
            })
        
        return alerts
    
    def get_inventory_value(self) -> Dict[str, float]:
        """Ombor qiymatini hisoblash"""
        results = self.db.query(
            func.sum(Inventory.quantity * Product.cost_price).label('total_cost'),
            func.sum(Inventory.quantity * Product.price).label('total_retail')
        ).join(Product, Product.id == Inventory.product_id).first()
        
        return {
            "total_cost": float(results.total_cost or 0),
            "total_retail": float(results.total_retail or 0),
            "potential_profit": float((results.total_retail or 0) - (results.total_cost or 0))
        }
    
    def create_inventory_for_product(self, product_id: int) -> Optional[Inventory]:
        """Mahsulot uchun ombor elementi yaratish"""
        product = self.db.query(Product).filter(Product.id == product_id).first()
        if not product:
            return None
        
        existing = self.db.query(Inventory).filter(
            Inventory.product_id == product_id
        ).first()
        
        if existing:
            return existing
        
        # Ombor birligi mahsulot sotuv birligidan (kg hardcode emas); pcs → dona
        _u = product.sale_unit or "dona"
        _u = "dona" if _u == "pcs" else _u
        inventory = Inventory(
            product_id=product_id,
            quantity=0,
            unit=_u,
            min_threshold=5,
            max_threshold=100
        )
        
        self.db.add(inventory)
        self.db.commit()
        self.db.refresh(inventory)
        
        return inventory
    
    def get_stock_movements(self, date_from: Optional[datetime] = None,
                           date_to: Optional[datetime] = None,
                           product_id: Optional[int] = None,
                           tenant_id: Optional[int] = None,
                           limit: int = 500) -> List[Dict]:
        """Ombor harakatlari tarixi — StockMovement jadvalidan (C3).

        tenant_id berilsa faqat shu tenant harakatlari (izolyatsiya). Eng yangi
        harakatlar birinchi. limit — katta tarixda og'irlashmaslik uchun.
        """
        from models import StockMovement

        query = self.db.query(StockMovement)
        if tenant_id is not None:
            query = query.filter(StockMovement.tenant_id == tenant_id)
        if product_id is not None:
            query = query.filter(StockMovement.product_id == product_id)
        if date_from:
            query = query.filter(StockMovement.created_at >= date_from)
        if date_to:
            query = query.filter(StockMovement.created_at <= date_to)

        movements = query.order_by(StockMovement.created_at.desc()).limit(limit).all()

        return [
            {
                "id": m.id,
                "product_id": m.product_id,
                "movement_type": m.movement_type,
                "quantity": m.quantity,
                "unit": m.unit,
                "unit_cost": m.unit_cost,
                "total_cost": m.total_cost,
                "reason": m.reason,
                "reference_id": m.reference_id,
                "reference_type": m.reference_type,
                "user_id": m.user_id,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in movements
        ]
    
    def predict_restock_date(self, product_id: int) -> Dict[str, Any]:
        """Qayta buyurtma berish sanasini bashorat qilish"""
        # O'rtacha kunlik sarfni hisoblash
        thirty_days_ago = datetime.now().replace(hour=0, minute=0, second=0) - datetime.timedelta(days=30)
        
        total_sold = self.db.query(func.sum(OrderItem.quantity)).join(
            Order, Order.id == OrderItem.order_id
        ).filter(
            OrderItem.product_id == product_id,
            Order.created_at >= thirty_days_ago,
            Order.status == "completed"
        ).scalar() or 0
        
        avg_daily_usage = total_sold / 30
        
        inventory = self.db.query(Inventory).filter(
            Inventory.product_id == product_id
        ).first()
        
        if not inventory or avg_daily_usage == 0:
            return {"days_until_empty": None, "recommended_restock_date": None}
        
        days_until_empty = inventory.quantity / avg_daily_usage
        
        restock_date = None
        if days_until_empty < 30:
            restock_date = (datetime.now() + datetime.timedelta(days=days_until_empty)).date()
        
        return {
            "current_quantity": inventory.quantity,
            "avg_daily_usage": round(avg_daily_usage, 2),
            "days_until_empty": round(days_until_empty, 1),
            "recommended_restock_date": restock_date.isoformat() if restock_date else None,
            "recommended_order_quantity": round(avg_daily_usage * 30 - inventory.quantity)
        }