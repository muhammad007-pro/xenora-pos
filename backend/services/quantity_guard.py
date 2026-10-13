"""MIQDOR CHEGARASI — omborga kiradigan miqdorning yuqori chegarasi. YAGONA MANBA.

═══ MUAMMO ═══
Qoldiq kiritishda miqdor maydoniga SHTRIX-KOD tushib qolardi: skaner fokus
miqdor maydonida turganida o'qiydi va 508 681 002 822 184 dona "kirim"
bo'ladi. Prodda 8 marta (XOZMAG 7, BARAKA 1). Egasi keyin hisobdan chiqarib
to'g'rilagan, lekin harakatlar tarixida astronomik raqamlar qoldi.

Server hech qanday yuqori chegarani tekshirmasdi — faqat `> 0`.

═══ QAROR ═══
`MAX_QTY = 1 000 000` — bitta qatorda bundan ko'p tovar real do'konda
bo'lmaydi (eng katta kirim prodda o'n minglar). Shtrix-kod esa 8-14 raqam,
ya'ni kamida 10 000 000 — chegara ularni ishonchli ushlaydi.

Xato 400 (422 EMAS): Pydantic `le=` 422 berardi va frontend uni umumiy
"validatsiya xatosi" deb ko'rsatardi. Bu yerda egaga ANIQ sabab kerak.

═══ QAYERDA ═══
Faqat OMBORGA YOZADIGAN yo'llar: boshlang'ich qoldiq, kirim, chiqim,
hisobdan chiqarish, priyomka, inventarizatsiya, partiya, ko'chirish,
peresort, firmaga vozvrat, AI-ombor. SOTUV (`OrderItemCreate`) ataylab
TEGILMAGAN — u yerda frontend faqat tasdiq so'raydi, to'smaydi.
"""
from __future__ import annotations

from typing import Iterable, Optional

from fastapi import HTTPException

MAX_QTY = 1_000_000

TOO_BIG_MSG = "Miqdor juda katta — shtrix-kod kiritib qo'ymadingizmi?"


def check_qty(value: Optional[float], label: Optional[str] = None) -> None:
    """`value` chegaradan oshsa 400. None — tekshirilmaydi (ixtiyoriy maydon).

    Manfiy tomon ham (abs) — PATCH orqali `-5e14` yozilishi ham xuddi
    shunday axlat. Musbatlik qoidasi bu yerda EMAS, har endpointning o'zida.
    """
    if value is None:
        return
    try:
        v = float(value)
    except (TypeError, ValueError):
        return
    # NaN/inf ham o'tmasin: `nan > X` False bo'lgani uchun alohida tekshiruv.
    if not (abs(v) <= MAX_QTY):
        prefix = f"{label}: " if label else ""
        shown = f"{v:,.0f}".replace(",", " ") if v == v and abs(v) != float("inf") else str(v)
        raise HTTPException(
            status_code=400,
            detail=f"{prefix}{TOO_BIG_MSG} (kiritildi: {shown}, ruxsat: {MAX_QTY:,} gacha)".replace(",", " "),
        )


def check_items(items: Iterable, *fields: str) -> None:
    """Hujjat qatorlari uchun: har qatorning `fields` maydonlari tekshiriladi."""
    for idx, it in enumerate(items or [], start=1):
        for f in fields:
            check_qty(getattr(it, f, None), f"{idx}-qator")
