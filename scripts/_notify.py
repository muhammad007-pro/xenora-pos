"""Standalone Telegram alert — cron skriptlar (monitor.py, backup.py) UCHUN UMUMIY.

Bir joyda: .env'dan (TELEGRAM_BOT_TOKEN + ALERT_CHAT_ID) o'qib, sendMessage yuboradi.
App'ga bog'liq EMAS (faqat stdlib). Sozlanmasa — (False, "sozlanmagan") qaytaradi (jim).
core/alert.py (app ichi) bilan bir xil kalitlar/mexanizm — dublikat mantiq yo'q.
"""
import os
import urllib.request
import urllib.parse
from pathlib import Path

DEFAULT_ENV = "/opt/xenora/backend/.env"


def read_env(key: str, env_file: str = DEFAULT_ENV):
    try:
        for ln in Path(env_file).read_text(encoding="utf-8", errors="ignore").splitlines():
            ln = ln.strip()
            if ln.startswith(key + "="):
                return ln.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return os.environ.get(key)


def send_telegram(text: str, env_file: str = DEFAULT_ENV):
    """Qaytadi: (ok: bool, sabab: str). Sozlanmasa (False,'unconfigured'); yuborilsa (True,'sent')."""
    token = read_env("TELEGRAM_BOT_TOKEN", env_file)
    chat  = read_env("ALERT_CHAT_ID", env_file)
    if not token or not chat:
        return False, "unconfigured"
    try:
        data = urllib.parse.urlencode(
            {"chat_id": chat, "text": text, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data)
        urllib.request.urlopen(req, timeout=10)
        return True, "sent"
    except Exception as e:
        return False, f"error: {e}"
