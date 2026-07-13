"""
Feature Flags — biznes turi tizimi (BOSQICH 1.3)

G'oya: bitta dastur — har xil biznes turlari (kafe, restoran, magazin...).
Har bir biznes turi o'zining standart funksiyalar to'plamiga ega.
Funksiyalar HECH QACHON o'chirilmaydi — faqat YASHIRILADI, va kafe
xohlasa qo'shimcha funksiyalarni qo'lda yoqishi mumkin (`enabled_features`
va `disabled_features` orqali, `Cafe` modelida saqlanadi).
"""

from enum import Enum
from typing import Iterable, FrozenSet


class FeatureTier(str, Enum):
    """Flag darajasi: FREE = tenant o'zi yoqadi, PRO = faqat super-admin"""
    FREE = "free"
    PRO  = "pro"


# Multi-filial uchun FREE limitı
FREE_BRANCH_LIMIT = 1


class BusinessType(str, Enum):
    """Qo'llab-quvvatlanadigan biznes turlari (ARCHITECTURE.md bo'lim 4)"""
    RESTAURANT = "restaurant"        # 🍽️ Restoran
    CAFE = "cafe"                    # ☕ Kafe
    FAST_FOOD = "fast_food"          # 🍔 Fast Food
    STORE = "store"                  # 🏪 Magazin
    SUPERMARKET = "supermarket"      # 🛒 Supermarket
    PHARMACY = "pharmacy"            # 💊 Dorixona
    SALON = "salon"                  # 💇 Go'zallik saloni
    FITNESS = "fitness"              # 💪 Fitnes klub
    AUTO_SERVICE = "auto_service"    # 🔧 Auto servis
    SCHOOL = "school"                # 📚 Kurs / Maktab
    HOTEL = "hotel"                  # 🏨 Mehmonxona
    DRY_CLEANING = "dry_cleaning"    # 👔 Kimyoviy tozalash


