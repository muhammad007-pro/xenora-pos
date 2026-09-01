"""UCH TARIF — Boshlang'ich (free) / Standart (standart) / Pro (pro). 2026-08-27.

PRINSIP:  Standart = kundalik ish.  Pro = tahlil va avtomatlashtirish.

ENG MUHIM KAFOLAT (shu fayldagi asosiy test):
    Mavjud PRO va FREE mijozlarning funksiyalari AYNAN o'zgarmasligi shart.
    Buni ta'minlovchi dizayn: STANDART to'plami PRO ning KICHIK TO'PLAMI
    (subset) sifatida HISOBLANADI, qo'lda yozilmaydi:
        pro   = free | standart | pro     va   standart ⊆ pro
        =>      free | pro                 (o'zgarishdan OLDINGI natija)

Ilgari `is_pro_plan()` IKKILIK edi (`plan != "free"`) — o'sha qator tegilmasa
`standart` avtomatik to'liq PRO bo'lib qolardi, ya'ni o'rta tarif bekorga.

Ishga tushirish:
    cd backend && py -m pytest tests/test_three_tier_plans.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.feature_flags import (
    BUSINESS_PRO_MATRIX, BUSINESS_STANDART_MATRIX, BusinessType,
    get_default_features, get_business_standart_features, get_business_pro_features,
    resolve_enabled_features, plan_rank, is_pro_plan, is_standart_plan,
    RANK_STANDART, RANK_PRO,
)
from core.subscription import (
    PLAN_LIMITS, VALID_PLANS, PUBLIC_PLANS, PLAN_PRICES_UZS, PLAN_DISPLAY_NAMES,
    get_plan_limits, is_within_user_limit, is_within_order_limit,
    is_within_branch_limit, UNLIMITED,
)

ALL_TYPES = list(BUSINESS_PRO_MATRIX)


def _n(bt, plan):
    return len(resolve_enabled_features(bt, None, None, plan))


# ══════════════════════════════════════════════════════════════════════════════
# 1) ASOSIY KAFOLAT — mavjud mijozlar o'zgarmaydi
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("bt", ALL_TYPES, ids=lambda b: b.value)
def test_standart_pro_ning_kichik_toplami(bt):
    """standart ⊆ pro — PRO mijoz natijasi o'zgarmasligining MATEMATIK asosi.

    Buzilsa: PRO tarifdagi jonli do'kon (eco aroma, FAZZA PERFUM) funksiyalari
    jimgina o'zgarib ketardi.
    """
    std = BUSINESS_STANDART_MATRIX[bt]
    pro = BUSINESS_PRO_MATRIX[bt]
    assert std <= pro, f"{bt.value}: standart PRO'dan chiqib ketdi: {std - pro}"


@pytest.mark.parametrize("bt", ALL_TYPES, ids=lambda b: b.value)
def test_pro_natijasi_free_plus_pro_ga_teng(bt):
    """PRO uchun natija = free | pro (standart qatlami hech narsa qo'shmaydi)."""
    kutilgan = ({f.value for f in get_default_features(bt)} |
                {f.value for f in get_business_pro_features(bt)})
    assert resolve_enabled_features(bt, None, None, "pro") == kutilgan


@pytest.mark.parametrize("bt", ALL_TYPES, ids=lambda b: b.value)
def test_free_natijasi_faqat_default(bt):
    """Boshlang'ich tarif hech qanday PRO/STANDART flag olmaydi."""
    assert resolve_enabled_features(bt, None, None, "free") == \
        {f.value for f in get_default_features(bt)}


# ══════════════════════════════════════════════════════════════════════════════
# 2) UCH DARAJA HAQIQATAN FARQ QILADI
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("bt", ALL_TYPES, ids=lambda b: b.value)
def test_funksiya_soni_qatiy_osadi(bt):
    """free < standart < pro — HAR biznes turida (talab)."""
    f, s, p = _n(bt, "free"), _n(bt, "standart"), _n(bt, "pro")
    assert f < s, f"{bt.value}: standart Boshlang'ichdan farq qilmaydi ({f} vs {s})"
    assert s < p, f"{bt.value}: pro Standartdan farq qilmaydi ({s} vs {p})"


def test_standart_pro_emas():
    """`standart` PRO darajasi EMAS — uch tarifning butun mohiyati."""
    assert is_pro_plan("standart") is False
    assert is_standart_plan("standart") is True
    assert is_pro_plan("pro") is True
    assert is_standart_plan("free") is False


def test_daraja_tartibi():
    assert plan_rank("free") == 0
    assert plan_rank("standart") == RANK_STANDART == 1
    assert plan_rank("pro") == RANK_PRO == 2
    assert plan_rank("enterprise") > plan_rank("pro")
    # eski nomlar
    assert plan_rank("basic") == plan_rank("free")
    assert plan_rank("premium") == plan_rank("pro")


def test_store_taqsimoti_kelishilganidek():
    """store uchun aniq kelishilgan bo'linish (buyurtmachi tasdiqlagan)."""
    std = {f.value for f in get_business_standart_features(BusinessType.STORE)}
    pro_only = {f.value for f in get_business_pro_features(BusinessType.STORE)} - std
    assert std == {
        "supplier_accounting", "wholesale_pricing", "internal_transfer",
        "goods_regrade", "write_off", "loss_report",
    }
    assert pro_only == {
        "abc_analysis", "turnover_analysis", "peak_hours",
        "auto_reorder", "markirovka", "markup_policy", "departments",
    }


# ══════════════════════════════════════════════════════════════════════════════
# 3) NOMA'LUM TARIF — jimgina tushmasin
# ══════════════════════════════════════════════════════════════════════════════

def test_nomalum_tarif_ogohlantiradi_va_eng_pastga_tushadi(caplog):
    """'standard' (imlo xatosi) — eng past darajaga tushadi, LEKIN log yozadi.

    Ilgari bu JIM edi: mijoz haqiqiy tarifi bo'la turib 3 user / 100 buyurtma
    limitiga tushib qolardi va hech kim sezmasdi.
    """
    import logging
    with caplog.at_level(logging.WARNING):
        n = len(resolve_enabled_features("store", None, None, "standard"))
        lim = get_plan_limits("standard")
    assert n == len(resolve_enabled_features("store", None, None, "free"))
    assert lim == PLAN_LIMITS["free"]
    matn = caplog.text.lower()
    assert "standard" in matn and "tarif" in matn, f"OGOHLANTIRISH YO'Q: {caplog.text!r}"


def test_bosh_tarif_yiqilmaydi():
    assert plan_rank(None) == 0
    assert plan_rank("") == 0
    assert get_plan_limits(None) == PLAN_LIMITS["free"]
    assert len(resolve_enabled_features("store", None, None, None)) > 0


# ══════════════════════════════════════════════════════════════════════════════
# 4) LIMITLAR
# ══════════════════════════════════════════════════════════════════════════════

def test_standart_limitlari():
    l = get_plan_limits("standart")
    assert (l.max_users, l.max_branches, l.max_orders_month) == (10, 2, UNLIMITED)


def test_limitlar_tarif_boyicha_osadi():
    f, s, p = get_plan_limits("free"), get_plan_limits("standart"), get_plan_limits("pro")
    assert f.max_users < s.max_users < p.max_users
    assert f.max_branches < s.max_branches < p.max_branches
    assert f.max_orders_month != UNLIMITED
    assert s.max_orders_month == UNLIMITED and p.max_orders_month == UNLIMITED


def test_filial_limiti_tekshiriladi():
    """2026-08-27 gacha max_branches HECH QAYERDA tekshirilmasdi."""
    assert is_within_branch_limit(0, "free")  is True    # 0 -> 1 mumkin
    assert is_within_branch_limit(1, "free")  is False   # 1 -> 2 YO'Q
    assert is_within_branch_limit(1, "standart") is True
    assert is_within_branch_limit(2, "standart") is False
    assert is_within_branch_limit(4, "pro")   is True
    assert is_within_branch_limit(5, "pro")   is False
    assert is_within_branch_limit(999, "enterprise") is True   # cheksiz


def test_user_va_buyurtma_limiti():
    assert is_within_user_limit(9, "standart") is True
    assert is_within_user_limit(10, "standart") is False
    assert is_within_order_limit(99, "free") is True
    assert is_within_order_limit(100, "free") is False
    assert is_within_order_limit(10**6, "standart") is True   # cheksiz


# ══════════════════════════════════════════════════════════════════════════════
# 5) NARX — YAGONA MANBA
# ══════════════════════════════════════════════════════════════════════════════

def test_narx_yagona_manba_va_osadi():
    assert PLAN_PRICES_UZS["free"]     == 249_000
    assert PLAN_PRICES_UZS["standart"] == 449_000
    assert PLAN_PRICES_UZS["pro"]      == 749_000
    assert PLAN_PRICES_UZS["free"] < PLAN_PRICES_UZS["standart"] < PLAN_PRICES_UZS["pro"]


def test_super_admin_alohida_narx_jadvali_yoq():
    """Ilgari routers/super_admin.py da ZID USD jadval bor edi (free=$10)."""
    from routers.super_admin import PLAN_PRICES
    assert PLAN_PRICES is PLAN_PRICES_UZS, "super_admin yana o'z narx jadvalini yaratdi"


def test_har_public_tarifda_nom_narx_limit_bor():
    for p in PUBLIC_PLANS:
        assert p in VALID_PLANS
        assert p in PLAN_LIMITS
        assert p in PLAN_PRICES_UZS
        assert PLAN_DISPLAY_NAMES.get(p)


def test_public_plans_enterprise_ni_kormaydi():
    assert "enterprise" not in PUBLIC_PLANS
    assert "enterprise" in VALID_PLANS      # API hali qabul qiladi (ataylab, keyin hal qilinadi)


# ══════════════════════════════════════════════════════════════════════════════
# 6) OVERRIDE'LAR TARIF USTIDAN ISHLASHDA DAVOM ETADI
# ══════════════════════════════════════════════════════════════════════════════

def test_enabled_override_standartda_ham_ishlaydi():
    """Super-admin istisnosi (masalan lux-parfum'dagi bonus_card)."""
    r = resolve_enabled_features("store", ["bonus_card"], None, "standart")
    assert "bonus_card" in r


def test_disabled_override_standart_flagini_ochiradi():
    std_flag = "write_off"   # store'da STANDART
    yoq = resolve_enabled_features("store", None, [std_flag], "standart")
    bor = resolve_enabled_features("store", None, None, "standart")
    assert std_flag in bor and std_flag not in yoq


def test_olik_flag_yiqitmaydi():
    """Bazada qolgan eskirgan kod butun hisoblashni buzmasin."""
    r = resolve_enabled_features("store", ["customer_return_ext"], None, "standart")
    assert "customer_return_ext" not in r
    assert len(r) == len(resolve_enabled_features("store", None, None, "standart"))
