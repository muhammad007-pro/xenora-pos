from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel, Field
import os
import uuid

from database import get_db
from models import Product, Category, User, Inventory, ProductBarcode
from schemas import ProductCreate, ProductUpdate, ProductInDB, PaginatedResponse, MessageResponse
from deps import resolve_tenant_id, get_current_user, get_current_active_user, has_permission, apply_tenant_filter
from config import settings
from routers.price_history import record_price_change
from core.audit import log_audit  # xodim harakatlarini yozish (audit)

router = APIRouter()


class BulkCategoryRequest(BaseModel):
    """Ommaviy kategoriya berish — bir nechta mahsulotga bir kategoriya."""
    product_ids: List[int] = Field(..., min_length=1)
    category_id: int

@router.get("/", response_model=PaginatedResponse)
async def get_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    category_id: Optional[int] = None,
    is_active: Optional[bool] = True,
    is_available: Optional[bool] = None,
    has_expiry: Optional[bool] = None,
    expiry_days: Optional[int] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Barcha mahsulotlarni olish"""
    from datetime import date, timedelta as td
    query = db.query(Product)
    # BOSQICH 1.5: tenant bo'yicha cheklash
    query = apply_tenant_filter(query, Product, current_user)

    if category_id:
        query = query.filter(Product.category_id == category_id)

    if is_active is not None:
        query = query.filter(Product.is_active == is_active)

    if is_available is not None:
        query = query.filter(Product.is_available == is_available)

    if has_expiry is True:
        query = query.filter(Product.expiry_date.isnot(None))
    elif has_expiry is False:
        query = query.filter(Product.expiry_date.is_(None))

    if expiry_days is not None:
        cutoff = date.today() + td(days=expiry_days)
        query = query.filter(Product.expiry_date.isnot(None), Product.expiry_date <= cutoff)

    if search:
        query = query.filter(
            Product.name.ilike(f"%{search}%") |
            Product.barcode.ilike(f"%{search}%") |
            Product.sku.ilike(f"%{search}%")
        )
    
    total = query.count()
    products = query.order_by(Product.name).offset((page - 1) * page_size).limit(page_size).all()
    
    return PaginatedResponse(
        items=[ProductInDB.model_validate(p) for p in products],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size
    )

@router.get("/all", response_model=List[ProductInDB])
async def get_all_products(
    category_id: Optional[int] = None,
    limit: int = Query(5000, ge=1, le=10000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Barcha mahsulotlarni paginatsiyasiz olish (POS offline katalog).

    C5: cheksiz emas — xavfsizlik uchun yuqori chegara (max 10000). POS offline
    uchun bir so'rovda butun katalog kerak, lekin patologik katta katalog (buzilgan
    import) server/klientni cho'ktirmasin. Amaliy do'kon katalogi bu chegaradan past.
    """
    query = db.query(Product).filter(Product.is_active == True, Product.is_available == True)
    # BOSQICH 1.5: tenant bo'yicha cheklash
    query = apply_tenant_filter(query, Product, current_user)

    if category_id:
        query = query.filter(Product.category_id == category_id)

    products = query.order_by(Product.name).limit(limit).all()
    return [ProductInDB.model_validate(p) for p in products]

