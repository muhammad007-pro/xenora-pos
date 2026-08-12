"""Ichki (do'kon) shtrix-kod generatsiyasi — tenant-scoped.

Ilgari bu mantiq `routers/ai_warehouse.py` ichida `_gen_internal_barcode`
bo'lib turgan va faqat AI-Ombor oqimidan chaqirilardi. Endi umumiy joyga
ko'chirildi: `/products/{id}/generate-barcode` va to'plam endpointi ham
AYNI generatordan foydalanadi — ikki xil kod sxemasi paydo bo'lmasin.

Mantiq AYNAN ko'chirildi (xulq o'zgarmadi) — AI-Ombor natijasi avvalgidek.
Yagona qo'shimcha: ixtiyoriy `check_alt_barcodes` bayrog'i (standart False,
ya'ni AI-Ombor yo'li tegilmagan).
"""
import random
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from models import Product, ProductBarcode
from utils.helpers import calculate_ean13_checksum


def ean13(base12: str) -> str:
    """12 raqamli bazaga nazorat raqamini qo'shadi → to'g'ri EAN-13."""
    return base12 + str(calculate_ean13_checksum(base12))


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
def gen_internal_barcode(
    db: Session,
    tenant_id: Optional[int],
    used: set,
    check_alt_barcodes: bool = False,
) -> str:
    """Tenant ichida unikal ichki EAN-13 qaytaradi.

    used — shu partiya ichida allaqachon berilgan kodlar (DB'ga hali yozilmagan
    bo'lishi mumkin), takrorlanmasligi uchun.

    check_alt_barcodes=True bo'lsa `product_barcodes` jadvali ham tekshiriladi
    (mahsulotning QO'SHIMCHA kodlari). AI-Ombor yo'li buni ISHLATMAYDI —
    o'sha yerdagi xulq bayt-ma-bayt avvalgidek qolishi uchun standart False.
    """
    for _ in range(30):
        code = ean13("20" + f"{random.randint(0, 10**10 - 1):010d}")
        if code in used:
            continue
        exists = (
            db.query(Product.id)
            .filter(Product.tenant_id == tenant_id, Product.barcode == code)
            .first()
        )
        if not exists and check_alt_barcodes:
            exists = (
                db.query(ProductBarcode.id)
                .filter(ProductBarcode.tenant_id == tenant_id, ProductBarcode.barcode == code)
                .first()
            )
        if not exists:
            used.add(code)
            return code
    # Juda kam ehtimol — vaqt asosida zaxira kod (u ham to'g'ri EAN-13)
    code = ean13("29" + f"{int(datetime.now().timestamp() * 1000) % 10**10:010d}")
    used.add(code)
    return code
