"""Narx tarixi — mahsulot narxi qachon, kim tomonidan o'zgartirildi"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timedelta

from database import get_db
from models import PriceHistory, Product, User
from deps import resolve_tenant_id, get_current_active_user, has_permission, apply_tenant_filter

router = APIRouter()


def _parse_sana(qiymat: str, maydon: str, kun_oxiri: bool = False) -> datetime:
    """ISO sana/vaqtni o'qiydi. Buzuq qiymatda 500 emas, 400 qaytadi.

    `kun_oxiri` — faqat SANA berilgan bo'lsa (masalan "2026-09-07"), oraliqning
    yuqori chegarasi shu kunning OXIRIGA suriladi. Aks holda `<= 00:00` bo'lib,
    "bugungacha" filtri bugungi yozuvlarni umuman ko'rsatmasdi.
    """
    try:
        dt = datetime.fromisoformat(qiymat)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"{maydon}: sana formati noto'g'ri (kutilgan YYYY-MM-DD)")
    if kun_oxiri and len(qiymat.strip()) <= 10:      # vaqt qismi berilmagan
        dt = dt + timedelta(days=1) - timedelta(microseconds=1)
    return dt


def _filtrla(q, product_id, date_from, date_to, reason):
    """Uchala endpointda AYNI filtr — ikki xil qoida paydo bo'lmasin."""
    if product_id:
        q = q.filter(PriceHistory.product_id == product_id)
    if date_from:
        q = q.filter(PriceHistory.created_at >= _parse_sana(date_from, "date_from"))
    if date_to:
        q = q.filter(PriceHistory.created_at <= _parse_sana(date_to, "date_to", True))
    if reason:
        q = q.filter(PriceHistory.reason == reason)
    return q


