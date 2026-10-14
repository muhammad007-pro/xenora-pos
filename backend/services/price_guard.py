"""NARX CHEGARASI — narx / tan narxning yuqori chegarasi. YAGONA MANBA.

═══ MUAMMO ═══
Kassir narx maydoniga son yozadi, skaner esa shtrix-kodni SHU maydonga qo'shib
yuboradi: "12000" + "4780019480…" = 1.2000478…e17. audit_logs da 11 marta,
3 do'konda (10.09–14.10). BARAKA'da RIZQ 200 GR tannarxi 4 780 045 170 147
bo'lib, "Ombor qiymati" 95,6 TRILLION ko'rindi. Miqdorda chegara bor edi
(`quantity_guard`, 1 000 000), narxda — yo'q.

═══ QAROR: 1 000 000 000 (1 mlrd so'm) ═══
• prodda eng qimmat haqiqiy tovar ~5,5 mln (MANHATTAN) — 180 baravar zaxira;
• EAN-13 / UPC-A shtrix-kodning O'ZI ≈ 4,7·10¹² — har doim ushlanadi;
• songa QO'SHILGAN har qanday shtrix-kod (auditdagi 11 holatning hammasi) ≥ 10¹² —
  ushlanadi;
• ushlanmaydigan yagona holat: 8 raqamli EAN-8 BO'SH maydonga (10–99 mln). Uni
  frontend "8+ raqam" tasdig'i ushlaydi (to'smaydi — 15 mln lik tovar ham bor).

Xato 400 (422 EMAS) — `quantity_guard` bilan bir xil sabab: egaga ANIQ xabar.

═══ QAYERDA ═══
Narx YOZILADIGAN yo'llar: mahsulot yaratish/tahrirlash (narx, tan narx, ulgurji,
pachka narxi), ombor kirimidagi tan narx, priyomka, AI-ombor, POS narx kelishuvi
(`unit_price_override`). Hisoblanadigan narxlar (ustama siyosati, o'rtacha tan
narx) — manbasi cheklangan, alohida tekshirilmaydi.
"""
from __future__ import annotations

from typing import Mapping, Optional

from fastapi import HTTPException

MAX_PRICE = 1_000_000_000

TOO_BIG_MSG = "Narx juda katta — shtrix-kod narx maydoniga tushib qolmadimi?"

PRODUCT_PRICE_FIELDS = {
    "price": "Narx",
    "cost_price": "Tan narx",
    "wholesale_price": "Ulgurji narx",
    "pack_price": "Pachka narxi",
}


def check_price(value: Optional[float], label: Optional[str] = None) -> None:
    """`value` chegaradan oshsa 400. None — tekshirilmaydi (ixtiyoriy maydon).
    NaN/inf ham o'tmaydi. Manfiy tomon ham (abs) — axlat har ikki yo'nalishda."""
    if value is None:
        return
    try:
        v = float(value)
    except (TypeError, ValueError):
        return
    if not (abs(v) <= MAX_PRICE):
        prefix = f"{label}: " if label else ""
        shown = f"{v:,.0f}".replace(",", " ") if v == v and abs(v) != float("inf") else str(v)
        raise HTTPException(
            status_code=400,
            detail=f"{prefix}{TOO_BIG_MSG} (kiritildi: {shown}, ruxsat: {MAX_PRICE:,} gacha)".replace(",", " "),
        )


def check_item_prices(items, *fields: str) -> None:
    """Hujjat qatorlari: har qatorning `fields` narx maydonlari (`quantity_guard.check_items` naqshi)."""
    for idx, it in enumerate(items or [], start=1):
        for f in fields:
            val = it.get(f) if isinstance(it, Mapping) else getattr(it, f, None)
            check_price(val, f"{idx}-qator")


def check_product_prices(data: Mapping) -> None:
    """Mahsulot payload'idagi barcha narx maydonlari (bor bo'lganlari)."""
    for key, label in PRODUCT_PRICE_FIELDS.items():
        if key in data:
            check_price(data.get(key), label)
