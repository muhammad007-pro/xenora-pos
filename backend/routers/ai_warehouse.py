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
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from deps import apply_tenant_filter, get_current_active_user, resolve_tenant_id
from models import Product, User
from services import ai_warehouse as ai

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
