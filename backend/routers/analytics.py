from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict

from database import get_db
from models import Order, Payment, Product, Customer, User, OrderItem, Category, Appointment, Service, Employee, ServiceOrder, Vehicle, Room, RoomBooking
from deps import get_current_user, get_current_active_user, has_permission, apply_tenant_filter, user_has_permission, resolve_tenant_id, require_feature
from services.analytics_service import AnalyticsService
from core.timeutils import tenant_now, to_local
from core.tenant_config import get_tenant_config
# TUZATISH (audit 2026-08): daromad CHEGIRMA AYIRILGAN bo'lishi kerak — avval
# OrderItem.total_price (katalog summasi) olinardi. Izoh/formula: utils/revenue.py
from utils.revenue import cost_expr, net_revenue_expr, order_subtotal_subq, returns_totals

router = APIRouter()

# Modul bo'ylab bitta subquery obyekti (SQLAlchemy konstruktsiyasi holatsiz).
_A_SUB_SQ       = order_subtotal_subq()
_A_REVENUE_EXPR = net_revenue_expr(_A_SUB_SQ)   # qator SOF tushumi
_A_COST_EXPR    = cost_expr()                   # sotuv paytidagi tan narx snapshot'i


@router.get("/summary")
async def get_summary(
    period: str = Query("today", pattern="^(today|week|month|year)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_analytics")),
):
    """Admin panel uchun yig'ma statistika (period=today|week|month|year)"""
    from sqlalchemy import func
    from deps import apply_tenant_filter

    now = tenant_now()
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start = now - timedelta(days=7)
    elif period == "month":
        start = now - timedelta(days=30)
    else:
        start = now - timedelta(days=365)

    orders_q = apply_tenant_filter(db.query(Order), Order, current_user).filter(
        Order.created_at >= start,
        Order.status == "completed",
    )
    orders = orders_q.all()
    total_orders   = len(orders)
    total_revenue  = sum(o.final_amount or 0 for o in orders)
    avg_order      = round(total_revenue / total_orders, 0) if total_orders else 0

    total_customers = apply_tenant_filter(db.query(Customer), Customer, current_user).count()

    payments = apply_tenant_filter(db.query(Payment), Payment, current_user).filter(
        Payment.created_at >= start,
        Payment.status == "paid",
    ).all()
    by_method: dict = {}
    for p in payments:
        by_method[p.method] = by_method.get(p.method, 0) + (p.amount or 0)

    # Kunlik daromad grafigi — TANLANGAN period bo'yicha, KPI filtridan MUSTAQIL
    # so'rov bilan. (Ilgari `orders` period=today bilan filtrlangani uchun 7 kunlik
    # grafik faqat bugungi kunni ko'rsatib, qolgan kunlarni bo'sh qoldirardi.)
    chart_days   = 30 if period == "month" else 7
    chart_start  = (now - timedelta(days=chart_days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    chart_orders = apply_tenant_filter(db.query(Order), Order, current_user).filter(
        Order.created_at >= chart_start,
        Order.status == "completed",
    ).all()
    # TUZATISH (mijozda topildi — dashboard kartalari BO'SH edi):
    # avvalgi kod har buyurtmani `created_at.replace(tzinfo=None)` bilan NAIVE qilib,
    # AWARE `day_start`/`day_end` bilan solishtirardi:
    #     TypeError: can't compare offset-naive and offset-aware datetimes
    # Bu butun endpointni 500 qilardi; frontend esa `.catch(() => null)` bilan
    # xatoni jimgina yutib, 4 ta KPI kartasi va grafikni BO'SH qoldirardi.
    # Xato faqat SOTUV BO'LGANDA chiqardi (sotuvsiz do'konda sikl bo'sh) — shu sabab
    # ilgari sezilmagan. Kod naive `datetime.now()` davrida yozilgan, keyin
    # `tenant_now()` (aware) kiritilgan — regressiya (a7ada36).
    #
    # Endi kunlar TOSHKENT sanasi bo'yicha guruhlanadi: qulash yo'q va yarim tundan
    # keyingi (00:00–05:00) sotuv o'z kuniga tushadi, oldingi kunga emas.
    rev_by_day: dict = {}
    for o in chart_orders:
        if not o.created_at:
            continue
        d = to_local(o.created_at).date()
        rev_by_day[d] = rev_by_day.get(d, 0) + (o.final_amount or 0)

    daily: list = []
    for i in range(chart_days - 1, -1, -1):
        d = (now - timedelta(days=i)).date()
        daily.append({"date": d.isoformat(), "revenue": rev_by_day.get(d, 0)})

    return {
        "total_revenue"      : total_revenue,
        "total_orders"       : total_orders,
        "total_customers"    : total_customers,
        "avg_order"          : avg_order,
        "by_payment_method"  : [{"method": k, "amount": v} for k, v in by_method.items()],
        "daily_revenue"      : daily,
    }


@router.get("/dashboard")
async def get_dashboard_data(
    range: str = Query("today", pattern="^(today|week|month|year)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_analytics"))
):
    """Dashboard uchun ma'lumotlar"""
    analytics_service = AnalyticsService(db)
    
    # Vaqt oralig'ini aniqlash
    now = tenant_now()
    
    if range == "today":
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now
        previous_start = start_date - timedelta(days=1)
        previous_end = start_date - timedelta(seconds=1)
    elif range == "week":
        start_date = now - timedelta(days=7)
        end_date = now
        previous_start = start_date - timedelta(days=7)
        previous_end = start_date - timedelta(seconds=1)
    elif range == "month":
        start_date = now - timedelta(days=30)
        end_date = now
        previous_start = start_date - timedelta(days=30)
        previous_end = start_date - timedelta(seconds=1)
    else:  # year
        start_date = now - timedelta(days=365)
        end_date = now
        previous_start = start_date - timedelta(days=365)
        previous_end = start_date - timedelta(seconds=1)
    
    # Joriy davr ma'lumotlari (BOSQICH 1.5: tenant bo'yicha cheklash)
    current_data = analytics_service.get_period_data(start_date, end_date, current_user=current_user)
    previous_data = analytics_service.get_period_data(previous_start, previous_end, current_user=current_user)

    # Trendlarni hisoblash
    def calc_trend(current, previous):
        if previous == 0:
            return 100 if current > 0 else 0
        return round((current - previous) / previous * 100, 1)
    
    # Daromad grafigi
    revenue_data = analytics_service.get_revenue_chart_data(start_date, end_date, range, current_user=current_user)

    # Ommabop mahsulotlar
    popular_products = analytics_service.get_popular_products(start_date, end_date, limit=5, current_user=current_user)

    # Kategoriyalar bo'yicha savdo
    categories_data = analytics_service.get_sales_by_category(start_date, end_date, current_user=current_user)

    # To'lov usullari
    payment_methods = analytics_service.get_payment_methods_data(start_date, end_date, current_user=current_user)

    # So'nggi buyurtmalar
    recent_orders = analytics_service.get_recent_orders(limit=10, current_user=current_user)

    # Sof foyda (net profit) — MAXFIY: faqat view_finance ruxsatli user ko'radi.
    # Mahsulot daromadi (OrderItem.total_price) - tan narx (cost_price * soni).
    # cost_price yo'q mahsulot uchun coalesce(...,0) — 0 deb olinadi, xato bermaydi.
    net_profit = None
    profit_trend = None
    # Oylik maqsad (dashboard ring) — ham MAXFIY (view_finance)
    monthly_goal_target = None
    monthly_actual = None
    goal_pct = None
    goal_remaining = None
    days_left = None
    if user_has_permission(current_user, "view_finance"):
        from sqlalchemy import func as sqlfunc

        def _net_profit(s, e):
            # TUZATISH 1 (daromad): chegirma AYIRILADI. Avval OrderItem.total_price
            #   (katalog summasi) olinardi → sof foyda chegirma summasiga teng
            #   miqdorda oshiq ko'rsatilardi.
            # TUZATISH 2 (tan narx): Product.cost_price (BUGUNGI narx) o'rniga
            #   OrderItem.unit_cost (SOTUV PAYTIDAGI snapshot) ustun — profit.py
            #   _COST_EXPR bilan aynan bir xil, ya'ni ikki sahifada bir xil raqam.
            q = db.query(
                sqlfunc.coalesce(sqlfunc.sum(_A_REVENUE_EXPR), 0).label("revenue"),
                sqlfunc.coalesce(
                    sqlfunc.sum(OrderItem.quantity * _A_COST_EXPR), 0
                ).label("cost"),
            ).join(Order, Order.id == OrderItem.order_id) \
             .join(Product, Product.id == OrderItem.product_id) \
             .join(_A_SUB_SQ, _A_SUB_SQ.c.order_id == OrderItem.order_id) \
             .filter(Order.created_at >= s, Order.created_at <= e, Order.status == "completed")
            q = apply_tenant_filter(q, Order, current_user)
            row = q.one()
            # QAYTARISH — yagona manbadan (utils/revenue.py). Dashboard'dagi
            # "Sof foyda" ham profit.py bilan BIR XIL raqam ko'rsatsin: vozvrat
            # QAYTARILGAN sana bo'yicha ayiriladi.
            _r = returns_totals(db, current_user, s, e)
            return round(
                (float(row.revenue or 0) - _r["revenue"]) - (float(row.cost or 0) - _r["cost"]),
                0,
            )

        net_profit = _net_profit(start_date, end_date)
        prev_profit = _net_profit(previous_start, previous_end)
        profit_trend = calc_trend(net_profit, prev_profit)

        # Oylik savdo maqsadi: shu oy boshidan hozirgacha savdo vs egasi belgilagan maqsad
        import calendar
        tid = resolve_tenant_id(db, current_user)
        goal_cfg = get_tenant_config(db, tid, "monthly_goal") if tid is not None else {}
        monthly_goal_target = float((goal_cfg or {}).get("target") or 0)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        mq = db.query(sqlfunc.coalesce(sqlfunc.sum(Order.final_amount), 0)).filter(
            Order.created_at >= month_start, Order.status == "completed"
        )
        mq = apply_tenant_filter(mq, Order, current_user)
        monthly_actual = round(float(mq.scalar() or 0), 0)
        goal_pct = round(monthly_actual / monthly_goal_target * 100, 1) if monthly_goal_target > 0 else 0
        goal_remaining = round(max(monthly_goal_target - monthly_actual, 0), 0)
        last_day = calendar.monthrange(now.year, now.month)[1]
        # TUZATISH: avval `+ 1` bor edi — bugungi kun ham "qolgan" deb sanalardi
        # (15-avgustda 17 chiqardi, do'konchi esa 16 kutadi). Endi BUGUN sanalmaydi:
        # oyning oxirgi kunida 0 chiqadi va UI "oxirgi kun" deb ko'rsatadi.
        # `now` — tenant_now() (Toshkent), ya'ni bu yerda timezone xatosi YO'Q edi.
        days_left = last_day - now.day

    return {
        # "total_revenue" — ORQAGA MOSLIK uchun saqlangan nom. Ma'nosi:
        # KASSAGA TUSHGAN PUL (cash-basis) = to'langan sotuvlar + nasiya qarzi
        # to'lovlari. Bu SOTUV (accrual) ko'rsatkichi EMAS — sotuv/foyda
        # `utils/revenue.py` va `/analytics/store-dashboard` da.
        "total_revenue": current_data["total_revenue"],
        "total_cash_in": current_data["total_cash_in"],   # aniq nom
        "sales_paid":    current_data["sales_paid"],      # shundan sotuv to'lovi
        "debt_payments": current_data["debt_payments"],   # shundan nasiya to'lovi
        "total_orders": current_data["total_orders"],
        "total_customers": current_data["total_customers"],
        "average_check": current_data["average_check"],
        "revenue_trend": calc_trend(current_data["total_revenue"], previous_data["total_revenue"]),
        "orders_trend": calc_trend(current_data["total_orders"], previous_data["total_orders"]),
        "customers_trend": calc_trend(current_data["total_customers"], previous_data["total_customers"]),
        "avg_check_trend": calc_trend(current_data["average_check"], previous_data["average_check"]),
        "net_profit": net_profit,
        "profit_trend": profit_trend,
        "monthly_goal_target": monthly_goal_target,
        "monthly_actual": monthly_actual,
        "goal_pct": goal_pct,
        "goal_remaining": goal_remaining,
        "days_left": days_left,
        "revenue_data": revenue_data,
        "popular_products": popular_products,
        "categories_data": categories_data,
        "payment_methods": payment_methods,
        "recent_orders": recent_orders
    }

@router.get("/sales")
async def get_sales_report(
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    group_by: str = Query("day", pattern="^(hour|day|week|month)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_analytics"))
):
    """Savdo hisoboti"""
    analytics_service = AnalyticsService(db)
    
    if not date_from:
        date_from = tenant_now() - timedelta(days=30)
    if not date_to:
        date_to = tenant_now()
    
    sales_data = analytics_service.get_sales_report(date_from, date_to, group_by, current_user=current_user)

    # Xulosa
    summary = analytics_service.get_sales_summary(date_from, date_to, current_user=current_user)
    
    return {
        "date_from": date_from,
        "date_to": date_to,
        "group_by": group_by,
        "data": sales_data,
        "summary": summary
    }

