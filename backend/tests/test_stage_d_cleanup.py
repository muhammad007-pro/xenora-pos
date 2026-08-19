"""BOSQICH D — tozalash testlari (mijoz vozvrati yagona yo'l bo'lib qoldi).

IKKI TOZALASH:

1) `routers/customer_returns_ext.py` (`/returns-ext`) O'CHIRILDI. U alohida
   jadval EMAS — o'sha `returns` jadvaliga `REXT...` raqami bilan yozardi, ammo
   BOSQICH A qo'shgan PUL HARAKATINI qilmasdi. Ya'ni ikkinchi, jimgina noto'g'ri
   yo'l edi; UI unga hech qachon ulanmagan. Jonli bazada `REXT%` yozuv 0 ta.

2) `exchange` (almashtirish) refund_method sifatida RAD ETILADI. `_refund_money`
   faqat cash/card/credit ni biladi — `exchange` kelsa hech narsa qilmasdi:
   pul qaytmasdi, qarz kamaymasdi, lekin vozvrat "tasdiqlangan" bo'lib turardi.

NOZIK JOY (jonli bazada topildi): `lux-parfum` (tenant 5) `enabled_features`
ichida `customer_return_ext` qolgan. Flag enum'dan olib tashlangach eski
`Feature(f)` chaqirig'i ValueError berardi va O'SHA DO'KONNING BUTUN funksiya
hisoblashi yiqilardi. Endi noma'lum kod e'tiborsiz qoldiriladi — shu sababli
baza tozalash (migratsiya) SHART EMAS.

Ishga tushirish:  cd backend && py -m pytest tests/test_stage_d_cleanup.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from pydantic import ValidationError

from core.feature_flags import Feature, resolve_enabled_features
from schemas import REFUND_METHODS, ReturnCreate, ReturnItemCreate


def _payload(method):
    return ReturnCreate(
        order_id=1, customer_id=1, reason="dislike", refund_method=method,
        items=[ReturnItemCreate(product_id=1, quantity=1, unit_price=45000)],
    )


# ── (b) exchange — kirishda RAD ETILADI ──────────────────────────────────────
def test_exchange_rad_etiladi():
    with pytest.raises(ValidationError) as e:
        _payload("exchange")
    assert "Almashtirish" in str(e.value)


def test_notogri_usul_rad_etiladi():
    with pytest.raises(ValidationError):
        _payload("bank_transfer")


@pytest.mark.parametrize("method", ["cash", "card", "credit"])
def test_ruxsat_etilgan_usullar_otadi(method):
    assert _payload(method).refund_method == method


def test_usul_normallashadi():
    """Katta harf / ortiqcha bo'shliq kelsa ham bitta ko'rinishga keltiriladi —
    aks holda `_refund_money` dagi `method in ("cash","card")` tekshiruvi
    JIMGINA o'tmay qolardi (pul qaytmasdi)."""
    assert _payload("  CASH ").refund_method == "cash"


def test_exchange_royxatda_yoq():
    assert "exchange" not in REFUND_METHODS


# ── (a) customer_return_ext — kod ham, flag ham yo'q ─────────────────────────
def test_returns_ext_moduli_yoq():
    with pytest.raises(ModuleNotFoundError):
        __import__("routers.customer_returns_ext")


def test_customer_return_ext_flagi_yoq():
    assert "customer_return_ext" not in {f.value for f in Feature}


def test_eskirgan_flag_tenantni_BUZMAYDI():
    """GOLDEN: bazada qolgan eskirgan kod butun hisoblashni yiqitmasin."""
    feats = resolve_enabled_features(
        "store",
        enabled_overrides=["customer_return_ext", "markirovka"],
        disabled_overrides=["customer_return_ext"],
        subscription_plan="pro",
    )
    assert "markirovka" in feats                 # yonidagi haqiqiy flag ishladi
    assert "customer_return_ext" not in feats    # eskirgan kod chiqmaydi
    assert "returns" in feats                    # standart to'plam buzilmadi
