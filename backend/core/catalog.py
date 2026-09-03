"""Umumiy katalog — NOMZODLARNI YIG'ISH qatlami (1-bosqich).

⚠️ BU BOSQICHDA O'QISH API'SI YO'Q. Ma'lumot jimgina to'planadi; hech bir
endpoint `catalog_candidates` dan o'qimaydi, ya'ni sizish xavfi nol. Katalogni
ko'rsatish (lookup) alohida bosqichda, super-admin tozalashidan KEYIN qo'shiladi.

NEGA UMUMAN YIG'AMIZ: yangi do'kon mahsulotni skaner qilganda nomi/kategoriyasi
o'zi to'lsin. Buning uchun avval ma'lumot to'planishi kerak — 2026-09-04 dagi
tahlil ko'rsatdiki, bir xil shtrix-kodli mahsulotlarning 87% ida nom har xil
yozilgan (masalan "FAZZA" va "FAZZA PLUS kok"). Ya'ni "birinchi kelgan nomni
katalogga yozish" ishlamaydi — variantlarni yig'ib, keyin ODAM tanlashi kerak.
Shu sabab bu jadval "katalog" emas, "NOMZODLAR" jadvali.

UCHTA QAT'IY QOIDA:

1. **Narx yo'q.** `catalog_candidates` da narx, tan narx, ta'minotchi va ombor
   qoldig'i ustunlari UMUMAN YO'Q (models.py). Bu kod intizomi emas — sxema
   darajasidagi kafolat: yozib bo'lmaydigan narsa sizib chiqmaydi.

2. **Ruxsatsiz yig'ilmaydi.** `cafes.catalog_share_enabled` standart `False`.
   Do'kon o'zi yoqmaguncha uning bironta ham mahsuloti yozilmaydi.

3. **Hech qachon to'smaydi.** `record_candidate()` HECH QANDAY istisno
   chiqarmaydi va HECH QACHON mahsulot yaratishni to'xtatmaydi. Xato bo'lsa —
   log'ga yoziladi, oqim davom etadi.

CHAQIRISH SHARTI: faqat asosiy `db.commit()` dan KEYIN chaqiring. Funksiya o'z
yozuvini o'zi commit qiladi; chaqiruvchida saqlanmagan o'zgarish qolsa, u ham
commit bo'lib ketadi.
"""
import logging
import re
import unicodedata
from typing import Optional

from sqlalchemy.orm import Session

from models import Cafe, CatalogCandidate

logger = logging.getLogger(__name__)

# Kirill → lotin. Do'konlar bir mahsulotni ikki alifboda yozadi ("Шампунь" va
# "shampun") — solishtirish uchun ikkalasi bitta kalitga tushishi kerak.
# O'zbek kirill harflari ham bor: ў→o, қ→q, ғ→g, ҳ→h (apostrof baribir
# tashlanadi, ya'ni "o'" va "o" birlashadi).
_CYR2LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "j", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "x", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sh",
    "ъ": "", "ы": "i", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "ў": "o", "қ": "q", "ғ": "g", "ҳ": "h",
}

# Apostrofning barcha ko'rinishlari — "o'" / "o‘" / "o`" / "oʻ" bir xil bo'lsin.
_APOSTROPHES = "'`‘’ʻʼ´"

_MULTISPACE = re.compile(r"\s+")
# Harf va raqamdan boshqa hamma narsa (nuqta, vergul, tire, qavs) — bo'shliqqa.
_NON_ALNUM = re.compile(r"[^0-9a-zЀ-ӿ]+")


def normalize_name(name: Optional[str]) -> str:
    """Solishtirish uchun nom kaliti. Ko'rsatish uchun EMAS.

    Nima tekislanadi:
      * registr           — "NIVEA" == "nivea"
      * ortiqcha bo'shliq — "coca  cola" == "coca cola"
      * apostrof          — "o'simlik" == "osimlik" (barcha apostrof belgilari)
      * nuqta/vergul/tire — "0.5L" == "0,5 l" == "0-5 l"
      * kirill/lotin      — "Шампунь" == "shampun"

    Asl nom `CatalogCandidate.name_original` da o'zgarishsiz saqlanadi —
    keyinchalik odam qaysi variant to'g'ri ekanini KO'RIB tanlaydi.
    """
    if not name:
        return ""
    s = unicodedata.normalize("NFKC", str(name)).strip().lower()
    for ch in _APOSTROPHES:
        s = s.replace(ch, "")
    s = "".join(_CYR2LAT.get(ch, ch) for ch in s)
    s = _NON_ALNUM.sub(" ", s)
    return _MULTISPACE.sub(" ", s).strip()