class Feature(str, Enum):
    """Tizimdagi yoqilishi/yashirilishi mumkin bo'lgan funksiyalar"""
    KITCHEN_DISPLAY = "kitchen_display"        # Oshxona ekrani (KDS)
    TABLE_MANAGEMENT = "table_management"      # Stol boshqaruvi
    WAITER = "waiter"                          # Ofitsiant rejimi
    TABLE_RESERVATION = "table_reservation"    # Stol bron qilish
    RECIPE = "recipe"                          # Retsept (ombordan avtomatik kamaytirish)
    BARCODE = "barcode"                        # Shtrix-kod skaneri
    SCALE = "scale"                            # Tarozi (kg/g o'lchov)
    EXPIRY_DATE = "expiry_date"                # Yaroqlilik muddati nazorati
    TIME_BOOKING = "time_booking"              # Vaqt bo'yicha bron (appointment)
    SERVICES = "services"                      # Xizmatlar ro'yxati (salon/auto/...)
    INVENTORY = "inventory"                    # Ombor boshqaruvi
    LOYALTY = "loyalty"                        # Sodiqlik dasturi (bonus)
    DELIVERY = "delivery"                      # Yetkazib berish
    QR_MENU = "qr_menu"                        # QR-menyu (mijoz o'zi buyurtma beradi)
    # Pro funksiyalar (BOSQICH 9)
    MODIFIERS = "modifiers"                    # Mahsulot modifikatorlari (o'lcham, o'tkirlik)
    COMBO = "combo"                            # Kombo/Set menyu
    HAPPY_HOUR = "happy_hour"                  # Vaqtga qarab avtomatik chegirma
    TABLE_MERGE = "table_merge"                # Stol birlashtirish
    COURSES = "courses"                        # Kursli ovqat (1-ovqat, 2-ovqat)
    WAITER_CALL = "waiter_call"                # Ofitsiant chaqirish (QR orqali)
    TIPS = "tips"                              # Choy puli (tips)
    CUSTOMER_HISTORY = "customer_history"      # Mijoz tarixi va sevimli taomlar
    VOICE_ORDER = "voice_order"                # Ovozli buyurtma (oshxona e'loni)
    # BOSQICH 17: Poteriya tizimi
    YIELD_TRACKING = "yield_tracking"          # Yield/poteriya hisobi (faqat oziq-ovqat)
    # BOSQICH 18: Xodimlar ovqati
    STAFF_MEAL = "staff_meal"                  # Xodimlar ovqati (bepul, ombor chiqimi, xarajat)
    # BOSQICH 19: Magazin Pro funksiyalar
    CREDIT_SALES = "credit_sales"              # Nasiya/qarz daftar (magazin/supermarket)
    WHOLESALE_PRICING = "wholesale_pricing"    # Ko'tara va dona narx (optom/rozn)
    RETURNS = "returns"                        # Qaytarish va almashtirish tizimi
    # BOSQICH 20: Magazin Pro II funksiyalar
    PROMOTIONS = "promotions"                  # Aksiya/murakkab chegirmalar (buy_x_get_y, flash)
    MULTI_BARCODE = "multi_barcode"            # Ko'p barcode (bir mahsulot uchun)
    QUICK_SELL = "quick_sell"                  # Tez sotuv paneli (1 bosishda)
    SUPPLIER_ACCOUNTING = "supplier_accounting"  # Yetkazib beruvchi hisob-kitob (priyomka)
    PRICE_HISTORY = "price_history"            # Narx o'zgarish tarixi (audit)
    RECEIPT_SETTINGS = "receipt_settings"      # Chek sozlamasi (do'kon nomi, QR)
    CASH_REGISTER = "cash_register"            # Kassa smena (boshlang'ich pul, kamomad)
    Z_REPORT = "z_report"                      # Z-hisobot (kun yakuni) + kassa farqi cheki
    DEPARTMENTS = "departments"                # Bo'limlar tizimi (seksiya/department)
    # BOSQICH 22: Dorixona maxsus funksiyalar
    PRESCRIPTION_ARCHIVE = "prescription_archive"  # Shifokor retsepti arxivi
    DRUG_ANALOGS = "drug_analogs"              # Dori o'rnini bosuvchi (analog)
    BATCH_TRACKING = "batch_tracking"          # Seriya/partiya nazorati
    DOSAGE_INFO = "dosage_info"                # Dozaj va qabul tartibi
    RX_REQUIRED = "rx_required"               # Retseptli/retseptsiz nazorat
    # BOSQICH 23: Salon maxsus funksiyalar
    ONLINE_BOOKING = "online_booking"          # Bo'sh vaqt hisoblash + double-booking bloklash
    STAFF_SCHEDULE = "staff_schedule"          # Usta haftalik ish jadvali
    BEFORE_AFTER_PHOTO = "before_after_photo"  # Oldin/keyin fotosuratlar
    SALON_CLIENT_HISTORY = "salon_client_history"  # Mijoz tarixi va reyting
    COMMISSION_REPORT = "commission_report"    # Usta komissiya hisoboti
    # BOSQICH 24: Magazin B2B oldi-berdi
    SUPPLIER_CARD = "supplier_card"            # Yetkazib beruvchi firma kartochkasi
    PURCHASE_RECEIPT = "purchase_receipt"      # Priyomka (qabul akti, nakladnoy)
    SUPPLIER_DEBT = "supplier_debt"            # Firmaga qarz / oldi-berdi tarixi
    SUPPLIER_RETURN = "supplier_return"        # Vozvrat postavshchikka
    # BOSQICH 25: Tovar harakati va hisobdan chiqarish
    WRITE_OFF           = "write_off"           # Utilizatsiya / Spisaniye
    GOODS_REGRADE       = "goods_regrade"       # Peresort (xato kirim tuzatish)
    CUSTOMER_RETURN_EXT = "customer_return_ext" # Vozvrat kengaytirilgan (brak/almashtirish)
    INTERNAL_TRANSFER   = "internal_transfer"   # Ichki ko'chirish (filiallar orasida)
    LOSS_REPORT         = "loss_report"         # Zarar hisoboti (utilizatsiya+brak jami)
    # BOSQICH 26: Narx, Aksiya va Markirovka
    MARKUP_POLICY       = "markup_policy"       # Avto-narx siyosati (naценka foizi)
    BONUS_CARD          = "bonus_card"          # Mijoz bonus kartasi (ball tizimi)
    MARKIROVKA          = "markirovka"          # Asl belgisi (DataMatrix/QR markirovka)
    # BOSQICH 27: Aqlli hisobot va nazorat
    ABC_ANALYSIS        = "abc_analysis"        # ABC tahlil (A=foyda ko'p, B=o'rta, C=kam)
    AUTO_REORDER        = "auto_reorder"        # Avto-zakaz (min qoldiq → ogohlantirish)
    TURNOVER_ANALYSIS   = "turnover_analysis"   # Oborot tahlili (tez/sekin/o'lik tovar)
    PEAK_HOURS          = "peak_hours"          # Peak soatlar/kunlar grafik
    STORE_DASHBOARD     = "store_dashboard"     # Umumiy dashboard (magazin egasi)


