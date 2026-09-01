"""OMBOR QO'RIQCHISI — qoldiq yetmasa sotuvni bloklaydi. YAGONA MANBA.

═══ MUAMMO ═══
POS sotuv yo'lida ombor UMUMAN tekshirilmasdi:
  • `order_service.create_order` faqat `product.is_available` (qo'lda bayroq)
  • ombordan ayirish TO'LOV paytida bo'ladi va yetmasa 0 da TO'XTAYDI
    (`recipe_inventory_service._deduct_product_directly:194`) — sotuv o'tadi
  • qaytgan `warnings` chaqiruvchi tomonidan TASHLAB YUBORILADI
    (`routers/payment.py`), `kitchen.py` esa `try/except: pass`
Natijada kamomad JIMGINA yo'qolardi: manfiy qoldiq ham qolmasdi, ya'ni
ekranda hech qanday signal yo'q edi. Fazza Parfum'da 15–31 avgustda
24 ta shunday sotuv topildi (297 dona).

Ziddiyat: xuddi shu ombordan QO'LDA chiqim/hisobdan o'chirish BLOKLANADI
(`routers/inventory.py`), sotish esa yo'q. Bu dizayn emas, e'tibordan
chetda qolgan bo'shliq edi.

═══ QAYERDA TEKSHIRILADI ═══
`order_service.create_order` — BUYURTMA YARATILAYOTGANDA, to'lov paytida
EMAS. To'lovda bloklash kech: mijoz allaqachon xizmat olgan, kassir chekni
yopolmay qoladi.

═══ ISTISNOLAR (ataylab BLOKLANMAYDI) ═══
1. `Cafe.block_oversell = False` -> qo'riqchi butunlay o'chiq.
   Mavjud do'konlar aynan shu holatda (migratsiya c8b3e5d90a17).
2. RETSEPTLI mahsulot -> tegilmaydi. Restoran taomi ingredient yetmasa ham
   tayyorlanishi mumkin (oshpaz o'rniga boshqa narsa qo'yadi). `kitchen.py`
   ham ataylab bloklamaydi — o'sha qarorga ziddiyat qilmaymiz.
3. `Inventory` yozuvi YO'Q mahsulot -> ombor nazorati o'chirilgan tovar yoki
   XIZMAT. Bloklash uni umuman sotib bo'lmaydigan qilardi.
4. INVENTARIZATSIYA (`InventoryCount.status == "draft"`) davomida qo'riqchi
   VAQTINCHA o'chadi. Sanoq paytida tizim qoldig'i ataylab noto'g'ri —
   sanaladigan tovarlar hisobdan chiqarilgan holatda turadi va bloklash
   savdoni to'xtatib qo'yardi. Inventarizatsiya TASDIQLANGACH (`confirmed`)
   qo'riqchi O'ZI QAYTA YOQILADI — qo'lda tugma yo'q, ya'ni yoqishni
   unutib bo'lmaydi.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from models import Cafe, Inventory, InventoryCount, Product, Recipe


class InsufficientStock(Exception):
    """Qoldiq yetmadi. `routers/order.py` uni 400 ga aylantiradi."""

    def __init__(self, shortages: List[dict]):
        self.shortages = shortages
        super().__init__(self.message)

    @property
    def message(self) -> str:
        parts = [
            f"{s['product_name']}, mavjud: {_fmt(s['available'])} {s['unit']}"
            for s in self.shortages
        ]
        return "Yetarli mahsulot yo'q: " + "; ".join(parts)


def _fmt(v: float) -> str:
    """1.0 -> "1", 1.5 -> "1.5" (do'konchiga ".0" ko'rinmasin)."""
    return str(int(v)) if float(v) == int(v) else str(round(float(v), 3))


def is_enabled(db: Session, tenant_id: Optional[int]) -> bool:
    """Qo'riqchi shu do'kon uchun YOQIQmi (inventarizatsiya hisobga olingan)."""
    if tenant_id is None:
        return False
    cafe = db.query(Cafe).filter(Cafe.id == tenant_id).first()
    if not cafe or not getattr(cafe, "block_oversell", False):
        return False
    # ISTISNO 4: ochiq inventarizatsiya bo'lsa vaqtincha o'chadi
    counting = (
        db.query(InventoryCount.id)
        .filter(InventoryCount.tenant_id == tenant_id, InventoryCount.status == "draft")
        .first()
    )
    return counting is None


def check(db: Session, tenant_id: Optional[int], items_data: List[dict]) -> None:
    """Savat ombordan o'tadimi? O'tmasa `InsufficientStock` ko'taradi.

    `items_data` — `order_service.create_order` ichidagi tayyor ro'yxat
    (bepul aksiya qatorlari ham QO'SHILGANDAN KEYIN chaqiriladi, chunki
    ular ham ombordan ayiriladi).

    MIQDOR: `base_qty` ishlatiladi — ombor BAZA birligida (dona/ml) yuritiladi.
    Pachka sotuvida `base_qty = pack_size × quantity`, ya'ni 1 pachka atir =
    100 ml talab qiladi. Aynan shu yerda oddiy `quantity` ni ishlatish
    xato bo'lardi.

    BIR MAHSULOT BIR NECHA QATORDA bo'lsa miqdorlar QO'SHILADI — aks holda
    har qator alohida "yetadi" deb o'tib ketardi.
    """
    if not is_enabled(db, tenant_id):
        return

    need: Dict[int, float] = {}
    for it in items_data:
        pid = it["product_id"]
        qty = float(it.get("base_qty") or it.get("quantity") or 0)
        if qty > 0:
            need[pid] = need.get(pid, 0.0) + qty
    if not need:
        return

    pids = list(need)
    # ISTISNO 2: retseptli mahsulotlar (ingredientdan tayyorlanadi)
    recipe_pids = {
        r.product_id for r in db.query(Recipe.product_id).filter(Recipe.product_id.in_(pids)).all()
    }
    inv_rows = (
        db.query(Inventory)
        .filter(Inventory.product_id.in_(pids), Inventory.tenant_id == tenant_id)
        .all()
    )
    inv_by_pid = {i.product_id: i for i in inv_rows}
    names = {
        p.id: p.name
        for p in db.query(Product.id, Product.name).filter(Product.id.in_(pids)).all()
    }

    shortages = []
    for pid, qty in need.items():
        if pid in recipe_pids:
            continue                     # ISTISNO 2
        inv = inv_by_pid.get(pid)
        if inv is None:
            continue                     # ISTISNO 3 (ombor nazorati yo'q / xizmat)
        available = float(inv.quantity or 0)
        if available < qty:
            shortages.append({
                "product_id":   pid,
                "product_name": names.get(pid, f"#{pid}"),
                "needed":       qty,
                "available":    available,
                "unit":         inv.unit or "dona",
            })

    if shortages:
        raise InsufficientStock(shortages)