@router.get("/products")
async def get_product_analytics(
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    limit: int = Query(20, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_analytics"))
):
    """Mahsulotlar analitikasi"""
    analytics_service = AnalyticsService(db)
    
    if not date_from:
        date_from = tenant_now() - timedelta(days=30)
    if not date_to:
        date_to = tenant_now()
    
    products = analytics_service.get_product_analytics(date_from, date_to, limit, current_user=current_user)
    
    return {
        "date_from": date_from,
        "date_to": date_to,
        "products": products
    }

@router.get("/categories")
async def get_category_analytics(
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_analytics"))
):
    """Kategoriyalar analitikasi"""
    analytics_service = AnalyticsService(db)
    
    if not date_from:
        date_from = tenant_now() - timedelta(days=30)
    if not date_to:
        date_to = tenant_now()
    
    categories = analytics_service.get_category_analytics(date_from, date_to, current_user=current_user)
    
    return {
        "date_from": date_from,
        "date_to": date_to,
        "categories": categories
    }

@router.get("/customers")
async def get_customer_analytics(
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_analytics"))
):
    """Mijozlar analitikasi"""
    analytics_service = AnalyticsService(db)
    
    if not date_from:
        date_from = tenant_now() - timedelta(days=30)
    if not date_to:
        date_to = tenant_now()
    
    return analytics_service.get_customer_analytics(date_from, date_to, current_user=current_user)

@router.get("/employees")
async def get_employee_performance(
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_analytics"))
):
    """Xodimlar samaradorligi"""
    analytics_service = AnalyticsService(db)
    
    if not date_from:
        date_from = tenant_now() - timedelta(days=30)
    if not date_to:
        date_to = tenant_now()
    
    return analytics_service.get_employee_performance(date_from, date_to, current_user=current_user)

@router.get("/hourly")
async def get_hourly_stats(
    date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_analytics"))
):
    """Soatlik statistika"""
    analytics_service = AnalyticsService(db)

    target_date = date or tenant_now()

    return analytics_service.get_hourly_stats(target_date, current_user=current_user)

@router.get("/export")
async def export_analytics(
    report_type: str = Query(..., pattern="^(sales|products|categories|customers)$"),
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    format: str = Query("csv", pattern="^(csv|excel|pdf)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_analytics"))
):
    """Analitikani eksport qilish"""
    analytics_service = AnalyticsService(db)
    
    if not date_from:
        date_from = tenant_now() - timedelta(days=30)
    if not date_to:
        date_to = tenant_now()
    
    file_path = analytics_service.export_report(report_type, date_from, date_to, format, current_user=current_user)
    
    return {
        "file_url": file_path,
        "report_type": report_type,
        "format": format
    }


