"""
Foyda tahlili — tan narx va sof foyda hisoboti (BOSQICH 15+)

Biznes turiga qarab hisob mantig'i:
  MAHSULOT_ASOSLI (restaurant, cafe, fast_food, store, supermarket, pharmacy):
    Daromad  = buyurtma elementlari summasi (bekor qilinganlardan tashqari)
    Tan narx = OrderItem.unit_cost snapshot; eski yozuvlarda Product.cost_price
    Pharmacy: + muddati o'tgan dorilar zarari (expired_loss)

  XIZMAT_ASOSLI (salon, fitness, auto_service, school, dry_cleaning):
    Daromad  = bajarilgan uchrashuvlar (Appointment.price) yig'indisi
    Tan narx = material (Service.cost_price) + usta komissiyasi (price * commission_pct%)
    Fitness/school: + a'zoliklar daromadi (Membership.price)

  MEHMONXONA (hotel):
    Daromad  = xona bronlash (RoomBooking.total_amount) + xizmatlar (Appointment.price)
    Tan narx = xona xarajati (Room.cost_per_night * tunlar) + xizmat materiallari

  Barcha turlarda:
    Sof foyda = Yalpi foyda - Operatsion xarajatlar (Expense)
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, cast
from sqlalchemy.dialects.postgresql import TIMESTAMP as PG_TIMESTAMP
from typing import Optional
from datetime import date, timedelta
import calendar

from database import get_db
from models import (
    Order, OrderItem, Product, Category, Expense, User, Cafe,
    Appointment, Service, RoomBooking, Room, Membership,
)
from deps import resolve_tenant_id, get_current_active_user, apply_tenant_filter, has_permission
# TUZATISH (audit 2026-08): daromad CHEGIRMA AYIRILGAN bo'lishi kerak. Avval
# OrderItem.total_price (katalog summasi) olinardi → foyda chegirma summasiga
# teng miqdorda oshiq chiqardi. Formula/taqsimlash izohi: utils/revenue.py
from utils.revenue import net_revenue_expr, order_subtotal_subq, returns_totals

router = APIRouter()

EXCLUDED_STATUSES = ["cancelled"]

_COST_EXPR = func.coalesce(
    func.nullif(OrderItem.unit_cost, 0.0),
    Product.cost_price,
    0.0,
)

# Bitta subquery obyekti butun modul bo'ylab qayta ishlatiladi (SQLAlchemy
# konstruktsiyasi holatsiz — bu xavfsiz va so'rovlar orasida ajralishning oldini oladi).
_SUB_SQ      = order_subtotal_subq()
_REVENUE_EXPR = net_revenue_expr(_SUB_SQ)   # qator SOF tushumi (chegirma ulushi ayirilgan)

_PRODUCT_TYPES     = frozenset({"restaurant", "cafe", "fast_food", "store", "supermarket", "pharmacy"})
_SERVICE_APT_TYPES = frozenset({"salon", "fitness", "auto_service", "school", "dry_cleaning"})
_MEMBERSHIP_TYPES  = frozenset({"fitness", "school"})


# ─── Yordamchi funksiyalar ────────────────────────────────────────────────────

def _period_range(period: str, start_date: Optional[date], end_date: Optional[date]):
    """today | week | month | custom(start_date..end_date)"""
    today = date.today()
    if start_date and end_date:
        return start_date, end_date
    if period == "today":
        return today, today
    if period == "week":
        return today - timedelta(days=6), today
    if period == "month":
        return today - timedelta(days=29), today
    return today, today


def _dt_bounds(start: date, end: date):
    """(start_date, end_date) → to'liq TIMESTAMP oralig'i, mahalliy zonada.

    `Expense.expense_date` DATE ustuni — u bilan `date` solishtirish to'g'ri.
    Ammo `Return.approved_at` TIMESTAMP — unga `date` berilsa kun 00:00 ga
    keltiriladi va kunning o'zi qamralmaydi (P0-4 izohiga qara).
    """
    from core.timeutils import day_bounds
    s, _        = day_bounds(start)
    _, next_day = day_bounds(end)
    return s, next_day - timedelta(microseconds=1)


def _get_biz_type(db: Session, current_user: User) -> str:
    if not current_user.tenant_id:
        return "restaurant"
    cafe = db.query(Cafe).filter(Cafe.id == current_user.tenant_id).first()
    return (cafe.business_type if cafe else "restaurant") or "restaurant"


def _sales_query(db: Session, current_user: User, start: date, end: date):
    q = (
        db.query(OrderItem)
        .join(Order, OrderItem.order_id == Order.id)
        .join(Product, OrderItem.product_id == Product.id)
        # Chegirmani qatorlar orasida proporsional taqsimlash uchun buyurtma
        # subtotali. Shu yerda BIR MARTA ulanadi → _sales_query ga tayangan
        # BARCHA hisobotlar (summary/timeline/top-products/by-category) avtomatik
        # sof tushumga o'tadi va ajralib ketmaydi.
        .join(_SUB_SQ, _SUB_SQ.c.order_id == OrderItem.order_id)
        .filter(
            Order.status.notin_(EXCLUDED_STATUSES),
            func.date(Order.created_at) >= start,
            func.date(Order.created_at) <= end,
        )
    )
    return apply_tenant_filter(q, Order, current_user)


def _fetch_expenses(db: Session, current_user: User, start: date, end: date) -> float:
    exp_q = db.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
        Expense.expense_date >= start,
        Expense.expense_date <= end,
    )
    return float(apply_tenant_filter(exp_q, Expense, current_user).scalar() or 0)


# ─── Takroriy xarajatlar (BOSQICH 37): lazy generatsiya ───────────────────────

def _recurring_due_dates(template: Expense, today: date):
    """Shablonning o'z sanasidan KEYINgi, bugungacha bo'lgan takror sanalar.

    Shablonning o'zi (template.expense_date) o'sha oy/hafta uchun birinchi yozuv
    bo'lib hisoblanadi — shuning uchun undan keyingilarni generatsiya qilamiz.
    """
    period = (template.recurrence_period or "monthly").lower()
    if period == "weekly":
        d = template.expense_date
        while True:
            d = d + timedelta(days=7)
            if d > today:
                break
            yield d
    else:  # monthly
        day = template.recurrence_day or template.expense_date.day
        y, m = template.expense_date.year, template.expense_date.month
        while True:
            m += 1
            if m > 12:
                m = 1
                y += 1
            last_day = calendar.monthrange(y, m)[1]
            d = date(y, m, min(day, last_day))
            if d > today:
                break
            yield d


def _recurring_instance_exists(db: Session, template: Expense, due: date) -> bool:
    """Shu shablon uchun bu davrda (oy yoki aniq sana) nusxa bormi? (ikki marta yaratmaslik)"""
    base = db.query(Expense.id).filter(Expense.recurrence_parent_id == template.id)
    if (template.recurrence_period or "monthly").lower() == "weekly":
        base = base.filter(Expense.expense_date == due)
    else:
        # oy bo'yicha — kun o'zgarsa ham bir oyda bitta nusxa
        base = base.filter(
            func.extract("year", Expense.expense_date) == due.year,
            func.extract("month", Expense.expense_date) == due.month,
        )
    return db.query(base.exists()).scalar()


def ensure_recurring_expenses(db: Session, current_user: User) -> int:
    """Tenant uchun yetishmagan takroriy xarajat nusxalarini shu kungача yaratadi.

    Idempotent: har bir (shablon, davr) uchun nusxa mavjudligi tekshiriladi, shuning
    uchun qayta chaqirilsa ham ikki marta yaratilmaydi. summary/timeline/expenses
    so'rovlarining boshida chaqiriladi — sof foyda hamma joyda to'g'ri bo'lsin.
    """
    today = date.today()
    templates = apply_tenant_filter(
        db.query(Expense).filter(Expense.is_recurring == True),  # noqa: E712
        Expense, current_user,
    ).all()

    created = 0
    for t in templates:
        for due in _recurring_due_dates(t, today):
            if _recurring_instance_exists(db, t, due):
                continue
            db.add(Expense(
                tenant_id            = t.tenant_id,
                category             = t.category,
                name                 = t.name,
                amount               = t.amount,
                expense_date         = due,
                notes                = t.notes,
                created_by           = t.created_by,
                is_recurring         = False,
                recurrence_parent_id = t.id,
            ))
            created += 1

    if created:
        db.commit()
    return created


def _product_summary(db: Session, current_user: User, start: date, end: date) -> dict:
    row = (
        _sales_query(db, current_user, start, end)
        .with_entities(
            func.coalesce(func.sum(_REVENUE_EXPR), 0).label("revenue"),
            func.coalesce(func.sum(_COST_EXPR * OrderItem.quantity), 0).label("cost"),
            func.count(func.distinct(OrderItem.order_id)).label("orders"),
        )
        .one()
    )
    # QAYTARISH (Return) — yagona manbadan ayiriladi (utils/revenue.py).
    # Ilgari umuman ayirilmasdi: tovar qaytsa ham foyda o'sha sotuvdan
    # olingandek qolaverardi. Sana — QAYTARILGAN sana (sotuv sanasi emas).
    #
    # TUZATISH (P0-4): bu yerga `date` obyekti uzatilardi. `returns_totals()`
    # ichida solishtirish TIMESTAMP ustuni bilan ketadi (`approved_at`), va
    # PostgreSQL `date` ni o'sha kunning 00:00 iga keltiradi. Ya'ni shart
    # `dt >= 28-avgust 00:00 AND dt <= 28-avgust 00:00` bo'lib qolardi va
    # AYNAN YARIM TUNDAGIdan boshqa hech qanday vozvrat tushmasdi:
    # "Bugun" davrida vozvrat AMALDA HECH QACHON ayirilmasdi, "Hafta"/"Oy" da esa
    # oxirgi kun tushib qolardi. Endi to'liq kun oralig'i (mahalliy zona) beriladi.
    ret = returns_totals(db, current_user, *_dt_bounds(start, end))
    return {
        "revenue": round(float(row.revenue or 0) - ret["revenue"], 2),
        "cost": round(float(row.cost or 0) - ret["cost"], 2),
        "orders_count": int(row.orders or 0),
        "returns_revenue": ret["revenue"],
        "returns_cost": ret["cost"],
        "returns_count": ret["count"],
    }


def _expired_loss(db: Session, current_user: User) -> float:
    """Pharmacy: muddati o'tgan va omborda qolgan dorilar zarari"""
    from models import Inventory
    today = date.today()
    q = (
        db.query(func.coalesce(func.sum(Product.cost_price * Inventory.quantity), 0))
        .join(Inventory, Inventory.product_id == Product.id)
        .filter(
            Product.expiry_date != None,
            Product.expiry_date < today,
            Inventory.quantity > 0,
            Product.cost_price > 0,
        )
    )
    return float(apply_tenant_filter(q, Product, current_user).scalar() or 0)