def gs1_check_digit(body: str) -> int:
    """GS1 mod-10 nazorat raqami (EAN-8, UPC-A, EAN-13 uchun bir xil qoida).

    Og'irlik O'NGDAN chapga: eng o'ngdagi ma'lumot raqami 3, keyingisi 1, ...
    Shu sabab funksiya uzunlikka bog'liq emas — nazorat raqamisiz "tana"
    beriladi. EAN-13 uchun natija `utils.helpers.calculate_ean13_checksum`
    bilan AYNAN bir xil (test bilan qulflangan).
    """
    total = 0
    for i, ch in enumerate(reversed(body)):
        total += int(ch) * (3 if i % 2 == 0 else 1)
    return (10 - total % 10) % 10


# Faqat shu uzunliklar zavod kodi bo'la oladi: EAN-8, UPC-A, EAN-13.
_VALID_LENGTHS = (8, 12, 13)


def is_shareable_barcode(barcode: Optional[str]) -> bool:
    """Kod umumiy katalogga yaroqlimi (OQ RO'YXAT — shubha bo'lsa "yo'q").

    Uch shart:
      1. EAN-13 / UPC-A / EAN-8 — boshqa uzunlik qabul qilinmaydi.
         (Prod bazada 3 raqamli, 26 belgili va harfli "kod"lar ham bor.)
      2. Nazorat raqami to'g'ri.
      3. Prefiks 2 EMAS.

    3-shart nega: GS1 da 2 bilan boshlanadigan kodlar "restricted circulation"
    — ya'ni do'kon ICHIDA yaratilgan kodlar. `core/barcode.py` bizning ichki
    kodlarimizni aynan shunday yaratadi ("20" + 10 raqam + nazorat, zaxira
    yo'lda "29"). Ular faqat bitta do'kon ichida ma'noga ega: ikki do'kon
    bir kodni ikki xil mahsulotga beradi va katalog zaharlanadi. Bu qoida
    barcha uzunliklarga tegishli — 2 bilan boshlanuvchi UPC-A/EAN-8 ham
    GS1 da do'kon ichki kodi.
    """
    if not barcode:
        return False
    code = str(barcode).strip()
    if len(code) not in _VALID_LENGTHS or not code.isdigit():
        return False
    if code[0] == "2":
        return False
    return gs1_check_digit(code[:-1]) == int(code[-1])


def _trim(value: Optional[str], limit: int) -> Optional[str]:
    """Bo'sh bo'lsa None, aks holda kesilgan matn (ustun uzunligiga sig'sin)."""
    if not value:
        return None
    text = str(value).strip()
    return text[:limit] or None