# в”Ђв”Ђ Restoran/Kafe chuqur analitika (BOSQICH 14b+) в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

@router.get("/waiter-report")
async def get_waiter_report(
    period: str = Query("week", pattern="^(today|week|month)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_analytics")),
):
    """Ofitsiant smena hisoboti вЂ” stol soni, tushum, tips (BOSQICH 14b+)"""
    now = tenant_now()
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start = now - timedelta(days=7)
    else:
        start = now - timedelta(days=30)

    orders = apply_tenant_filter(db.query(Order), Order, current_user).filter(
        Order.created_at >= start,
        Order.status == "completed",
        Order.waiter_id.isnot(None),
    ).all()

    order_ids = [o.id for o in orders]
    payments = db.query(Payment).filter(Payment.order_id.in_(order_ids)).all() if order_ids else []
    tips_by_order: dict = {}
    for p in payments:
        tips_by_order[p.order_id] = tips_by_order.get(p.order_id, 0) + (p.tip_amount or 0)

    waiter_ids = list({o.waiter_id for o in orders})
    waiters = db.query(User).filter(User.id.in_(waiter_ids)).all() if waiter_ids else []
    waiter_map = {w.id: w.full_name for w in waiters}

    stats: dict = defaultdict(lambda: {"orders": 0, "tables": set(), "revenue": 0.0, "tips": 0.0})
    for o in orders:
        s = stats[o.waiter_id]
        s["orders"] += 1
        if o.table_id:
            s["tables"].add(o.table_id)
        s["revenue"] += o.final_amount or 0
        s["tips"] += tips_by_order.get(o.id, 0)

    return sorted([
        {
            "id": wid,
            "name": waiter_map.get(wid, "вЂ”"),
            "orders_count": s["orders"],
            "tables_count": len(s["tables"]),
            "total_revenue": round(s["revenue"], 0),
            "tips_total": round(s["tips"], 0),
        }
        for wid, s in stats.items()
    ], key=lambda x: -x["total_revenue"])


@router.get("/kitchen-stats")
async def get_kitchen_stats(
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_analytics")),
):
    """Oshxona taom tayyorlash o'rtacha vaqti statistikasi (BOSQICH 14b+)"""
    start = tenant_now() - timedelta(days=days)
    orders = apply_tenant_filter(db.query(Order), Order, current_user).filter(
        Order.preparing_started_at.isnot(None),
        Order.completed_at.isnot(None),
        Order.status == "completed",
        Order.created_at >= start,
    ).all()

    daily: dict = defaultdict(list)
    for o in orders:
        sec = (o.completed_at - o.preparing_started_at).total_seconds()
        if 0 < sec < 7200:
            daily[o.created_at.date().isoformat()].append(sec / 60)

    all_times = [t for v in daily.values() for t in v]
    overall_avg = round(sum(all_times) / len(all_times), 1) if all_times else 0

    return {
        "overall_avg_minutes": overall_avg,
        "total_orders": len(orders),
        "daily_stats": sorted([
            {"date": d, "avg_minutes": round(sum(v) / len(v), 1), "count": len(v)}
            for d, v in daily.items()
        ], key=lambda x: x["date"]),
    }


@router.get("/loyalty-tiers")
async def get_loyalty_tiers(
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_analytics")),
):
    """Mijozlar sodiqlik darajalari statistikasi (BOSQICH 14b+)"""
    customers = apply_tenant_filter(db.query(Customer), Customer, current_user).all()

    TIER_CONFIG = [
        ("Platinum", 5_000_000, 20),
        ("Gold",     2_000_000, 15),
        ("Silver",     500_000, 10),
        ("Bronze",           0,  5),
    ]

    counts: dict = {t[0]: 0   for t in TIER_CONFIG}
    spent:  dict = {t[0]: 0.0 for t in TIER_CONFIG}

    for c in customers:
        tier = "Bronze"
        for name, threshold, _ in TIER_CONFIG:
            if c.total_spent >= threshold:
                tier = name
                break
        counts[tier] += 1
        spent[tier]  += c.total_spent

    return [
        {
            "tier":         name,
            "threshold":    threshold,
            "discount_pct": discount,
            "count":        counts[name],
            "total_spent":  round(spent[name], 0),
        }
        for name, threshold, discount in TIER_CONFIG
    ]


# в”Ђв”Ђ Magazin/Supermarket chuqur analitika (BOSQICH 14j+) в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