def _appointment_summary(db: Session, current_user: User, start: date, end: date) -> dict:
    """Xizmat asosli: bajarilgan uchrashuvlar bo'yicha daromad va tan narx"""
    apts = apply_tenant_filter(
        db.query(Appointment).filter(
            Appointment.status == "completed",
            Appointment.date >= start,
            Appointment.date <= end,
        ),
        Appointment, current_user,
    ).all()

    revenue = sum(a.price or 0 for a in apts)
    material_cost = 0.0
    commission_cost = 0.0
    for a in apts:
        svc = a.service
        if svc:
            material_cost += svc.cost_price or 0
            commission_cost += (a.price or 0) * ((svc.commission_pct or 0) / 100)

    return {
        "revenue": revenue,
        "material_cost": material_cost,
        "commission_cost": commission_cost,
        "total_cost": material_cost + commission_cost,
        "appointments_count": len(apts),
    }


def _membership_revenue(db: Session, current_user: User, start: date, end: date) -> float:
    """Fitness/maktab: davr ichida boshlangan a'zoliklar daromadi"""
    row = apply_tenant_filter(
        db.query(func.coalesce(func.sum(Membership.price), 0)).filter(
            Membership.start_date >= start,
            Membership.start_date <= end,
            Membership.status.notin_(["cancelled"]),
        ),
        Membership, current_user,
    ).scalar()
    return float(row or 0)


