"""
AI-Ombor router — rasmdan mahsulot o'qish (BOSQICH 1: backend asos).

Endpoint:
  GET  /api/v1/ai-warehouse/status  — funksiya yoqilgan/sozlanganmi (frontend uchun)
  POST /api/v1/ai-warehouse/scan    — rasm yuboriladi → mahsulot ro'yxati qaytadi

Bu bosqichda FAQAT O'QISH: rasmni AI o'qiydi, ombordagi mavjud mahsulot bilan
dublikat mosligini ko'rsatadi. OMBORGA QO'SHISH / kirim yozish — keyingi bosqichda.

XAVFSIZLIK / IZOLYATSIYA:
  - Autentifikatsiya majburiy (get_current_active_user).
  - Dublikat tekshiruvi FAQAT foydalanuvchi o'z tenant'i (kafe) mahsulotlari
    bilan (apply_tenant_filter) — boshqa do'kon omboriga tegmaydi.
  - API kalit serverda; rasm diskka saqlanmaydi.
  - Kalit yo'q / xato bo'lsa — tushunarli HTTP xato (server crash emas).
"""
import random
import re
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import settings
from core.audit import log_audit
from database import get_db
from deps import (
    apply_tenant_filter, get_current_active_user, has_permission, resolve_tenant_id,
)
from models import Category, Inventory, Product, StockMovement, User
from services import ai_warehouse as ai
from utils.helpers import calculate_ean13_checksum

router = APIRouter()


# ── Javob sxemalari ─────────────────────────────────────────────────────────
class ScannedProduct(BaseModel):
    name: str
    quantity: float
    unit_price: float
    confidence: int
    matched_product_id: Optional[int] = None   # ombordagi o'xshash mahsulot (bor bo'lsa)
    matched_name: Optional[str] = None
    match_score: Optional[int] = None


class ScanResponse(BaseModel):
    products: List[ScannedProduct]
    error: Optional[str] = None
    reason: Optional[str] = None
    usage: Optional[dict] = None


class AiStatus(BaseModel):
    enabled: bool
    configured: bool
    model: str


# ── Nom normalizatsiya + dublikat moslik ────────────────────────────────────
def _normalize(name: str) -> str:
    """Taqqoslash uchun: kichik harf, tinish belgisi → bo'shliq, bo'shliqlar bir."""
    s = (name or "").lower()
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)   # \w kirill/lotinni ham qamraydi
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _similarity(a: str, b: str) -> int:
    """0..100 o'xshashlik: aniq moslik / ichki moslik / token ustma-ustligi."""
    if not a or not b:
        return 0
    if a == b:
        return 100
    if a in b or b in a:
        return 88
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0
    inter = len(ta & tb)
    union = len(ta | tb)
    return int(round(100 * inter / union)) if union else 0


# Bundan past ballli moslikni "mos" deb ko'rsatmaymiz (noto'g'ri taklif bermaslik).
_MATCH_THRESHOLD = 60


def _match_existing(db: Session, current_user: User, products: List[dict]) -> None:
    """Har scanланган mahsulotга ombordagi eng o'xshash mahsulotni biriktiradi
    (FAQAT o'z tenant'i — tenant izolyatsiya). products ro'yxatini joyida yangilaydi."""
    if not products:
        return
    q = db.query(Product.id, Product.name)
    q = apply_tenant_filter(q, Product, current_user)   # boshqa do'kon mahsuloti ko'rinmaydi
    existing = [(pid, pname, _normalize(pname)) for pid, pname in q.all()]
    if not existing:
        return
    for item in products:
        norm = _normalize(item["name"])
        best_id, best_name, best_score = None, None, 0
        for pid, pname, pnorm in existing:
            score = _similarity(norm, pnorm)
            if score > best_score:
                best_id, best_name, best_score = pid, pname, score
        if best_score >= _MATCH_THRESHOLD:
            item["matched_product_id"] = best_id
            item["matched_name"] = best_name
            item["match_score"] = best_score


# ── Endpointlar ─────────────────────────────────────────────────────────────
@router.get("/status", response_model=AiStatus)
async def ai_status(current_user: User = Depends(get_current_active_user)):
    """Funksiya yoqilgan va sozlanganmi (frontend tugmani ko'rsatish/yashirish uchun)."""
    return AiStatus(
        enabled=bool(settings.AI_WAREHOUSE_ENABLED),
        configured=ai.is_configured(),
        model=settings.AI_WAREHOUSE_MODEL,
    )


@router.post("/scan", response_model=ScanResponse)
async def scan(
    file: UploadFile = File(..., description="Qog'oz mahsulot ro'yxati rasmi"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Rasmdan mahsulot ro'yxatini o'qiydi va ombordagi mavjud mahsulot bilan
    dublikat mosligini qaytaradi. Omborga hech narsa YOZMAYDI (bu bosqichda).
    """
    # 1) Rasmni tekshir (turi + hajmi) — server himoyasi
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            detail="Faqat rasm fayli yuboring (image/*).")
    raw = await file.read()
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Bo'sh fayl.")
    if len(raw) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=f"Rasm juda katta (max {settings.MAX_UPLOAD_SIZE // (1024*1024)} MB).")

    tenant_id = resolve_tenant_id(db, current_user)

    # 2) AI orqali o'qish (xato → tushunarli HTTP, crash emas)
    try:
        result = ai.scan_image(raw, tenant_id=tenant_id)
    except ai.AiWarehouseError as e:
        raise HTTPException(status_code=e.http_status,
                            detail={"code": e.code, "message": e.message})

    # 3) Ombordagi mavjud mahsulot bilan dublikat moslik (o'z tenant'i)
    _match_existing(db, current_user, result["products"])

    return ScanResponse(**result)


# ════════════════════════════════════════════════════════════════════════════
# BOSQICH 3: TASDIQLASH — o'qilgan mahsulotlarni HAQIQATAN omborga qo'shish
#   · YANGI mahsulot → products jadvaliga (shtrix-kod avto yaratiladi + saqlanadi)
#   · MAVJUD mahsulot (matched) → dublikat yaratmaydi, faqat qoldiq (+narx) yangilanadi
#   · har biriga ombor kirimi (StockMovement type='in', manba='ai_warehouse')
#   TRANZAKSIYA: hammasi yoki hech nima (bitta commit; xatoda rollback).
#   RUXSAT: manage_inventory (kassir/ofitsiantda yo'q → 403).
# ════════════════════════════════════════════════════════════════════════════
class ConfirmItem(BaseModel):
    name: str
    quantity: float
    unit_price: float                        # kelish narxi (dona, tan narx)
    sell_price: Optional[float] = None        # sotish narxi (yangi mahsulot uchun)
    matched_product_id: Optional[int] = None  # berilsa — mavjud mahsulotga kirim (yangi yaratmaydi)
    barcode: Optional[str] = None             # yangi mahsulot: admin kiritsa; bo'sh → avto yaratiladi
    unit: Optional[str] = "dona"


class ConfirmRequest(BaseModel):
    items: List[ConfirmItem]
    category_id: Optional[int] = None         # yangi mahsulotlar kategoriyasi (ixtiyoriy)
    markup_pct: Optional[float] = None        # sell_price berilmagan yangi mahsulotga ustama %
    update_existing_price: bool = False       # mavjud (matched) mahsulot narxini yangilaydimi


class ConfirmedProduct(BaseModel):
    product_id: int
    name: str
    barcode: Optional[str] = None
    quantity: float
    unit_price: float
    sell_price: float
    is_new: bool


class ConfirmResponse(BaseModel):
    added: int
    new_count: int
    existing_count: int
    total_qty: float
    total_cost: float
    products: List[ConfirmedProduct]
    message: str


# HAQIQIY EAN-13 ichki (do'kon) kod: "20" prefiks + 10 tasodifiy raqam + nazorat
# raqami = 13 belgi. Prefiks 20-29 GS1 da "do'kon ichki (restricted circulation)"
# uchun ajratilgan — ichki kod uchun to'g'ri tanlov.
#
# TUZATISH: avval "20" + 11 tasodifiy raqam yozilardi, ya'ni 13-chi belgi
# NAZORAT RAQAMI emas, oddiy tasodifiy raqam edi. Bunday kod EAN-13 sifatida
# yaroqsiz: kamera skaner (ML Kit / BarcodeDetector / ZXing) va lazer skaner
# nazorat raqamini tekshiradi va noto'g'ri bo'lsa kodni QAYTARMAYDI.
# DIQQAT: mavjud (allaqachon yaratilgan) barkodlarga TEGILMAYDI — bu faqat
# yangi generatsiya. Eski kodlar `products.barcode` aniq mosligi bilan
# (barcodes.py lookup 2-qadam) va CODE128 yorliq bilan ishlashda davom etadi.
#
# Tenant ichida (va shu partiya ichida) UNIKAL — mahsulot bilan bir vaqtda saqlanadi.
def _gen_internal_barcode(db: Session, tenant_id: Optional[int], used: set) -> str:
    def _ean13(base12: str) -> str:
        """12 raqamli bazaga nazorat raqamini qo'shadi → to'g'ri EAN-13."""
        return base12 + str(calculate_ean13_checksum(base12))

    for _ in range(30):
        code = _ean13("20" + f"{random.randint(0, 10**10 - 1):010d}")
        if code in used:
            continue
        exists = (
            db.query(Product.id)
            .filter(Product.tenant_id == tenant_id, Product.barcode == code)
            .first()
        )
        if not exists:
            used.add(code)
            return code
    # Juda kam ehtimol — vaqt asosida zaxira kod (u ham to'g'ri EAN-13)
    code = _ean13("29" + f"{int(datetime.now().timestamp() * 1000) % 10**10:010d}")
    used.add(code)
    return code


def _get_or_create_inventory(db: Session, product_id: int, tenant_id: Optional[int],
                             branch_id: Optional[int], unit: str) -> Inventory:
    inv = (
        db.query(Inventory)
        .filter(Inventory.tenant_id == tenant_id, Inventory.product_id == product_id)
        .first()
    )
    if inv is None:
        inv = Inventory(
            tenant_id=tenant_id, branch_id=branch_id, product_id=product_id,
            quantity=0.0, unit=unit or "dona", min_threshold=5.0, max_threshold=100.0,
        )
        db.add(inv)
        db.flush()
    return inv


@router.post("/confirm", response_model=ConfirmResponse)
async def confirm(
    body: ConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_inventory")),
):
    """O'qilgan (va tahrirlangan) mahsulotlarni omborga qo'shadi + kirim yozadi.

    Tranzaksiya: bitta commit — biror qatorda xato bo'lsa HECH NARSA saqlanmaydi
    (yarim qo'shilib qolmaydi). Faqat o'z tenant omboriga tegadi.
    """
    if not body.items:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Mahsulot ro'yxati bo'sh.")

    tenant_id = resolve_tenant_id(db, current_user)
    branch_id = getattr(current_user, "_active_branch_id", None)

    # Yangi mahsulot kategoriyasi (berilsa) — o'z tenant'ida bo'lishi shart
    category_id = None
    if body.category_id:
        cat = (
            apply_tenant_filter(db.query(Category), Category, current_user)
            .filter(Category.id == body.category_id).first()
        )
        if not cat:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Kategoriya topilmadi.")
        category_id = cat.id

    markup = None
    if body.markup_pct is not None and body.markup_pct >= 0:
        markup = float(body.markup_pct)

    used_barcodes: set = set()
    confirmed: List[ConfirmedProduct] = []
    new_count = existing_count = 0
    total_qty = total_cost = 0.0

    try:
        for idx, it in enumerate(body.items, start=1):
            name = (it.name or "").strip()
            if not name:
                raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                    detail=f"{idx}-qatorda mahsulot nomi yo'q.")
            if it.quantity is None or it.quantity <= 0:
                raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                    detail=f"'{name}' — miqdor musbat bo'lishi kerak.")
            cost = max(0.0, float(it.unit_price or 0))
            unit = (it.unit or "dona").strip() or "dona"

            # ── MAVJUD mahsulot (dublikat) → yangi yaratmaymiz ──
            if it.matched_product_id:
                product = (
                    apply_tenant_filter(db.query(Product), Product, current_user)
                    .filter(Product.id == it.matched_product_id).first()
                )
                if not product:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                        detail=f"'{name}' — mos mahsulot topilmadi (id={it.matched_product_id}).")
                is_new = False
                sell = float(product.price or 0)
                if body.update_existing_price:
                    product.cost_price = cost
                    if it.sell_price is not None and it.sell_price > 0:
                        sell = float(it.sell_price)
                        product.price = sell
                existing_count += 1

            # ── YANGI mahsulot → products'ga qo'shamiz (shtrix-kod bilan) ──
            else:
                # Sotish narxi: berilgan → o'sha; aks holda ustama %; aks holda tan narx
                if it.sell_price is not None and it.sell_price > 0:
                    sell = float(it.sell_price)
                elif markup is not None:
                    sell = round(cost * (1 + markup / 100.0), 2)
                else:
                    sell = cost
                if sell <= 0:
                    sell = cost if cost > 0 else 1.0  # price NOT NULL — 0 bo'lmasin

                # Shtrix-kod: admin kiritsa tekshiramiz, aks holda avto yaratamiz.
                # YARATISH + SAQLASH bir tranzaksiyada (label chop etilganda skanerlansin).
                barcode = (it.barcode or "").strip() or None
                if barcode:
                    if barcode in used_barcodes:
                        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                            detail=f"'{name}' — shtrix-kod {barcode} takrorlangan.")
                    taken = (
                        db.query(Product.id)
                        .filter(Product.tenant_id == tenant_id, Product.barcode == barcode)
                        .first()
                    )
                    if taken:
                        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                            detail=f"'{name}' — shtrix-kod {barcode} band.")
                    used_barcodes.add(barcode)
                else:
                    barcode = _gen_internal_barcode(db, tenant_id, used_barcodes)

                product = Product(
                    tenant_id=tenant_id,
                    name=name,
                    price=sell,
                    cost_price=cost,
                    barcode=barcode,
                    category_id=category_id,
                    sale_unit=unit,
                    is_active=True,
                    is_available=True,
                )
                db.add(product)
                db.flush()   # product.id + barcode saqlanadi (kirimdan oldin)
                is_new = True
                new_count += 1

            # ── Ombor kirimi: qoldiq oshadi + StockMovement (manba: AI-ombor) ──
            inv = _get_or_create_inventory(db, product.id, tenant_id, branch_id, unit)
            inv.quantity = float(inv.quantity or 0) + float(it.quantity)
            inv.last_restock = datetime.now()
            inv.updated_at = datetime.now()

            mv = StockMovement(
                tenant_id=tenant_id,
                branch_id=inv.branch_id,
                inventory_id=inv.id,
                product_id=product.id,
                movement_type="in",
                quantity=float(it.quantity),
                unit=inv.unit,
                unit_cost=cost,
                total_cost=round(float(it.quantity) * cost, 2),
                reason="ai_scan",
                reference_type="ai_warehouse",
                notes="AI-ombor orqali (rasmdan o'qildi)",
                user_id=current_user.id,
            )
            db.add(mv)

            total_qty += float(it.quantity)
            total_cost += round(float(it.quantity) * cost, 2)
            confirmed.append(ConfirmedProduct(
                product_id=product.id, name=product.name, barcode=product.barcode,
                quantity=float(it.quantity), unit_price=cost, sell_price=float(sell),
                is_new=is_new,
            ))

        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Omborga qo'shishda xato: {e}")

    # Audit: KIM AI-ombor orqali tasdiqladi (asosiy amaldan keyin, buzmaydi)
    log_audit(current_user, "ai_warehouse", "CREATE", None, tenant_id=tenant_id, detail={
        "added": len(confirmed), "new": new_count, "existing": existing_count,
        "total_qty": round(total_qty, 3), "total_cost": round(total_cost, 2),
    })

    return ConfirmResponse(
        added=len(confirmed),
        new_count=new_count,
        existing_count=existing_count,
        total_qty=round(total_qty, 3),
        total_cost=round(total_cost, 2),
        products=confirmed,
        message=f"{len(confirmed)} ta mahsulot omborga qo'shildi "
                f"({new_count} yangi, {existing_count} mavjud yangilandi).",
    )