# ── Guruh feature to'plamlari (DRY) ─────────────────────────────────────────────
# Bir oilaga (guruhga) kiruvchi biznes turlari BIR XIL feature to'plamini oladi.
# business_type enum (nom) o'zgarmaydi — faqat ortidagi default flaglar birlashtirilgan.

# 🍽️ Ovqatlanish (food): restaurant + cafe + fast_food — bir xil to'plam.
FOOD_FEATURES: frozenset[Feature] = frozenset({
    Feature.KITCHEN_DISPLAY, Feature.TABLE_MANAGEMENT, Feature.WAITER,
    Feature.TABLE_RESERVATION, Feature.RECIPE, Feature.SCALE,
    Feature.INVENTORY, Feature.LOYALTY, Feature.DELIVERY, Feature.QR_MENU,
    Feature.MODIFIERS, Feature.COMBO, Feature.HAPPY_HOUR, Feature.TABLE_MERGE,
    Feature.COURSES, Feature.WAITER_CALL, Feature.TIPS, Feature.CUSTOMER_HISTORY,
    Feature.VOICE_ORDER, Feature.YIELD_TRACKING, Feature.STAFF_MEAL,
    Feature.Z_REPORT,
})

# 🏪 Chakana savdo (retail): store + supermarket — bir xil to'plam.
# FAQAT FREE flaglar (14). PRO flaglar (wholesale_pricing, supplier_accounting,
# departments, supplier_card/debt/return, purchase_receipt, write_off, goods_regrade,
# customer_return_ext, internal_transfer, loss_report, markup_policy, bonus_card,
# markirovka, abc_analysis, auto_reorder, turnover_analysis, peak_hours) DEFAULT'DAN
# OLIB TASHLANDI — ular pulli (PRO). FEATURE_TIERS'da PRO bo'lib qoladi va super-admin
# enabled_features override orqali tenantga qo'lda yoqa oladi (monetizatsiya).
RETAIL_FEATURES: frozenset[Feature] = frozenset({
    Feature.BARCODE, Feature.SCALE, Feature.INVENTORY, Feature.LOYALTY,
    Feature.CREDIT_SALES, Feature.RETURNS, Feature.PROMOTIONS,
    Feature.MULTI_BARCODE, Feature.QUICK_SELL, Feature.PRICE_HISTORY,
    Feature.RECEIPT_SETTINGS, Feature.CASH_REGISTER, Feature.Z_REPORT,
    Feature.STORE_DASHBOARD,
    # Firma (FREE) — o'rtacha do'kon 10-15 firma bilan ishlaydi, asosiy ehtiyoj.
    # supplier_return: sut/non vozvrati kundalik jarayon.
    Feature.SUPPLIER_CARD, Feature.PURCHASE_RECEIPT, Feature.SUPPLIER_DEBT,
    Feature.SUPPLIER_RETURN,
})