def record_candidate(
    db: Session,
    tenant_id: Optional[int],
    barcode: Optional[str],
    name: Optional[str],
    category_hint: Optional[str] = None,
    unit: Optional[str] = None,
) -> bool:
    """Nomzodni yozadi. HECH QACHON istisno chiqarmaydi.

    Qaytaradi: yozildimi (True) yoki jimgina o'tkazib yuborildimi (False).
    Qaytish qiymati faqat test/log uchun — chaqiruvchi unga qaramaydi.

    Har tenant har barkod bo'yicha BITTA qator (UNIQUE constraint): mahsulot
    tahrirlansa yangi qator emas, mavjudi yangilanadi. Ya'ni bitta do'kon bir
    nomni ko'p marta yozib "ovoz" ko'paytira olmaydi.

    ⚠️ try/except butun tanani o'raydi va ATAYLAB shu yerda — chaqiruv joyida
    emas. Shunda yangi chaqiruv qo'shgan odam himoyani qo'shishni unuta olmaydi
    (routers/product.py da ham, ai_warehouse.py da ham bir xil kafolat).
    """
    try:
        if not tenant_id:
            return False   # tenant noma'lum (platforma egasi, ko'p kafe) — yozmaymiz

        if not is_shareable_barcode(barcode):
            return False

        normalized = normalize_name(name)
        if not normalized:
            return False

        cafe = db.query(Cafe).filter(Cafe.id == tenant_id).first()
        if cafe is None or not cafe.catalog_share_enabled:
            return False   # RUXSAT YO'Q — standart holat

        code = str(barcode).strip()
        row = (
            db.query(CatalogCandidate)
            .filter(
                CatalogCandidate.tenant_id == tenant_id,
                CatalogCandidate.barcode == code,
            )
            .first()
        )
        if row is None:
            db.add(CatalogCandidate(
                tenant_id=tenant_id,
                barcode=code,
                name_normalized=normalized[:200],
                name_original=_trim(name, 200),
                category_hint=_trim(category_hint, 100),
                unit=_trim(unit, 20),
            ))
        else:
            row.name_normalized = normalized[:200]
            row.name_original = _trim(name, 200)
            if category_hint:
                row.category_hint = _trim(category_hint, 100)
            if unit:
                row.unit = _trim(unit, 20)

        db.commit()
        return True

    except Exception as exc:  # noqa: BLE001 — bu qatlam hech qachon to'smaydi
        # ROLLBACK SHART: sessiya buzuq qolsa, chaqiruvchining KEYINGI commit'i
        # yiqiladi. Asosiy amal allaqachon commit bo'lgani uchun bu yerdagi
        # rollback faqat SHU funksiyaning yozuvini bekor qiladi.
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning("catalog_candidate yozilmadi (o'tkazib yuborildi): %s", exc)
        return False


def record_candidates_bulk(db: Session, tenant_id: Optional[int], items) -> int:
    """Bir nechta nomzod — BITTA commit bilan. HECH QACHON istisno chiqarmaydi.

    `items` — (barcode, name, category_hint, unit) to'rtliklari yoki
    (barcode, name) juftliklari.

    NEGA ALOHIDA FUNKSIYA: AI-Ombor bitta nakladnoyda 30-50 mahsulot yaratadi.
    Har biriga `record_candidate()` chaqirilsa 50 ta commit bo'lardi va javob
    sezilarli sekinlashardi. Bu yerda tekshiruvlar aynan bir xil, faqat yozuv
    bir marta commit qilinadi.

    Qaytaradi: yozilgan nomzodlar soni.
    """
    try:
        if not tenant_id:
            return 0

        cafe = db.query(Cafe).filter(Cafe.id == tenant_id).first()
        if cafe is None or not cafe.catalog_share_enabled:
            return 0

        written = 0
        for item in items:
            barcode, name = item[0], item[1]
            category_hint = item[2] if len(item) > 2 else None
            unit = item[3] if len(item) > 3 else None

            if not is_shareable_barcode(barcode):
                continue
            normalized = normalize_name(name)
            if not normalized:
                continue

            code = str(barcode).strip()
            row = (
                db.query(CatalogCandidate)
                .filter(
                    CatalogCandidate.tenant_id == tenant_id,
                    CatalogCandidate.barcode == code,
                )
                .first()
            )
            if row is None:
                db.add(CatalogCandidate(
                    tenant_id=tenant_id,
                    barcode=code,
                    name_normalized=normalized[:200],
                    name_original=_trim(name, 200),
                    category_hint=_trim(category_hint, 100),
                    unit=_trim(unit, 20),
                ))
            else:
                row.name_normalized = normalized[:200]
                row.name_original = _trim(name, 200)
                if category_hint:
                    row.category_hint = _trim(category_hint, 100)
                if unit:
                    row.unit = _trim(unit, 20)
            written += 1

        if written:
            db.commit()
        return written

    except Exception as exc:  # noqa: BLE001 — bu qatlam hech qachon to'smaydi
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning("catalog_candidates to'plami yozilmadi: %s", exc)
        return 0