@router.get("/product/{product_id}")
async def get_product_price_history(
    product_id: int,
    limit: int = Query(50, ge=1, le=200),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    reason: Optional[str] = Query(None, description="manual|stock_in|receipt|ai_warehouse|recipe"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Bitta mahsulotning narx/tan narx o'zgarish tarixi (eng yangisi tepada).

    ⚠️ TENANT: `tenant_id` bo'yicha filtr MAJBURIY — boshqa do'konning narx
    tarixi hech qachon qaytmaydi.
    """
    tid = resolve_tenant_id(db, current_user)
    q = db.query(PriceHistory).filter(
        PriceHistory.product_id == product_id,
        PriceHistory.tenant_id == tid,
    )
    q = _filtrla(q, None, date_from, date_to, reason)
    # id — teng vaqtli yozuvlar uchun ajratuvchi: created_at soniya aniqligida
    # bo'lgani uchun bir tranzaksiyadagi ikki yozuv bir xil vaqt oladi va
    # tartib tasodifiy bo'lib qolardi. Kattaroq id = keyinroq yozilgan.
    rows = q.order_by(PriceHistory.created_at.desc(), PriceHistory.id.desc()).limit(limit).all()

    return [_hist_dict(r) for r in rows]


@router.get("/")
async def get_price_history(
    product_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    reason: Optional[str] = Query(None, description="manual|stock_in|receipt|ai_warehouse|recipe"),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports")),
):
    """Narx o'zgarishlar logi (admin uchun), eng yangisi tepada.

    ⚠️ TENANT: `tenant_id` bo'yicha filtr MAJBURIY.
    """
    tid = resolve_tenant_id(db, current_user)
    q = db.query(PriceHistory).filter(PriceHistory.tenant_id == tid)
    q = _filtrla(q, product_id, date_from, date_to, reason)
    total = q.count()
    rows = (q.order_by(PriceHistory.created_at.desc(), PriceHistory.id.desc())
            .offset((page - 1) * page_size).limit(page_size).all())
    return {"items": [_hist_dict(r) for r in rows], "total": total}


# `reason` uchun standart qiymatlar — tarixda "narx nega o'zgardi" degan savolga
# javob shu ustundan o'qiladi. Qo'lda tahrirlashda foydalanuvchi o'z matnini
# yozishi mumkin, qolgan to'rttasi AVTOMATIK oqimlar.
REASON_MANUAL = "manual"            # qo'lda tahrirlash (PATCH /products/{id})
REASON_STOCK_IN = "stock_in"        # ombor kirimi
REASON_RECEIPT = "receipt"          # priyomka tasdiqlash
REASON_AI_WAREHOUSE = "ai_warehouse"  # AI-ombor (rasmdan o'qish)
REASON_RECIPE = "recipe"            # retseptdan avtomatik hisob

# Ekranda ko'rsatiladigan matn. Do'konchi "stock_in" ni emas, "Ombor kirimi" ni
# ko'rishi kerak. Ro'yxatda yo'q qiymat (foydalanuvchi o'zi yozgan sabab)
# o'zgarishsiz qaytadi.
REASON_LABELS = {
    REASON_MANUAL: "Qo'lda tahrirlash",
    REASON_STOCK_IN: "Ombor kirimi",
    REASON_RECEIPT: "Priyomka",
    REASON_AI_WAREHOUSE: "AI-ombor",
    REASON_RECIPE: "Retsept",
}


def record_price_change(
    db: Session,
    tenant_id: Optional[int],
    product: Product,
    new_price: Optional[float],
    new_cost: Optional[float],
    changed_by: Optional[int],
    reason: str,
):
    """Sotuv narxi YOKI tan narx o'zgarganda tarixga yozadi.

    ⚠️ 2026-09-07 TUZATISH — ikkita nuqson birga tuzatildi:

      1) Bu funksiyani FAQAT `routers/product.py` (qo'lda tahrirlash) chaqirardi.
         Tan narxni avtomatik o'zgartiradigan to'rt yo'l — ombor kirimi,
         priyomka, AI-ombor, retseptdan hisob — umuman chaqirmasdi. Prod
         o'lchovi: tan narxi kirim orqali o'zgargan 60 ta mahsulotdan atigi
         4 tasining tarixda izi bor edi. Endi beshalasi ham shu yerdan o'tadi.

      2) Shart `new_price` ni ham talab qilardi, ya'ni "faqat tan narx
         o'zgardi" holati yozilmay qolardi. Endi IKKALASI teng bo'lsagina
         chiqib ketiladi.

    `new_price=None` — "sotuv narxi o'zgarmaydi" degani. Ustun NOT NULL
    bo'lgani uchun old_price va new_price ikkalasiga ham JORIY narx yoziladi
    (None emas — aks holda INSERT yiqilardi).

    ⚠️ COMMIT QILMAYDI — faqat `db.add()`. Chaqiruvchi o'z tranzaksiyasida
    commit qiladi, shunda kirim va uning tarixi BIRGA saqlanadi yoki BIRGA
    bekor bo'ladi (yarim holat bo'lmaydi).

    `changed_by` — o'zgarishni boshlagan foydalanuvchi; noma'lum bo'lsa None
    (ustun nullable).
    """
    joriy_narx = product.price
    joriy_tan = product.cost_price

    # Sotuv narxi uzatilmagan bo'lsa — o'zgarmaydi.
    if new_price is None:
        new_price = joriy_narx
    # Tan narx uzatilmagan bo'lsa — o'zgarmaydi.
    if new_cost is None:
        new_cost = joriy_tan

    # IKKALASI ham teng bo'lsagina chiqib ketamiz. Ya'ni faqat tan narx
    # o'zgargan holat ham yoziladi (eski shart aynan shuni bloklardi).
    if joriy_narx == new_price and joriy_tan == new_cost:
        return

    ph = PriceHistory(
        tenant_id=tenant_id,
        product_id=product.id,
        old_price=joriy_narx,
        new_price=new_price,
        old_cost=joriy_tan,
        new_cost=new_cost,
        reason=reason,
        changed_by=changed_by,
    )
    db.add(ph)


def _hist_dict(r: PriceHistory) -> dict:
    return {
        "id": r.id,
        "product_id": r.product_id,
        "product_name": r.product.name if r.product else None,
        "old_price": r.old_price,
        "new_price": r.new_price,
        "old_cost": r.old_cost,
        "new_cost": r.new_cost,
        "change_pct": round((r.new_price - r.old_price) / r.old_price * 100, 1) if r.old_price else 0,
        "cost_change_pct": (round((r.new_cost - r.old_cost) / r.old_cost * 100, 1)
                            if r.old_cost else 0),
        "reason": r.reason,
        # Xom qiymat ("stock_in") API iste'molchilariga kerak, inson o'qiydigani
        # esa ekran uchun. Ro'yxatda yo'q sabab (foydalanuvchi matni) o'zicha qaytadi.
        "reason_label": REASON_LABELS.get(r.reason, r.reason),
        "changed_by": r.changer.full_name if r.changer else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }
