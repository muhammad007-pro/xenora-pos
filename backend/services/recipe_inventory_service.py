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
        # Retsept yo'q → mahsulotning O'ZI ombor birligi (magazin/dorixona/chakana).
        # Sotilgan miqdor to'g'ridan mahsulot omboridan ayiriladi (sotuv = chiqim).
        return _deduct_product_directly(db, product_id, quantity, tenant_id, order_id, user_id)

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

        # ROW-LOCK: bir vaqtda 2 sotuv bir ingredientni ayirsa lost update bo'lmasin
        # (SELECT ... FOR UPDATE). Qulf shu tranzaksiya commit'ida bo'shaydi. PostgreSQL'da
        # ishlaydi; qo'llab-quvvatlamaydigan dialektda (SQLite) SQLAlchemy jimgina o'tkazadi.
        inventory = inv_q.with_for_update().first()

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


def _deduct_product_directly(
    db: Session,
    product_id: int,
    quantity: float,
    tenant_id: Optional[int] = None,
    order_id: Optional[int] = None,
    user_id: Optional[int] = None,
) -> dict:
    """Retseptsiz mahsulot (chakana tovar) omboridan to'g'ridan chiqim.

    Mahsulotning O'Z Inventory yozuvidan sotilgan miqdorni ayiradi va StockMovement
    (movement_type="sale") yozadi — sotuv ombor harakati bilan bog'lanadi (qaytarish
    bilan izchil). Ombor yozuvi bo'lmasa — jimgina o'tkazib yuboriladi (ombor nazorati
    o'chirilgan tovar/xizmat). Manfiy qoldiqqa tushmaydi (0 da to'xtaydi), sotuvni bloklamaydi.
    """
    from models import Inventory, Product, StockMovement

    inv_q = db.query(Inventory).filter(Inventory.product_id == product_id)
    if tenant_id:
        inv_q = inv_q.filter(Inventory.tenant_id == tenant_id)
    inventory = inv_q.with_for_update().first()   # ROW-LOCK (lost update oldини oladi)

    if not inventory:
        # Ombor nazorati yo'q tovar (masalan xizmat) — chiqim shart emas.
        return {"success": True, "deducted": [], "warnings": []}

    actual = quantity if inventory.quantity >= quantity else inventory.quantity
    inventory.quantity -= actual

    # Ombor harakati (chiqim/sotuv) — qaytarish bilan izchil audit izi.
    product = db.query(Product).filter(Product.id == product_id).first()
    unit_cost = (product.cost_price if product else 0.0) or 0.0
    db.add(StockMovement(
        tenant_id=tenant_id,
        product_id=product_id,
        inventory_id=inventory.id,
        movement_type="sale",
        quantity=actual,
        unit=inventory.unit or "dona",
        unit_cost=unit_cost,
        total_cost=round(unit_cost * actual, 2),
        reason="sale",
        reference_id=order_id,
        reference_type="order",
        user_id=user_id,
    ))

    warnings = []
    if actual < quantity:
        warnings.append({
            "product_id": product_id,
            "needed": quantity,
            "available": actual,
            "reason": "Ombor qoldig'i yetarli emas (0 gacha ayirildi)",
        })
    if inventory.quantity <= (inventory.min_threshold or 0):
        warnings.append({
            "product_id": product_id,
            "reason": f"Kam qoldi: {inventory.quantity} {inventory.unit}",
        })

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Direct product deduction commit error: {e}")
        return {"success": False, "deducted": [], "warnings": [str(e)]}

    return {
        "success": True,
        "deducted": [{"product_id": product_id, "deducted": actual, "remaining": inventory.quantity}],
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
            # BOSQICH B1 (pachka/dona): ombordan ayiriladigan DONA miqdori.
            # base_qty bo'lsa (pachka: pack_size×soni) shuni, aks holda quantity
            # (oddiy/dona). Hozir hamma base_qty=NULL → aynan quantity → xulq bir xil.
            quantity=item.base_qty if item.base_qty is not None else item.quantity,
            tenant_id=tenant_id,
            order_id=order_id,
            user_id=user_id,
        )
        result["product_id"] = item.product_id
        result["quantity"]   = item.quantity
        results.append(result)

    return results


# ─────────────────────────────────────────────────────────────────────────────
# TIKLASH (refund/qaytarish) — deduct ning teskarisi
# Sotuv omborni kamaytirdi; to'liq qaytarish (refund) omborni qaytadan oshiradi.
# StockMovement(movement_type="return", reason="refund") audit izi bilan.
# Idempotentlik chaqiruvchida (Order.ingredients_restored) nazorat qilinadi.
# ─────────────────────────────────────────────────────────────────────────────

