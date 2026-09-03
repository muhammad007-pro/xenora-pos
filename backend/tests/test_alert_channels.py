"""ALERT KANALLARI — biznes va texnika ARALASHMASLIGI.

MUAMMO: `core/alert.send_alert` `ALERT_CHAT_ID` ga qattiq bog'langan edi va
uning yagona chaqiruvchisi Sentry (`core/observability._maybe_alert`). Ya'ni
har 5xx uchun "🔴 XENORA xato" xabari obuna ogohlantirishlari keladigan
chatga tushardi va egasi o'qishi kerak bo'lgan "obuna tugayapti" xabarini
ko'mib qo'yardi.

ENDI:
  ALERT_CHAT_ID        — BIZNES (obuna ogohlantirishlari)
  SENTRY_ALERT_CHAT_ID — TEXNIKA (5xx); BO'SH bo'lsa Telegram xabari UMUMAN
                         yuborilmaydi

⚠️ Tarmoqqa chiqilmaydi: yuborish qatlami har testda to'siladi.

Ishga tushirish:  cd backend && py -m pytest tests/test_alert_channels.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import core.alert as alert_mod
import core.observability as obs
from config import settings

BIZNES = "111111"
TEXNIK = "999999"


@pytest.fixture()
def yuborilgan(monkeypatch):
    """`send_alert` fon oqumini to'sib, (chat, matn) juftini yig'adi."""
    box = []
    monkeypatch.setattr(alert_mod, "_post",
                        lambda token, chat, text: box.append((chat, text)))
    monkeypatch.setattr(settings, "SENTRY_BOT_TOKEN", "")

    # Fon oqumi test ichida yugurmasin — darhol chaqiramiz.
    class _Thread:
        def __init__(self, target=None, args=(), daemon=None):
            self._t, self._a = target, args

        def start(self):
            self._t(*self._a)

    monkeypatch.setattr(alert_mod.threading, "Thread", _Thread)
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "test-token")
    alert_mod._last_sent.clear()          # spam himoyasi testlar orasida qolmasin
    return box


def _sentry_event():
    return {
        "level": "error",
        "tags": {"tenant_id": 26, "rid": "abc"},
        "request": {"method": "GET", "url": "/api/v1/orders"},
        "exception": {"values": [{"type": "ValueError"}]},
    }


# ══════════════════════════════════════════════════════════════════════════
#  send_alert — chat ANIQ berilishi shart
# ══════════════════════════════════════════════════════════════════════════

def test_chat_berilmasa_YUBORILMAYDI(yuborilgan):
    """Standart qiymat ATAYLAB ALERT_CHAT_ID emas — tasodifan biznes
    kanaliga yozib yuborish yo'li yopiq."""
    assert alert_mod.send_alert("salom") is False
    assert yuborilgan == []


def test_chat_berilsa_YUBORILADI(yuborilgan):
    assert alert_mod.send_alert("salom", chat_id=TEXNIK) is True
    assert yuborilgan == [(TEXNIK, "salom")]


def test_token_yoq_bolsa_jim(yuborilgan, monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "")
    assert alert_mod.send_alert("salom", chat_id=TEXNIK) is False
    assert yuborilgan == []


# ══════════════════════════════════════════════════════════════════════════
#  Sentry — o'z kanaliga, biznes kanaliga EMAS
# ══════════════════════════════════════════════════════════════════════════

def test_sentry_TEXNIK_kanalga_ketadi(yuborilgan, monkeypatch):
    monkeypatch.setattr(settings, "ALERT_CHAT_ID", BIZNES)
    monkeypatch.setattr(settings, "SENTRY_ALERT_CHAT_ID", TEXNIK)

    obs._maybe_alert(_sentry_event(), None)

    assert len(yuborilgan) == 1
    chat, matn = yuborilgan[0]
    assert chat == TEXNIK, "Sentry xatosi BIZNES kanaliga tushdi!"
    assert chat != BIZNES
    assert "XENORA xato" in matn