@router.get("/store-margin")
async def get_store_margin(
    period: str = Query("week", pattern="^(today|week|month|all)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_analytics")),
):
    """Mahsulot foyda marjasi hisoboti вЂ” sotish vs xarid narxi (BOSQICH 14j+)"""
    now = tenant_now()
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start = now - timedelta(days=7)
    elif period == "month":
        start = now - timedelta(days=30)
    else:
        start = datetime(2000, 1, 1)

    from sqlalchemy import func as sqlfunc
    query = db.query(
        Product.id,
        Product.name,
        Product.price,
        Product.cost_price,
        sqlfunc.sum(OrderItem.quantity).label("qty_sold"),
        # TUZATISH: marja chegirma AYIRILGAN tushumdan (avval katalog summasidan).
        sqlfunc.sum(_A_REVENUE_EXPR).label("revenue"),
    ).join(OrderItem, OrderItem.product_id == Product.id)\
     .join(Order, Order.id == OrderItem.order_id)\
     .join(_A_SUB_SQ, _A_SUB_SQ.c.order_id == OrderItem.order_id)\
     .filter(Order.created_at >= start, Order.status == "completed")
    query = apply_tenant_filter(query, Order, current_user)
    results = query.group_by(Product.id, Product.name, Product.price, Product.cost_price)\
        .order_by(sqlfunc.sum(_A_REVENUE_EXPR).desc()).limit(50).all()

    total_revenue = 0.0
    total_profit  = 0.0
    items = []
    for r in results:
        revenue = float(r.revenue or 0)
        qty     = int(r.qty_sold or 0)
        cost    = (r.cost_price or 0) * qty
        profit  = revenue - cost
        margin  = round(profit / revenue * 100, 1) if revenue > 0 else 0
        total_revenue += revenue
        total_profit  += profit
        items.append({
            "id": r.id, "name": r.name,
            "sell_price": r.price, "cost_price": r.cost_price or 0,
            "qty_sold": qty, "revenue": round(revenue, 0),
            "cost": round(cost, 0), "profit": round(profit, 0),
            "margin_pct": margin,
        })

    return {
        "items": items,
        "total_revenue": round(total_revenue, 0),
        "total_profit":  round(total_profit, 0),
        "overall_margin_pct": round(total_profit / total_revenue * 100, 1) if total_revenue > 0 else 0,
    }


@router.get("/cashier-report")
async def get_cashier_report(
    period: str = Query("week", pattern="^(today|week|month)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_analytics")),
):
    """Kassir smena hisoboti вЂ” to'lov usullari breakdown (BOSQICH 14j+)"""
    now = tenant_now()
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start = now - timedelta(days=7)
    else:
        start = now - timedelta(days=30)

    payments = apply_tenant_filter(db.query(Payment), Payment, current_user).filter(
        Payment.created_at >= start,
        Payment.status == "paid",
    ).all()

    cashier_ids = list({p.cashier_id for p in payments if p.cashier_id})
    cashiers    = db.query(User).filter(User.id.in_(cashier_ids)).all() if cashier_ids else []
    cashier_map = {c.id: c.full_name for c in cashiers}

    stats: dict = defaultdict(lambda: {
        "cash": 0.0, "card": 0.0, "click": 0.0,
        "payme": 0.0, "qr": 0.0, "total": 0.0,
        "tips": 0.0, "transactions": 0
    })
    for p in payments:
        s = stats[p.cashier_id or 0]
        method = p.method if isinstance(p.method, str) else p.method.value
        s[method] = s.get(method, 0.0) + (p.amount or 0)
        s["total"]        += p.amount or 0
        s["tips"]         += p.tip_amount or 0
        s["transactions"] += 1

    return sorted([
        {
            "cashier_id":   cid,
            "name":         cashier_map.get(cid, "Kassasiz") if cid else "Kassasiz",
            "transactions": s["transactions"],
            "total":        round(s["total"], 0),
            "cash":         round(s["cash"], 0),
            "card":         round(s["card"], 0),
            "click":        round(s["click"], 0),
            "payme":        round(s["payme"], 0),
            "qr":           round(s["qr"], 0),
            "tips":         round(s["tips"], 0),
        }
        for cid, s in stats.items()
    ], key=lambda x: -x["total"])


# в”Ђв”Ђ Dorixona chuqur analitika (BOSQICH 14k+) в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

@router.get("/pharmacy-stats", dependencies=[Depends(require_feature("prescription_archive"))])
async def get_pharmacy_stats(
    period: str = Query("week", pattern="^(today|week|month)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_analytics")),
):
    """Dorixona retsept statistikasi вЂ” kunlik/haftalik/oylik (BOSQICH 14k+)"""
    now = tenant_now()
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start = now - timedelta(days=7)
    else:
        start = now - timedelta(days=30)

    orders = apply_tenant_filter(db.query(Order), Order, current_user).filter(
        Order.created_at >= start,
        Order.status == "completed",
        Order.biz_meta.isnot(None),
    ).all()
    rx_orders = [o for o in orders if o.biz_meta and o.biz_meta.get("rx_patient_name")]

    daily_map: dict = defaultdict(lambda: {"count": 0, "revenue": 0.0, "patients": set()})
    for o in rx_orders:
        day = o.created_at.date().isoformat()
        daily_map[day]["count"]   += 1
        daily_map[day]["revenue"] += o.final_amount or 0
        pname = o.biz_meta.get("rx_patient_name", "")
        if pname:
            daily_map[day]["patients"].add(pname)

    total_revenue    = sum(o.final_amount or 0 for o in rx_orders)
    unique_patients  = len({o.biz_meta.get("rx_patient_name") for o in rx_orders if o.biz_meta and o.biz_meta.get("rx_patient_name")})

    return {
        "total_rx":        len(rx_orders),
        "total_revenue":   round(total_revenue, 0),
        "avg_rx_amount":   round(total_revenue / len(rx_orders), 0) if rx_orders else 0,
        "unique_patients": unique_patients,
        "daily_stats": sorted([
            {"date": d, "count": v["count"], "revenue": round(v["revenue"], 0), "patients": len(v["patients"])}
            for d, v in daily_map.items()
        ], key=lambda x: x["date"]),
    }


@router.get("/rx-patients", dependencies=[Depends(require_feature("prescription_archive"))])
async def get_rx_patients(
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_analytics")),
):
    """Retsept bemorlar ro'yxati (BOSQICH 14k+)"""
    orders = apply_tenant_filter(db.query(Order), Order, current_user).filter(
        Order.biz_meta.isnot(None),
        Order.status.in_(["completed", "pending", "ready"]),
    ).order_by(Order.created_at.desc()).all()

    patients: dict = {}
    for o in orders:
        if not (o.biz_meta and o.biz_meta.get("rx_patient_name")):
            continue
        name  = o.biz_meta["rx_patient_name"]
        phone = o.biz_meta.get("rx_patient_phone", "")
        key   = name.lower().strip()
        if key not in patients:
            patients[key] = {
                "name": name, "phone": phone,
                "rx_count": 0, "total_spent": 0.0, "last_visit": None,
            }
        patients[key]["rx_count"]    += 1
        patients[key]["total_spent"] += o.final_amount or 0
        d = o.created_at.isoformat()
        if patients[key]["last_visit"] is None or d > patients[key]["last_visit"]:
            patients[key]["last_visit"] = d

    result = sorted(patients.values(), key=lambda x: -(x["total_spent"]))

    if search:
        sl = search.lower()
        result = [p for p in result if sl in p["name"].lower() or sl in (p["phone"] or "")]

    total = len(result)
    paged = result[(page - 1) * page_size: page * page_size]
    return {"items": paged, "total": total, "page": page, "page_size": page_size}


# в”Ђв”Ђ Salon/Fitnes chuqur analitika (BOSQICH 14l+) в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

