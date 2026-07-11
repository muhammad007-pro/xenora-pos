from sqlalchemy.orm import Session, selectinload, joinedload
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from datetime import datetime, time
from typing import Optional, List

from models import Order, OrderItem, Product, Table, User, Shift
from schemas import OrderCreate, OrderUpdate

class OrderService:
    def __init__(self, db: Session):
        self.db = db

    def generate_order_number(self) -> str:
        """Buyurtma raqami — ICHKI unikal id (YYMMDD + 4 tasodifiy raqam).
        To'qnashuvni oldini olish uchun bazada band emasligini tekshiradi (retry).
        Bu ko'rinadigan raqam emas — ko'rinadigan raqam `daily_number`."""
        import random

        now = datetime.now()
        prefix = f"{str(now.year)[-2:]}{now.month:02d}{now.day:02d}"
        for _ in range(20):
            candidate = f"{prefix}{random.randint(1000, 9999)}"
            if not self.db.query(Order.id).filter(Order.order_number == candidate).first():
                return candidate
        # Zaxira: millisekund asosida (deyarli to'qnashmas)
        return f"{prefix}{int(now.timestamp() * 1000) % 10000:04d}"

    def _next_daily_number(self, tenant_id: Optional[int]) -> int:
        """Kunlik chek raqami — shu TENANT + shu KUN bo'yicha eng katta daily_number + 1.
        Kun boshida 1 dan boshlanadi. Tenant izolyatsiya: har tenant alohida sanaydi.

        "Kun" — timezone('Asia/Tashkent', created_at)::date ifodasi bilan aniqlanadi
        (unique indeks uq_orders_tenant_day_daily bilan AYNAN bir xil). Shu sabab max+1 va
        unique constraint bir xil kun-guruhini ko'radi → konkurensiyada IntegrityError →
        create_order retry qiladi."""
        from sqlalchemy import cast, Date
        day_expr   = cast(func.timezone('Asia/Tashkent', Order.created_at), Date)
        today_expr = cast(func.timezone('Asia/Tashkent', func.now()), Date)
        q = self.db.query(func.max(Order.daily_number)).filter(day_expr == today_expr)
        if tenant_id is not None:
            q = q.filter(Order.tenant_id == tenant_id)
        else:
            q = q.filter(Order.tenant_id.is_(None))
        return (q.scalar() or 0) + 1

    def _product_cost(self, product: Product) -> float:
        """Sotuv paytidagi tan narx snapshoti (retseptli bo'lsa — retseptdan)"""
        from services.cost_service import get_product_cost
        return get_product_cost(self.db, product.id)

    def create_order(self, order_data: OrderCreate, waiter_id: int, tenant_id: Optional[int] = None) -> Order:
        """Yangi buyurtma yaratish.

        tenant_id — buyurtma egasi tenant (kunlik chek raqami SHU tenant bo'yicha sanaladi).
        order_number ichki unikal id; daily_number — ko'rinadigan kunlik raqam.
        order_number to'qnashuvida (unique constraint) qayta urinadi.
        """
        # Elementlar va summani hisoblash (DB yozuvisiz — retry'da qayta ishlatiladi).
        # product ORM emas, product_id (rollback'dan keyin expiry muammosi bo'lmasin).
        total_amount = 0
        items_data = []
        for item in order_data.items:
            product = self.db.query(Product).filter(Product.id == item.product_id).first()
            if not product:
                raise ValueError(f"Mahsulot topilmadi: {item.product_id}")
            if not product.is_available:
                raise ValueError(f"Mahsulot mavjud emas: {product.name}")
            unit_price = product.price
            total_price = unit_price * item.quantity
            total_amount += total_price
            items_data.append({
                "product_id": product.id,
                "quantity": item.quantity,
                "unit_price": unit_price,
                "unit_cost": self._product_cost(product),
                "total_price": total_price,
                "notes": item.notes,
            })

        # Narx: agar frontend yuborsa (POS/delivery), shuni ishlatamiz
        if order_data.total_amount is not None:
            total_amount = order_data.total_amount
        final = order_data.final_amount if order_data.final_amount is not None else total_amount

        # Biznes-turi xususiy meta (pharmacy rx, auto_service car, school student, dry_cleaning)
        biz_meta = {}
        if getattr(order_data, 'rx_patient_name', None):
            biz_meta['rx_patient_name']  = order_data.rx_patient_name
            biz_meta['rx_patient_phone'] = order_data.rx_patient_phone
            biz_meta['rx_number']        = order_data.rx_number
        if getattr(order_data, 'car_plate', None):
            biz_meta['car_plate'] = order_data.car_plate
            biz_meta['car_make']  = order_data.car_make
            biz_meta['car_model'] = order_data.car_model
            biz_meta['car_year']  = order_data.car_year
        if getattr(order_data, 'student_name', None):
            biz_meta['student_name']  = order_data.student_name
            biz_meta['student_phone'] = order_data.student_phone
            biz_meta['student_group'] = order_data.student_group
        if getattr(order_data, 'cleaning_items', None):
            biz_meta['cleaning_items'] = order_data.cleaning_items
            biz_meta['cleaning_notes'] = order_data.cleaning_notes
        # C1: POS savatcha snapshot — held qayta ochilganda modifikator/og'irlik tiklanadi.
        if getattr(order_data, 'cart_snapshot', None):
            biz_meta['cart'] = order_data.cart_snapshot

        # Z-hisobot: buyurtmani kassirning joriy ochiq smenasiga bog'lash.
        active_shift = self.db.query(Shift).filter(
            Shift.user_id == waiter_id,
            Shift.end_time.is_(None),
        ).first()
        shift_id = active_shift.id if active_shift else None

        # Yaratish — order_number unique to'qnashuvida qayta urinadi (retry)
        for _ in range(5):
            order = Order(
                order_number=self.generate_order_number(),
                daily_number=self._next_daily_number(tenant_id),
                tenant_id=tenant_id,
                table_id=order_data.table_id,
                waiter_id=waiter_id,
                shift_id=shift_id,
                customer_id=order_data.customer_id,
                total_amount=total_amount,
                discount_amount=order_data.discount_amount or 0,
                tax_amount=order_data.tax_amount or 0,
                final_amount=final,
                notes=order_data.notes,
                order_type=order_data.order_type or "dine-in",
                source=order_data.source or "pos",
                delivery_address=order_data.delivery_address,
                delivery_phone=order_data.delivery_phone,
                delivery_note=getattr(order_data, 'delivery_note', None),
                biz_meta=biz_meta or None,
                status="pending",
            )
            self.db.add(order)
            try:
                self.db.flush()  # ID olish + order_number unique tekshiruvi
            except IntegrityError:
                self.db.rollback()
                continue

            for item_data in items_data:
                self.db.add(OrderItem(
                    order_id=order.id,
                    product_id=item_data["product_id"],
                    quantity=item_data["quantity"],
                    unit_price=item_data["unit_price"],
                    unit_cost=item_data["unit_cost"],
                    total_price=item_data["total_price"],
                    notes=item_data["notes"],
                ))
            try:
                self.db.commit()
            except IntegrityError:
                self.db.rollback()
                continue
            self.db.refresh(order)
            return order

        raise ValueError("Buyurtma raqami yaratilmadi (unique to'qnashuv)")
    
    def update_order(self, order_id: int, order_data: OrderUpdate) -> Optional[Order]:
        """Buyurtmani yangilash"""
        order = self.db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return None
        
        update_data = order_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(order, field, value)
        
        if "status" in update_data and update_data["status"] == "completed":
            order.completed_at = datetime.now()
        
        self.db.commit()
        self.db.refresh(order)
        
        return order
    
    def add_item(self, order_id: int, product_id: int, quantity: int, notes: Optional[str] = None) -> Optional[Order]:
        """Buyurtmaga mahsulot qo'shish"""
        order = self.db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return None
        
        product = self.db.query(Product).filter(Product.id == product_id).first()
        if not product:
            return None
        
        # Mavjud elementni tekshirish
        existing_item = self.db.query(OrderItem).filter(
            OrderItem.order_id == order_id,
            OrderItem.product_id == product_id
        ).first()
        
        if existing_item:
            existing_item.quantity += quantity
            existing_item.total_price = existing_item.unit_price * existing_item.quantity
        else:
            order_item = OrderItem(
                order_id=order_id,
                product_id=product_id,
                quantity=quantity,
                unit_price=product.price,
                unit_cost=self._product_cost(product),
                total_price=product.price * quantity,
                notes=notes
            )
            self.db.add(order_item)
        
        # Jami summani yangilash
        self._update_order_total(order)
        
        self.db.commit()
        self.db.refresh(order)
        
        return order
    
    def remove_item(self, order_id: int, item_id: int) -> bool:
        """Buyurtmadan mahsulotni o'chirish"""
        item = self.db.query(OrderItem).filter(
            OrderItem.id == item_id,
            OrderItem.order_id == order_id
        ).first()
        
        if not item:
            return False
        
        self.db.delete(item)
        
        # Jami summani yangilash
        order = self.db.query(Order).filter(Order.id == order_id).first()
        self._update_order_total(order)
        
        self.db.commit()
        
        return True
    
    def _update_order_total(self, order: Order):
        """Buyurtma jami summasini yangilash"""
        items = self.db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
        total = sum(item.total_price for item in items)
        order.total_amount = total
        order.final_amount = total - (order.discount_amount or 0)
    
    def cancel_order(self, order_id: int, reason: Optional[str] = None) -> Optional[Order]:
        """Buyurtmani bekor qilish"""
        order = self.db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return None
        
        order.status = "cancelled"
        if reason:
            order.notes = f"{order.notes or ''}\nBekor qilish sababi: {reason}".strip()
        
        self.db.commit()
        self.db.refresh(order)
        
        return order
    
    def get_orders(self, page: int, page_size: int, current_user: Optional[User] = None, **filters):
        """Buyurtmalarni filtrlash"""
        # N+1 oldini olish: har buyurtma uchun items/payments/waiter/shift ni alohida
        # so'rov qilmasdan oldindan yuklaymiz (_enrich_order va OrderInDB shularni o'qiydi).
        # items/payments — kolleksiya → selectinload (bitta qo'shimcha IN so'rov, dekart
        # ko'paytmasi bo'lmaydi); waiter/shift.register — bir-bir → joinedload.
        query = self.db.query(Order).options(
            selectinload(Order.items),
            selectinload(Order.payments),
            joinedload(Order.waiter),
            joinedload(Order.shift).joinedload(Shift.register),
        )

        # BOSQICH 1.5: tenant bo'yicha cheklash
        if current_user is not None:
            from deps import apply_tenant_filter
            query = apply_tenant_filter(query, Order, current_user)

        if filters.get("status"):
            statuses = [s.strip() for s in str(filters["status"]).split(",")]
            query = query.filter(Order.status.in_(statuses))

        # Kassir (waiter) bo'yicha — qaysi kassir sotgan
        if filters.get("cashier_id"):
            query = query.filter(Order.waiter_id == filters["cashier_id"])

        # Kassa bo'yicha — Order.shift_id -> Shift.register_id JOIN orqali
        if filters.get("register_id"):
            query = query.join(Shift, Order.shift_id == Shift.id).filter(
                Shift.register_id == filters["register_id"]
            )

        if filters.get("table_id"):
            query = query.filter(Order.table_id == filters["table_id"])

        if filters.get("order_type"):
            query = query.filter(Order.order_type == filters["order_type"])

        if filters.get("date_from"):
            query = query.filter(Order.created_at >= filters["date_from"])

        if filters.get("date_to"):
            query = query.filter(Order.created_at <= filters["date_to"])

        if filters.get("has_rx") is True:
            query = query.filter(Order.biz_meta.isnot(None))

        if filters.get("has_student") is True:
            query = query.filter(Order.biz_meta.op('->>')('student_name').isnot(None))

        if filters.get("student_group"):
            query = query.filter(
                Order.biz_meta.op('->>')('student_group') == filters["student_group"]
            )

        if filters.get("has_cleaning") is True:
            query = query.filter(Order.biz_meta.op('->>')('cleaning_items').isnot(None))

        if filters.get("search"):
            from sqlalchemy import cast, String
            s = f"%{filters['search']}%"
            query = query.filter(
                Order.order_number.ilike(s) |
                cast(Order.biz_meta, String).ilike(s)
            )

        total = query.count()
        orders = query.order_by(Order.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

        return orders, total
    
    def apply_discount(self, order_id: int, discount_amount: float) -> Optional[Order]:
        """Buyurtmaga chegirma qo'llash"""
        order = self.db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return None
        
        if discount_amount > order.total_amount:
            discount_amount = order.total_amount
        
        order.discount_amount = discount_amount
        order.final_amount = order.total_amount - discount_amount
        
        self.db.commit()
        self.db.refresh(order)
        
        return order