# Har bir biznes turi uchun STANDART (default) funksiyalar to'plami.
# Bu yerda yo'q funksiya — UI'da yashirin, lekin Cafe.enabled_features
# orqali istalgan vaqt qo'lda yoqish mumkin (funksiyalar o'chirilmaydi).
BUSINESS_FEATURE_MATRIX: dict[BusinessType, frozenset[Feature]] = {
    # 🍽️ Ovqatlanish oilasi — bir xil FOOD_FEATURES
    BusinessType.RESTAURANT: FOOD_FEATURES,
    BusinessType.CAFE:       FOOD_FEATURES,
    BusinessType.FAST_FOOD:  FOOD_FEATURES,
    # 🏪 Chakana savdo oilasi — bir xil RETAIL_FEATURES
    BusinessType.STORE:       RETAIL_FEATURES,
    BusinessType.SUPERMARKET: RETAIL_FEATURES,
    BusinessType.PHARMACY: frozenset({
        Feature.BARCODE, Feature.EXPIRY_DATE, Feature.INVENTORY, Feature.LOYALTY,
        Feature.RETURNS, Feature.RECEIPT_SETTINGS, Feature.CASH_REGISTER, Feature.Z_REPORT,
        Feature.PRICE_HISTORY,   # supplier_accounting (PRO) default'dan olindi — pulli
        # BOSQICH 22: dorixona maxsus
        Feature.PRESCRIPTION_ARCHIVE, Feature.DRUG_ANALOGS,
        Feature.BATCH_TRACKING, Feature.DOSAGE_INFO, Feature.RX_REQUIRED,
    }),
    BusinessType.SALON: frozenset({
        Feature.TIME_BOOKING, Feature.SERVICES, Feature.INVENTORY, Feature.LOYALTY,
        Feature.CUSTOMER_HISTORY,
        # BOSQICH 23: salon maxsus
        Feature.ONLINE_BOOKING, Feature.STAFF_SCHEDULE, Feature.BEFORE_AFTER_PHOTO,
        Feature.SALON_CLIENT_HISTORY, Feature.COMMISSION_REPORT,
    }),
    BusinessType.FITNESS: frozenset({
        Feature.TIME_BOOKING, Feature.SERVICES, Feature.LOYALTY,
    }),
    BusinessType.AUTO_SERVICE: frozenset({
        Feature.TIME_BOOKING, Feature.SERVICES, Feature.INVENTORY,
    }),
    BusinessType.SCHOOL: frozenset({
        Feature.TIME_BOOKING, Feature.SERVICES, Feature.LOYALTY,
    }),
    BusinessType.HOTEL: frozenset({
        Feature.TABLE_RESERVATION, Feature.TIME_BOOKING, Feature.SERVICES,
        Feature.INVENTORY, Feature.LOYALTY,
    }),
    BusinessType.DRY_CLEANING: frozenset({
        Feature.TIME_BOOKING, Feature.SERVICES, Feature.INVENTORY,
    }),
}


# ── PRO funksiyalar — BIZNES TURI bo'yicha (O'ZGARISH 3 mapping) ────────────────
# G'oya: har biznes turi FAQAT O'ZИГА tegishli PRO funksiyalarni ko'radi. PRO tarif
# = shu to'plamni ochadi (global BARCHA PRO emas). Begona biznesga oid PRO funksiya
# umuman ko'rinmaydi. Qoida: "kam yashir, ko'p ko'rsat" — shubhada funksiya qoldiriladi.
#
# BUSINESS_FEATURE_MATRIX (yuqorida) = FREE default (hammaga yoniq).
# BUSINESS_PRO_MATRIX (quyida)      = shu biznesning PRO funksiyalari (PRO tarifda yoniq).

# Universal PRO — analitika/loyallik, HAR BIR biznesga foydali
_UNIVERSAL_PRO: frozenset[Feature] = frozenset({
    Feature.PEAK_HOURS,       # peak soat/kun grafik
    Feature.BONUS_CARD,       # mijoz bonus kartasi
    Feature.ABC_ANALYSIS,     # ABC foyda tahlili
})
# Ombor/ta'minot PRO — ombori/yetkazuvchisi bor bizneslar
_INVENTORY_PRO: frozenset[Feature] = frozenset({
    Feature.WRITE_OFF,             # utilizatsiya/spisaniye
    Feature.AUTO_REORDER,          # avto-zakaz (min qoldiq)
    Feature.TURNOVER_ANALYSIS,     # oborot tahlili
    Feature.SUPPLIER_ACCOUNTING,   # yetkazib beruvchi hisob-kitob
    Feature.INTERNAL_TRANSFER,     # filiallar aro ko'chirish
    Feature.LOSS_REPORT,           # zarar hisoboti
})
# Chakana-maxsus PRO — faqat savdo (magazin/dorixona) uchun mantiqли
_RETAIL_ONLY_PRO: frozenset[Feature] = frozenset({
    Feature.WHOLESALE_PRICING,     # optom/dona narx
    Feature.DEPARTMENTS,           # bo'limlar/seksiyalar
    Feature.GOODS_REGRADE,         # peresort
    Feature.MARKUP_POLICY,         # avto-narx siyosati
    Feature.CUSTOMER_RETURN_EXT,   # kengaytirilgan qaytarish
    Feature.MARKIROVKA,            # DataMatrix markirovka
})