@router.get("/salon-services", dependencies=[Depends(require_feature("services"))])
async def get_salon_services(
    period: str = Query("week", pattern="^(today|week|month)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_analytics")),
):
    """Xizmat tahlili вЂ” qaysi xizmat ko'p bronlanadi, tushum (BOSQICH 14l+)"""
    now = tenant_now()
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start = now - timedelta(days=7)
    else:
        start = now - timedelta(days=30)

    apts = apply_tenant_filter(db.query(Appointment), Appointment, current_user).filter(
        Appointment.created_at >= start,
        Appointment.status.in_(["completed", "confirmed", "pending"]),
    ).all()

    svc_ids = list({a.service_id for a in apts if a.service_id})
    svcs = db.query(Service).filter(Service.id.in_(svc_ids)).all() if svc_ids else []
    svc_map = {s.id: s.name for s in svcs}

    stats: dict = defaultdict(lambda: {"count": 0, "revenue": 0.0, "completed": 0, "duration_total": 0})
    for a in apts:
        key = a.service_id or 0
        s = stats[key]
        s["count"]          += 1
        s["revenue"]        += a.price or 0
        s["duration_total"] += a.duration_minutes or 0
        if a.status == "completed":
            s["completed"] += 1

    total_rev = sum(v["revenue"] for v in stats.values()) or 1
    result = sorted([
        {
            "service_id":   svc_id,
            "name":         svc_map.get(svc_id, "Boshqa"),
            "count":        s["count"],
            "completed":    s["completed"],
            "revenue":      round(s["revenue"], 0),
            "avg_price":    round(s["revenue"] / s["count"], 0) if s["count"] else 0,
            "avg_duration": round(s["duration_total"] / s["count"], 0) if s["count"] else 0,
            "share_pct":    round(s["revenue"] / total_rev * 100, 1),
        }
        for svc_id, s in stats.items()
    ], key=lambda x: -x["revenue"])

    return {"items": result, "total_revenue": round(sum(s["revenue"] for s in stats.values()), 0)}


@router.get("/master-report", dependencies=[Depends(require_feature("commission_report"))])
async def get_master_report(
    period: str = Query("week", pattern="^(today|week|month)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_analytics")),
):
    """Usta daromad hisoboti вЂ” randevu soni, tushum, o'rtacha narx (BOSQICH 14l+)"""
    now = tenant_now()
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start = now - timedelta(days=7)
    else:
        start = now - timedelta(days=30)

    apts = apply_tenant_filter(db.query(Appointment), Appointment, current_user).filter(
        Appointment.created_at >= start,
        Appointment.employee_id.isnot(None),
        Appointment.status.in_(["completed", "confirmed", "pending"]),
    ).all()

    emp_ids = list({a.employee_id for a in apts})
    emps = db.query(Employee).filter(Employee.id.in_(emp_ids)).all() if emp_ids else []
    emp_map = {e.id: e.full_name for e in emps}

    svc_ids = list({a.service_id for a in apts if a.service_id})
    svcs = db.query(Service).filter(Service.id.in_(svc_ids)).all() if svc_ids else []
    svc_map = {s.id: s.name for s in svcs}

    stats: dict = defaultdict(lambda: {"count": 0, "completed": 0, "revenue": 0.0, "services": set()})
    for a in apts:
        s = stats[a.employee_id]
        s["count"]   += 1
        s["revenue"] += a.price or 0
        if a.status == "completed":
            s["completed"] += 1
        if a.service_id:
            s["services"].add(svc_map.get(a.service_id, "вЂ”"))

    return sorted([
        {
            "employee_id": eid,
            "name":        emp_map.get(eid, "вЂ”"),
            "count":       s["count"],
            "completed":   s["completed"],
            "revenue":     round(s["revenue"], 0),
            "avg_check":   round(s["revenue"] / s["count"], 0) if s["count"] else 0,
            "services":    list(s["services"])[:5],
        }
        for eid, s in stats.items()
    ], key=lambda x: -x["revenue"])


# в”Ђв”Ђ Auto servis chuqur analitika (BOSQICH 14m+) в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

@router.get("/auto-stats")
async def get_auto_stats(
    period: str = Query("week", pattern="^(today|week|month)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_analytics")),
):
    """Auto servis statistikasi вЂ” status counts, tushum, davomiylik (BOSQICH 14m+)"""
    now = tenant_now()
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start = now - timedelta(days=7)
    else:
        start = now - timedelta(days=30)

    orders = apply_tenant_filter(db.query(ServiceOrder), ServiceOrder, current_user).filter(
        ServiceOrder.created_at >= start,
    ).all()

    status_counts = {"pending": 0, "in_progress": 0, "done": 0, "delivered": 0}
    for o in orders:
        if o.status in status_counts:
            status_counts[o.status] += 1

    total_revenue = sum(o.total_amount or 0 for o in orders)
    total_paid    = sum(o.paid_amount  or 0 for o in orders)
    debt_total    = sum((o.total_amount or 0) - (o.paid_amount or 0)
                        for o in orders if (o.total_amount or 0) > (o.paid_amount or 0))

    daily_map: dict = defaultdict(float)
    for o in orders:
        day = o.created_at.date().isoformat()
        daily_map[day] += o.total_amount or 0

    durations = []
    for o in orders:
        if o.completion_date and o.intake_date and o.status in ("done", "delivered"):
            hrs = (o.completion_date - o.intake_date).total_seconds() / 3600
            if 0 < hrs < 720:
                durations.append(hrs)
    avg_hours = round(sum(durations) / len(durations), 1) if durations else 0

    return {
        "total":         len(orders),
        "total_revenue": round(total_revenue, 0),
        "total_paid":    round(total_paid, 0),
        "debt_total":    round(debt_total, 0),
        "avg_hours":     avg_hours,
        "status_counts": status_counts,
        "daily": sorted([
            {"date": d, "revenue": round(r, 0)} for d, r in daily_map.items()
        ], key=lambda x: x["date"]),
    }


# в”Ђв”Ђ Maktab/Kurs chuqur analitika (BOSQICH 14n+) в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

@router.get("/school-stats")
async def get_school_stats(
    period: str = Query("month", pattern="^(today|week|month)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_analytics")),
):
    """Maktab/Kurs statistikasi вЂ” o'quvchilar, tushum, kunlik/oylik breakdown (BOSQICH 14n+)"""
    now = tenant_now()
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start = now - timedelta(days=7)
    else:
        start = now - timedelta(days=30)

    from sqlalchemy import cast as sa_cast, String
    orders = apply_tenant_filter(db.query(Order), Order, current_user).filter(
        Order.created_at >= start,
        Order.biz_meta.isnot(None),
        Order.status.in_(["completed", "pending", "ready"]),
    ).all()
    school_orders = [o for o in orders if o.biz_meta and o.biz_meta.get("student_name")]

    total_revenue   = sum(o.final_amount or 0 for o in school_orders)
    unique_students = len({o.biz_meta.get("student_name","").lower().strip() for o in school_orders if o.biz_meta.get("student_name")})
    unique_groups   = len({o.biz_meta.get("student_group","").lower().strip() for o in school_orders if o.biz_meta.get("student_group")})

    daily_map: dict = defaultdict(lambda: {"count": 0, "revenue": 0.0, "students": set()})
    for o in school_orders:
        day = o.created_at.date().isoformat()
        daily_map[day]["count"]   += 1
        daily_map[day]["revenue"] += o.final_amount or 0
        name = (o.biz_meta or {}).get("student_name", "")
        if name:
            daily_map[day]["students"].add(name.lower())

    # Monthly breakdown (last 6 months)
    monthly_map: dict = defaultdict(lambda: {"count": 0, "revenue": 0.0, "students": set()})
    all_orders = apply_tenant_filter(db.query(Order), Order, current_user).filter(
        Order.biz_meta.isnot(None),
        Order.created_at >= now - timedelta(days=180),
        Order.status.in_(["completed", "pending", "ready"]),
    ).all()
    for o in all_orders:
        if not (o.biz_meta and o.biz_meta.get("student_name")):
            continue
        month = o.created_at.strftime("%Y-%m")
        monthly_map[month]["count"]   += 1
        monthly_map[month]["revenue"] += o.final_amount or 0
        monthly_map[month]["students"].add((o.biz_meta.get("student_name") or "").lower())

    return {
        "total_orders":    len(school_orders),
        "total_revenue":   round(total_revenue, 0),
        "unique_students": unique_students,
        "unique_groups":   unique_groups,
        "avg_check":       round(total_revenue / len(school_orders), 0) if school_orders else 0,
        "daily": sorted([
            {"date": d, "count": v["count"], "revenue": round(v["revenue"], 0), "students": len(v["students"])}
            for d, v in daily_map.items()
        ], key=lambda x: x["date"]),
        "monthly": sorted([
            {"month": m, "count": v["count"], "revenue": round(v["revenue"], 0), "students": len(v["students"])}
            for m, v in monthly_map.items()
        ], key=lambda x: x["month"]),
    }


