"""Sentry (xato kuzatuvi) — yengil, PII-himoyali, ko'p-tenant tag bilan.

- SENTRY_DSN BO'SH → Sentry umuman ishga tushmaydi (dev shovqinsiz, RAM tejaladi).
- traces_sample_rate past (perf o'chiq) — RAM/kvota tejash.
- before_send: maxfiy ma'lumot (token/parol/PIN/telefon/ism) TOZALANADI, rid tag qo'yiladi,
  JIDDIY (500/server) xato Telegram'ga (spam himoya bilan) yuboriladi. 4xx yuborilMAYDI.
- Tag: tenant_id + user_id (ISM/TELEFON EMAS) — panelda "qaysi do'kon" darrov ko'rinadi.
"""
import logging

from config import settings
from core.logger import request_id_var

logger = logging.getLogger(__name__)

# Maxfiy maydon nomlari — request data/extra ichida maskalanadi (kichik harfda solishtiriladi).
_SENSITIVE_KEYS = {
    "password", "old_password", "new_password", "pin", "pin_code",
    "hashed_password", "hashed_pin", "token", "access_token", "refresh_token",
    "authorization", "cookie", "secret", "api_key", "anthropic_api_key",
    "secret_key", "phone", "customer_phone", "owner_phone", "card_number", "reference",
}
_SCRUB = "[tozalandi]"


def _scrub(obj):
    if isinstance(obj, dict):
        return {k: (_SCRUB if str(k).lower() in _SENSITIVE_KEYS else _scrub(v))
                for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_scrub(v) for v in obj]
    return obj


def _before_send(event, hint):
    # ── PII scrub ──
    req = event.get("request")
    if isinstance(req, dict):
        hdrs = req.get("headers")
        if isinstance(hdrs, dict):
            for h in list(hdrs):
                if str(h).lower() in ("authorization", "cookie"):
                    hdrs[h] = _SCRUB
        if "cookies" in req:
            req["cookies"] = _SCRUB
        if isinstance(req.get("data"), (dict, list)):
            req["data"] = _scrub(req["data"])
    if isinstance(event.get("extra"), dict):
        event["extra"] = _scrub(event["extra"])

    # ── rid tag (log bilan bog'lash) ──
    try:
        rid = request_id_var.get("-")
        if rid and rid != "-":
            event.setdefault("tags", {})["rid"] = rid
    except Exception:
        pass

    # ── Jiddiy xato → Telegram ──
    try:
        _maybe_alert(event, hint)
    except Exception:
        pass
    return event


def _maybe_alert(event, hint):
    from core.alert import send_alert
    # TEXNIK kanal. Bo'sh → Telegram xabari UMUMAN yuborilmaydi (Sentry'ning
    # o'zi ishlayveradi). Biznes kanaliga (ALERT_CHAT_ID) tushmaydi: u yerda
    # obuna ogohlantirishlari bor, texnik shovqin ularni ko'mib qo'yardi.
    chat = settings.SENTRY_ALERT_CHAT_ID
    if not chat:
        return
    # 4xx (foydalanuvchi xatosi) → YUBORILMAYDI
    exc_info = (hint or {}).get("exc_info")
    if exc_info:
        status = getattr(exc_info[1], "status_code", None)
        if isinstance(status, int) and 400 <= status < 500:
            return
    if event.get("level") not in ("error", "fatal", None):
        return

    tags = event.get("tags") or {}
    req  = event.get("request") or {}
    vals = ((event.get("exception") or {}).get("values")) or []
    etype = vals[-1].get("type") if vals else "?"
    tid   = tags.get("tenant_id", "?")
    text = (
        f"🔴 <b>XENORA xato</b>\n"
        f"Do'kon (tenant): {tid}\n"
        f"Xato: {etype}\n"
        f"{req.get('method','')} {req.get('url','')}\n"
        f"rid: {tags.get('rid', '-')}"
    )
    # Spam kaliti: tenant + xato turi + endpoint → bir xil xato takrorlansa bloklanadi
    send_alert(text, key=f"{tid}:{etype}:{req.get('url','')}", chat_id=chat)


def init_sentry() -> None:
    """main.py da app'dan OLDIN chaqiriladi. DSN bo'sh → hech narsa qilmaydi."""
    dsn = settings.SENTRY_DSN
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.starlette import StarletteIntegration
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        sentry_sdk.init(
            dsn=dsn,
            environment=settings.SENTRY_ENVIRONMENT or settings.ENVIRONMENT,
            release=settings.VERSION,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            profiles_sample_rate=0.0,
            send_default_pii=False,          # PII yubormaslik (qo'shimcha himoya)
            max_breadcrumbs=20,              # yengil
            before_send=_before_send,
            integrations=[StarletteIntegration(), FastApiIntegration()],
        )
        logger.info("Sentry yoqildi (env=%s)", settings.SENTRY_ENVIRONMENT or settings.ENVIRONMENT)
    except Exception as e:
        logger.warning("Sentry init o'tkazib yuborildi (xato): %s", e)


def set_request_context(user) -> None:
    """get_current_user'dan: joriy so'rovga tenant/user tag (PII EMAS — faqat id).
    Sentry o'chiq (DSN bo'sh) → deyarli nol xarajat (darhol qaytadi)."""
    if not settings.SENTRY_DSN or user is None:
        return
    try:
        import sentry_sdk
        sentry_sdk.set_tag("tenant_id", getattr(user, "tenant_id", None))
        sentry_sdk.set_tag("user_id", getattr(user, "id", None))
    except Exception:
        pass
