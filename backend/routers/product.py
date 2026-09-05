from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import or_
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel, Field
import logging
import os
import uuid

from database import get_db
from models import (
    Product, Category, User, Inventory, ProductBarcode,
    CatalogCandidate, OffProduct,
)
from schemas import ProductCreate, ProductUpdate, ProductInDB, PaginatedResponse, MessageResponse
from deps import resolve_tenant_id, get_current_user, get_current_active_user, has_permission, apply_tenant_filter
from config import settings
from routers.price_history import record_price_change
from core.audit import log_audit  # xodim harakatlarini yozish (audit)
from core.barcode import gen_internal_barcode  # ichki EAN-13 (AI-Ombor bilan AYNI generator)
from core.catalog import record_candidate, is_shareable_barcode  # umumiy katalog
from core.rate_limit import WindowLimiter

logger = logging.getLogger(__name__)

router = APIRouter()

# Shtrix-kod lookup cheklovi — TENANT boshiga soatiga (IP emas: bir do'konning
# kassirlari bitta NAT ortida bo'lishi mumkin). Modul darajasida — jarayon
# umri davomida bitta hisoblagich.
_lookup_limiter = WindowLimiter(settings.RATE_LIMIT_LOOKUP_PER_HOUR, 3600.0)


class BulkCategoryRequest(BaseModel):
    """Ommaviy kategoriya berish — bir nechta mahsulotga bir kategoriya."""
    product_ids: List[int] = Field(..., min_length=1)
    category_id: int


class BarcodeLookupResponse(BaseModel):
    """`GET /products/lookup/{barcode}` javobi — TAKLIF, majburiyat emas.

    ⚠️ Bu sxemaga `tenant_id`, narx yoki ombor qoldig'i HECH QACHON
    qo'shilmasin. Nomzodlar jadvalida narx ustuni ataylab yo'q; bu yerda ham
    shunday bo'lib qolsin (qarang: `core/catalog.py` boshidagi uchta qoida).
    """
    barcode: str
    found: bool
    # "own" | "catalog" | "off" | None
    source: Optional[str] = None
    name: Optional[str] = None
    brand: Optional[str] = None        # faqat `off`
    quantity: Optional[str] = None     # faqat `off` ("450 г", "1.5 L")
    category: Optional[str] = None     # kategoriya NOMI (id emas — UI o'zi moslaydi)
    unit: Optional[str] = None         # faqat `catalog`
    votes: Optional[int] = None        # faqat `catalog` — nechta do'kon shu nomni yozgan
    product_id: Optional[int] = None   # faqat `own`
    message: Optional[str] = None      # faqat `own` — ogohlantirish matni

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

    # UMUMIY KATALOG: nomzod yoziladi (do'kon ruxsat bergan bo'lsa). Eng oxirida —
    # barcha commit'lardan KEYIN, ya'ni mahsulot allaqachon saqlangan.
    #
    # ⚠️ IKKI QATLAM HIMOYA, ataylab: `record_candidate` o'z ichida ham
    # try/except bilan o'ralgan, lekin bu yerdagisi ARGUMENTLARNI ham qamrab
    # oladi. Masalan `product.category.name` — lazy-load, ya'ni funksiyaga
    # KIRISHDAN oldin xato berishi mumkin. Golden test aynan shuni ushladi.
    # Katalog qatlami nima bo'lsa ham mahsulot yaratish to'xtamaydi.
    try:
        record_candidate(db, tid, product.barcode, product.name,
                         category_hint=category.name, unit=product.sale_unit)
    except Exception as _e:      # noqa: BLE001
        logger.warning("katalog nomzodi yozilmadi (mahsulot yaratildi): %s", _e)

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