# в”Ђв”Ђ Kimyoviy tozalash chuqur analitika (BOSQICH 14o+) в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

@router.get("/dry-stats")
async def get_dry_stats(
    period: str = Query("month", pattern="^(today|week|month)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_analytics")),
):
    """Kimyoviy tozalash statistikasi вЂ” status counts, tushum, kunlik (BOSQICH 14o+)"""
    now = tenant_now()
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start = now - timedelta(days=7)
    else:
        start = now - timedelta(days=30)

    orders = apply_tenant_filter(db.query(Order), Order, current_user).filter(
        Order.created_at >= start,
        Order.biz_meta.isnot(None),
    ).all()
    dry_orders = [o for o in orders if o.biz_meta and o.biz_meta.get("cleaning_items") is not None]

    status_counts = {"pending": 0, "preparing": 0, "ready": 0, "completed": 0, "cancelled": 0}
    total_revenue = 0.0
    daily_map: dict = defaultdict(lambda: {"count": 0, "revenue": 0.0})

    for o in dry_orders:
        if o.status in status_counts:
            status_counts[o.status] += 1
        total_revenue += o.final_amount or 0
        day = o.created_at.date().isoformat()
        daily_map[day]["count"]   += 1
        daily_map[day]["revenue"] += o.final_amount or 0

    avg_check = round(total_revenue / len(dry_orders), 0) if dry_orders else 0

    return {
        "total":         len(dry_orders),
        "total_revenue": round(total_revenue, 0),
        "avg_check":     avg_check,
        "status_counts": status_counts,
        "daily": sorted([
            {"date": d, "count": v["count"], "revenue": round(v["revenue"], 0)}
            for d, v in daily_map.items()
        ], key=lambda x: x["date"]),
    }


# в”Ђв”Ђ Mehmonxona chuqur analitika (BOSQICH 14p+) в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

@router.get("/hotel-stats")
async def get_hotel_stats(
    period: str = Query("month", pattern="^(today|week|month)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_analytics")),
):
    """Mehmonxona statistikasi вЂ” tushum, band xonalar, dolzarblik (BOSQICH 14p+)"""
    from datetime import date as ddate
    now = tenant_now()
    today = tenant_now().date()
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_date = today
    elif period == "week":
        start = now - timedelta(days=7)
        start_date = today - timedelta(days=7)
    else:
        start = now - timedelta(days=30)
        start_date = today - timedelta(days=30)

    bookings = apply_tenant_filter(db.query(RoomBooking), RoomBooking, current_user).filter(
        RoomBooking.created_at >= start,
    ).all()

    rooms_all = apply_tenant_filter(db.query(Room), Room, current_user).filter(Room.is_active == True).all()
    total_rooms   = len(rooms_all)
    occupied_now  = sum(1 for r in rooms_all if r.status == "occupied")
    occupancy_pct = round(occupied_now / total_rooms * 100, 1) if total_rooms else 0

    active_bk   = [b for b in bookings if b.status not in ("cancelled",)]
    total_rev   = sum(b.total_amount or 0 for b in active_bk)
    total_paid  = sum(b.paid_amount  or 0 for b in active_bk)
    total_nights= sum(b.nights or 0 for b in active_bk)
    debt_total  = sum((b.total_amount or 0) - (b.paid_amount or 0)
                      for b in active_bk if (b.total_amount or 0) > (b.paid_amount or 0))

    status_counts = {"pending": 0, "confirmed": 0, "checked_in": 0, "checked_out": 0, "cancelled": 0}
    for b in bookings:
        if b.status in status_counts:
            status_counts[b.status] += 1

    daily_map: dict = defaultdict(float)
    for b in active_bk:
        day = b.created_at.date().isoformat()
        daily_map[day] += b.total_amount or 0

    # Room type revenue
    room_map = {r.id: r for r in rooms_all}
    type_rev: dict = defaultdict(float)
    for b in active_bk:
        rt = room_map.get(b.room_id)
        rtype = (rt.room_type if rt else "other") or "other"
        type_rev[rtype] += b.total_amount or 0

    return {
        "total_bookings":  len(bookings),
        "total_revenue":   round(total_rev, 0),
        "total_paid":      round(total_paid, 0),
        "debt_total":      round(debt_total, 0),
        "total_nights":    total_nights,
        "total_rooms":     total_rooms,
        "occupied_now":    occupied_now,
        "occupancy_pct":   occupancy_pct,
        "status_counts":   status_counts,
        "room_type_revenue": [
            {"type": k, "revenue": round(v, 0)}
            for k, v in sorted(type_rev.items(), key=lambda x: -x[1])
        ],
        "daily": sorted([
            {"date": d, "revenue": round(r, 0)} for d, r in daily_map.items()
        ], key=lambda x: x["date"]),
    }


# ── Magazin/Supermarket aqlli hisobot (BOSQICH 27) ─────────────────────────────

