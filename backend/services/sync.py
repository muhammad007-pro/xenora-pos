from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import json
import os
from typing import Dict, Any, Optional

class SyncService:
    """Ma'lumotlarni sinxronizatsiya qilish xizmati"""
    
    def __init__(self, db: Session):
        self.db = db
        self.sync_dir = "sync"
        os.makedirs(self.sync_dir, exist_ok=True)
    
    def export_data(self, tables: Optional[list] = None) -> Dict[str, Any]:
        """Ma'lumotlarni eksport qilish"""
        from models import (
            Category, Product, Table, User, Customer, 
            Discount, Inventory, Order, Payment
        )
        
        export_data = {
            "version": "1.0",
            "exported_at": datetime.now().isoformat(),
            "data": {}
        }
        
        all_tables = {
            "categories": Category,
            "products": Product,
            "tables": Table,
            "users": User,
            "customers": Customer,
            "discounts": Discount,
            "inventory": Inventory
        }
        
        export_tables = tables or list(all_tables.keys())
        
        for table_name in export_tables:
            if table_name in all_tables:
                model = all_tables[table_name]
                records = self.db.query(model).all()
                
                export_data["data"][table_name] = []
                for record in records:
                    record_dict = {}
                    for column in record.__table__.columns:
                        value = getattr(record, column.name)
                        if isinstance(value, datetime):
                            value = value.isoformat()
                        elif hasattr(value, '__dict__'):
                            continue
                        record_dict[column.name] = value
                    export_data["data"][table_name].append(record_dict)
        
        # Faylga saqlash
        filename = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(self.sync_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        return {
            "filename": filename,
            "filepath": filepath,
            "tables_exported": export_tables,
            "exported_at": export_data["exported_at"]
        }
    
    def import_data(self, filename: str, tables: Optional[list] = None) -> Dict[str, Any]:
        """Ma'lumotlarni import qilish"""
        from models import Category, Product, Table, User, Customer, Discount, Inventory
        
        filepath = os.path.join(self.sync_dir, filename)
        
        if not os.path.exists(filepath):
            return {"success": False, "error": "Fayl topilmadi"}
        
        with open(filepath, 'r', encoding='utf-8') as f:
            import_data = json.load(f)
        
        imported_counts = {}
        
        model_map = {
            "categories": Category,
            "products": Product,
            "tables": Table,
            "users": User,
            "customers": Customer,
            "discounts": Discount,
            "inventory": Inventory
        }
        
        import_tables = tables or list(import_data["data"].keys())
        
        for table_name in import_tables:
            if table_name in import_data["data"] and table_name in model_map:
                model = model_map[table_name]
                count = 0
                
                for record_data in import_data["data"][table_name]:
                    # Mavjud yozuvni tekshirish
                    existing = None
                    if "id" in record_data:
                        existing = self.db.query(model).filter(
                            model.id == record_data["id"]
                        ).first()
                    
                    if existing:
                        # Yangilash
                        for key, value in record_data.items():
                            if hasattr(existing, key) and key != "id":
                                setattr(existing, key, value)
                    else:
                        # Yangi yozuv
                        new_record = model()
                        for key, value in record_data.items():
                            if hasattr(new_record, key):
                                setattr(new_record, key, value)
                        self.db.add(new_record)
                        count += 1
                
                imported_counts[table_name] = count
        
        self.db.commit()
        
        return {
            "success": True,
            "imported_counts": imported_counts,
            "imported_at": datetime.now().isoformat()
        }
    
    def get_sync_status(self) -> Dict[str, Any]:
        """Sinxronizatsiya holatini olish"""
        files = []
        if os.path.exists(self.sync_dir):
            for file in os.listdir(self.sync_dir):
                if file.endswith('.json'):
                    filepath = os.path.join(self.sync_dir, file)
                    stat = os.stat(filepath)
                    files.append({
                        "name": file,
                        "size": stat.st_size,
                        "created": datetime.fromtimestamp(stat.st_ctime).isoformat()
                    })
        
        files.sort(key=lambda x: x["created"], reverse=True)
        
        return {
            "sync_dir": self.sync_dir,
            "files": files[:10],
            "total_files": len(files)
        }
    
    def sync_offline_orders(self, orders: list) -> Dict[str, Any]:
        """Offline buyurtmalarni sinxronizatsiya qilish"""
        from models import Order, OrderItem, Product
        
        synced_count = 0
        failed_orders = []
        
        for order_data in orders:
            try:
                # Buyurtmani yaratish
                order = Order(
                    order_number=order_data.get("order_number"),
                    table_id=order_data.get("table_id"),
                    waiter_id=order_data.get("waiter_id"),
                    total_amount=order_data.get("total_amount", 0),
                    final_amount=order_data.get("final_amount", 0),
                    status="pending",
                    created_at=datetime.fromisoformat(order_data.get("created_at"))
                )
                self.db.add(order)
                self.db.flush()
                
                # Buyurtma elementlari
                for item_data in order_data.get("items", []):
                    from services.cost_service import get_product_cost
                    item = OrderItem(
                        order_id=order.id,
                        product_id=item_data["product_id"],
                        quantity=item_data["quantity"],
                        unit_price=item_data["unit_price"],
                        unit_cost=get_product_cost(self.db, item_data["product_id"]),
                        total_price=item_data["total_price"]
                    )
                    self.db.add(item)
                
                synced_count += 1
                
            except Exception as e:
                failed_orders.append({
                    "order_data": order_data,
                    "error": str(e)
                })
        
        self.db.commit()
        
        return {
            "success": True,
            "synced_count": synced_count,
            "failed_count": len(failed_orders),
            "failed_orders": failed_orders
        }
    
    def generate_offline_package(self, device_id: str) -> Dict[str, Any]:
        """Offline ishlash uchun paket yaratish"""
        package = {
            "version": "1.0",
            "generated_at": datetime.now().isoformat(),
            "device_id": device_id,
            "data": {
                "categories": [],
                "products": [],
                "tables": [],
                "discounts": []
            }
        }
        
        # Kategoriyalar
        from models import Category
        categories = self.db.query(Category).filter(Category.is_active == True).all()
        for cat in categories:
            package["data"]["categories"].append({
                "id": cat.id,
                "name": cat.name,
                "parent_id": cat.parent_id,
                "display_order": cat.display_order
            })
        
        # Mahsulotlar
        from models import Product
        products = self.db.query(Product).filter(
            Product.is_active == True,
            Product.is_available == True
        ).all()
        for prod in products:
            package["data"]["products"].append({
                "id": prod.id,
                "name": prod.name,
                "price": prod.price,
                "category_id": prod.category_id,
                "barcode": prod.barcode,
                "image_url": prod.image_url
            })
        
        # Stollar
        from models import Table
        tables = self.db.query(Table).all()
        for table in tables:
            package["data"]["tables"].append({
                "id": table.id,
                "number": table.number,
                "name": table.name,
                "capacity": table.capacity,
                "section": table.section,
                "status": table.status
            })
        
        # Chegirmalar
        from models import Discount
        now = datetime.now()
        discounts = self.db.query(Discount).filter(
            Discount.is_active == True,
            (Discount.valid_from.is_(None) | (Discount.valid_from <= now)),
            (Discount.valid_to.is_(None) | (Discount.valid_to >= now))
        ).all()
        for disc in discounts:
            package["data"]["discounts"].append({
                "id": disc.id,
                "name": disc.name,
                "type": disc.type,
                "value": disc.value,
                "min_order_amount": disc.min_order_amount
            })
        
        # Faylga saqlash
        filename = f"offline_{device_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(self.sync_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(package, f, ensure_ascii=False)
        
        return {
            "filename": filename,
            "filepath": filepath,
            "categories_count": len(package["data"]["categories"]),
            "products_count": len(package["data"]["products"]),
            "tables_count": len(package["data"]["tables"]),
            "discounts_count": len(package["data"]["discounts"])
        }