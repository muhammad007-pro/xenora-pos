"""TO'LOV USULLARI — yoqilgan tenderlar ro'yxati.

MUAMMO (2026-10-06 aniqlandi):

1. Click/Payme tugmalari POS'da HAR DOIM ko'rinardi, lekin shlyuz
   integratsiyasi YO'Q — `services/payment_service.py`
   `_process_online_payment` TODO stub: `status="pending"` yozuv yaratadi va
   hech qanday API'ga chiqmaydi. `confirm_payment()` mavjud, lekin
   CHAQIRUVCHISI yo'q; webhook/callback marshruti ham yo'q.
   PRODDA: 24 ta pending CLICK, HAMMASI (24/24) BEKOR QILINGAN buyurtmada —
   kassir bosadi, to'lov o'tmaydi, sotuv bekor bo'ladi.

2. Sozlamalar sahifasida toggle'lar bor va saqlanardi, lekin POS ularni
   UMUMAN O'QIMASDI → sozlama hech narsaga ta'sir qilmasdi.
   (PRODDA `tenant_settings` da `payment` yozuvi 0 ta — hech kim saqlamagan.)

3. ⛔ `transfer` sozlamalar UI'sida bor edi, `PaymentMethod` enum'ida YO'Q.
   POS ro'yxatni o'qiy boshlagach kassir uni tanlab, server
   `invalid input value for enum` bilan 500 berib BUTUN sotuvni rollback
   qilardi (v1.9.1 da `credit` bilan aynan shunday bo'lgan).

Nimani qulflaydi:
  • standart = faqat `cash`+`card` (Click/Payme O'CHIQ)
  • sozlama bilan yoqish ishlaydi
  • `cash` HECH QACHON o'chmaydi (aks holda POS'da tender qolmaydi)
  • enum'da yo'q qiymat (`transfer`) ro'yxatdan TASHLANADI
  • POS endpointi MAXFIY KALITLARNI qaytarmaydi
  • ⚠️ enum TEGILMAGAN — mavjud 24 CLICK + 35 CREDIT yozuvi o'qilishi shart

Ishga tushirish:  cd backend && py -m pytest tests/test_payment_methods.py -v
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Cafe, PaymentMethod, PaymentStatus, User
from core.tenant_config import set_tenant_config

import routers.settings as st_router

TID = 1


class _User:
    is_superuser = True
    tenant_id = TID
    id = 5
    role = None
    _active_branch_id = None


@pytest.fixture()
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    s = sessionmaker(bind=eng)()
    s.add(Cafe(id=TID, name="XOZMAG", code="XOZMAG"))
    s.add(User(id=5, tenant_id=TID, full_name="Admin",
               phone="+998900000005", hashed_password="x"))
    s.commit()
    yield s
    s.close()


def _usullar(db):
    out = asyncio.run(st_router.get_enabled_payment_methods(
        db=db, current_user=_User()))
    return out["methods"]


# ═══════════════════════════════════════════════════════════════════════════
# 1. STANDART — Click/Payme O'CHIQ
# ═══════════════════════════════════════════════════════════════════════════
def test_standart_faqat_naqd_va_karta(db):
    assert _usullar(db) == ["cash", "card"]


def test_standart_click_payme_YOQ(db):
    m = _usullar(db)
    assert "click" not in m
    assert "payme" not in m


def test_sozlama_yozuvi_yoq_bolsa_ham_ishlaydi(db):
    """PRODDA aynan shunday: `tenant_settings` da `payment` yozuvi 0 ta."""
    assert _usullar(db) == ["cash", "card"]


# ═══════════════════════════════════════════════════════════════════════════
# 2. SOZLAMA BILAN YOQISH (shlyuz ulanganda)
# ═══════════════════════════════════════════════════════════════════════════
def test_click_sozlama_bilan_yoqiladi(db):
    set_tenant_config(db, TID, "payment", {"methods": ["cash", "card", "click"]})
    assert _usullar(db) == ["cash", "card", "click"]


def test_payme_ham_yoqiladi(db):
    set_tenant_config(db, TID, "payment", {"methods": ["cash", "card", "payme"]})
    assert _usullar(db) == ["cash", "card", "payme"]


def test_karta_ochirilishi_mumkin(db):
    """Faqat naqd ishlaydigan do'kon — kartani o'chirsa bo'ladi."""
    set_tenant_config(db, TID, "payment", {"methods": ["cash"]})
    assert _usullar(db) == ["cash"]


def test_tartib_barqaror(db):
    """Naqd/karta HAR DOIM boshida — kassir tugmalari joyini o'zgartirmasin."""
    set_tenant_config(db, TID, "payment", {"methods": ["payme", "click", "card", "cash"]})
    assert _usullar(db) == ["cash", "card", "payme", "click"]


