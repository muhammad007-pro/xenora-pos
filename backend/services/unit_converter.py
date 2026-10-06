"""
Unit Converter — o'lchov birliklari konvertori (BOSQICH 1.4)

Universal POS turli birliklarda ishlaydi: restoran retseptida "250 g go'sht",
magazinda "1 quti", dorixonada "1 dona" va h.k. Bu servis:
  1) bir xil turkum ichida birликlarni bir-biriga aylantiradi (kg <-> g, l <-> ml)
  2) miqdorni foydalanuvchi tiliga (uz/ru/en) mos qilib chiroyli formatlaydi
"""

import math

from core.constants import (
    BASE_UNIT_BY_CATEGORY,
    DEFAULT_LANGUAGE,
    Language,
    UNITS,
    UnitCategory,
    get_unit,
    tr,
    unit_short,
    units_by_category,
)


class IncompatibleUnitsError(ValueError):
    """Bir-biriga aylantirib bo'lmaydigan turkumdagi birliklar (masalan kg -> dona)"""
    pass


def inventory_unit(sale_unit: str | None) -> str:
    """Mahsulotning SOTUV birligidan OMBOR birligini beradi.

    Yagona farq — `pcs` → `dona` (ombor ekranida o'zbekcha o'qilsin). Qolgan
    birliklar o'zgarmaydi.

    ⚠️ YAGONA MANBA. Bu ikki qator ilgari `product.py` (yaratish) va
    `inventory.py` (lazily-create) da ALOHIDA takrorlangan edi. 2026-09-09 da
    uchinchi chaqiruvchi (mahsulot tahrirlanganda birlikni sinxronlash) qo'shildi
    — shuning uchun bir joyga yig'ildi: qoida o'zgarsa, uch joyda emas, shu yerda
    o'zgaradi.
    """
    u = (sale_unit or "dona").strip() or "dona"
    return "dona" if u == "pcs" else u


# ---------------------------------------------------------------------------
# PACHKA/QOP YORLIG'I — frontend bilan BIR XIL matn
#
# Chek yorlig'i `sale_unit` ga qarab o'zgaradi. Frontendda bu yagona manbada
# turadi: `frontend/js/core/receipt-print.js` → `packKind()` / `packSizeLabel()`
# / `fmtPackQty()`. Backend termal chek yo'li (`routers/order.py`
# → `escpos_print_receipt`) esa "dona" ni QOTIB yozardi:
#
#     f" (pachka, {int(base_qty / quantity)} dona)"
#
# Natijada 20 kg qop chekda "(pachka, 20 dona)" bo'lib chiqardi, `int()` esa
# kasrni kesib tashlardi (0.5 → 0).
#
# ⚠️ IKKI MANBA — ATAYLAB: backend frontend faylini o'qiy olmaydi. Shuning
# uchun qoida shu yerda TAKRORLANADI va `tests/test_pack_label.py` ikkisining
# mos kelishini qulflaydi. Birini o'zgartirsang ikkinchisini ham o'zgartir.
# ---------------------------------------------------------------------------

#: Og'irlik/suyuqlik — ulgurji "qop" (frontend `_PACK_WEIGHT_UNITS`)
PACK_WEIGHT_UNITS = ("kg", "g", "l", "litr")
#: Hajm (atir/flakon) — "butun" (frontend `_PACK_VOL_UNITS`)
PACK_VOL_UNITS = ("ml", "dl", "cl")
#: Uzunlik (kabel/mato) — "o'ram" (frontend `_PACK_LENGTH_UNITS`).
#: Ilgari "pachka, 150 dona" chiqardi — birlik yolg'on edi (2026-10-07).
PACK_LENGTH_UNITS = ("m", "sm")


def fmt_pack_qty(value: float | None) -> str:
    """Miqdorni 3 xonagacha yaxlitlab, ortiqcha nollarsiz matn qiladi.

    Frontend `fmtPackQty()` bilan AYNAN bir xil natija berishi shart:
    `String(Math.round(n * 1000) / 1000)`.

    Shu sabab `round()` ISHLATILMAYDI — Python `round()` bankir yaxlitlashini
    qiladi (yarmi juftga: `round(0.0005, 3) == 0.0`), JS `Math.round` esa
    yarmini YUQORIGA. `floor(x * 1000 + 0.5)` ikkalasida bir xil.

    Shuningdek `f"{v:g}"` ham ishlatilmaydi: u katta sonni ilmiy ko'rinishga
    o'tkazadi (1000000 → "1e+06"), JS `String()` esa "1000000" beradi.

    >>> fmt_pack_qty(20)
    '20'
    >>> fmt_pack_qty(0.5)
    '0.5'
    >>> fmt_pack_qty(0.7405882)
    '0.741'
    >>> fmt_pack_qty(None)
    '0'
    """
    try:
        n = float(value or 0)
    except (TypeError, ValueError):
        return "0"
    if n != n or n in (float("inf"), float("-inf")):   # NaN / cheksizlik
        return "0"
    v = math.floor(n * 1000 + 0.5) / 1000
    if v == int(v):
        return str(int(v))
    return f"{v:.3f}".rstrip("0").rstrip(".")


