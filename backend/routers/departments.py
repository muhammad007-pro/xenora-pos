"""Bo'limlar (Departments) вЂ” magazin/supermarket fizik seksiyalari, CRUD + hisobotlar"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func as sqlfunc
from datetime import datetime, timedelta
from typing import Optional

from database import get_db
from models import Department, Category, Product, OrderItem, Order, Inventory, User
from deps import resolve_tenant_id, get_current_active_user, has_permission, apply_tenant_filter

from deps import require_feature  # funksiya-flag himoyasi (O'ZGARISH 3)
router = APIRouter(dependencies=[Depends(require_feature("departments"))])


# в”Ђв”Ђ CRUD в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

@router.get("/")
async def list_departments(
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Barcha bo'limlar"""
    tid = resolve_tenant_id(db, current_user)
    q = db.query(Department).filter(Department.tenant_id == tid)
    if is_active is not None:
        q = q.filter(Department.is_active == is_active)
    depts = q.order_by(Department.display_order.asc(), Department.name.asc()).all()
    return [_dept_dict(d, db, tid) for d in depts]


@router.post("/")
async def create_department(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu")),
):
    """Yangi bo'lim yaratish"""
    tid = resolve_tenant_id(db, current_user)
    dept = Department(
        tenant_id=tid,
        name=data.get("name", "").strip(),
        description=data.get("description"),
        color=data.get("color", "#6366f1"),
        icon=data.get("icon"),
        display_order=data.get("display_order", 0),
        is_active=data.get("is_active", True),
    )
    if not dept.name:
        raise HTTPException(status_code=400, detail="Nomi kiritilmagan")
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return _dept_dict(dept, db, tid)


@router.put("/{dept_id}")
async def update_department(
    dept_id: int,
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu")),
):
    tid = resolve_tenant_id(db, current_user)
    dept = db.query(Department).filter(Department.id == dept_id, Department.tenant_id == tid).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Bo'lim topilmadi")
    for field in ("name", "description", "color", "icon", "display_order", "is_active"):
        if field in data:
            setattr(dept, field, data[field])
    db.commit()
    db.refresh(dept)
    return _dept_dict(dept, db, tid)


@router.delete("/{dept_id}")
async def delete_department(
    dept_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu")),
):
    tid = resolve_tenant_id(db, current_user)
    dept = db.query(Department).filter(Department.id == dept_id, Department.tenant_id == tid).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Bo'lim topilmadi")
    prod_count = db.query(Product).filter(Product.department_id == dept_id, Product.tenant_id == tid).count()
    if prod_count > 0:
        dept.is_active = False
        db.commit()
        return {"ok": True, "message": f"{prod_count} mahsulot bor, o'chirilmadi вЂ” nofaol qilindi"}
    db.delete(dept)
    db.commit()
    return {"ok": True}


@router.get("/{dept_id}/products")
async def get_department_products(
    dept_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Bo'limdagi mahsulotlar"""
    tid = resolve_tenant_id(db, current_user)
    q = db.query(Product).filter(
        Product.department_id == dept_id,
        Product.tenant_id == tid,
        Product.is_active == True,
    )
    total = q.count()
    products = q.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "items": [_prod_dict(p) for p in products],
    }


# в”Ђв”Ђ Hisobotlar в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

@router.get("/report/sales")
async def dept_sales_report(
    period: str = Query("month", pattern="^(today|week|month|year)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports")),
):
    """Bo'lim bo'yicha sotuv hisoboti"""
    tid = resolve_tenant_id(db, current_user)
    now = datetime.now()
    start = {
        "today": now.replace(hour=0, minute=0, second=0, microsecond=0),
        "week":  now - timedelta(days=7),
        "month": now - timedelta(days=30),
        "year":  now - timedelta(days=365),
    }[period]

    depts = db.query(Department).filter(Department.tenant_id == tid, Department.is_active == True).all()
    result = []

    for dept in depts:
        # Bo'limdagi mahsulot id lari
        prod_ids = [p.id for p in db.query(Product.id).filter(
            Product.department_id == dept.id, Product.tenant_id == tid,
        ).all()]
        if not prod_ids:
            continue

        rows = db.query(
            sqlfunc.sum(OrderItem.quantity).label("qty"),
            sqlfunc.sum(OrderItem.total_price).label("revenue"),
        ).join(OrderItem.order).filter(
            OrderItem.product_id.in_(prod_ids),
            Order.tenant_id == tid,
            Order.status == "completed",
            Order.created_at >= start,
        ).first()

        revenue = float(rows.revenue or 0)
        qty     = float(rows.qty or 0)

        # Foyda (revenue - cost)
        cost_rows = db.query(sqlfunc.sum(
            OrderItem.quantity * Product.cost_price
        )).join(Product, Product.id == OrderItem.product_id).filter(
            OrderItem.product_id.in_(prod_ids),
            OrderItem.order_id.in_(
                db.query(Order.id).filter(
                    Order.tenant_id == tid, Order.status == "completed",
                    Order.created_at >= start,
                )
            ),
        ).scalar() or 0

        result.append({
            "id":      dept.id,
            "name":    dept.name,
            "color":   dept.color,
            "icon":    dept.icon,
            "qty":     round(qty, 2),
            "revenue": round(revenue, 0),
            "cost":    round(float(cost_rows), 0),
            "profit":  round(revenue - float(cost_rows), 0),
            "margin":  round((revenue - float(cost_rows)) / revenue * 100, 1) if revenue else 0,
        })

    result.sort(key=lambda x: x["revenue"], reverse=True)
    return {"period": period, "departments": result}