@router.post("/", response_model=ProductInDB)
async def create_product(
    product_data: ProductCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu"))
):
    """Yangi mahsulot yaratish"""
    # Kategoriya tekshirish
    category = db.query(Category).filter(Category.id == product_data.category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Kategoriya topilmadi")
    
    # BOSQICH 1.5/39: tenant aniqlanadi — barcode tekshiruvi shu tenant ICHIDA
    tid = resolve_tenant_id(db, current_user)

    # Barcode tekshirish (faqat shu tenant ichida — boshqa do'kon kodi to'sib qo'ymasin)
    # BUG 8: faqat FAOL mahsulot barkodi band hisoblansin. O'chirilgan (soft-delete)
    # mahsulotning barkodi qayta ishlatilsa bo'ladi (delete_product uni None qiladi).
    if product_data.barcode:
        existing = db.query(Product).filter(
            Product.tenant_id == tid,
            Product.barcode == product_data.barcode,
            Product.is_active == True,
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Bu barcode band")

    # yangi yozuv yaratuvchi tenant'iga biriktiriladi
    product = Product(**product_data.model_dump(), tenant_id=tid)
    db.add(product)
    db.commit()
    db.refresh(product)

    # BUG 9: mahsulot yaratilgach DOIM 0 qoldiqli Inventory qatori yaratiladi —
    # soni kiritilmasa ham mahsulot omborda 0 bilan ko'rinadi (inner join tushirib
    # qoldirmaydi). Kassir keyin kirim qiladi. Birlik mahsulot sotuv birligidan
    # (pcs → dona, inventory.py:182 lazily-create bilan mos).
    _u = product.sale_unit or "dona"
    _u = "dona" if _u == "pcs" else _u
    inventory = Inventory(product_id=product.id, quantity=0, unit=_u, tenant_id=tid)
    db.add(inventory)
    db.commit()

    return ProductInDB.model_validate(product)

# DIQQAT: bu route `/{product_id}` PATCH'idan OLDIN turishi shart — FastAPI aks holda
# "bulk-category" ni product_id deb o'qiydi. Literal path birinchi mos kelishi uchun.
@router.patch("/bulk-category", response_model=MessageResponse)
async def bulk_set_category(
    payload: BulkCategoryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu")),
):
    """Ommaviy kategoriya berish — tanlangan mahsulotlarga bir kategoriya.

    250 mahsulotni tez ajratish uchun: 250 alohida so'rov o'rniga 1 ta.
    FAQAT category_id yangilanadi (boshqa maydonlarga tegilmaydi). Tenant-scoped:
    kategoriya ham, mahsulotlar ham shu tenantniki bo'lishi shart.
    """
    tid = resolve_tenant_id(db, current_user)

    # Kategoriya shu tenantники bo'lishi shart (boshqa do'kon kategoriyasi berilmasin)
    category = apply_tenant_filter(db.query(Category), Category, current_user) \
        .filter(Category.id == payload.category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Kategoriya topilmadi")

    # Faqat shu tenantга tegишли va tanlangan id'lardagi mahsulotlar yangilanadi
    q = apply_tenant_filter(db.query(Product), Product, current_user) \
        .filter(Product.id.in_(payload.product_ids))
    updated = q.update({Product.category_id: payload.category_id}, synchronize_session=False)
    db.commit()

    log_audit(current_user, "products", "BULK_CATEGORY", None, detail={
        "category_id": payload.category_id,
        "category_name": category.name,
        "count": updated,
    })
    return MessageResponse(message=f"{updated} ta mahsulotga '{category.name}' kategoriyasi berildi")

@router.patch("/{product_id}/availability")
async def set_product_availability(
    product_id: int,
    is_available: bool,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu")),
):
    """Stop-list: mahsulotni sotuvdan yoqish/o'chirish"""
    product = apply_tenant_filter(db.query(Product), Product, current_user) \
        .filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")
    product.is_available = is_available
    db.commit()
    return {"id": product_id, "name": product.name, "is_available": is_available}


@router.get("/{product_id}", response_model=ProductInDB)
async def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Mahsulot ma'lumotlarini olish"""
    product = apply_tenant_filter(db.query(Product), Product, current_user).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")
    
    return ProductInDB.model_validate(product)

@router.patch("/{product_id}", response_model=ProductInDB)
async def update_product(
    product_id: int,
    product_data: ProductUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu"))
):
    """Mahsulotni yangilash"""
    product = apply_tenant_filter(db.query(Product), Product, current_user).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")

    _old = {"price": product.price, "cost_price": product.cost_price, "name": product.name}
    update_data = product_data.model_dump(exclude_unset=True)

    new_price = update_data.get("price", product.price)
    new_cost  = update_data.get("cost_price", product.cost_price)
    if new_price != product.price or new_cost != product.cost_price:
        tid = resolve_tenant_id(db, current_user)
        record_price_change(db, tid, product, new_price, new_cost,
                            current_user.id, update_data.get("price_change_reason"))

    for field, value in update_data.items():
        if field != "price_change_reason":
            setattr(product, field, value)

    db.commit()
    db.refresh(product)

    # Audit: mahsulot o'zgartirildi (narx old→new ham yoziladi)
    log_audit(current_user, "products", "UPDATE", product.id, detail={
        "name": product.name,
        "fields": [k for k in update_data.keys() if k != "price_change_reason"],
        "price_old": _old["price"], "price_new": product.price,
        "cost_old": _old["cost_price"], "cost_new": product.cost_price,
    })
    return ProductInDB.model_validate(product)

@router.delete("/{product_id}", response_model=MessageResponse)
async def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu"))
):
    """Mahsulotni o'chirish"""
    product = apply_tenant_filter(db.query(Product), Product, current_user).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")
    
    # Soft delete - faqat nofaol qilish
    product.is_active = False
    product.is_available = False

    # BUG 8: barkod/sku'ni bo'shatish → DB constraint (uq_products_tenant_barcode /
    # uq_products_tenant_sku) ozod bo'ladi, o'sha barkod yangi mahsulotga berilsa
    # bo'ladi (Postgres bir nechta NULL'ga ruxsat beradi). Faqat soft-delete paytida —
    # faol mahsulot barkodi o'zgarmaydi.
    product.barcode = None
    product.sku = None

    # Qo'shimcha barkodlar (PLU/multi-barcode) ham uq_product_barcodes_tenant_barcode
    # bilan band bo'lmasin — mahsulot bilan birga o'chiriladi.
    db.query(ProductBarcode).filter(
        ProductBarcode.product_id == product.id,
        ProductBarcode.tenant_id == product.tenant_id,
    ).delete(synchronize_session=False)

    db.commit()

    # Audit: KIM mahsulotni o'chirdi
    log_audit(current_user, "products", "DELETE", product.id, detail={
        "name": product.name, "price": product.price,
    })
    return MessageResponse(message="Mahsulot o'chirildi")

@router.post("/{product_id}/image")
async def upload_product_image(
    product_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu"))
):
    """Mahsulot rasmini yuklash"""
    product = apply_tenant_filter(db.query(Product), Product, current_user).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")
    
    # Fayl kengaytmasini tekshirish
    allowed_extensions = ['.jpg', '.jpeg', '.png', '.webp']
    file_ext = os.path.splitext(file.filename)[1].lower()
    
    if file_ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail="Faqat rasm fayllari yuklash mumkin")
    
    # Fayl nomini yaratish
    filename = f"product_{product_id}_{uuid.uuid4().hex[:8]}{file_ext}"
    file_path = os.path.join(settings.UPLOAD_DIR, "products", filename)
    
    # Papkani yaratish
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    # Faylni saqlash
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)
    
    # URL ni saqlash
    product.image_url = f"/uploads/products/{filename}"
    db.commit()
    
    return {"message": "Rasm yuklandi", "image_url": product.image_url}

@router.get("/barcode/{barcode}", response_model=ProductInDB)
async def get_product_by_barcode(
    barcode: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Barcode bo'yicha mahsulotni topish"""
    product = apply_tenant_filter(db.query(Product), Product, current_user).filter(Product.barcode == barcode).first()
    if not product:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")

    return ProductInDB.model_validate(product)


@router.get("/{product_id}/analogs", response_model=List[ProductInDB])
async def get_drug_analogs(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """BOSQICH 22: Dori analoglarini topish — bir xil active_ingredient ga ega dorilar"""
    product = (
        apply_tenant_filter(db.query(Product), Product, current_user)
        .filter(Product.id == product_id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")

    if not product.active_ingredient:
        return []

    analogs = (
        apply_tenant_filter(db.query(Product), Product, current_user)
        .filter(
            Product.active_ingredient.ilike(f"%{product.active_ingredient}%"),
            Product.id != product_id,
            Product.is_active == True,
        )
        .all()
    )
    return [ProductInDB.model_validate(p) for p in analogs]
