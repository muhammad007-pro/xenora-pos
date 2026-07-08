from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from database import get_db
from models import Recipe, RecipeItem, Product, User
from schemas import MessageResponse
from deps import resolve_tenant_id, get_current_active_user, has_permission, apply_tenant_filter

router = APIRouter()

@router.get("/")
async def get_recipes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Barcha retseptlarni olish"""
    query = db.query(Recipe)
    # BOSQICH 1.5: tenant bo'yicha cheklash
    query = apply_tenant_filter(query, Recipe, current_user)

    if search:
        query = query.filter(Recipe.name.ilike(f"%{search}%"))

    total = query.count()
    recipes = query.offset((page - 1) * page_size).limit(page_size).all()

    result = []
    for r in recipes:
        items = db.query(RecipeItem).filter(RecipeItem.recipe_id == r.id).all()
        result.append({
            "id": r.id,
            "product_id": r.product_id,
            "name": r.name,
            "description": r.description,
            "preparation_time": r.preparation_time,
            "created_at": r.created_at,
            "items": [
                {
                    "id": i.id,
                    "ingredient_id": i.ingredient_id,
                    "ingredient_name": i.ingredient.name if i.ingredient else None,
                    "quantity": i.quantity,
                    "unit": i.unit,
                    "notes": i.notes
                }
                for i in items
            ]
        })

    return {
        "items": result,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }

@router.get("/product/{product_id}")
async def get_recipe_by_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Mahsulot bo'yicha retseptni olish"""
    # BOSQICH 1.5: tenant bo'yicha cheklash
    recipe = apply_tenant_filter(db.query(Recipe), Recipe, current_user).filter(
        Recipe.product_id == product_id
    ).first()

    if not recipe:
        return None

    items = db.query(RecipeItem).filter(RecipeItem.recipe_id == recipe.id).all()

    return {
        "id": recipe.id,
        "product_id": recipe.product_id,
        "name": recipe.name,
        "description": recipe.description,
        "preparation_time": recipe.preparation_time,
        "items": [
            {
                "id": i.id,
                "ingredient_id": i.ingredient_id,
                "ingredient_name": i.ingredient.name if i.ingredient else None,
                "quantity": i.quantity,
                "unit": i.unit,
                "notes": i.notes
            }
            for i in items
        ]
    }

@router.post("/")
async def create_recipe(
    product_id: int,
    name: str,
    items: List[dict],
    description: Optional[str] = None,
    preparation_time: int = 15,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu"))
):
    """Yangi retsept yaratish"""
    # Mahsulot mavjudligini tekshirish (BOSQICH 1.5: tenant bo'yicha)
    product = apply_tenant_filter(db.query(Product), Product, current_user).filter(
        Product.id == product_id
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")

    # Retsept mavjudligini tekshirish
    existing = apply_tenant_filter(db.query(Recipe), Recipe, current_user).filter(
        Recipe.product_id == product_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Bu mahsulot uchun retsept allaqachon mavjud")

    # BOSQICH 1.5: yangi retsept yaratuvchi tenant'iga biriktiriladi
    recipe = Recipe(
        product_id=product_id,
        name=name,
        description=description,
        preparation_time=preparation_time,
        tenant_id=resolve_tenant_id(db, current_user)
    )
    db.add(recipe)
    db.flush()

    for item in items:
        ingredient = apply_tenant_filter(db.query(Product), Product, current_user).filter(
            Product.id == item["ingredient_id"]
        ).first()
        if not ingredient:
            raise HTTPException(status_code=404, detail=f"Ingredient topilmadi: {item['ingredient_id']}")

        recipe_item = RecipeItem(
            recipe_id=recipe.id,
            ingredient_id=item["ingredient_id"],
            quantity=item["quantity"],
            unit=item.get("unit", "kg"),
            notes=item.get("notes"),
            tenant_id=resolve_tenant_id(db, current_user)
        )
        db.add(recipe_item)

    # BOSQICH 15: tan narxni ingredientlardan avtomatik hisoblab mahsulotga yozish
    from services.cost_service import sync_product_cost_from_recipe
    db.flush()
    cost = sync_product_cost_from_recipe(db, product_id)

    db.commit()
    db.refresh(recipe)

    return {"success": True, "recipe_id": recipe.id, "cost_price": cost, "message": "Retsept yaratildi"}

@router.put("/{recipe_id}")
async def update_recipe(
    recipe_id: int,
    name: Optional[str] = None,
    description: Optional[str] = None,
    preparation_time: Optional[int] = None,
    items: Optional[List[dict]] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu"))
):
    """Retseptni yangilash"""
    # BOSQICH 1.5: tenant bo'yicha cheklash
    recipe = apply_tenant_filter(db.query(Recipe), Recipe, current_user).filter(Recipe.id == recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Retsept topilmadi")

    if name:
        recipe.name = name
    if description:
        recipe.description = description
    if preparation_time:
        recipe.preparation_time = preparation_time

    if items is not None:
        db.query(RecipeItem).filter(RecipeItem.recipe_id == recipe_id).delete()

        for item in items:
            recipe_item = RecipeItem(
                recipe_id=recipe_id,
                ingredient_id=item["ingredient_id"],
                quantity=item["quantity"],
                unit=item.get("unit", "kg"),
                notes=item.get("notes"),
                tenant_id=resolve_tenant_id(db, current_user)
            )
            db.add(recipe_item)

    # BOSQICH 15: tan narxni qayta hisoblash
    from services.cost_service import sync_product_cost_from_recipe
    db.flush()
    sync_product_cost_from_recipe(db, recipe.product_id)

    db.commit()

    return MessageResponse(message="Retsept yangilandi")

@router.delete("/{recipe_id}")
async def delete_recipe(
    recipe_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu"))
):
    """Retseptni o'chirish"""
    # BOSQICH 1.5: tenant bo'yicha cheklash
    recipe = apply_tenant_filter(db.query(Recipe), Recipe, current_user).filter(Recipe.id == recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Retsept topilmadi")

    db.delete(recipe)
    db.commit()

    return MessageResponse(message="Retsept o'chirildi")

@router.get("/{recipe_id}/ingredients")
async def get_recipe_ingredients(
    recipe_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Retsept ingredientlarini olish"""
    # BOSQICH 1.5: avval retsept tenant'ga tegishliligini tekshirish
    recipe = apply_tenant_filter(db.query(Recipe), Recipe, current_user).filter(Recipe.id == recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Retsept topilmadi")

    items = db.query(RecipeItem).filter(RecipeItem.recipe_id == recipe_id).all()

    return [
        {
            "id": i.id,
            "ingredient_id": i.ingredient_id,
            "ingredient_name": i.ingredient.name if i.ingredient else None,
            "quantity": i.quantity,
            "unit": i.unit,
            "notes": i.notes
        }
        for i in items
    ]