RETAIL_PRO:      frozenset[Feature] = _UNIVERSAL_PRO | _INVENTORY_PRO | _RETAIL_ONLY_PRO   # 15 (to'liq)
PHARMACY_PRO:    frozenset[Feature] = RETAIL_PRO                                            # dorixona retail-og'ir
# Ovqatlanish: universal + ombor + DEPARTMENTS (oshxona seksiyalari) + MARKUP_POLICY
# (menyu avto-narx). Retail-maxsus (optom, peresort, markirovka, mijoz-qaytarish)
# OLINMADI — food'ga mantiqsiz.
FOOD_PRO:        frozenset[Feature] = _UNIVERSAL_PRO | _INVENTORY_PRO | frozenset({Feature.DEPARTMENTS, Feature.MARKUP_POLICY})
SERVICE_INV_PRO: frozenset[Feature] = _UNIVERSAL_PRO | _INVENTORY_PRO   # ombori bor xizmat (salon/auto/hotel/kimyoviy)
SERVICE_PRO:     frozenset[Feature] = _UNIVERSAL_PRO                    # ombori yo'q xizmat (fitnes/maktab)

BUSINESS_PRO_MATRIX: dict[BusinessType, frozenset[Feature]] = {
    # 🍽️ Ovqatlanish
    BusinessType.RESTAURANT: FOOD_PRO,
    BusinessType.CAFE:       FOOD_PRO,
    BusinessType.FAST_FOOD:  FOOD_PRO,
    # 🏪 Chakana savdo
    BusinessType.STORE:       RETAIL_PRO,
    BusinessType.SUPERMARKET: RETAIL_PRO,
    BusinessType.PHARMACY:    PHARMACY_PRO,
    # 💇 Xizmat (ombori bor)
    BusinessType.SALON:        SERVICE_INV_PRO,
    BusinessType.AUTO_SERVICE: SERVICE_INV_PRO,
    BusinessType.HOTEL:        SERVICE_INV_PRO,
    BusinessType.DRY_CLEANING: SERVICE_INV_PRO,
    # 💪 Xizmat (ombori yo'q)
    BusinessType.FITNESS:      SERVICE_PRO,
    BusinessType.SCHOOL:       SERVICE_PRO,
}