@router.get("/abc-analysis")
async def get_abc_analysis(
    period: str = Query("month", pattern="^(week|month|quarter|all)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_analytics")),
):
    """ABC tahlil — tovarlarni foyda ulushi bo'yicha A/B/C guruhiga ajratish"""
    from sqlalchemy import func as sqlfunc
    now = tenant_now()
    if period == "week":
        start = now - timedelta(days=7)
    elif period == "month":
        start = now - timedelta(days=30)
    elif period == "quarter":
        start = now - timedelta(days=90)
    else:
        start = datetime(2000, 1, 1)

    rows = db.query(
        Product.id,
        Product.name,
        Product.cost_price,
        sqlfunc.sum(OrderItem.quantity).label("qty_sold"),
        # ABC tahlili reyting hisoboti, lekin daromad shu yerda ham chegirma
        # ayirilgan bo'lsin — mijoz turli sahifada turli raqam ko'rmasin.
        sqlfunc.sum(_A_REVENUE_EXPR).label("revenue"),
    ).join(OrderItem, OrderItem.product_id == Product.id)\
     .join(Order, Order.id == OrderItem.order_id)\
     .join(_A_SUB_SQ, _A_SUB_SQ.c.order_id == OrderItem.order_id)\
     .filter(Order.created_at >= start, Order.status == "completed")
    rows = apply_tenant_filter(rows, Order, current_user)
    rows = rows.group_by(Product.id, Product.name, Product.cost_price).all()

    items = []
    for r in rows:
        revenue = float(r.revenue or 0)
        qty     = float(r.qty_sold or 0)
        cost    = (r.cost_price or 0) * qty
        profit  = revenue - cost
        items.append({
            "id": r.id, "name": r.name,
            "qty_sold": round(qty, 2),
            "revenue":  round(revenue, 0),
            "profit":   round(profit, 0),
            "margin_pct": round(profit / revenue * 100, 1) if revenue > 0 else 0,
        })

    items.sort(key=lambda x: -x["profit"])
    total_profit = sum(i["profit"] for i in items)

    cumulative = 0.0
    for item in items:
        cumulative += item["profit"]
        pct = cumulative / total_profit * 100 if total_profit > 0 else 0
        if pct <= 80:
            item["group"] = "A"
        elif pct <= 95:
            item["group"] = "B"
        else:
            item["group"] = "C"
        item["cumulative_pct"] = round(pct, 1)

    a_items = [i for i in items if i["group"] == "A"]
    b_items = [i for i in items if i["group"] == "B"]
    c_items = [i for i in items if i["group"] == "C"]

    return {
        "items": items,
        "total_profit": round(total_profit, 0),
        "summary": {
            "A": {"count": len(a_items), "profit": round(sum(i["profit"] for i in a_items), 0), "pct": 80},
            "B": {"count": len(b_items), "profit": round(sum(i["profit"] for i in b_items), 0), "pct": 15},
            "C": {"count": len(c_items), "profit": round(sum(i["profit"] for i in c_items), 0), "pct": 5},
        },
    }


@router.get("/reorder-alerts", dependencies=[Depends(require_feature("auto_reorder"))])
async def get_reorder_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_analytics")),
):
    """Minimal qoldiqdan past tovarlar + avto-zakaz ro'yxati"""
    from models import Inventory, ProductReorderSetting, Supplier
    settings_q = db.query(ProductReorderSetting).filter(
        ProductReorderSetting.tenant_id == current_user.tenant_id
    ).all()

    alerts = []
    for rs in settings_q:
        inv = db.query(Inventory).filter(
            Inventory.tenant_id == current_user.tenant_id,
            Inventory.product_id == rs.product_id,
        ).first()
        current_qty = inv.quantity if inv else 0.0
        if current_qty < rs.min_qty:
            prod = db.query(Product).filter(Product.id == rs.product_id).first()
            sup  = db.query(Supplier).filter(Supplier.id == rs.preferred_supplier_id).first() if rs.preferred_supplier_id else None
            alerts.append({
                "product_id":     rs.product_id,
                "product_name":   prod.name if prod else "—",
                "current_qty":    round(current_qty, 2),
                "min_qty":        rs.min_qty,
                "reorder_qty":    rs.reorder_qty,
                "deficit":        round(rs.min_qty - current_qty, 2),
                "supplier_id":    sup.id if sup else None,
                "supplier_name":  sup.name if sup else None,
                "supplier_phone": sup.phone if sup else None,
                "setting_id":     rs.id,
                "notes":          rs.notes,
            })

    alerts.sort(key=lambda x: -(x["deficit"]))
    return {"alerts": alerts, "total": len(alerts)}


@router.get("/turnover")
async def get_turnover_analysis(
    period: str = Query("month", pattern="^(week|month|quarter)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_analytics")),
):
    """Oborot tahlili — tovar qancha tez sotiladi (tez/sekin/o'lik)"""
    from models import Inventory
    from sqlalchemy import func as sqlfunc
    now = tenant_now()
    days_map = {"week": 7, "month": 30, "quarter": 90}
    days = days_map[period]
    start = now - timedelta(days=days)

    sold_rows = db.query(
        Product.id,
        Product.name,
        sqlfunc.sum(OrderItem.quantity).label("qty_sold"),
    ).join(OrderItem, OrderItem.product_id == Product.id)\
     .join(Order, Order.id == OrderItem.order_id)\
     .filter(Order.created_at >= start, Order.status == "completed")
    sold_rows = apply_tenant_filter(sold_rows, Order, current_user)
    sold_rows = sold_rows.group_by(Product.id, Product.name).all()

    sold_map = {r.id: float(r.qty_sold or 0) for r in sold_rows}

    inventories = apply_tenant_filter(
        db.query(Inventory), Inventory, current_user
    ).all()

    result = []
    for inv in inventories:
        qty_sold  = sold_map.get(inv.product_id, 0)
        avg_daily = qty_sold / days if days > 0 else 0
        days_of_stock = inv.quantity / avg_daily if avg_daily > 0 else 9999

        if qty_sold == 0:
            category = "dead"
        elif days_of_stock < 7:
            category = "fast"
        elif days_of_stock < 30:
            category = "normal"
        elif days_of_stock < 90:
            category = "slow"
        else:
            category = "dead"

        prod = db.query(Product).filter(Product.id == inv.product_id).first()
        result.append({
            "product_id":    inv.product_id,
            "product_name":  prod.name if prod else "—",
            "current_qty":   round(inv.quantity, 2),
            "qty_sold":      round(qty_sold, 2),
            "avg_daily":     round(avg_daily, 3),
            "days_of_stock": round(days_of_stock, 1) if days_of_stock < 9999 else None,
            "category":      category,
        })

    result.sort(key=lambda x: (["fast","normal","slow","dead"].index(x["category"]), x["days_of_stock"] or 9999))
    counts = {c: sum(1 for i in result if i["category"] == c) for c in ["fast","normal","slow","dead"]}
    return {"items": result, "counts": counts, "period_days": days}


@router.get("/peak-hours", dependencies=[Depends(require_feature("peak_hours"))])
async def get_peak_hours(
    period: str = Query("month", pattern="^(week|month|quarter)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_analytics")),
):
    """Peak soatlar va kunlar — qaysi vaqtda ko'p savdo bo'ladi"""
    now = tenant_now()
    if period == "week":
        start = now - timedelta(days=7)
    elif period == "month":
        start = now - timedelta(days=30)
    else:
        start = now - timedelta(days=90)

    orders = apply_tenant_filter(db.query(Order), Order, current_user).filter(
        Order.created_at >= start,
        Order.status == "completed",
    ).all()

    hour_stats: dict = {h: {"count": 0, "revenue": 0.0} for h in range(24)}
    day_stats:  dict = {d: {"count": 0, "revenue": 0.0} for d in range(7)}
    day_names = ["Dushanba","Seshanba","Chorshanba","Payshanba","Juma","Shanba","Yakshanba"]

    for o in orders:
        if not o.created_at:
            continue
        dt = o.created_at.replace(tzinfo=None) if o.created_at.tzinfo else o.created_at
        hour_stats[dt.hour]["count"]    += 1
        hour_stats[dt.hour]["revenue"]  += o.final_amount or 0
        day_stats[dt.weekday()]["count"]   += 1
        day_stats[dt.weekday()]["revenue"] += o.final_amount or 0

    hours_list = [
        {"hour": h, "label": f"{h:02d}:00",
         "count": s["count"], "revenue": round(s["revenue"], 0)}
        for h, s in hour_stats.items()
    ]
    days_list = [
        {"day": d, "label": day_names[d],
         "count": s["count"], "revenue": round(s["revenue"], 0)}
        for d, s in day_stats.items()
    ]

    peak_hour = max(hours_list, key=lambda x: x["count"], default=None)
    peak_day  = max(days_list,  key=lambda x: x["count"], default=None)

    return {
        "hours":        hours_list,
        "days":         days_list,
        "peak_hour":    peak_hour,
        "peak_day":     peak_day,
        "total_orders": len(orders),
    }


