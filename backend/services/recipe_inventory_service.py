"""
Retsept asosida inventardan avtomatik kamaytirish (BOSQICH 5.4)
Yield (poteriya) hisobi qo'shildi (BOSQICH 17)

Buyurtma elementi "served" yoki "completed" bo'lganda:
  product.recipe → har bir ingredient uchun:
    1) yield_pct bo'lsa — xom miqdor (raw_qty) hisoblanadi
    2) Inventory.quantity raw_qty miqdorga kamaytiriladi
    3) Farq (raw_qty - recipe_qty) WasteLog ga "recipe" turi bilan yoziladi

Agar ingredient yetarli bo'lmasa — ogohlantirish qaytariladi (buyurtma bekor qilinmaydi).
"""
from sqlalchemy.orm import Session
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def deduct_recipe_ingredients(
    db: Session,
    product_id: int,
    quantity: float,
    tenant_id: Optional[int] = None,
    order_id: Optional[int] = None,
    user_id: Optional[int] = None,
) -> dict:
    """
    Bitta order item uchun retsept ingredientlarini inventardan kamaytirish.
    yield_pct bo'lsa — xom miqdor (raw_qty) ishlatiladi, farq WasteLog ga yoziladi.
    Qaytaradi: { "success": bool, "deducted": [...], "warnings": [...] }
    """
    from models import Recipe, RecipeItem, Inventory, WasteLog

    recipe = db.query(Recipe).filter(
        Recipe.product_id == product_id,
    ).first()

    if not recipe:
        return {"success": True, "deducted": [], "warnings": []}

    deducted = []
    warnings = []

    for item in recipe.items:
        # Retseptda kerakli tayyor/pishgan miqdor (1 porsiya × buyurtma soni)
        recipe_qty = item.quantity * quantity

        # BOSQICH 17: yield_pct bo'lsa xom miqdorni hisoblash
        # Misol: 700g pishgan go'sht, yield 70% → 700 / 0.70 = 1000g xom ketadi
        ingredient = item.ingredient
        yield_pct = (ingredient.yield_pct if ingredient and ingredient.yield_pct else None)
        if yield_pct and 0 < yield_pct < 100:
            raw_qty = recipe_qty / (yield_pct / 100)
        else:
            raw_qty = recipe_qty

        inv_q = db.query(Inventory).filter(
            Inventory.product_id == item.ingredient_id,
        )
        if tenant_id:
            inv_q = inv_q.filter(Inventory.tenant_id == tenant_id)

        inventory = inv_q.first()

        if not inventory:
            warnings.append({
                "ingredient_id": item.ingredient_id,
                "reason": "Omborda topilmadi",
            })
            continue

        if inventory.quantity < raw_qty:
            warnings.append({
                "ingredient_id": item.ingredient_id,
                "ingredient_name": ingredient.name if ingredient else str(item.ingredient_id),
                "needed": raw_qty,
                "available": inventory.quantity,
                "reason": "Miqdor yetarli emas",
            })
            actual_deduct = inventory.quantity
        else:
            actual_deduct = raw_qty

        inventory.quantity -= actual_deduct
        deducted.append({
            "ingredient_id": item.ingredient_id,
            "deducted": actual_deduct,
            "remaining": inventory.quantity,
        })

        # BOSQICH 17: poteriya miqdorini WasteLog ga yozish
        # Poteriya = xom ketgan - tayyor kerakli (faqat yield_pct bo'lganda)
        waste_qty = actual_deduct - recipe_qty
        if waste_qty > 0.0001 and ingredient:
            unit_cost = ingredient.cost_price or 0.0
            db.add(WasteLog(
                tenant_id=tenant_id,
                product_id=item.ingredient_id,
                quantity=round(waste_qty, 6),
                unit=item.unit or "kg",
                unit_cost=unit_cost,
                total_cost=round(unit_cost * waste_qty, 2),
                waste_type="recipe",
                order_id=order_id,
                user_id=user_id,
            ))

        # Kam qoldi tekshirish
        if inventory.quantity <= (inventory.min_threshold or 0):
            warnings.append({
                "ingredient_id": item.ingredient_id,
                "reason": f"Kam qoldi: {inventory.quantity} {inventory.unit}",
            })

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Recipe deduction commit error: {e}")
        return {"success": False, "deducted": [], "warnings": [str(e)]}

    return {
        "success": True,
        "deducted": deducted,
        "warnings": warnings,
    }


def deduct_order_ingredients(
    db: Session,
    order_id: int,
    tenant_id: Optional[int] = None,
    user_id: Optional[int] = None,
) -> list:
    """Butun buyurtma uchun barcha retsept ingredientlarini kamaytirish"""
    from models import Order

    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return []

    results = []
    for item in order.items:
        result = deduct_recipe_ingredients(
            db=db,
            product_id=item.product_id,
            quantity=item.quantity,
            tenant_id=tenant_id,
            order_id=order_id,
            user_id=user_id,
        )
        result["product_id"] = item.product_id
        result["quantity"]   = item.quantity
        results.append(result)

    return results