# ── Har bir flag uchun tarif darajasi ──────────────────────────────────────────
# FREE  — tenant egasi settings.html orqali o'zi yoqib/o'chira oladi
# PRO   — faqat super-admin yoqa oladi (tenant PRO tarif sotib olishi kerak)
FEATURE_TIERS: dict[Feature, FeatureTier] = {
    # ── Umumiy (FREE) ─────────────────────────────────────────────────────────
    Feature.INVENTORY:          FeatureTier.FREE,
    Feature.BARCODE:            FeatureTier.FREE,
    Feature.CASH_REGISTER:      FeatureTier.FREE,
    Feature.Z_REPORT:           FeatureTier.FREE,   # Z-hisobot + kassa farqi (kun yakuni)
    Feature.RECEIPT_SETTINGS:   FeatureTier.FREE,
    Feature.RETURNS:            FeatureTier.FREE,
    Feature.QUICK_SELL:         FeatureTier.FREE,
    Feature.SCALE:              FeatureTier.FREE,
    Feature.LOYALTY:            FeatureTier.FREE,
    Feature.CUSTOMER_HISTORY:   FeatureTier.FREE,
    Feature.EXPIRY_DATE:        FeatureTier.FREE,
    Feature.MULTI_BARCODE:      FeatureTier.FREE,
    Feature.PRICE_HISTORY:      FeatureTier.FREE,
    Feature.STORE_DASHBOARD:    FeatureTier.FREE,
    Feature.CREDIT_SALES:       FeatureTier.FREE,   # Qarz/Nasiya — egasi sozlamadan boshqaradi
    Feature.PROMOTIONS:         FeatureTier.FREE,   # Aksiya — egasi sozlamadan boshqaradi
    # ── Biznesga xos (FREE) ───────────────────────────────────────────────────
    Feature.KITCHEN_DISPLAY:    FeatureTier.FREE,
    Feature.TABLE_MANAGEMENT:   FeatureTier.FREE,
    Feature.WAITER:             FeatureTier.FREE,
    Feature.TABLE_RESERVATION:  FeatureTier.FREE,
    Feature.RECIPE:             FeatureTier.FREE,
    Feature.MODIFIERS:          FeatureTier.FREE,
    Feature.COMBO:              FeatureTier.FREE,
    Feature.COURSES:            FeatureTier.FREE,
    Feature.TABLE_MERGE:        FeatureTier.FREE,
    Feature.QR_MENU:            FeatureTier.FREE,
    Feature.HAPPY_HOUR:         FeatureTier.FREE,
    Feature.WAITER_CALL:        FeatureTier.FREE,
    Feature.TIPS:               FeatureTier.FREE,
    Feature.VOICE_ORDER:        FeatureTier.FREE,
    Feature.DELIVERY:           FeatureTier.FREE,
    Feature.YIELD_TRACKING:     FeatureTier.FREE,
    Feature.STAFF_MEAL:         FeatureTier.FREE,
    Feature.TIME_BOOKING:       FeatureTier.FREE,
    Feature.SERVICES:           FeatureTier.FREE,
    # ── Dorixona (FREE) ───────────────────────────────────────────────────────
    Feature.PRESCRIPTION_ARCHIVE:  FeatureTier.FREE,
    Feature.DRUG_ANALOGS:          FeatureTier.FREE,
    Feature.BATCH_TRACKING:        FeatureTier.FREE,
    Feature.DOSAGE_INFO:           FeatureTier.FREE,
    Feature.RX_REQUIRED:           FeatureTier.FREE,
    # ── Salon (FREE) ──────────────────────────────────────────────────────────
    Feature.ONLINE_BOOKING:        FeatureTier.FREE,
    Feature.STAFF_SCHEDULE:        FeatureTier.FREE,
    Feature.BEFORE_AFTER_PHOTO:    FeatureTier.FREE,
    Feature.SALON_CLIENT_HISTORY:  FeatureTier.FREE,
    Feature.COMMISSION_REPORT:     FeatureTier.FREE,
    # ── Chakana firma (FREE) — o'rtacha do'kon asosiy ehtiyoji ─────────────────
    Feature.SUPPLIER_CARD:         FeatureTier.FREE,
    Feature.PURCHASE_RECEIPT:      FeatureTier.FREE,
    Feature.SUPPLIER_DEBT:         FeatureTier.FREE,
    Feature.SUPPLIER_RETURN:       FeatureTier.FREE,
    # ── PRO flaglar ───────────────────────────────────────────────────────────
    Feature.WHOLESALE_PRICING:    FeatureTier.PRO,
    Feature.DEPARTMENTS:          FeatureTier.PRO,
    Feature.SUPPLIER_ACCOUNTING:  FeatureTier.PRO,
    Feature.WRITE_OFF:            FeatureTier.PRO,
    Feature.GOODS_REGRADE:        FeatureTier.PRO,
    Feature.MARKUP_POLICY:        FeatureTier.PRO,
    Feature.BONUS_CARD:           FeatureTier.PRO,
    Feature.ABC_ANALYSIS:         FeatureTier.PRO,
    Feature.AUTO_REORDER:         FeatureTier.PRO,
    Feature.TURNOVER_ANALYSIS:    FeatureTier.PRO,
    Feature.PEAK_HOURS:           FeatureTier.PRO,
    Feature.LOSS_REPORT:          FeatureTier.PRO,
    Feature.CUSTOMER_RETURN_EXT:  FeatureTier.PRO,
    Feature.INTERNAL_TRANSFER:    FeatureTier.PRO,
    Feature.MARKIROVKA:           FeatureTier.PRO,
}


def get_feature_tier(feature: Feature | str) -> FeatureTier:
    """Flag darajasini qaytaradi (FREE yoki PRO)."""
    if isinstance(feature, str):
        feature = Feature(feature)
    return FEATURE_TIERS.get(feature, FeatureTier.PRO)  # noma'lum → PRO (xavfsiz)


def is_pro_feature(feature: Feature | str) -> bool:
    """Flag PRO darajasidami?"""
    return get_feature_tier(feature) == FeatureTier.PRO