def pack_word(sale_unit: str | None) -> tuple[str, str]:
    """(pachka_so'zi, birlik_so'zi) — frontend `packKind()` bilan bir xil.

    Frontend yorliqni gap boshida ishlatadi ("Qop (20 kg)"), bu yerda esa u
    mahsulot nomidan keyin qavs ichida turadi ("SHAKAR (qop, 20 kg)") —
    shuning uchun KICHIK harf. So'z TANLOVI bir xil.

    >>> pack_word("kg")
    ('qop', 'kg')
    >>> pack_word("ml")
    ('butun', 'ml')
    >>> pack_word("m")
    ("o'ram", 'm')
    >>> pack_word("pcs")
    ('pachka', 'dona')
    """
    u = (sale_unit or "").strip().lower()
    if u in PACK_WEIGHT_UNITS:
        return "qop", u
    if u in PACK_VOL_UNITS:
        return "butun", u
    if u in PACK_LENGTH_UNITS:
        return "o'ram", u
    return "pachka", "dona"


def pack_size_label(sale_unit: str | None, per: float | None) -> str:
    """Chek yorlig'i: "qop, 20 kg" | "butun, 150 ml" | "pachka, 10 dona".

    `per` — bitta pachkadagi miqdor (`base_qty / quantity`).

    ⚠️ `pcs`/`dona` uchun chiqish AVVALGIDEK ("pachka, 10 dona") — mavjud
    cheklar bit-bitiga o'zgarmaydi.

    >>> pack_size_label("kg", 20)
    'qop, 20 kg'
    >>> pack_size_label("pcs", 10)
    'pachka, 10 dona'
    """
    word, unit = pack_word(sale_unit)
    return f"{word}, {fmt_pack_qty(per)} {unit}"


def can_convert(from_unit: str, to_unit: str) -> bool:
    """Ikki birlik bir xil turkumga tegishli bo'lsa — True (konvertatsiya mumkin)"""
    return get_unit(from_unit).category == get_unit(to_unit).category


def to_base(value: float, unit_code: str) -> float:
    """Qiymatni shu turkumning BAZA birligiga aylantiradi (masalan 1.5 kg -> 1500 g)"""
    unit = get_unit(unit_code)
    return value * unit.to_base_factor


def from_base(value: float, unit_code: str) -> float:
    """Baza birlikdagi qiymatni berilgan birlikka aylantiradi (masalan 1500 g -> 1.5 kg)"""
    unit = get_unit(unit_code)
    return value / unit.to_base_factor


def convert(value: float, from_unit: str, to_unit: str) -> float:
    """
    Qiymatni bir birlikdan boshqasiga aylantiradi.
    Faqat bir xil turkum ichida ishlaydi (masalan kg <-> g, l <-> ml).

    >>> convert(1.5, "kg", "g")
    1500.0
    >>> convert(250, "ml", "l")
    0.25
    """
    source = get_unit(from_unit)
    target = get_unit(to_unit)

    if source.category != target.category:
        raise IncompatibleUnitsError(
            f"'{from_unit}' ({source.category.value}) ni "
            f"'{to_unit}' ({target.category.value}) ga aylantirib bo'lmaydi — "
            f"turkumlar har xil"
        )

    return (value * source.to_base_factor) / target.to_base_factor


def humanize_quantity(value: float, unit_code: str) -> tuple[float, str]:
    """
    Qiymatni o'sha turkum ichida eng o'qilishi qulay birlikka moslab qaytaradi.
    Masalan: 1500 g -> (1.5, "kg"), 250 g -> (250, "g"), 2000 ml -> (2, "l").

    Tanlov qoidasi: agar baza birlikdagi qiymat 1000 dan katta/teng bo'lsa
    va kattaroq birlikka butun/qulay aylantirilsa — kattaroq birlik tanlanadi.
    """
    unit = get_unit(unit_code)
    base_value = to_base(value, unit_code)

    candidates = sorted(
        units_by_category(unit.category),
        key=lambda u: u.to_base_factor,
        reverse=True,
    )
    for candidate in candidates:
        converted = base_value / candidate.to_base_factor
        if converted >= 1:
            return round(converted, 3), candidate.code

    return round(base_value, 3), BASE_UNIT_BY_CATEGORY[unit.category]


def format_quantity(
    value: float,
    unit_code: str,
    lang: "Language | str | None" = None,
    auto: bool = False,
    decimals: int | None = None,
) -> str:
    """
    Miqdorni foydalanuvchi tiliga mos o'lchov birligi belgisi bilan formatlaydi.

    - lang: "uz" | "ru" | "en" (standart: o'zbekcha)
    - auto=True: qiymatni eng qulay birlikka avtomatik moslaydi
                 (masalan 1500 g -> "1.5 kg")
    - decimals: kasr xonalar soni (berilmasa — ortiqcha nollarsiz chiqadi)

    >>> format_quantity(1.5, "kg", lang="ru")
    '1.5 кг'
    >>> format_quantity(1500, "g", lang="uz", auto=True)
    '1.5 kg'
    """
    display_unit = unit_code
    display_value = value

    if auto:
        display_value, display_unit = humanize_quantity(value, unit_code)

    if decimals is not None:
        number_text = f"{display_value:.{decimals}f}"
    else:
        # Butun son bo'lsa — kasrsiz, aks holda ortiqcha nollarsiz ko'rsatish
        rounded = round(display_value, 3)
        number_text = f"{rounded:g}"

    return f"{number_text} {unit_short(display_unit, lang)}"