def restore_recipe_ingredients(
    db: Session,
    product_id: int,
    quantity: float,
    tenant_id: Optional[int] = None,
    order_id: Optional[int] = None,
    user_id: Optional[int] = None,
) -> dict:
    """Bitta order item uchun retsept ingredientlarini omborga QAYTARISH.

    deduct_recipe_ingredients bilan bir xil miqdor hisobi (yield_pct → raw_qty),
    lekin quantity ni ayirmasdan qo'shadi. Retseptsiz mahsulot bo'lsa — o'zini tiklaydi.
    """
    from models import Recipe, Inventory, StockMovement

    recipe = db.query(Recipe).filter(
        Recipe.product_id == product_id,
    ).first()

    if not recipe:
        return _restore_product_directly(db, product_id, quantity, tenant_id, order_id, user_id)

    restored = []
    for item in recipe.items:
        recipe_qty = item.quantity * quantity
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
        inventory = inv_q.with_for_update().first()   # ROW-LOCK (tiklashda ham race yo'q)

        if not inventory:
            # Ombor yozuvi yo'q ingredient — tiklashga joy yo'q, o'tkazib yuboriladi.
            continue

        inventory.quantity += raw_qty
        unit_cost = (ingredient.cost_price if ingredient else 0.0) or 0.0
        db.add(StockMovement(
            tenant_id=tenant_id,
            product_id=item.ingredient_id,
            inventory_id=inventory.id,
            movement_type="return",
            quantity=round(raw_qty, 6),
            unit=inventory.unit or "kg",
            unit_cost=unit_cost,
            total_cost=round(unit_cost * raw_qty, 2),
            reason="refund",
            reference_id=order_id,
            reference_type="order",
            user_id=user_id,
        ))
        restored.append({
            "ingredient_id": item.ingredient_id,
            "restored": raw_qty,
            "remaining": inventory.quantity,
        })

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Recipe restore commit error: {e}")
        return {"success": False, "restored": [], "warnings": [str(e)]}

    return {"success": True, "restored": restored, "warnings": []}


def _restore_product_directly(
    db: Session,
    product_id: int,
    quantity: float,
    tenant_id: Optional[int] = None,
    order_id: Optional[int] = None,
    user_id: Optional[int] = None,
) -> dict:
    """Retseptsiz mahsulot (chakana tovar) omboriga to'g'ridan QAYTARISH.

    _deduct_product_directly ning teskarisi — sotilgan miqdorni qaytadan qo'shadi
    va StockMovement(movement_type="return") yozadi. Ombor yozuvi bo'lmasa o'tkaziladi.
    """
    from models import Inventory, Product, StockMovement

    inv_q = db.query(Inventory).filter(Inventory.product_id == product_id)
    if tenant_id:
        inv_q = inv_q.filter(Inventory.tenant_id == tenant_id)
    inventory = inv_q.with_for_update().first()   # ROW-LOCK (tiklashda ham race yo'q)

    if not inventory:
        return {"success": True, "restored": [], "warnings": []}

    inventory.quantity += quantity
    product = db.query(Product).filter(Product.id == product_id).first()
    unit_cost = (product.cost_price if product else 0.0) or 0.0
    db.add(StockMovement(
        tenant_id=tenant_id,
        product_id=product_id,
        inventory_id=inventory.id,
        movement_type="return",
        quantity=quantity,
        unit=inventory.unit or "dona",
        unit_cost=unit_cost,
        total_cost=round(unit_cost * quantity, 2),
        reason="refund",
        reference_id=order_id,
        reference_type="order",
        user_id=user_id,
    ))

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Direct product restore commit error: {e}")
        return {"success": False, "restored": [], "warnings": [str(e)]}

    return {
        "success": True,
        "restored": [{"product_id": product_id, "restored": quantity, "remaining": inventory.quantity}],
        "warnings": [],
    }


def restore_order_ingredients(
    db: Session,
    order_id: int,
    tenant_id: Optional[int] = None,
    user_id: Optional[int] = None,
) -> list:
    """Butun buyurtma uchun sotuvda kamaygan omborni QAYTARISH (refund).

    deduct_order_ingredients ning teskarisi. Idempotentlik chaqiruvchida
    (Order.ingredients_restored flag) nazorat qilinishi SHART — bu funksiya
    o'zi ikki marta chaqirilsa ombor ikki marta oshadi.
    """
    from models import Order

    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return []

    results = []
    for item in order.items:
        result = restore_recipe_ingredients(
            db=db,
            product_id=item.product_id,
            # BOSQICH B1 (pachka/dona): omborga QAYTARILADIGAN dona miqdori — deduct
            # bilan bir xil fallback (base_qty ?? quantity). base_qty=NULL → quantity.
            quantity=item.base_qty if item.base_qty is not None else item.quantity,
            tenant_id=tenant_id,
            order_id=order_id,
            user_id=user_id,
        )
        result["product_id"] = item.product_id
        result["quantity"]   = item.quantity
        results.append(result)

    return results