def get_free_features() -> FrozenSet[Feature]:
    """Barcha FREE tier flaglarni qaytaradi."""
    return frozenset(f for f, t in FEATURE_TIERS.items() if t == FeatureTier.FREE)


def get_pro_features() -> FrozenSet[Feature]:
    """Barcha PRO tier flaglarni qaytaradi."""
    return frozenset(f for f, t in FEATURE_TIERS.items() if t == FeatureTier.PRO)


def get_default_features(business_type: BusinessType | str) -> frozenset[Feature]:
    """Berilgan biznes turi uchun standart (FREE) funksiyalar to'plamini qaytaradi"""
    if not isinstance(business_type, BusinessType):
        business_type = BusinessType(business_type)
    return BUSINESS_FEATURE_MATRIX.get(business_type, frozenset())


def get_business_pro_features(business_type: BusinessType | str) -> frozenset[Feature]:
    """Shu biznes turiga tegishli PRO funksiyalar (PRO tarifda ochiladi)."""
    if not isinstance(business_type, BusinessType):
        business_type = BusinessType(business_type)
    return BUSINESS_PRO_MATRIX.get(business_type, frozenset())


def get_all_business_features(business_type: BusinessType | str) -> frozenset[Feature]:
    """Shu biznes turiga tegishli BARCHA funksiya (FREE default + PRO).
    "in_business" tekshiruvi va begonani yashirish uchun yagona manba."""
    return get_default_features(business_type) | get_business_pro_features(business_type)


def is_pro_plan(subscription_plan: str | None) -> bool:
    """Tarif PRO darajasidami? free'dan boshqasi (pro/enterprise) — PRO."""
    return bool(subscription_plan) and str(subscription_plan).strip().lower() != "free"


def resolve_enabled_features(
    business_type: BusinessType | str,
    enabled_overrides: Iterable[str] | None = None,
    disabled_overrides: Iterable[str] | None = None,
    subscription_plan: str | None = None,
) -> set[str]:
    """
    Kafe uchun yakuniy yoqilgan funksiyalar ro'yxatini hisoblaydi:
    standart (FREE) to'plam + (PRO tarif bo'lsa) SHU biznes turining PRO flaglari
    + qo'lda yoqilganlar - qo'lda o'chirilganlar.

    O'ZGARISH 3: ilgari PRO tarif = GLOBAL BARCHA PRO flag ochilardi — shu sababli
    restoran ham magazin PRO funksiyalarini (markirovka, optom...) olardi. Endi
    PRO tarif = FAQAT shu biznes turining PRO funksiyalari (BUSINESS_PRO_MATRIX).
    Begona biznes turiga oid PRO funksiya umuman ochilmaydi.

    Yangi PRO tenant → o'z biznesining hamma PRO funksiyasi BOSHIDA YONIQ; tenant
    keyin kerakmasini disabled_overrides orqali o'chiradi (O'ZGARISH 2 toggle).

    enabled_overrides — super-admin ataylab bergan istisno (monetizatsiya hatch),
    saqlanadi. Funksiyalar hech qachon butunlay o'chirilmaydi — bu funksiya faqat
    "qaysi funksiyalar UI'da ko'rinadi" degan savolga javob beradi.
    """
    features = {f.value for f in get_default_features(business_type)}

    # PRO tarif → SHU biznes turining PRO flaglari avtomatik yoqiladi (global emas).
    if is_pro_plan(subscription_plan):
        features |= {f.value for f in get_business_pro_features(business_type)}

    if enabled_overrides:
        features |= {Feature(f).value for f in enabled_overrides}

    if disabled_overrides:
        features -= {Feature(f).value for f in disabled_overrides}

    return features


def is_feature_enabled(
    business_type: BusinessType | str,
    feature: Feature | str,
    enabled_overrides: Iterable[str] | None = None,
    disabled_overrides: Iterable[str] | None = None,
    subscription_plan: str | None = None,
) -> bool:
    """Berilgan funksiya shu kafe uchun yoqilganmi — yagona tekshiruv nuqtasi"""
    feature_value = feature.value if isinstance(feature, Feature) else feature
    return feature_value in resolve_enabled_features(
        business_type, enabled_overrides, disabled_overrides, subscription_plan
    )