@router.get("/store-dashboard")
async def get_store_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_analytics")),
):
    """Magazin egasi uchun umumiy dashboard — barcha ko'rsatkichlar bir joyda"""
    from models import Inventory, ProductReorderSetting, Supplier
    from sqlalchemy import func as sqlfunc
    from services.supplier_debt import total_debt
    now = tenant_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now - timedelta(days=30)

    # 1. Bugungi buyurtmalar
    today_orders = apply_tenant_filter(db.query(Order), Order, current_user).filter(
        Order.created_at >= today_start,
        Order.status == "completed",
    ).all()
    # ⚠️ NOM ANIQLIGI (2026-08-19): `today_revenue` — bu ACCRUAL SOTUV, ya'ni
    # BUGUN SOTILGAN tovar summasi. Nasiyaga berilgan tovar ham shu yerda
    # (sotuv sodir bo'lgan, pul esa hali kelmagan).
    #
    # Bu "kassaga tushgan pul" EMAS — quyida ilgari shunday deb yozilgan edi va
    # o'sha izoh chalg'ituvchi edi. Kassaga tushgan pul boshqa endpointda:
    # `/analytics/dashboard` (`total_cash_in`, `utils/cashflow.py`).
    #
    # Shu sababli nasiya qarzi to'lovlari BU YERGA QO'SHILMAYDI — qo'shilsa
    # sotuv ikki marta hisoblanardi (tovar sotilgan kunda bir marta, qarz
    # to'langan kunda yana bir marta). 2026-08 auditidagi vozvrat xatosining
    # aynan takrori bo'lardi.
    today_revenue = sum(o.final_amount or 0 for o in today_orders)

    # 2. Bugungi foyda (tan narx bo'yicha)
    # TUZATISH: `rev` endi chegirma AYIRILGAN sof tushum (avval katalog summasi).
    today_item_rows = db.query(
        OrderItem.product_id,
        sqlfunc.sum(OrderItem.quantity).label("qty"),
        sqlfunc.sum(_A_REVENUE_EXPR).label("rev"),
    ).join(Order, Order.id == OrderItem.order_id)\
     .join(_A_SUB_SQ, _A_SUB_SQ.c.order_id == OrderItem.order_id).filter(
        Order.created_at >= today_start,
        Order.status == "completed",
        Order.tenant_id == current_user.tenant_id,
    ).group_by(OrderItem.product_id).all()

    today_cost = 0.0
    for ti in today_item_rows:
        prod = db.query(Product).filter(Product.id == ti.product_id).first()
        if prod and prod.cost_price:
            today_cost += (prod.cost_price or 0) * float(ti.qty or 0)
    # TUZATISH: foyda `final_amount` dan EMAS — u soliq va xizmat haqini ham
    # o'z ichiga oladi (restoran rejimida 12% + 10%), ular mahsulot daromadi emas.
    # Mahsulot sof tushumidan hisoblanadi. `today_revenue` (ACCRUAL SOTUV —
    # yuqoridagi izohga qara, "kassaga tushgan pul" EMAS) ko'rsatkich sifatida
    # o'z holicha qoladi.
    today_net_revenue = sum(float(ti.rev or 0) for ti in today_item_rows)
    today_profit = today_net_revenue - today_cost

    # 3. Top 5 tovar (bugun tushum bo'yicha)
    top5_list = []
    for t in sorted(today_item_rows, key=lambda x: -(x.rev or 0))[:5]:
        prod = db.query(Product).filter(Product.id == t.product_id).first()
        top5_list.append({
            "product_name": prod.name if prod else "—",
            "qty":          round(float(t.qty or 0), 2),
            "revenue":      round(float(t.rev or 0), 0),
        })

    # 4. Kam qoldiq soni
    reorder_settings = db.query(ProductReorderSetting).filter(
        ProductReorderSetting.tenant_id == current_user.tenant_id
    ).all()
    low_stock_count = 0
    for rs in reorder_settings:
        inv = db.query(Inventory).filter(
            Inventory.tenant_id == current_user.tenant_id,
            Inventory.product_id == rs.product_id,
        ).first()
        if (inv.quantity if inv else 0) < rs.min_qty:
            low_stock_count += 1

    # 5. Firma qarzlari
    # FAZA 1 TUZATISH: ilgari shu yerda MUTLAQO BOSHQA formula turardi —
    #     status != "paid" bo'lgan priyomkalar summasi
    # ya'ni draft (hali omborga kirmagan) nakladnoylarni ham qo'shar, to'lov va
    # vozvratni esa UMUMAN ayirmasdi. Natijada "Firmalar qarzi" soni Qarzlar
    # tabidagi son bilan mos kelmasdi. Endi ikkalasi bitta servisni chaqiradi.
    supplier_debt = 0.0
    try:
        active_suppliers = apply_tenant_filter(
            db.query(Supplier), Supplier, current_user
        ).filter(Supplier.is_active == True).all()
        supplier_debt = total_debt(db, active_suppliers)
    except Exception:
        pass

    # 6. Oylik tushum trendi (oxirgi 7 kun)
    daily_trend = []
    for i in range(6, -1, -1):
        d_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        d_end   = (now - timedelta(days=i)).replace(hour=23, minute=59, second=59)
        d_orders = apply_tenant_filter(db.query(Order), Order, current_user).filter(
            Order.created_at >= d_start,
            Order.created_at <= d_end,
            Order.status == "completed",
        ).all()
        daily_trend.append({
            "date":    d_start.date().isoformat(),
            "revenue": round(sum(o.final_amount or 0 for o in d_orders), 0),
            "orders":  len(d_orders),
        })

    # 7. Oylik jami
    month_orders  = apply_tenant_filter(db.query(Order), Order, current_user).filter(
        Order.created_at >= month_start,
        Order.status == "completed",
    ).all()
    month_revenue = sum(o.final_amount or 0 for o in month_orders)

    return {
        "today_revenue":   round(today_revenue, 0),
        "today_profit":    round(today_profit, 0),
        "today_orders":    len(today_orders),
        "month_revenue":   round(month_revenue, 0),
        "low_stock_count": low_stock_count,
        "supplier_debt":   round(supplier_debt, 0),
        "top5_today":      top5_list,
        "daily_trend":     daily_trend,
    }

