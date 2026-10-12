from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from models import Order, OrderItem, Payment, Product, Category, Customer, User, Table

class AnalyticsService:
    def __init__(self, db: Session):
        self.db = db

    def _bd(self, bd, current_user):
        """Hisobot kuni qoidasi (core/business_day.py). Berilmasa — tenantdan.
        Kalendar rejimida `window()` aynan `created_at BETWEEN start AND end`."""
        if bd is not None:
            return bd
        from core.business_day import BusinessDay
        return BusinessDay(self.db, current_user)

    def get_period_data(self, start_date: datetime, end_date: datetime, current_user=None, bd=None) -> Dict[str, Any]:
        """Davr uchun asosiy ko'rsatkichlar"""
        from deps import apply_tenant_filter
        from core.business_day import shift_of_payment
        bd = self._bd(bd, current_user)

        # Buyurtmalar
        orders_query = self.db.query(Order).filter(
            bd.window(Order.created_at, Order.shift_id, start_date, end_date)
        )
        if current_user is not None:
            orders_query = apply_tenant_filter(orders_query, Order, current_user)

        total_orders = orders_query.count()
        completed_orders = orders_query.filter(Order.status == "completed").count()

        # ── KASSAGA TUSHGAN PUL (cash-basis) ────────────────────────────────
        # DIQQAT: bu ko'rsatkich SOTUV (accrual) EMAS. U faqat HAQIQATAN kelgan
        # pulni sanaydi: `Payment.status == "paid"`. Nasiyaga berilgan sotuv
        # bu yerga KIRMAYDI, chunki uning to'lovi `pending` holatda qoladi
        # (services/payment_service.py) — pul hali kelmagan.
        # Accrual (sotuv/foyda) tomoni butunlay boshqa manbada:
        # `utils/revenue.py` + `/analytics/store-dashboard`.
        payments_query = self.db.query(Payment).filter(
            bd.window(Payment.created_at, shift_of_payment(), start_date, end_date),
            Payment.status == "paid"
        )
        if current_user is not None:
            payments_query = apply_tenant_filter(payments_query, Payment, current_user)

        sales_paid = payments_query.with_entities(func.sum(Payment.amount)).scalar() or 0

        # Nasiya qarzi to'lovlari — ilgari HECH QAYERDA ko'rinmasdi. Ular
        # `Payment` yozuvi yaratmaydi, ya'ni yuqoridagi so'rov ularni ko'rmaydi.
        # Bu yerga qo'shish IKKI MARTA HISOBLASH EMAS: nasiya sotuvi bu
        # ko'rsatkichga sotuv kunida umuman kirmagan (to'lovi `pending` edi).
        debt_paid = 0.0
        if current_user is not None:
            from utils.cashflow import debt_payments_totals
            debt_paid = debt_payments_totals(
                self.db, current_user, start_date, end_date
            )["total"]

        total_cash_in = float(sales_paid or 0) + float(debt_paid or 0)

        # Mijozlar
        customers_query = self.db.query(Customer).filter(
            Customer.created_at >= start_date,
            Customer.created_at <= end_date
        )
        if current_user is not None:
            customers_query = apply_tenant_filter(customers_query, Customer, current_user)
        total_customers = customers_query.count()
        
        # O'rtacha chek — FAQAT sotuv qismidan. Qarz to'lovi buyurtma emas,
        # uni bo'linmaga qo'shsak o'rtacha chek soxta oshib ketardi.
        average_check = float(sales_paid or 0) / completed_orders if completed_orders > 0 else 0

        return {
            # Nomi orqaga moslik uchun saqlandi (frontend shu kalitni o'qiydi),
            # MA'NOSI esa aniq: "kassaga tushgan pul" = sotuv to'lovlari + qarz
            # to'lovlari. Sotuv (accrual) ko'rsatkichi bu EMAS.
            "total_revenue": total_cash_in,
            "total_cash_in": total_cash_in,   # aniq nom — yangi kod shuni o'qisin
            "sales_paid": float(sales_paid or 0),
            "debt_payments": float(debt_paid or 0),
            "total_orders": total_orders,
            "total_customers": total_customers,
            "average_check": average_check,
            "completed_orders": completed_orders
        }
    
    def get_revenue_chart_data(self, start_date: datetime, end_date: datetime, range_type: str, current_user=None, bd=None) -> Dict[str, List]:
        """Daromad grafigi uchun ma'lumotlar.

        TUZATISH (2026-10, feature/business-day): ilgari `to_char(created_at, ...)`
        bilan SQL'da guruhlanardi — u SERVER zonasida (UTC) kesadi: Toshkent
        14:00 dagi sotuv "09:00" ustuniga, 00:00–05:00 dagisi KECHAGI kunga
        tushardi (PostgreSQL'ga xos funksiya ham). Endi har to'lov qatori
        Python'da tenant zonasiga va ish kuniga (`bd.day_of`) yoziladi —
        yorliq shakli o'zgarmadi.
        """
        from core.timeutils import to_local
        bd = self._bd(bd, current_user)

        chart_query = self.db.query(
            Order.created_at, Order.shift_id, Payment.amount,
        ).join(Payment, Payment.order_id == Order.id).filter(
            bd.window(Order.created_at, Order.shift_id, start_date, end_date),
            Payment.status == "paid"
        )
        if current_user is not None:
            from deps import apply_tenant_filter
            chart_query = apply_tenant_filter(chart_query, Order, current_user)

        buckets: Dict[str, float] = {}
        for created_at, shift_id, amount in chart_query.all():
            if created_at is None:
                continue
            day = bd.day_of(created_at, shift_id)
            if range_type == "today":
                # Soat — haqiqiy mahalliy soat; sana — ish kuni (tungi soatlar
                # smena kunining oxirida turadi).
                key = f"{day.isoformat()} {to_local(created_at).hour:02d}:00"
            elif range_type in ("week", "month"):
                key = day.isoformat()
            else:
                key = day.strftime("%Y-%m")
            buckets[key] = buckets.get(key, 0.0) + float(amount or 0)

        keys = sorted(buckets)
        return {
            "labels": keys,
            "values": [buckets[k] for k in keys]
        }

    def get_popular_products(self, start_date: datetime, end_date: datetime, limit: int = 5, current_user=None, bd=None) -> List[Dict]:
        """Ommabop mahsulotlar"""
        query = self.db.query(
            Product.id,
            Product.name,
            func.sum(OrderItem.quantity).label('total_quantity'),
            func.sum(OrderItem.total_price).label('total_revenue')
        ).join(OrderItem, OrderItem.product_id == Product.id).join(
            Order, Order.id == OrderItem.order_id
        ).filter(
            self._bd(bd, current_user).window(Order.created_at, Order.shift_id, start_date, end_date),
            Order.status == "completed"
        )
        if current_user is not None:
            from deps import apply_tenant_filter
            query = apply_tenant_filter(query, Order, current_user)

        results = query.group_by(Product.id, Product.name).order_by(
            func.sum(OrderItem.quantity).desc()
        ).limit(limit).all()

        return [
            {
                "id": r.id,
                "name": r.name,
                "quantity": int(r.total_quantity or 0),
                "revenue": float(r.total_revenue or 0)
            }
            for r in results
        ]
    
    def get_sales_by_category(self, start_date: datetime, end_date: datetime, current_user=None, bd=None) -> List[Dict]:
        """Kategoriyalar bo'yicha savdo"""
        query = self.db.query(
            Category.id,
            Category.name,
            func.sum(OrderItem.total_price).label('total_revenue')
        ).join(Product, Product.category_id == Category.id).join(
            OrderItem, OrderItem.product_id == Product.id
        ).join(Order, Order.id == OrderItem.order_id).filter(
            self._bd(bd, current_user).window(Order.created_at, Order.shift_id, start_date, end_date),
            Order.status == "completed"
        )
        if current_user is not None:
            from deps import apply_tenant_filter
            query = apply_tenant_filter(query, Order, current_user)

        results = query.group_by(Category.id, Category.name).order_by(
            func.sum(OrderItem.total_price).desc()
        ).all()

        return [
            {
                "id": r.id,
                "name": r.name,
                "revenue": float(r.total_revenue or 0)
            }
            for r in results
        ]
    
    def get_payment_methods_data(self, start_date: datetime, end_date: datetime, current_user=None, bd=None) -> List[Dict]:
        """To'lov usullari bo'yicha ma'lumot"""
        from core.business_day import shift_of_payment
        query = self.db.query(
            Payment.method,
            func.sum(Payment.amount).label('total'),
            func.count(Payment.id).label('count')
        ).filter(
            self._bd(bd, current_user).window(Payment.created_at, shift_of_payment(), start_date, end_date),
            Payment.status == "paid"
        )
        if current_user is not None:
            from deps import apply_tenant_filter
            query = apply_tenant_filter(query, Payment, current_user)

        results = query.group_by(Payment.method).all()

        return [
            {
                "method": r.method,
                "total": float(r.total or 0),
                "count": r.count
            }
            for r in results
        ]
    
    def get_recent_orders(self, limit: int = 10, current_user=None) -> List[Dict]:
        """So'nggi buyurtmalar"""
        query = self.db.query(Order)
        if current_user is not None:
            from deps import apply_tenant_filter
            query = apply_tenant_filter(query, Order, current_user)
        orders = query.order_by(Order.created_at.desc()).limit(limit).all()

        result = []
        for order in orders:
            result.append({
                "id": order.id,
                "order_number": order.order_number,
                "table_number": order.table.number if order.table else None,
                "waiter_name": order.waiter.full_name if order.waiter else None,
                "total_amount": order.total_amount,
                "final_amount": order.final_amount,
                "status": order.status,
                "created_at": order.created_at.isoformat() if order.created_at else None
            })
        
        return result
    
    def get_sales_report(self, date_from: datetime, date_to: datetime, group_by: str, current_user=None) -> List[Dict]:
        """Savdo hisoboti.

        TUZATISH (2026-10): `to_char(created_at)` UTC'da guruhlardi (Toshkent
        00:00–05:00 kechagi kunga). Endi tenant zonasi + ish kuni, Python'da.
        Natija shakli o'zgarmadi (period / orders_count / revenue / avg_check).
        """
        from core.timeutils import to_local
        bd = self._bd(None, current_user)

        report_query = self.db.query(
            Order.created_at, Order.shift_id, Payment.amount,
        ).join(Payment, Payment.order_id == Order.id).filter(
            bd.window(Order.created_at, Order.shift_id, date_from, date_to),
            Payment.status == "paid"
        )
        if current_user is not None:
            from deps import apply_tenant_filter
            report_query = apply_tenant_filter(report_query, Order, current_user)

        agg: Dict[str, list] = {}
        for created_at, shift_id, amount in report_query.all():
            if created_at is None:
                continue
            day = bd.day_of(created_at, shift_id)
            if group_by == "hour":
                key = f"{day.isoformat()} {to_local(created_at).hour:02d}:00"
            elif group_by == "day":
                key = day.isoformat()
            elif group_by == "week":
                iso = day.isocalendar()
                key = f"{iso[0]}-{iso[1]:02d}"
            else:  # month
                key = day.strftime("%Y-%m")
            cur = agg.setdefault(key, [0, 0.0])
            cur[0] += 1
            cur[1] += float(amount or 0)

        return [
            {
                "period": k,
                "orders_count": agg[k][0],
                "revenue": agg[k][1],
                "avg_check": agg[k][1] / agg[k][0] if agg[k][0] else 0.0,
            }
            for k in sorted(agg)
        ]
    
    def get_sales_summary(self, date_from: datetime, date_to: datetime, current_user=None) -> Dict[str, Any]:
        """Savdo xulosasi"""
        payments = self.db.query(Payment).filter(
            Payment.created_at >= date_from,
            Payment.created_at <= date_to,
            Payment.status == "paid"
        )
        if current_user is not None:
            from deps import apply_tenant_filter
            payments = apply_tenant_filter(payments, Payment, current_user)

        total_revenue = payments.with_entities(func.sum(Payment.amount)).scalar() or 0
        
        # Naqd va karta bo'yicha
        cash_total = payments.filter(Payment.method == "cash").with_entities(
            func.sum(Payment.amount)
        ).scalar() or 0
        
        card_total = payments.filter(Payment.method == "card").with_entities(
            func.sum(Payment.amount)
        ).scalar() or 0
        
        orders_count_query = self.db.query(Order).filter(
            Order.created_at >= date_from,
            Order.created_at <= date_to
        )
        if current_user is not None:
            from deps import apply_tenant_filter
            orders_count_query = apply_tenant_filter(orders_count_query, Order, current_user)
        orders_count = orders_count_query.count()

        return {
            "total_revenue": float(total_revenue),
            "cash_total": float(cash_total),
            "card_total": float(card_total),
            "orders_count": orders_count
        }
    
    def get_product_analytics(self, date_from: datetime, date_to: datetime, limit: int = 20, current_user=None) -> List[Dict]:
        """Mahsulotlar analitikasi"""
        query = self.db.query(
            Product.id,
            Product.name,
            Category.name.label('category_name'),
            func.sum(OrderItem.quantity).label('total_quantity'),
            func.sum(OrderItem.total_price).label('total_revenue'),
            func.count(func.distinct(Order.id)).label('orders_count')
        ).join(Category, Category.id == Product.category_id).join(
            OrderItem, OrderItem.product_id == Product.id
        ).join(Order, Order.id == OrderItem.order_id).filter(
            Order.created_at >= date_from,
            Order.created_at <= date_to,
            Order.status == "completed"
        )
        if current_user is not None:
            from deps import apply_tenant_filter
            query = apply_tenant_filter(query, Order, current_user)

        results = query.group_by(Product.id, Product.name, Category.name).order_by(
            func.sum(OrderItem.total_price).desc()
        ).limit(limit).all()

        return [
            {
                "id": r.id,
                "name": r.name,
                "category": r.category_name,
                "quantity": int(r.total_quantity or 0),
                "revenue": float(r.total_revenue or 0),
                "orders_count": r.orders_count
            }
            for r in results
        ]
    
    def get_category_analytics(self, date_from: datetime, date_to: datetime, current_user=None) -> List[Dict]:
        """Kategoriyalar analitikasi"""
        query = self.db.query(
            Category.id,
            Category.name,
            func.count(func.distinct(Product.id)).label('products_count'),
            func.sum(OrderItem.quantity).label('total_quantity'),
            func.sum(OrderItem.total_price).label('total_revenue')
        ).join(Product, Product.category_id == Category.id).join(
            OrderItem, OrderItem.product_id == Product.id
        ).join(Order, Order.id == OrderItem.order_id).filter(
            Order.created_at >= date_from,
            Order.created_at <= date_to,
            Order.status == "completed"
        )
        if current_user is not None:
            from deps import apply_tenant_filter
            query = apply_tenant_filter(query, Order, current_user)

        results = query.group_by(Category.id, Category.name).order_by(
            func.sum(OrderItem.total_price).desc()
        ).all()

        return [
            {
                "id": r.id,
                "name": r.name,
                "products_count": r.products_count,
                "quantity": int(r.total_quantity or 0),
                "revenue": float(r.total_revenue or 0)
            }
            for r in results
        ]
    
    def get_customer_analytics(self, date_from: datetime, date_to: datetime, current_user=None) -> Dict[str, Any]:
        """Mijozlar analitikasi"""
        from deps import apply_tenant_filter

        # Yangi mijozlar
        new_customers_query = self.db.query(Customer).filter(
            Customer.created_at >= date_from,
            Customer.created_at <= date_to
        )
        if current_user is not None:
            new_customers_query = apply_tenant_filter(new_customers_query, Customer, current_user)
        new_customers = new_customers_query.count()

        # Qaytgan mijozlar
        returning_query = self.db.query(
            func.count(func.distinct(Order.customer_id))
        ).filter(
            Order.created_at >= date_from,
            Order.created_at <= date_to,
            Order.customer_id.isnot(None)
        )
        if current_user is not None:
            returning_query = apply_tenant_filter(returning_query, Order, current_user)
        returning_customers = returning_query.scalar() or 0

        # Top mijozlar
        top_query = self.db.query(
            Customer.id,
            Customer.name,
            Customer.phone,
            func.count(Order.id).label('orders_count'),
            func.sum(Order.final_amount).label('total_spent')
        ).join(Order, Order.customer_id == Customer.id).filter(
            Order.created_at >= date_from,
            Order.created_at <= date_to,
            Order.status == "completed"
        )
        if current_user is not None:
            top_query = apply_tenant_filter(top_query, Customer, current_user)

        top_customers = top_query.group_by(Customer.id, Customer.name, Customer.phone).order_by(
            func.sum(Order.final_amount).desc()
        ).limit(10).all()

        return {
            "new_customers": new_customers,
            "returning_customers": returning_customers,
            "top_customers": [
                {
                    "id": c.id,
                    "name": c.name,
                    "phone": c.phone,
                    "orders_count": c.orders_count,
                    "total_spent": float(c.total_spent or 0)
                }
                for c in top_customers
            ]
        }
    
    def get_employee_performance(self, date_from: datetime, date_to: datetime, current_user=None) -> List[Dict]:
        """Xodimlar samaradorligi"""
        query = self.db.query(
            User.id,
            User.full_name,
            func.count(Order.id).label('orders_count'),
            func.sum(Order.final_amount).label('total_sales'),
            func.avg(Order.final_amount).label('avg_check')
        ).join(Order, Order.waiter_id == User.id).filter(
            Order.created_at >= date_from,
            Order.created_at <= date_to,
            Order.status == "completed"
        )
        if current_user is not None:
            from deps import apply_tenant_filter
            query = apply_tenant_filter(query, Order, current_user)

        results = query.group_by(User.id, User.full_name).order_by(
            func.sum(Order.final_amount).desc()
        ).all()

        return [
            {
                "id": r.id,
                "name": r.full_name,
                "orders_count": r.orders_count,
                "total_sales": float(r.total_sales or 0),
                "avg_check": float(r.avg_check or 0)
            }
            for r in results
        ]
    
    def get_hourly_stats(self, date: datetime, current_user=None) -> List[Dict]:
        """Soatlik statistika.

        TUZATISH (2026-10): `extract('hour', created_at)` UTC soatini berardi —
        Toshkent 14:00 dagi sotuv "9" ustunida turardi. Endi mahalliy soat.
        Kun chegarasi `day_bounds` (tenant zonasi): naive `date` ham shu
        zonaning sanasi deb olinadi. Bu SOAT kesimi — ish kuni qoidasi
        qo'llanmaydi (kalendar kunning 0–23 soati).
        """
        from core.timeutils import day_bounds, to_local
        start_of_day, end_of_day = day_bounds(date.date() if isinstance(date, datetime) else date)

        query = self.db.query(
            Order.created_at, Payment.amount,
        ).join(Payment, Payment.order_id == Order.id).filter(
            Order.created_at >= start_of_day,
            Order.created_at < end_of_day,
            Payment.status == "paid"
        )
        if current_user is not None:
            from deps import apply_tenant_filter
            query = apply_tenant_filter(query, Order, current_user)

        counts = [0] * 24
        revenue = [0.0] * 24
        for created_at, amount in query.all():
            if created_at is None:
                continue
            h = to_local(created_at).hour
            counts[h] += 1
            revenue[h] += float(amount or 0)

        return [
            {"hour": h, "orders_count": counts[h], "revenue": revenue[h]}
            for h in range(24)
        ]
    
    def export_report(self, report_type: str, date_from: datetime, date_to: datetime, format: str, current_user=None) -> str:
        """Hisobotni eksport qilish"""
        import csv
        import os
        from datetime import datetime
        
        filename = f"{report_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format}"
        filepath = os.path.join("static", "exports", filename)
        
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        if report_type == "sales":
            data = self.get_sales_report(date_from, date_to, "day", current_user=current_user)
            
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=["period", "orders_count", "revenue", "avg_check"])
                writer.writeheader()
                writer.writerows(data)
        
        return f"/static/exports/{filename}"