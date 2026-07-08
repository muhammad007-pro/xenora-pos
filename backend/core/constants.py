"""
Konstantalar va o'lchov birliklari (BOSQICH 1.4)

KO'P TILLILIK: tizimning barcha "inson o'qiydigan" nomlari (o'lchov birliklari,
til nomlari va h.k.) o'zbek (uz), rus (ru) va ingliz (en) tillarida saqlanadi.
Frontend/backend `tr(...)` orqali foydalanuvchi tilidan kelib chiqib mos
matnni oladi — kelajakda boshqa lug'atlar (status nomlari, xabarlar va h.k.)
ham xuddi shu naqsh bo'yicha qo'shilishi mumkin.
"""

from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# 1) KO'P TILLILIK ASOSI (i18n)
# ---------------------------------------------------------------------------

class Language(str, Enum):
    """Tizim qo'llab-quvvatlaydigan tillar"""
    UZ = "uz"   # O'zbekcha
    RU = "ru"   # Ruscha
    EN = "en"   # Inglizcha


DEFAULT_LANGUAGE = Language.UZ
SUPPORTED_LANGUAGES: tuple[Language, ...] = (Language.UZ, Language.RU, Language.EN)

# "Lokalizatsiya qilingan matn" — har bir til kodiga mos satr
LocalizedText = dict[str, str]


def tr(text: "LocalizedText | str", lang: "Language | str | None" = None) -> str:
    """
    Lokalizatsiya qilingan matnni berilgan tilda qaytaradi.

    Qidiruv tartibi: so'ralgan til -> DEFAULT_LANGUAGE (uz) -> mavjud
    bo'lgan birinchi til -> matnning o'zi (agar oddiy string bo'lsa).
    Hech qachon xato tashlamaydi — aks holda UI yiqiladi.
    """
    if isinstance(text, str):
        return text

    if lang is None:
        lang = DEFAULT_LANGUAGE
    lang_code = lang.value if isinstance(lang, Language) else str(lang)

    if lang_code in text:
        return text[lang_code]
    if DEFAULT_LANGUAGE.value in text:
        return text[DEFAULT_LANGUAGE.value]
    if text:
        return next(iter(text.values()))
    return ""


def normalize_language(value: "Language | str | None") -> Language:
    """Foydalanuvchi/so'rovdan kelgan til kodini xavfsiz Language'ga aylantiradi"""
    if isinstance(value, Language):
        return value
    try:
        return Language(str(value).lower())
    except (ValueError, AttributeError):
        return DEFAULT_LANGUAGE


# ---------------------------------------------------------------------------
# 2) O'LCHOV BIRLIKLARI
# ---------------------------------------------------------------------------

class UnitCategory(str, Enum):
    """O'lchov birligi turkumi — faqat bir xil turkum ichida konvertatsiya mumkin"""
    WEIGHT = "weight"   # Og'irlik (kg, g)
    VOLUME = "volume"   # Hajm (litr, ml)
    COUNT = "count"     # Sanoq (dona, porsiya, paket...)
    LENGTH = "length"   # Uzunlik (metr, sm)


@dataclass(frozen=True)
class MeasurementUnit:
    """
    Bitta o'lchov birligi.

    `to_base_factor` — shu birlikni turkumning BAZA birligiga aylantirish
    koeffitsienti (masalan 1 kg = 1000 g bo'lsa, "g" uchun factor = 1,
    "kg" uchun factor = 1000 — chunki baza birlik har doim eng kichigi).
    """
    code: str
    category: UnitCategory
    to_base_factor: float
    name: LocalizedText = field(default_factory=dict)
    short: LocalizedText = field(default_factory=dict)


# Har turkum uchun BAZA birlik (konvertatsiya shu orqali amalga oshadi)
BASE_UNIT_BY_CATEGORY: dict[UnitCategory, str] = {
    UnitCategory.WEIGHT: "g",
    UnitCategory.VOLUME: "ml",
    UnitCategory.COUNT: "pcs",
    UnitCategory.LENGTH: "cm",
}

