"""
Tan narx hisoblash servisi (BOSQICH 15: sof foyda)

Mahsulot tan narxi ikki xil aniqlanadi:
  1) Retseptli taom — ingredientlar tan narxidan AVTOMATIK yig'iladi
     (ingredient.cost_price ingredientning sale_unit birligi uchun deb olinadi,
      retsept birligi boshqa bo'lsa unit_converter orqali moslashtiriladi)
  2) Tayyor mahsulot (suv, cola...) — products.cost_price qo'lda kiritilgan qiymat
"""
from sqlalchemy.orm import Session

from models import Product, Recipe, RecipeItem
from services.unit_converter import convert, can_convert


def calculate_recipe_cost(db: Session, recipe: Recipe) -> float:
    """Retsept tannarxi — yield_pct hisobga olinadi (BOSQICH 17)

    Agar ingredient.yield_pct = 80 → 1kg tayyor uchun 1/0.80 = 1.25kg xom kerak.
    yield_pct kiritilmagan bo'lsa — eski mantiq (o'zgarishsiz).
    """
    total = 0.0
    items = db.query(RecipeItem).filter(RecipeItem.recipe_id == recipe.id).all()
    for item in items:
        ingredient = db.query(Product).filter(Product.id == item.ingredient_id).first()
        if not ingredient or not ingredient.cost_price:
            continue

        qty = item.quantity or 0
        # Retsept birligi ingredientning narx birligidan farq qilsa — konvertatsiya
        if item.unit and ingredient.sale_unit and item.unit != ingredient.sale_unit:
            try:
                if can_convert(item.unit, ingredient.sale_unit):
                    qty = convert(qty, item.unit, ingredient.sale_unit)
            except Exception:
                pass

        # BOSQICH 17: yield_pct — xom miqdorga o'tkazish
        # Misol: 700g pishgan go'sht, yield 70% → 700 / 0.70 = 1000g xom ketadi
        if ingredient.yield_pct and 0 < ingredient.yield_pct < 100:
            qty = qty / (ingredient.yield_pct / 100)

        total += ingredient.cost_price * qty
    return round(total, 2)


def get_product_cost(db: Session, product_id: int) -> float:
    """
    Mahsulotning amaldagi tan narxi:
    retsepti bo'lsa — retseptdan, bo'lmasa — products.cost_price.
    """
    recipe = db.query(Recipe).filter(Recipe.product_id == product_id).first()
    if recipe:
        cost = calculate_recipe_cost(db, recipe)
        if cost > 0:
            return cost

    product = db.query(Product).filter(Product.id == product_id).first()
    return product.cost_price or 0.0 if product else 0.0


def sync_product_cost_from_recipe(db: Session, product_id: int) -> float:
    """
    Retseptdan hisoblangan tan narxni products.cost_price ga yozib qo'yadi
    (retsept yaratilganda/yangilanganda chaqiriladi). Hisoblangan qiymatni qaytaradi.
    Chaqiruvchi o'zi db.commit() qilishi kerak.
    """
    recipe = db.query(Recipe).filter(Recipe.product_id == product_id).first()
    if not recipe:
        return 0.0

    cost = calculate_recipe_cost(db, recipe)
    if cost > 0:
        product = db.query(Product).filter(Product.id == product_id).first()
        if product:
            product.cost_price = cost
    return cost
