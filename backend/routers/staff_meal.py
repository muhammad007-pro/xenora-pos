"""
Xodimlar ovqati (Staff Meal) — BOSQICH 18

Xodimlar bepul ovqatlanganda:
  - Taom retsepti asosida ombordan mahsulotlar kamayadi
  - StaffMeal yozuvi saqlanadi (kim, nima, qancha, narx)
  - StockMovement tarixi yoziladi (movement_type='staff_meal')
  - Savdoga (orders) bog'liq emas — daromad hisoblanmaydi
  - Xarajat sifatida hisobotlarda ko'rinadi
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from datetime import date

from database import get_db
from models import StaffMeal, Employee, Product, Inventory, StockMovement, User
from schemas import StaffMealCreate, StaffMealInDB
from deps import get_current_active_user as get_current_user, resolve_tenant_id, has_permission
from services.recipe_inventory_service import deduct_recipe_ingredients

router = APIRouter()


@router.post("/", response_model=StaffMealInDB)
async def create_staff_meal(
    data: StaffMealCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Xodim ovqatini qayd etish — ombordan retsept asosida kamaytirish"""
    tenant_id = resolve_tenant_id(db, current_user)

    employee = db.query(Employee).filter(Employee.id == data.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Xodim topilmadi")

    product = db.query(Product).filter(Product.id == data.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")

    cost_price = product.cost_price or 0.0
    total_cost = round(cost_price * data.quantity, 2)

    # Retsept asosida ombordan kamaytirish
    deduct_result = deduct_recipe_ingredients(
        db=db,
        product_id=data.product_id,
        quantity=data.quantity,
        tenant_id=tenant_id,
        order_id=None,
        user_id=current_user.id,
    )

    # StockMovement tarixi: har bir ingredient uchun staff_meal yozuvi
    for item in deduct_result.get("deducted", []):
        inv = db.query(Inventory).filter(
            Inventory.product_id == item["ingredient_id"],
        )
        if tenant_id:
            inv = inv.filter(Inventory.tenant_id == tenant_id)
        inv_rec = inv.first()

        ingr_product = db.query(Product).filter(Product.id == item["ingredient_id"]).first()
        unit_cost = ingr_product.cost_price if ingr_product else 0.0
        qty = item["deducted"]

        db.add(StockMovement(
            tenant_id=tenant_id,
            branch_id=current_user.branch_id if hasattr(current_user, "branch_id") else None,
            inventory_id=inv_rec.id if inv_rec else None,
            product_id=item["ingredient_id"],
            movement_type="staff_meal",
            quantity=qty,
            unit=inv_rec.unit if inv_rec else "dona",
            unit_cost=unit_cost,
            total_cost=round(unit_cost * qty, 2),
            reason="staff_meal",
            reference_type="staff_meal",
            user_id=current_user.id,
        ))

    # StaffMeal yozuvi
    meal = StaffMeal(
        tenant_id=tenant_id,
        branch_id=current_user.branch_id if hasattr(current_user, "branch_id") else None,
        employee_id=data.employee_id,
        product_id=data.product_id,
        quantity=data.quantity,
        cost_price=cost_price,
        total_cost=total_cost,
        notes=data.notes,
        created_by=current_user.id,
    )
    db.add(meal)
    db.commit()
    db.refresh(meal)

    return StaffMealInDB(
        id=meal.id,
        tenant_id=meal.tenant_id,
        branch_id=meal.branch_id,
        employee_id=meal.employee_id,
        product_id=meal.product_id,
        quantity=meal.quantity,
        cost_price=meal.cost_price,
        total_cost=meal.total_cost,
        notes=meal.notes,
        created_by=meal.created_by,
        created_at=meal.created_at,
        employee_name=employee.full_name,
        employee_position=employee.position,
        product_name=product.name,
    )


@router.get("/")
async def list_staff_meals(
    employee_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Xodimlar ovqati ro'yxati"""
    tenant_id = resolve_tenant_id(db, current_user)

    q = db.query(StaffMeal)
    if tenant_id:
        q = q.filter(StaffMeal.tenant_id == tenant_id)
    if employee_id:
        q = q.filter(StaffMeal.employee_id == employee_id)
    if date_from:
        q = q.filter(func.date(StaffMeal.created_at) >= date_from)
    if date_to:
        q = q.filter(func.date(StaffMeal.created_at) <= date_to)

    total = q.count()
    meals = q.order_by(StaffMeal.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for m in meals:
        items.append({
            "id": m.id,
            "employee_id": m.employee_id,
            "employee_name": m.employee.full_name if m.employee else None,
            "employee_position": m.employee.position if m.employee else None,
            "product_id": m.product_id,
            "product_name": m.product.name if m.product else None,
            "quantity": m.quantity,
            "cost_price": m.cost_price,
            "total_cost": m.total_cost,
            "notes": m.notes,
            "created_at": m.created_at,
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get("/report")
async def staff_meal_report(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports")),
):
    """Xodimlar ovqati hisoboti — jami xarajat, xodim bo'yicha breakdown"""
    tenant_id = resolve_tenant_id(db, current_user)

    q = db.query(StaffMeal)
    if tenant_id:
        q = q.filter(StaffMeal.tenant_id == tenant_id)
    if date_from:
        q = q.filter(func.date(StaffMeal.created_at) >= date_from)
    if date_to:
        q = q.filter(func.date(StaffMeal.created_at) <= date_to)

    meals = q.all()

    total_count = len(meals)
    total_cost = sum(m.total_cost for m in meals)

    # Xodim bo'yicha breakdown
    by_employee: dict = {}
    for m in meals:
        emp_name = m.employee.full_name if m.employee else f"#{m.employee_id}"
        emp_pos = m.employee.position if m.employee else ""
        key = m.employee_id
        if key not in by_employee:
            by_employee[key] = {
                "employee_id": m.employee_id,
                "employee_name": emp_name,
                "employee_position": emp_pos,
                "count": 0,
                "total_cost": 0.0,
            }
        by_employee[key]["count"] += 1
        by_employee[key]["total_cost"] = round(by_employee[key]["total_cost"] + m.total_cost, 2)

    by_employee_list = sorted(by_employee.values(), key=lambda x: x["total_cost"], reverse=True)

    return {
        "total_count": total_count,
        "total_cost": round(total_cost, 2),
        "date_from": date_from,
        "date_to": date_to,
        "by_employee": by_employee_list,
    }


@router.delete("/{meal_id}")
async def delete_staff_meal(
    meal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Xodim ovqati yozuvini o'chirish (ombor qaytarilmaydi)"""
    tenant_id = resolve_tenant_id(db, current_user)

    meal = db.query(StaffMeal).filter(StaffMeal.id == meal_id)
    if tenant_id:
        meal = meal.filter(StaffMeal.tenant_id == tenant_id)
    meal = meal.first()

    if not meal:
        raise HTTPException(status_code=404, detail="Yozuv topilmadi")

    db.delete(meal)
    db.commit()
    return {"success": True, "message": "Yozuv o'chirildi"}