def test_sentry_kanali_BOSH_bolsa_UMUMAN_yuborilmaydi(yuborilgan, monkeypatch):
    """Asosiy talab: bo'sh = o'chiq. Biznes kanaliga ham tushmasin."""
    monkeypatch.setattr(settings, "ALERT_CHAT_ID", BIZNES)
    monkeypatch.setattr(settings, "SENTRY_ALERT_CHAT_ID", "")

    obs._maybe_alert(_sentry_event(), None)

    assert yuborilgan == []


def test_sentry_4xx_yubormaydi(yuborilgan, monkeypatch):
    """Eski xulq saqlangan: foydalanuvchi xatosi alert emas."""
    monkeypatch.setattr(settings, "SENTRY_ALERT_CHAT_ID", TEXNIK)

    class Ex(Exception):
        status_code = 404

    obs._maybe_alert(_sentry_event(), {"exc_info": (Ex, Ex(), None)})
    assert yuborilgan == []


def test_obuna_kanali_sentrydan_MUSTAQIL(yuborilgan, monkeypatch):
    """Obuna yo'li `send_to_chat` ishlatadi — SENTRY_ALERT_CHAT_ID o'chiq
    bo'lsa ham ishlashda davom etadi."""
    monkeypatch.setattr(settings, "SENTRY_ALERT_CHAT_ID", "")
    monkeypatch.setattr(alert_mod, "_post_sync",
                        lambda token, chat, text, timeout=10: box.append((chat, text)) or True)
    box = []
    assert alert_mod.send_to_chat("obuna xabari", BIZNES) is True
    assert box == [(BIZNES, "obuna xabari")]


# ══════════════════════════════════════════════════════════════════════════
#  Sentry uchun ALOHIDA BOT (token)
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def tokenlar(monkeypatch):
    """Qaysi TOKEN bilan yuborilganini yig'adi."""
    box = []
    monkeypatch.setattr(alert_mod, "_post",
                        lambda token, chat, text: box.append((token, chat)))

    class _Thread:
        def __init__(self, target=None, args=(), daemon=None):
            self._t, self._a = target, args

        def start(self):
            self._t(*self._a)

    monkeypatch.setattr(alert_mod.threading, "Thread", _Thread)
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "ASOSIY")
    monkeypatch.setattr(settings, "SENTRY_ALERT_CHAT_ID", TEXNIK)
    alert_mod._last_sent.clear()
    return box


def test_sentry_OZ_boti_bilan_yuboriladi(tokenlar, monkeypatch):
    monkeypatch.setattr(settings, "SENTRY_BOT_TOKEN", "TEXNIK-BOT")
    obs._maybe_alert(_sentry_event(), None)
    assert tokenlar == [("TEXNIK-BOT", TEXNIK)]


def test_sentry_boti_BOSH_bolsa_asosiy_token(tokenlar, monkeypatch):
    """Orqaga moslik: kalit qo'shilmagan o'rnatmalar avvalgidek ishlaydi."""
    monkeypatch.setattr(settings, "SENTRY_BOT_TOKEN", "")
    obs._maybe_alert(_sentry_event(), None)
    assert tokenlar == [("ASOSIY", TEXNIK)]


def test_obuna_yoli_ASOSIY_botda_qoladi(monkeypatch):
    """`send_to_chat` SENTRY_BOT_TOKEN ni umuman bilmaydi."""
    box = []
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "ASOSIY")
    monkeypatch.setattr(settings, "SENTRY_BOT_TOKEN", "TEXNIK-BOT")
    monkeypatch.setattr(alert_mod, "_post_sync",
                        lambda token, chat, text, timeout=10: box.append((token, chat)) or True)
    assert alert_mod.send_to_chat("obuna", BIZNES) is True
    assert box == [("ASOSIY", BIZNES)]