def _hotel_summary(db: Session, current_user: User, start: date, end: date) -> dict:
    """Mehmonxona: xona bronlash + xizmat uchrashuvlari"""
    bookings = apply_tenant_filter(
        db.query(RoomBooking).filter(
            RoomBooking.status.notin_(["cancelled"]),
            RoomBooking.check_in >= start,
            RoomBooking.check_in <= end,
        ),
        RoomBooking, current_user,
    ).all()

    room_revenue = sum(b.total_amount or 0 for b in bookings)
    room_cost = sum(
        (b.room.cost_per_night or 0) * (b.nights or 1) if b.room else 0
        for b in bookings
    )

    apt = _appointment_summary(db, current_user, start, end)
    return {
        "room_revenue": room_revenue,
        "service_revenue": apt["revenue"],
        "total_revenue": room_revenue + apt["revenue"],
        "room_cost": room_cost,
        "service_material_cost": apt["material_cost"],
        "total_cost": room_cost + apt["total_cost"],
        "bookings_count": len(bookings),
        "appointments_count": apt["appointments_count"],
    }


# ─── Asosiy endpointlar ───────────────────────────────────────────────────────

@router.get("/summary")
async def get_profit_summary(
    period: str = Query("today", description="today | week | month"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_finance")),
):
    """Davr bo'yicha foyda xulosasi — biznes turiga mos ko'rsatkichlar"""
    ensure_recurring_expenses(db, current_user)  # takroriy xarajatlar shu oygacha generatsiya
    start, end = _period_range(period, start_date, end_date)
    biz_type  = _get_biz_type(db, current_user)
    expenses  = _fetch_expenses(db, current_user, start, end)
    base = {"period": {"from": start.isoformat(), "to": end.isoformat()}, "business_type": biz_type}

    # ── Mahsulot asosli (restoran, kafe, magazin, dorixona, ...) ──────────────
    if biz_type in _PRODUCT_TYPES:
        d = _product_summary(db, current_user, start, end)
        gross = d["revenue"] - d["cost"]
        net   = gross - expenses
        result = {
            **base,
            "revenue":         round(d["revenue"], 0),
            "cost":            round(d["cost"], 0),
            "gross_profit":    round(gross, 0),
            "expenses":        round(expenses, 0),
            "net_profit":      round(net, 0),
            # YAGONA ekran: bu SOF foyda — operatsion xarajat AYIRILGAN.
            # Boshqa uch ekran YALPI foyda ko'rsatadi (xarajatsiz), shuning
            # uchun ular bilan farq qilishi NORMAL, xato emas.
            "profit_kind":     "net",
            "profit_label":    "Sof foyda (xarajat ayirilgan)",
            "orders_count":    d["orders_count"],
            "margin_pct":      round(gross / d["revenue"] * 100, 1) if d["revenue"] > 0 else 0,
            "net_margin_pct":  round(net  / d["revenue"] * 100, 1) if d["revenue"] > 0 else 0,
        }
        if biz_type == "pharmacy":
            result["expired_loss"] = round(_expired_loss(db, current_user), 0)
        return result

    # ── Xizmat asosli (salon, fitnes, auto, kurs, tozalash) ──────────────────
    if biz_type in _SERVICE_APT_TYPES:
        apt      = _appointment_summary(db, current_user, start, end)
        revenue  = apt["revenue"]
        mbr_rev  = 0.0
        if biz_type in _MEMBERSHIP_TYPES:
            mbr_rev  = _membership_revenue(db, current_user, start, end)
            revenue += mbr_rev
        gross = revenue - apt["total_cost"]
        net   = gross - expenses
        result = {
            **base,
            "revenue":            round(revenue, 0),
            "material_cost":      round(apt["material_cost"], 0),
            "commission_cost":    round(apt["commission_cost"], 0),
            "total_cost":         round(apt["total_cost"], 0),
            "gross_profit":       round(gross, 0),
            "expenses":           round(expenses, 0),
            "net_profit":         round(net, 0),
            "appointments_count": apt["appointments_count"],
            "margin_pct":         round(gross / revenue * 100, 1) if revenue > 0 else 0,
            "net_margin_pct":     round(net   / revenue * 100, 1) if revenue > 0 else 0,
        }
        if biz_type in _MEMBERSHIP_TYPES:
            result["membership_revenue"] = round(mbr_rev, 0)
        return result

    # ── Mehmonxona ─────────────────────────────────────────────────────────────
    if biz_type == "hotel":
        h       = _hotel_summary(db, current_user, start, end)
        revenue = h["total_revenue"]
        gross   = revenue - h["total_cost"]
        net     = gross - expenses
        return {
            **base,
            "room_revenue":       round(h["room_revenue"], 0),
            "service_revenue":    round(h["service_revenue"], 0),
            "total_revenue":      round(revenue, 0),
            "room_cost":          round(h["room_cost"], 0),
            "service_cost":       round(h["service_material_cost"], 0),
            "total_cost":         round(h["total_cost"], 0),
            "gross_profit":       round(gross, 0),
            "expenses":           round(expenses, 0),
            "net_profit":         round(net, 0),
            "bookings_count":     h["bookings_count"],
            "appointments_count": h["appointments_count"],
            "margin_pct":         round(gross / revenue * 100, 1) if revenue > 0 else 0,
            "net_margin_pct":     round(net   / revenue * 100, 1) if revenue > 0 else 0,
        }

    # ── Fallback ───────────────────────────────────────────────────────────────
    d = _product_summary(db, current_user, start, end)
    gross = d["revenue"] - d["cost"]
    net   = gross - expenses
    return {
        **base,
        "revenue":        round(d["revenue"], 0),
        "cost":           round(d["cost"], 0),
        "gross_profit":   round(gross, 0),
        "expenses":       round(expenses, 0),
        "net_profit":     round(net, 0),
        "orders_count":   d["orders_count"],
        "margin_pct":     round(gross / d["revenue"] * 100, 1) if d["revenue"] > 0 else 0,
        "net_margin_pct": round(net   / d["revenue"] * 100, 1) if d["revenue"] > 0 else 0,
    }


@router.get("/timeline")
async def get_profit_timeline(
    days:  int = Query(30, ge=1, le=365),
    group: str = Query("day", description="day | week | month"),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_finance")),
):
    """Kunlik/haftalik/oylik daromad-tannarx-foyda grafigi uchun nuqtalar"""
    ensure_recurring_expenses(db, current_user)  # takroriy xarajatlar shu oygacha generatsiya
    start = date.today() - timedelta(days=days - 1)
    end   = date.today()
    trunc = {"day": "day", "week": "week", "month": "month"}.get(group, "day")
    biz_type = _get_biz_type(db, current_user)

    # Xarajatlar xaritasi (barcha turlarda bir xil)
    exp_bucket = func.date_trunc(trunc, Expense.expense_date).label("bucket")
    exp_q = (
        db.query(exp_bucket, func.sum(Expense.amount).label("amount"))
        .filter(Expense.expense_date >= start, Expense.expense_date <= end)
        .group_by(exp_bucket)
    )
    exp_map = {
        r.bucket.date().isoformat(): float(r.amount or 0)
        for r in apply_tenant_filter(exp_q, Expense, current_user).all()
        if r.bucket
    }

    if biz_type in _SERVICE_APT_TYPES or biz_type == "hotel":
        # Appointment asosli timeline
        apt_bucket = func.date_trunc(
            trunc, cast(Appointment.date, PG_TIMESTAMP)
        ).label("bucket")
        apt_q = (
            db.query(
                apt_bucket,
                func.sum(Appointment.price).label("revenue"),
                func.count(Appointment.id).label("count"),
            )
            .filter(
                Appointment.status == "completed",
                Appointment.date >= start,
                Appointment.date <= end,
            )
            .group_by(apt_bucket)
            .order_by(apt_bucket)
        )
        rows = apply_tenant_filter(apt_q, Appointment, current_user).all()

        # Hotel uchun room booking daromadini ham qo'shamiz
        rb_map: dict[str, float] = {}
        if biz_type == "hotel":
            rb_bucket = func.date_trunc(
                trunc, cast(RoomBooking.check_in, PG_TIMESTAMP)
            ).label("bucket")
            rb_q = (
                db.query(rb_bucket, func.sum(RoomBooking.total_amount).label("amount"))
                .filter(
                    RoomBooking.status.notin_(["cancelled"]),
                    RoomBooking.check_in >= start,
                    RoomBooking.check_in <= end,
                )
                .group_by(rb_bucket)
            )
            rb_map = {
                r.bucket.date().isoformat(): float(r.amount or 0)
                for r in apply_tenant_filter(rb_q, RoomBooking, current_user).all()
                if r.bucket
            }

        points = []
        for r in rows:
            d_key   = r.bucket.date().isoformat() if r.bucket else None
            revenue = float(r.revenue or 0) + rb_map.get(d_key, 0)
            exp_amt = exp_map.get(d_key, 0)
            points.append({
                "date":         d_key,
                "revenue":      round(revenue, 0),
                "cost":         0,
                "gross_profit": round(revenue, 0),
                "expenses":     round(exp_amt, 0),
                "net_profit":   round(revenue - exp_amt, 0),
            })
        return {"group": trunc, "days": days, "business_type": biz_type, "points": points}

    # Mahsulot asosli timeline (asl mantiq)
    bucket = func.date_trunc(trunc, Order.created_at).label("bucket")
    rows = (
        _sales_query(db, current_user, start, end)
        .with_entities(
            bucket,
            func.sum(_REVENUE_EXPR).label("revenue"),
            func.sum(_COST_EXPR * OrderItem.quantity).label("cost"),
        )
        .group_by(bucket)
        .order_by(bucket)
        .all()
    )

    points = []
    for r in rows:
        d_key   = r.bucket.date().isoformat() if r.bucket else None
        revenue = float(r.revenue or 0)
        cost    = float(r.cost or 0)
        exp_amt = exp_map.get(d_key, 0)
        points.append({
            "date":         d_key,
            "revenue":      round(revenue, 0),
            "cost":         round(cost, 0),
            "gross_profit": round(revenue - cost, 0),
            "expenses":     round(exp_amt, 0),
            "net_profit":   round(revenue - cost - exp_amt, 0),
        })
    return {"group": trunc, "days": days, "business_type": biz_type, "points": points}


@router.get("/top-products")
async def get_top_profit_items(
    limit: int = Query(10, ge=1, le=50),
    order: str = Query("best", description="best | worst"),
    days:  int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_finance")),
):
    """TOP mahsulotlar yoki xizmatlar foyda bo'yicha (biznes turiga qarab)"""
    start    = date.today() - timedelta(days=days - 1)
    end      = date.today()
    biz_type = _get_biz_type(db, current_user)

    # ── Xizmat asosli: Service bo'yicha ───────────────────────────────────────
    if biz_type in _SERVICE_APT_TYPES or biz_type == "hotel":
        apts = apply_tenant_filter(
            db.query(Appointment).filter(
                Appointment.status == "completed",
                Appointment.date >= start,
                Appointment.date <= end,
                Appointment.service_id != None,
            ),
            Appointment, current_user,
        ).all()

        svc_stats: dict[int, dict] = {}
        for a in apts:
            svc = a.service
            if not svc:
                continue
            sid = svc.id
            if sid not in svc_stats:
                svc_stats[sid] = {
                    "service_id": sid,
                    "name": svc.name,
                    "price": svc.price,
                    "cost_price": svc.cost_price,
                    "commission_pct": svc.commission_pct,
                    "count": 0,
                    "revenue": 0.0,
                    "material_cost": 0.0,
                    "commission_cost": 0.0,
                }
            st = svc_stats[sid]
            apt_price = a.price or 0
            st["count"]           += 1
            st["revenue"]         += apt_price
            st["material_cost"]   += svc.cost_price or 0
            st["commission_cost"] += apt_price * ((svc.commission_pct or 0) / 100)

        items = []
        for st in svc_stats.values():
            rev    = st["revenue"]
            cost   = st["material_cost"] + st["commission_cost"]
            profit = rev - cost
            items.append({
                **st,
                "revenue":         round(rev, 0),
                "material_cost":   round(st["material_cost"], 0),
                "commission_cost": round(st["commission_cost"], 0),
                "total_cost":      round(cost, 0),
                "profit":          round(profit, 0),
                "margin_pct":      round(profit / rev * 100, 1) if rev > 0 else 0,
            })

        items.sort(key=lambda x: x["profit"], reverse=(order != "worst"))
        return {"order": order, "days": days, "business_type": biz_type, "items": items[:limit]}

    # ── Mahsulot asosli: asl mantiq ───────────────────────────────────────────
    # TUZATISH: foyda endi SOF tushumdan hisoblanadi. Avval `unit_price` (katalog
    # narxi) olinardi — chegirma bilan sotilgan mahsulot foydali ko'rinib, "eng
    # foydali/eng zararli" reytingi ham noto'g'ri chiqardi.
    profit_expr = (
        func.sum(_REVENUE_EXPR) - func.sum(_COST_EXPR * OrderItem.quantity)
    ).label("profit")

    q = (
        _sales_query(db, current_user, start, end)
        .with_entities(
            Product.id,
            Product.name,
            Product.price,
            Product.cost_price,
            func.sum(OrderItem.quantity).label("qty_sold"),
            func.sum(_REVENUE_EXPR).label("revenue"),
            func.sum(_COST_EXPR * OrderItem.quantity).label("cost"),
            profit_expr,
        )
        .group_by(Product.id, Product.name, Product.price, Product.cost_price)
        .order_by(profit_expr.asc() if order == "worst" else profit_expr.desc())
        .limit(limit)
    )

    items = []
    for r in q.all():
        revenue = float(r.revenue or 0)
        profit  = float(r.profit or 0)
        items.append({
            "product_id": r.id,
            "name":        r.name,
            "price":       r.price,
            "cost_price":  r.cost_price,
            "qty_sold":    int(r.qty_sold or 0),
            "revenue":     round(revenue, 0),
            "cost":        round(float(r.cost or 0), 0),
            "profit":      round(profit, 0),
            "margin_pct":  round(profit / revenue * 100, 1) if revenue > 0 else 0,
        })
    return {"order": order, "days": days, "business_type": biz_type, "items": items}


@router.get("/by-category")
async def get_profit_by_category(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_finance")),
):
    """Kategoriya bo'yicha daromad, tan narx va foyda"""
    start    = date.today() - timedelta(days=days - 1)
    end      = date.today()
    biz_type = _get_biz_type(db, current_user)

    # ── Xizmat asosli: Service.category bo'yicha ─────────────────────────────
    if biz_type in _SERVICE_APT_TYPES or biz_type == "hotel":
        apts = apply_tenant_filter(
            db.query(Appointment).filter(
                Appointment.status == "completed",
                Appointment.date >= start,
                Appointment.date <= end,
            ),
            Appointment, current_user,
        ).all()

        cat_stats: dict[str, dict] = {}
        for a in apts:
            cat = (a.service.category if a.service else None) or "Boshqa"
            if cat not in cat_stats:
                cat_stats[cat] = {"name": cat, "revenue": 0.0, "cost": 0.0}
            cs = cat_stats[cat]
            cs["revenue"] += a.price or 0
            if a.service:
                cs["cost"] += (a.service.cost_price or 0)
                cs["cost"] += (a.price or 0) * ((a.service.commission_pct or 0) / 100)

        items = []
        for cs in sorted(cat_stats.values(), key=lambda x: -x["revenue"]):
            rev    = cs["revenue"]
            cost   = cs["cost"]
            profit = rev - cost
            items.append({
                "category_id": None,
                "name":        cs["name"],
                "revenue":     round(rev, 0),
                "cost":        round(cost, 0),
                "profit":      round(profit, 0),
                "margin_pct":  round(profit / rev * 100, 1) if rev > 0 else 0,
            })
        return {"days": days, "business_type": biz_type, "items": items}

    # ── Mahsulot asosli: asl mantiq ───────────────────────────────────────────
    rows = (
        _sales_query(db, current_user, start, end)
        .outerjoin(Category, Product.category_id == Category.id)
        .with_entities(
            Category.id,
            func.coalesce(Category.name, "Boshqa").label("name"),
            func.sum(_REVENUE_EXPR).label("revenue"),
            func.sum(_COST_EXPR * OrderItem.quantity).label("cost"),
        )
        .group_by(Category.id, Category.name)
        .order_by(func.sum(_REVENUE_EXPR).desc())
        .all()
    )

    items = []
    for r in rows:
        revenue = float(r.revenue or 0)
        cost    = float(r.cost or 0)
        profit  = revenue - cost
        items.append({
            "category_id": r.id,
            "name":        r.name,
            "revenue":     round(revenue, 0),
            "cost":        round(cost, 0),
            "profit":      round(profit, 0),
            "margin_pct":  round(profit / revenue * 100, 1) if revenue > 0 else 0,
        })
    return {"days": days, "business_type": biz_type, "items": items}


# ─── Mahsulot tan narxi (barcha tizimlar uchun) ───────────────────────────────

@router.get("/product-cost/{product_id}")
async def get_product_cost_info(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_finance")),
):
    """Mahsulot tan narxi va marjasi (retseptli bo'lsa — retseptdan hisoblangan)"""
    from services.cost_service import get_product_cost
    from models import Recipe

    product = apply_tenant_filter(db.query(Product), Product, current_user).filter(
        Product.id == product_id
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")

    cost      = get_product_cost(db, product_id)
    has_recipe = db.query(Recipe).filter(Recipe.product_id == product_id).first() is not None
    profit    = (product.price or 0) - cost

    return {
        "product_id":      product.id,
        "name":            product.name,
        "price":           product.price,
        "cost_price":      cost,
        "from_recipe":     has_recipe,
        "profit_per_unit": round(profit, 2),
        "margin_pct":      round(profit / product.price * 100, 1) if product.price else 0,
    }


@router.get("/service-cost/{service_id}")
async def get_service_cost_info(
    service_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_finance")),
):
    """Xizmat tan narxi: material + komissiya ulushi"""
    svc = apply_tenant_filter(db.query(Service), Service, current_user).filter(
        Service.id == service_id
    ).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Xizmat topilmadi")

    material   = svc.cost_price or 0
    commission = (svc.price or 0) * ((svc.commission_pct or 0) / 100)
    total_cost = material + commission
    profit     = (svc.price or 0) - total_cost

    return {
        "service_id":      svc.id,
        "name":            svc.name,
        "price":           svc.price,
        "material_cost":   round(material, 2),
        "commission_pct":  svc.commission_pct,
        "commission_cost": round(commission, 2),
        "total_cost":      round(total_cost, 2),
        "profit_per_unit": round(profit, 2),
        "margin_pct":      round(profit / svc.price * 100, 1) if svc.price else 0,
    }


# ─── Xarajatlar CRUD ──────────────────────────────────────────────────────────

EXPENSE_CATEGORIES = ["rent", "salary", "utility", "supplies", "marketing", "other"]


@router.get("/expenses")
async def get_expenses(
    period: str = Query("month"),
    start_date: Optional[date] = None,
    end_date:   Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_finance")),
):
    """Davr ichidagi xarajatlar ro'yxati"""
    ensure_recurring_expenses(db, current_user)  # takroriy xarajatlar shu oygacha generatsiya
    start, end = _period_range(period, start_date, end_date)
    q = db.query(Expense).filter(
        Expense.expense_date >= start,
        Expense.expense_date <= end,
    )
    expenses = apply_tenant_filter(q, Expense, current_user).order_by(
        Expense.expense_date.desc(), Expense.id.desc()
    ).all()

    return {
        "period": {"from": start.isoformat(), "to": end.isoformat()},
        "total":  round(sum(e.amount for e in expenses), 0),
        "items": [
            {
                "id":                   e.id,
                "category":             e.category,
                "name":                 e.name,
                "amount":               e.amount,
                "expense_date":         e.expense_date.isoformat(),
                "notes":                e.notes,
                "salary_id":            e.salary_id,             # maosh-avto xarajat belgisi
                "is_recurring":         e.is_recurring,          # takroriy shablon
                "recurrence_period":    e.recurrence_period if e.is_recurring else None,
                "recurrence_day":       e.recurrence_day if e.is_recurring else None,
                "recurrence_parent_id": e.recurrence_parent_id,  # generatsiya qilingan nusxa
            }
            for e in expenses
        ],
    }


@router.post("/expenses")
async def create_expense(
    expense_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_finance")),
):
    """Yangi xarajat kiritish:
       { name, amount, category?, expense_date?, notes?,
         is_recurring?, recurrence_period?, recurrence_day? }

    is_recurring=True bo'lsa — bu shablon; keyingi oy/haftalarda profit so'rovida
    avtomatik nusxalanadi (ensure_recurring_expenses). Shablonning o'zi kiritilgan
    sana uchun birinchi xarajat bo'lib hisoblanadi.
    """
    name   = (expense_data.get("name") or "").strip()
    amount = expense_data.get("amount")
    if not name or amount is None or float(amount) <= 0:
        raise HTTPException(status_code=400, detail="Nomi va musbat summa majburiy")

    category = expense_data.get("category", "other")
    if category not in EXPENSE_CATEGORIES:
        category = "other"

    exp_date = expense_data.get("expense_date")
    try:
        exp_date = date.fromisoformat(exp_date) if exp_date else date.today()
    except ValueError:
        raise HTTPException(status_code=400, detail="Sana formati noto'g'ri (YYYY-MM-DD)")

    # ── Takroriylik (BOSQICH 37) ─────────────────────────────────────────────
    is_recurring = bool(expense_data.get("is_recurring"))
    rec_period   = "monthly"
    rec_day      = None
    if is_recurring:
        rec_period = (expense_data.get("recurrence_period") or "monthly").lower()
        if rec_period not in ("monthly", "weekly"):
            rec_period = "monthly"
        if rec_period == "monthly":
            try:
                rec_day = int(expense_data.get("recurrence_day") or exp_date.day)
            except (TypeError, ValueError):
                rec_day = exp_date.day
            rec_day = max(1, min(31, rec_day))

    expense = Expense(
        tenant_id         = resolve_tenant_id(db, current_user),
        category          = category,
        name              = name,
        amount            = float(amount),
        expense_date      = exp_date,
        notes             = expense_data.get("notes"),
        created_by        = current_user.id,
        is_recurring      = is_recurring,
        recurrence_period = rec_period,
        recurrence_day    = rec_day,
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return {"success": True, "expense_id": expense.id, "message": "Xarajat qo'shildi"}


@router.delete("/expenses/{expense_id}")
async def delete_expense(
    expense_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_finance")),
):
    """Xarajatni o'chirish.

    - Maoshга bog'langan xarajat (salary_id) o'chirilsa, invariantni saqlash uchun
      tegishli maosh "to'lanmagan" holatiga qaytariladi (sof foyda izchil qolsin).
    - Takroriy shablon (is_recurring) o'chirilsa, kelajakда yangi nusxa
      generatsiya qilinmaydi; allaqachon yaratilgan nusxalar tarix sifatida qoladi
      (recurrence_parent_id FK ondelete=SET NULL).
    """
    from models import Salary  # lokal import — tsiklik importdan saqlanish
    expense = apply_tenant_filter(db.query(Expense), Expense, current_user).filter(
        Expense.id == expense_id
    ).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Xarajat topilmadi")

    linked_salary_id = expense.salary_id
    db.delete(expense)
    if linked_salary_id:
        salary = db.query(Salary).filter(Salary.id == linked_salary_id).first()
        if salary and salary.is_paid:
            salary.is_paid = False
            salary.paid_at = None

    db.commit()
    return {"success": True, "message": "Xarajat o'chirildi"}