# ════════════════════════════════════════════════════════════════════════════
# ICHKI SHTRIX-KOD BERISH — zavod kodi yo'q mahsulotlar uchun (parfumeriya)
#   Kod: EAN-13, "20" prefiks (GS1 "do'kon ichki") + nazorat raqami.
#   Generator: core/barcode.py — AI-Ombor oqimi bilan AYNI (ikki xil sxema
#   paydo bo'lmasin). Kod `products.barcode` ga yoziladi, ya'ni
#   /barcodes/lookup/{barcode} uni darrov topadi (sotuvda ishlaydi).
# ════════════════════════════════════════════════════════════════════════════
class GenerateBarcodesRequest(BaseModel):
    """To'plam: aniq id'lar YOKI barcode'i yo'q hammasi."""
    product_ids: Optional[List[int]] = None
    all_without_barcode: bool = False


class GeneratedBarcodeItem(BaseModel):
    product_id: int
    name: str
    barcode: str


class SkippedBarcodeItem(BaseModel):
    product_id: int
    name: str
    reason: str


class GenerateBarcodesResponse(BaseModel):
    generated: List[GeneratedBarcodeItem]
    generated_count: int
    skipped: List[SkippedBarcodeItem]
    skipped_count: int
    message: str


def _has_barcode(p: Product) -> bool:
    return bool(p.barcode and str(p.barcode).strip())


# DIQQAT: literal path `/{product_id}` dan OLDIN (bulk-category bilan bir xil sabab).
@router.post("/generate-barcodes", response_model=GenerateBarcodesResponse)
async def generate_barcodes_bulk(
    payload: GenerateBarcodesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu")),
):
    """Bir nechta mahsulotga birdan ichki EAN-13 beradi.

    `all_without_barcode=true` — shu tenantdagi kodi YO'Q hamma mahsulot.
    Allaqachon kodi bori o'tkazib yuboriladi (qayta yozilmaydi) va javobda
    `skipped` ro'yxatida ko'rsatiladi.

    TRANZAKSIYA: hammasi yoki hech nima — bitta commit, xatoda rollback.
    """
    tid = resolve_tenant_id(db, current_user)
    if not tid:
        raise HTTPException(status_code=400, detail="Tenant (kafe) aniqlanmadi")

    if not payload.all_without_barcode and not payload.product_ids:
        raise HTTPException(status_code=400,
                            detail="product_ids ro'yxati yoki all_without_barcode=true kerak")

    q = apply_tenant_filter(db.query(Product), Product, current_user)
    if payload.all_without_barcode:
        q = q.filter(or_(Product.barcode.is_(None), Product.barcode == ""))
    else:
        q = q.filter(Product.id.in_(payload.product_ids))
    products = q.order_by(Product.id).all()

    if not products:
        return GenerateBarcodesResponse(
            generated=[], generated_count=0, skipped=[], skipped_count=0,
            message="Mos mahsulot topilmadi",
        )

    generated: List[GeneratedBarcodeItem] = []
    skipped: List[SkippedBarcodeItem] = []
    used: set = set()   # shu partiya ichida takrorlanmasin

    try:
        for p in products:
            if _has_barcode(p):
                skipped.append(SkippedBarcodeItem(
                    product_id=p.id, name=p.name, reason="Shtrix-kod allaqachon bor"))
                continue
            code = gen_internal_barcode(db, tid, used, check_alt_barcodes=True)
            p.barcode = code
            generated.append(GeneratedBarcodeItem(product_id=p.id, name=p.name, barcode=code))
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Shtrix-kod berishda xato — hech narsa saqlanmadi")

    if generated:
        log_audit(current_user, "products", "GENERATE_BARCODE", None, detail={
            "count": len(generated),
            "skipped": len(skipped),
            "product_ids": [g.product_id for g in generated],
        })

    return GenerateBarcodesResponse(
        generated=generated, generated_count=len(generated),
        skipped=skipped, skipped_count=len(skipped),
        message=f"{len(generated)} ta mahsulotga shtrix-kod berildi"
              + (f", {len(skipped)} ta o'tkazib yuborildi" if skipped else ""),
    )


