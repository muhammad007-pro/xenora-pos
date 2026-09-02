"""Telegram alert — Sentry jiddiy xatolari + kelajakdagi ichki ogohlantirishlar UCHUN.

scripts/monitor.py (cron) bilan BIR XIL .env kalitlari (TELEGRAM_BOT_TOKEN, ALERT_CHAT_ID)
va bir xil sendMessage mexanizmi — dublikat mantiq yo'q, faqat ikki jarayon (app vs cron).
Sozlanmasa JIM (False qaytaradi). Yuborish FON oqumida — so'rov/before_send bloklanmaydi.
Spam himoyasi: bir `key` ALERT_SUPPRESS_MINUTES daqiqada 1 marta (jarayon ichi; single-worker'ga yetarli).
"""
import time
import threading
import logging
import urllib.request
import urllib.parse

from config import settings

logger = logging.getLogger(__name__)

_last_sent: dict[str, float] = {}
_lock = threading.Lock()


def _post_sync(token: str, chat: str, text: str, timeout: int = 10) -> bool:
    """Telegram'ga SINXRON yuboradi. Muvaffaqiyatni qaytaradi, HECH QACHON otmaydi.

    `_post` (fon oqumi) o'rniga alohida funksiya kerak edi: obuna
    ogohlantirishlari yuborilgani BAZAGA yoziladi, ya'ni "yuborildi" deb
    belgilashdan OLDIN haqiqatan yetib borganini bilish shart. Fon oqumida
    natija yo'qoladi va Telegram o'chgan bo'lsa xabar "yuborilgan" deb
    belgilanib, MIJOZ HECH NARSA OLMASDAN qolardi.
    Bu funksiya scheduler vazifasidan chaqiriladi — u yerda bloklash zararsiz
    (so'rov yo'lida emas). Xato bo'lsa False -> yozuv yozilmaydi -> keyingi
    soatlik yugurishda qayta uriniladi.
    """
    try:
        data = urllib.parse.urlencode(
            {"chat_id": chat, "text": text, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except Exception as e:
        # Telegram ishlamasligi CHAQIRUVCHINI to'xtatmasin — faqat log.
        logger.warning("Telegram (sinxron) yuborilmadi: %s", e)
        return False


def send_to_chat(text: str, chat_id: str, timeout: int = 10) -> bool:
    """Aniq bir chat'ga sinxron yuborish (obuna ogohlantirishlari uchun).

    Spam himoyasi YO'Q — takrorni chaqiruvchi bazada nazorat qiladi
    (`subscription_alerts` jadvali), ya'ni restart ham unutmaydi.
    Sozlanmagan yoki chat bo'sh bo'lsa -> False (jim).
    """
    token = settings.TELEGRAM_BOT_TOKEN
    if not token or not chat_id:
        return False
    return _post_sync(token, str(chat_id), text, timeout)


def _post(token: str, chat: str, text: str) -> None:
    try:
        data = urllib.parse.urlencode(
            {"chat_id": chat, "text": text, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data)
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        logger.warning("Telegram alert yuborilmadi: %s", e)


def send_alert(text: str, key: str = "") -> bool:
    """Alertni Telegram'ga (fon oqumda). key — spam himoya guruhi.
    Qaytadi: True (navbatga qo'yildi) / False (sozlanmagan yoki suppress)."""
    token = settings.TELEGRAM_BOT_TOKEN
    chat  = settings.ALERT_CHAT_ID
    if not token or not chat:
        return False
    now = time.time()
    k = key or text[:60]
    with _lock:
        if now - _last_sent.get(k, 0) < settings.ALERT_SUPPRESS_MINUTES * 60:
            return False
        _last_sent[k] = now
    threading.Thread(target=_post, args=(token, chat, text), daemon=True).start()
    return True