# To'liq o'lchov birliklari ro'yxati — universal POS uchun
# (restoran/kafe: kg, g, l, ml, porsiya | magazin: dona, paket, quti | ...)
UNITS: dict[str, MeasurementUnit] = {
    # --- Og'irlik ---
    "g": MeasurementUnit(
        code="g", category=UnitCategory.WEIGHT, to_base_factor=1,
        name={"uz": "gramm", "ru": "грамм", "en": "gram"},
        short={"uz": "g", "ru": "г", "en": "g"},
    ),
    "kg": MeasurementUnit(
        code="kg", category=UnitCategory.WEIGHT, to_base_factor=1000,
        name={"uz": "kilogramm", "ru": "килограмм", "en": "kilogram"},
        short={"uz": "kg", "ru": "кг", "en": "kg"},
    ),

    # --- Hajm ---
    "ml": MeasurementUnit(
        code="ml", category=UnitCategory.VOLUME, to_base_factor=1,
        name={"uz": "millilitr", "ru": "миллилитр", "en": "milliliter"},
        short={"uz": "ml", "ru": "мл", "en": "ml"},
    ),
    "l": MeasurementUnit(
        code="l", category=UnitCategory.VOLUME, to_base_factor=1000,
        name={"uz": "litr", "ru": "литр", "en": "liter"},
        short={"uz": "l", "ru": "л", "en": "l"},
    ),

    # --- Uzunlik ---
    "cm": MeasurementUnit(
        code="cm", category=UnitCategory.LENGTH, to_base_factor=1,
        name={"uz": "santimetr", "ru": "сантиметр", "en": "centimeter"},
        short={"uz": "sm", "ru": "см", "en": "cm"},
    ),
    "m": MeasurementUnit(
        code="m", category=UnitCategory.LENGTH, to_base_factor=100,
        name={"uz": "metr", "ru": "метр", "en": "meter"},
        short={"uz": "m", "ru": "м", "en": "m"},
    ),

    # --- Sanoq (bo'linmaydigan birliklar) ---
    "pcs": MeasurementUnit(
        code="pcs", category=UnitCategory.COUNT, to_base_factor=1,
        name={"uz": "dona", "ru": "штука", "en": "piece"},
        short={"uz": "dona", "ru": "шт", "en": "pcs"},
    ),
    "portion": MeasurementUnit(
        code="portion", category=UnitCategory.COUNT, to_base_factor=1,
        name={"uz": "porsiya", "ru": "порция", "en": "portion"},
        short={"uz": "porsiya", "ru": "порц", "en": "portion"},
    ),
    "pack": MeasurementUnit(
        code="pack", category=UnitCategory.COUNT, to_base_factor=1,
        name={"uz": "paket", "ru": "упаковка", "en": "pack"},
        short={"uz": "paket", "ru": "уп", "en": "pack"},
    ),
    "box": MeasurementUnit(
        code="box", category=UnitCategory.COUNT, to_base_factor=1,
        name={"uz": "quti", "ru": "коробка", "en": "box"},
        short={"uz": "quti", "ru": "кор", "en": "box"},
    ),
    "bottle": MeasurementUnit(
        code="bottle", category=UnitCategory.COUNT, to_base_factor=1,
        name={"uz": "shisha", "ru": "бутылка", "en": "bottle"},
        short={"uz": "shisha", "ru": "бут", "en": "bottle"},
    ),
}


def get_unit(code: str) -> MeasurementUnit:
    """Kod bo'yicha o'lchov birligini topadi, topilmasa xato tashlaydi"""
    unit = UNITS.get(code)
    if unit is None:
        raise ValueError(f"Noma'lum o'lchov birligi: '{code}'")
    return unit


def unit_name(code: str, lang: "Language | str | None" = None) -> str:
    """O'lchov birligining to'liq nomi (masalan: kilogramm / килограмм / kilogram)"""
    return tr(get_unit(code).name, lang)


def unit_short(code: str, lang: "Language | str | None" = None) -> str:
    """O'lchov birligining qisqa belgisi (masalan: kg / кг / kg)"""
    return tr(get_unit(code).short, lang)


def units_by_category(category: "UnitCategory | str") -> list[MeasurementUnit]:
    """Berilgan turkumdagi barcha o'lchov birliklari"""
    if not isinstance(category, UnitCategory):
        category = UnitCategory(category)
    return [u for u in UNITS.values() if u.category == category]