@router.post("/{product_id}/generate-barcode", response_model=ProductInDB)
async def generate_barcode_single(
    product_id: int,
    force: bool = Query(False, description="Mavjud kodni ALMASHTIRISH (ehtiyot bo'ling)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu")),
):
    """Bitta mahsulotga ichki EAN-13 beradi.

    Kodi allaqachon bo'lsa 400 — tasodifan qayta yozilmasin. Ataylab
    almashtirish uchun `?force=true` (eski kod audit logga yoziladi;
    eski yorliqlar ishlamay qoladi).
    """
    tid = resolve_tenant_id(db, current_user)
    if not tid:
        raise HTTPException(status_code=400, detail="Tenant (kafe) aniqlanmadi")

    product = apply_tenant_filter(db.query(Product), Product, current_user) \
        .filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")

    old = product.barcode
    if _has_barcode(product) and not force:
        raise HTTPException(
            status_code=400,
            detail=f"Mahsulotda shtrix-kod allaqachon bor ({old}). Almashtirish uchun force=true.",
        )

    code = gen_internal_barcode(db, tid, set(), check_alt_barcodes=True)
    product.barcode = code
    db.commit()
    db.refresh(product)

    log_audit(current_user, "products", "GENERATE_BARCODE", product.id, detail={
        "barcode": code, "old_barcode": old, "forced": bool(force),
    })
    return ProductInDB.model_validate(product)


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

    # UMUMIY KATALOG: nom yoki barkod tahrirlangan bo'lishi mumkin — nomzod
    # yangilanadi (yangi qator emas: UNIQUE(tenant_id, barcode)).
    # try/except sababi yuqorida (create_product) izohlangan.
    try:
        record_candidate(db, product.tenant_id, product.barcode, product.name,
                         category_hint=(product.category.name if product.category else None),
                         unit=product.sale_unit)
    except Exception as _e:      # noqa: BLE001
        logger.warning("katalog nomzodi yangilanmadi (mahsulot saqlandi): %s", _e)

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