@router.get("/report/inventory")
async def dept_inventory_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports")),
):
    """Bo'lim bo'yicha ombor qoldiqlari"""
    tid = resolve_tenant_id(db, current_user)
    depts = db.query(Department).filter(Department.tenant_id == tid, Department.is_active == True).all()
    result = []

    for dept in depts:
        products = db.query(Product).filter(
            Product.department_id == dept.id,
            Product.tenant_id == tid,
            Product.is_active == True,
        ).all()
        if not products:
            continue

        total_value = sum(
            _stock_qty(p) * (p.cost_price or p.price or 0)
            for p in products
        )
        low_stock = sum(
            1 for p in products
            if _stock_qty(p) < _min_threshold(p)
        )

        result.append({
            "id":          dept.id,
            "name":        dept.name,
            "color":       dept.color,
            "icon":        dept.icon,
            "products":    len(products),
            "total_value": round(total_value, 0),
            "low_stock":   low_stock,
        })

    return result


@router.get("/report/chart")
async def dept_chart(
    period: str = Query("week", pattern="^(week|month)$"),
    dept_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports")),
):
    """Bo'lim(lar) bo'yicha kunlik sotuv grafigi"""
    tid = resolve_tenant_id(db, current_user)
    now = datetime.now()
    days = 7 if period == "week" else 30
    start = now - timedelta(days=days)

    if dept_id:
        dept_filter = [dept_id]
    else:
        dept_filter = [
            d.id for d in db.query(Department.id).filter(
                Department.tenant_id == tid, Department.is_active == True,
            ).all()
        ]

    chart = {}  # date_str в†’ {dept_id: amount}

    for d_id in dept_filter:
        prod_ids = [p.id for p in db.query(Product.id).filter(
            Product.department_id == d_id, Product.tenant_id == tid,
        ).all()]
        if not prod_ids:
            continue

        rows = db.query(
            sqlfunc.date(Order.created_at).label("day"),
            sqlfunc.sum(OrderItem.total_price).label("total"),
        ).join(OrderItem.order).filter(
            OrderItem.product_id.in_(prod_ids),
            Order.tenant_id == tid,
            Order.status == "completed",
            Order.created_at >= start,
        ).group_by(sqlfunc.date(Order.created_at)).all()

        for row in rows:
            day_str = str(row.day)
            if day_str not in chart:
                chart[day_str] = {}
            chart[day_str][d_id] = round(float(row.total or 0), 0)

    dept_names = {}
    dept_colors = {}
    for d_id in dept_filter:
        dept = db.query(Department).filter(Department.id == d_id).first()
        if dept:
            dept_names[d_id] = dept.name
            dept_colors[d_id] = dept.color

    return {
        "period": period,
        "dates":  sorted(chart.keys()),
        "data":   chart,
        "departments": [{"id": d_id, "name": dept_names.get(d_id, ""), "color": dept_colors.get(d_id, "")} for d_id in dept_filter],
    }


def _dept_dict(dept: Department, db: Session, tid: int) -> dict:
    prod_count = db.query(Product).filter(
        Product.department_id == dept.id, Product.tenant_id == tid, Product.is_active == True,
    ).count()
    cat_count = db.query(Category).filter(
        Category.department_id == dept.id, Category.tenant_id == tid,
    ).count()
    return {
        "id":            dept.id,
        "name":          dept.name,
        "description":   dept.description,
        "color":         dept.color,
        "icon":          dept.icon,
        "display_order": dept.display_order,
        "is_active":     dept.is_active,
        "products_count": prod_count,
        "categories_count": cat_count,
    }


def _stock_qty(p: Product) -> float:
    """Mahsulot ombor qoldig'i — Inventory jadvalidan (Product'da stock ustuni yo'q)."""
    return sum((inv.quantity or 0) for inv in (p.inventory_items or []))


def _min_threshold(p: Product) -> float:
    """Minimal qoldiq chegarasi — Inventory'dan (default 5)."""
    invs = p.inventory_items or []
    if invs and invs[0].min_threshold is not None:
        return invs[0].min_threshold
    return 5


def _prod_dict(p: Product) -> dict:
    return {
        "id":             p.id,
        "name":           p.name,
        "price":          p.price,
        "cost_price":     p.cost_price,
        "stock_quantity": _stock_qty(p),
        "barcode":        p.barcode,
        "image_url":      p.image_url,
    }