# ---------------------------------------------------------------------------
# NARX <-> MIQDOR HISOB-KITOBI
#
# Amaliy holat: omborchi "1.5 kg olma — 10 000 so'm" deb kiritadi (umumiy
# narx + umumiy miqdor). Tizim shundan kelib chiqib istalgan o'lchov birligi
# uchun (1 kg uchun, 1 g uchun, 1 dona uchun...) narxni hisoblab beradi —
# va aksincha, narxi ma'lum birlik bo'yicha bo'lsa, umumiy summani topadi.
# ---------------------------------------------------------------------------

def calculate_unit_price(
    total_price: float,
    quantity: float,
    quantity_unit: str,
    target_unit: "str | None" = None,
) -> float:
    """
    Umumiy narx va umumiy miqdordan kelib chiqib, BIR BIRLIK narxini hisoblaydi.

    - target_unit berilmasa — natija `quantity_unit` bo'yicha (masalan 1 kg uchun)
    - target_unit berilsa va u bilan bir turkumda bo'lsa — o'sha birlikka
      konvertatsiya qilib hisoblanadi (masalan "1 kg uchun narx" -> "1 g uchun narx")

    Misol: "1.5 kg olma — 10 000 so'm"
    >>> calculate_unit_price(10_000, 1.5, "kg")
    6666.666666666667          # 1 kg olma narxi
    >>> calculate_unit_price(10_000, 1.5, "kg", target_unit="g")
    6.666666666666667          # 1 gramm olma narxi
    """
    if quantity <= 0:
        raise ValueError("Miqdor noldan katta bo'lishi kerak")

    target_unit = target_unit or quantity_unit

    # Avval narxni "1 quantity_unit uchun" ko'rinishga keltiramiz,
    # so'ng kerak bo'lsa maqsadli birlikka moslaymiz.
    price_per_quantity_unit = total_price / quantity

    if target_unit == quantity_unit:
        return price_per_quantity_unit

    if not can_convert(quantity_unit, target_unit):
        raise IncompatibleUnitsError(
            f"Narxni '{quantity_unit}' dan '{target_unit}' ga o'tkazib bo'lmaydi — "
            f"turkumlar har xil"
        )

    # 1 target_unit qancha quantity_unit ekanini topamiz va shunga ko'paytiramiz
    one_target_in_quantity_unit = convert(1, target_unit, quantity_unit)
    return price_per_quantity_unit * one_target_in_quantity_unit


def calculate_total_price(
    unit_price: float,
    quantity: float,
    price_unit: str,
    quantity_unit: "str | None" = None,
) -> float:
    """
    Bitta birlik narxi va miqdordan kelib chiqib, umumiy summani hisoblaydi.
    `quantity_unit` berilsa va u `price_unit`dan farq qilsa — avval miqdor
    narx birligiga moslab konvertatsiya qilinadi.

    Misol: "1 kg olma 6 666.67 so'm, 1.5 kg sotib olindi — qancha to'lash kerak?"
    >>> calculate_total_price(6666.67, 1.5, "kg")
    10000.005
    >>> calculate_total_price(6666.67, 1500, "kg", quantity_unit="g")
    10000.005
    """
    quantity_unit = quantity_unit or price_unit

    if quantity_unit == price_unit:
        return unit_price * quantity

    if not can_convert(quantity_unit, price_unit):
        raise IncompatibleUnitsError(
            f"Miqdorni '{quantity_unit}' dan '{price_unit}' ga o'tkazib bo'lmaydi — "
            f"turkumlar har xil"
        )

    quantity_in_price_unit = convert(quantity, quantity_unit, price_unit)
    return unit_price * quantity_in_price_unit


def format_unit_price(
    total_price: float,
    quantity: float,
    quantity_unit: str,
    target_unit: "str | None" = None,
    lang: "Language | str | None" = None,
    decimals: int = 0,
) -> str:
    """
    Bir birlik narxini tayyor matn ko'rinishida qaytaradi — masalan:
    "10 000 so'm / 1.5 kg" kiritilsa -> "6 667 so'm/kg" (uz/ru/en belgisi bilan).

    Pul birligi UZS deb olingan ("so'm"/"сум"/"sum") — kerak bo'lsa kelajakda
    `currency` parametri qo'shib kengaytirish mumkin.
    """
    target_unit = target_unit or quantity_unit
    price = calculate_unit_price(total_price, quantity, quantity_unit, target_unit)

    currency_label = {"uz": "so'm", "ru": "сум", "en": "UZS"}
    money_text = f"{round(price, decimals):,.{decimals}f}".replace(",", " ")

    return f"{money_text} {tr(currency_label, lang)}/{unit_short(target_unit, lang)}"