@router.get("/lookup/{barcode}", response_model=BarcodeLookupResponse)
async def lookup_barcode(
    barcode: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu")),
):
    """Shtrix-kod bo'yicha mahsulot ma'lumotini TAKLIF qiladi (uch qatlam).

    Mahsulot qo'shish oynasi shu endpointni chaqiradi va nom/kategoriya
    maydonlarini oldindan to'ldiradi. Javob — TAKLIF, majburiyat emas:
    foydalanuvchi hammasini o'zgartira oladi.

    QATLAMLAR (birinchi topilgan g'olib):
      1. `own`     — do'konning O'Z bazasida shu kod bor. Bu holda taklif emas,
                     OGOHLANTIRISH: mahsulot ikki marta kiritilishining oldini
                     oladi. `product_id` qaytadi (UI mavjud kartaga o'tkazadi).
      2. `catalog` — `catalog_candidates`: boshqa do'konlar kiritgan nomlar.
                     Eng ko'p ovoz olgan yozuv tanlanadi (bir xil nom necha
                     do'konda uchraganiga qarab).
      3. `off`     — `off_products`: Open Food Facts kesimi (tashqi baza).

    ⚠️ TENANT IZOLYATSIYASI — uchta qat'iy qoida:
      • `tenant_id` HECH QACHON javobga chiqmaydi. 2-qatlamdan faqat nom va
        kategoriya olinadi; "qaysi do'kon shuni sotadi" ma'lumoti berilmaydi.
      • 2-qatlamda so'rovchining O'Z yozuvlari chiqarib tashlanadi — aks holda
        do'kon o'z nomini "boshqa manba" sifatida qaytarib olardi.
      • FAQAT ANIQ shtrix-kod bo'yicha. Nom bo'yicha qidiruv YO'Q va
        qo'shilmasin: u butun katalogni varaqlash imkonini berardi.

    ⚠️ NARX HECH QACHON QAYTMAYDI. `catalog_candidates` da narx ustuni umuman
    yo'q (sxema darajasidagi kafolat), `off_products` da ham. Bu funksiya
    nom taklif qiladi, raqobatchining narxini emas.

    Tezlik chegarasi: tenant boshiga soatiga `RATE_LIMIT_LOOKUP_PER_HOUR`
    (standart 500). Oshsa 429 — lekin UI buni jimgina yutadi, kassir ishi
    to'xtamaydi.
    """
    code = (barcode or "").strip()
    if not code or len(code) > 32:
        return BarcodeLookupResponse(barcode=code, found=False)

    # Cheklov kaliti: tenant. Platforma egasida tenant yo'q — foydalanuvchi bo'yicha.
    tenant_id = resolve_tenant_id(db, current_user)
    limit_key = f"t{tenant_id}" if tenant_id else f"u{current_user.id}"
    if not _lookup_limiter.allow(limit_key):
        logger.warning("LOOKUP RATE LIMIT: %s", limit_key)
        raise HTTPException(
            status_code=429,
            detail="Juda ko'p so'rov. Biroz kuting.",
            headers={"Retry-After": "60"},
        )

    # ── 1-qatlam: O'Z bazasi ────────────────────────────────────────────────
    own = (
        apply_tenant_filter(db.query(Product), Product, current_user)
        .filter(Product.barcode == code)
        .first()
    )
    if own is None:
        # Qo'shimcha shtrix-kodlar (bir mahsulotga bir nechta kod) ham hisobga
        # olinadi — aks holda "yo'q" deb aytib, dublikat yaratishga yo'l qo'yardik.
        extra = (
            apply_tenant_filter(db.query(ProductBarcode), ProductBarcode, current_user)
            .filter(ProductBarcode.barcode == code)
            .first()
        )
        if extra is not None:
            own = (
                apply_tenant_filter(db.query(Product), Product, current_user)
                .filter(Product.id == extra.product_id)
                .first()
            )

    if own is not None:
        kat = db.query(Category.name).filter(Category.id == own.category_id).scalar()
        return BarcodeLookupResponse(
            barcode=code,
            found=True,
            source="own",
            name=own.name,
            category=kat,
            product_id=own.id,
            message="Bu mahsulot bazangizda bor",
        )

    # Qolgan ikki qatlam faqat haqiqiy zavod kodlari uchun — ichki do'kon
    # kodlari (prefiks 2) va nostandart uzunliklar umumiy katalogga tushmaydi,
    # ya'ni ularni so'rash befoyda (bir xil filtr: core/catalog.py).
    if not is_shareable_barcode(code):
        return BarcodeLookupResponse(barcode=code, found=False)

    # ── 2-qatlam: umumiy katalog nomzodlari (boshqa do'konlar) ──────────────
    q = db.query(CatalogCandidate).filter(CatalogCandidate.barcode == code)
    if tenant_id is not None:
        q = q.filter(CatalogCandidate.tenant_id != tenant_id)   # o'z ovozi qaytmasin
    nomzodlar = q.all()
    if nomzodlar:
        # Ovoz sanash: bir xil normalizatsiyalangan nom necha do'konda uchradi.
        # Eng ko'p ovoz olgan guruh yutadi; teng bo'lsa — kattaroq id, ya'ni
        # keyinroq yozilgani (yangiroq nom ehtimol to'g'riroq yozilgan).
        guruh: dict = {}
        for n in nomzodlar:
            guruh.setdefault(n.name_normalized, []).append(n)
        eng = max(guruh.values(), key=lambda g: (len(g), max(x.id for x in g)))
        golib = max(eng, key=lambda x: x.id)
        return BarcodeLookupResponse(
            barcode=code,
            found=True,
            source="catalog",
            name=golib.name_original,
            category=golib.category_hint,
            unit=golib.unit,
            votes=len(eng),
        )

    # ── 3-qatlam: Open Food Facts kesimi ────────────────────────────────────
    off = db.query(OffProduct).filter(OffProduct.barcode == code).first()
    if off is not None:
        return BarcodeLookupResponse(
            barcode=code,
            found=True,
            source="off",
            name=off.name,
            brand=off.brand,
            quantity=off.quantity,
            category=off.category,
        )

    return BarcodeLookupResponse(barcode=code, found=False)


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
