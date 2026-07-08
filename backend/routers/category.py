from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from database import get_db
from models import Category, User
from schemas import CategoryCreate, CategoryUpdate, CategoryInDB, PaginatedResponse, MessageResponse
from deps import resolve_tenant_id, get_current_user, get_current_active_user, has_permission, apply_tenant_filter

router = APIRouter()

@router.get("/", response_model=PaginatedResponse)
async def get_categories(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=1000),
    parent_id: Optional[int] = None,
    is_active: Optional[bool] = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Barcha kategoriyalarni olish"""
    query = db.query(Category)
    # BOSQICH 1.5: tenant bo'yicha cheklash
    query = apply_tenant_filter(query, Category, current_user)

    if parent_id is not None:
        query = query.filter(Category.parent_id == parent_id)
    else:
        query = query.filter(Category.parent_id.is_(None))
    
    if is_active is not None:
        query = query.filter(Category.is_active == is_active)
    
    total = query.count()
    categories = query.order_by(Category.display_order, Category.name).offset((page - 1) * page_size).limit(page_size).all()
    
    return PaginatedResponse(
        items=[CategoryInDB.model_validate(c) for c in categories],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size
    )

@router.get("/all", response_model=List[CategoryInDB])
async def get_all_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Barcha kategoriyalarni paginatsiyasiz olish"""
    query = db.query(Category).filter(Category.is_active == True)
    # BOSQICH 1.5: tenant bo'yicha cheklash
    query = apply_tenant_filter(query, Category, current_user)
    categories = query.order_by(Category.display_order, Category.name).all()
    return [CategoryInDB.model_validate(c) for c in categories]

@router.post("/", response_model=CategoryInDB)
async def create_category(
    category_data: CategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu"))
):
    """Yangi kategoriya yaratish"""
    existing = db.query(Category).filter(Category.name == category_data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Bu nomdagi kategoriya mavjud")
    
    # BOSQICH 1.5: yangi yozuv yaratuvchi tenant'iga biriktiriladi
    category = Category(**category_data.model_dump(), tenant_id=resolve_tenant_id(db, current_user))
    db.add(category)
    db.commit()
    db.refresh(category)
    
    return CategoryInDB.model_validate(category)

@router.get("/{category_id}", response_model=CategoryInDB)
async def get_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Kategoriya ma'lumotlarini olish"""
    # BOSQICH 1.5: tenant bo'yicha cheklash
    category = apply_tenant_filter(db.query(Category), Category, current_user).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Kategoriya topilmadi")
    
    return CategoryInDB.model_validate(category)

@router.patch("/{category_id}", response_model=CategoryInDB)
async def update_category(
    category_id: int,
    category_data: CategoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu"))
):
    """Kategoriyani yangilash"""
    category = apply_tenant_filter(db.query(Category), Category, current_user).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Kategoriya topilmadi")
    
    update_data = category_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(category, field, value)
    
    db.commit()
    db.refresh(category)
    
    return CategoryInDB.model_validate(category)

@router.delete("/{category_id}", response_model=MessageResponse)
async def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu"))
):
    """Kategoriyani o'chirish"""
    category = apply_tenant_filter(db.query(Category), Category, current_user).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Kategoriya topilmadi")
    
    # Mahsulotlar mavjudligini tekshirish
    if category.products:
        raise HTTPException(status_code=400, detail="Bu kategoriyada mahsulotlar mavjud, avval ularni o'chiring")
    
    db.delete(category)
    db.commit()
    
    return MessageResponse(message="Kategoriya o'chirildi")

@router.get("/{category_id}/products")
async def get_category_products(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Kategoriyaga tegishli mahsulotlarni olish"""
    from schemas import ProductInDB

    category = apply_tenant_filter(db.query(Category), Category, current_user).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Kategoriya topilmadi")
    
    products = category.products
    return [ProductInDB.model_validate(p) for p in products if p.is_active]