# ═══════════════════════════════════════════════════════════════════════════
# 3. ⚠️ XAVFSIZLIK CHEGARALARI
# ═══════════════════════════════════════════════════════════════════════════
def test_cash_HAR_DOIM_qoladi(db):
    """Hammasi o'chirilsa ham naqd qoladi — aks holda POS'da tender yo'q."""
    set_tenant_config(db, TID, "payment", {"methods": []})
    assert _usullar(db) == ["cash"]
    set_tenant_config(db, TID, "payment", {"methods": ["payme"]})
    assert _usullar(db)[0] == "cash"


def test_enumda_YOQ_qiymat_tashlanadi(db):
    """⛔ `transfer` — enum'da yo'q. Ro'yxatda qolsa kassir uni tanlab
    server 500 berardi va BUTUN sotuv rollback bo'lardi."""
    set_tenant_config(db, TID, "payment",
                      {"methods": ["cash", "card", "transfer"]})
    m = _usullar(db)
    assert "transfer" not in m
    assert m == ["cash", "card"]


def test_notanish_qiymatlar_tashlanadi(db):
    set_tenant_config(db, TID, "payment",
                      {"methods": ["cash", "bitcoin", 42, None, "card"]})
    assert _usullar(db) == ["cash", "card"]


def test_buzuq_sozlama_standartga_qaytadi(db):
    for buzuq in ({"methods": "cash,card"}, {"methods": None}, {}, {"methods": 5}):
        set_tenant_config(db, TID, "payment", buzuq)
        assert _usullar(db) == ["cash", "card"], buzuq


def test_credit_va_room_charge_royxatda_YOQ(db):
    """GOLDEN: nasiya/xonaga POS'da BIZNES TURI bo'yicha ko'rinadi, sozlamaga
    bog'liq EMAS. Ro'yxatga tushsa POS mantig'i ikki joydan boshqarilardi."""
    set_tenant_config(db, TID, "payment",
                      {"methods": ["cash", "card", "credit", "room_charge"]})
    m = _usullar(db)
    assert "credit" not in m
    assert "room_charge" not in m


def test_POS_endpointi_MAXFIY_KALIT_qaytarmaydi(db):
    """Kassir o'qiydi — `secret_key`/`key` javobga TUSHMASIN."""
    set_tenant_config(db, TID, "payment", {
        "methods": ["cash", "card", "click"],
        "click": {"merchant_id": "M1", "service_id": "S1", "secret_key": "MAXFIY"},
        "payme": {"merchant_id": "M2", "key": "MAXFIY2"},
    })
    out = asyncio.run(st_router.get_enabled_payment_methods(
        db=db, current_user=_User()))
    assert set(out) == {"methods"}
    matn = str(out)
    assert "MAXFIY" not in matn and "M1" not in matn and "S1" not in matn


def test_admin_endpointi_methods_ni_ANIQ_qaytaradi(db):
    """Sozlamalar UI'si birinchi ochilishda haqiqatni ko'rsin — ilgari
    `if (r.methods)` shartida to'xtab, toggle'lar HTML standartida qolardi."""
    out = asyncio.run(st_router.get_payment_settings(db=db, current_user=_User()))
    assert out["methods"] == ["cash", "card"]


# ═══════════════════════════════════════════════════════════════════════════
# 4. ⚠️ GOLDEN — ENUM TEGILMAGAN (mavjud yozuvlar o'qilishi shart)
# ═══════════════════════════════════════════════════════════════════════════
def test_enum_qiymatlari_saqlangan(db):
    """PRODDA 24 ta CLICK + 35 ta CREDIT pending yozuvi bor — enum'dan
    qiymat olib tashlansa ular O'QILMAY QOLARDI (500)."""
    qiymatlar = {m.value for m in PaymentMethod}
    for kerak in ("cash", "card", "click", "payme", "qr", "credit", "room_charge"):
        assert kerak in qiymatlar, f"{kerak} enum'dan yo'qolgan"


def test_transfer_enumda_hali_ham_YOQ(db):
    """Qaror: `transfer` UI'dan OLIB TASHLANDI, enum'ga QO'SHILMADI.
    Agar kelajakda qo'shilsa — migratsiya bilan va bu test yangilanadi."""
    assert "transfer" not in {m.value for m in PaymentMethod}


def test_payment_status_failed_mavjud(db):
    """Eski pending Click yozuvlarini `failed` deb belgilash uchun kerak
    (tozalash SQL'i shu statusni ishlatadi)."""
    assert PaymentStatus.FAILED.value == "failed"
