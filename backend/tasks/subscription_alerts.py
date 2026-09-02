"""Obuna muddati bo'yicha Telegram ogohlantirishlari.

MUAMMO: mijoz ekranga qaramasa muddat tugayotganini bilmasdi. Bannerni
(`core/subscription-banner.js`) faqat ilovaga KIRGAN odam ko'radi; do'kon
egasi bir hafta kirmasa, muddat jimgina tugardi va birinchi signal — kassir
"nega ishlamayapti?" deb qo'ng'iroq qilishi bo'lardi.

IKKI QABUL QILUVCHI:
  • "admin"  — super-admin kanali (`ALERT_CHAT_ID`), BARCHA tenantlar bo'yicha,
               5 bosqich: 7/3/1 kun, muddat tugagani, muhlat tugab bloklangani.
  • "owner"  — do'kon egasi (`cafes.telegram_chat_id`), FAQAT 7/3/1 kun.
               Egasiga "bloklandingiz" xabarini bot emas, odam aytgani ma'qul;
               qolaversa o'sha paytda u allaqachon ilovada blok ekranini ko'radi.

BIR YUGURISHDA BIR QABUL QILUVCHIGA KO'PI BILAN BITTA XABAR: eng SHOSHILINCH
bosqich tanlanadi. Server bir kun o'chib qolsa, `days_left` 7 dan 2 ga sakraydi
— bunda "7 kun qoldi" emas, "3 kun qoldi" yuboriladi (eskirgan xabar emas,
o'rinlisi). Bosqichlar shu sabab `==` emas, `<=` bilan tanlanadi.

TAKROR: `subscription_alerts` jadvali, UNIQUE(tenant_id, stage, expiry_date,
audience). Kalitda MUDDAT SANASI bor — obuna uzaytirilsa yangi tsikl
o'z-o'zidan ochiladi, hech narsani nollash kerak emas.

XAVFSIZLIK:
  • Xabarda faqat: do'kon nomi, id (adminga), tarif, narx, sana, qo'llab-quvvatlash
    telefoni. Parol, token, mijoz yoki savdo ma'lumoti YO'Q.
  • Do'kon nomi `html.escape` bilan qochiriladi — `parse_mode=HTML` ishlatiladi,
    nomdagi `<` xabarni buzishi yoki teg kiritishi mumkin edi.
  • Telegram ishlamasa vazifa TO'XTAMAYDI: yuborilmagan bo'lsa yozuv yozilmaydi
    va keyingi soatda qayta uriniladi (`core/alert.send_to_chat` -> False).

KILL-SWITCH: `SUBSCRIPTION_ALERTS_ENABLED` (standart **False**). O'chiq bo'lsa
vazifa umuman ishlamaydi — deploy jonli mijozlarga xabar yubormaydi.
`ENFORCE_SUBSCRIPTION` dan MUSTAQIL: ogohlantirish — xabar berish, bloklash emas.
"""
import html
import logging
from datetime import datetime
from typing import Optional

from config import settings
from core.subscription import (
    PLAN_DISPLAY_NAMES, PLAN_PRICES_UZS, effective_expiry, subscription_state,
)

logger = logging.getLogger(__name__)

# Bosqich -> necha kun qolganda. Tartib MUHIM: shoshilinchdan pastga.
DAY_STAGES = (("d1", 1), ("d3", 3), ("d7", 7))

# Egasiga yuboriladigan bosqichlar (qolganlari faqat super-adminga).
OWNER_STAGES = frozenset({"d1", "d3", "d7"})


def _fmt_date(d) -> str:
    return d.strftime("%d.%m.%Y")


def _fmt_money(v: int) -> str:
    """749000 -> '749 000'."""
    return f"{v:,}".replace(",", " ")


def _plan_line(plan: str) -> str:
    key = (plan or "free").lower()
    name = PLAN_DISPLAY_NAMES.get(key, key)
    price = PLAN_PRICES_UZS.get(key, 0)
    if price:
        return f"Tarif: {name} · {_fmt_money(price)} so'm/oy"
    return f"Tarif: {name}"


def pick_stage(st: dict) -> Optional[str]:
    """Tenant holatidan ogohlantirish bosqichini tanlaydi.

    Qaytadi: 'd7'|'d3'|'d1'|'expired'|'blocked' yoki None (kerak emas).
    """
    state = st.get("state")

    # Qo'lda qo'yilgan bloklar — super-admin ATAYLAB qilgan, bot xabar bermaydi.
    if state in ("blocked", "inactive"):
        return None

    # Muhlat ham tugadi -> qattiq blok.
    if state == "expired":
        return "blocked"

    # Muddat o'tdi, muhlat davom etyapti.
    if state == "grace" or st.get("in_grace"):
        return "expired"

    days = st.get("days_left")
    if days is None:
        return None
    for stage, limit in DAY_STAGES:      # d1 -> d3 -> d7 (shoshilinchdan)
        if days <= limit:
            return stage
    return None


def build_message(cafe, st: dict, stage: str, audience: str) -> str:
    """Ogohlantirish matni. Do'kon nomi HTML uchun qochiriladi."""
    name = html.escape(cafe.name or f"#{cafe.id}")
    ident = f"{name} (#{cafe.id})" if audience == "admin" else name
    exp = effective_expiry(cafe)
    plan = _plan_line(getattr(cafe, "subscription_plan", "free"))
    tolov = f"To'lov: {settings.SUPPORT_CONTACT}"

    if stage in ("d1", "d3", "d7"):
        kun = st.get("days_left")
        head = f"⚠️ {ident} — obuna {kun} kundan keyin tugaydi ({_fmt_date(exp)})"
        return f"{head}\n{plan}\n{tolov}"

    if stage == "expired":
        qoldi = st.get("grace_days_left")
        head = f"🔴 {ident} — obuna muddati tugadi ({_fmt_date(exp)})"
        return f"{head}\nMuhlat: yana {qoldi} kun\n{plan}\n{tolov}"

    # stage == "blocked"
    lines = [
        f"⛔ {ident} — muhlat tugadi, obuna bloklangan holatda",
        f"Muddat tugagan: {_fmt_date(exp)}",
        plan,
        tolov,
    ]
    if not settings.ENFORCE_SUBSCRIPTION:
        # ALDAMASLIK UCHUN: enforcement o'chiq bo'lsa do'kon aslida ishlayapti.
        # Busiz super-admin "bloklandi" deb o'ylab, bekorga qo'ng'iroq qilardi.
        lines.append("(ENFORCE_SUBSCRIPTION o'chiq — do'kon hali ishlayapti)")
    return "\n".join(lines)


def _already_sent(db, SubscriptionAlert, tenant_id, stage, expiry_date, audience) -> bool:
    return db.query(SubscriptionAlert.id).filter(
        SubscriptionAlert.tenant_id == tenant_id,
        SubscriptionAlert.stage == stage,
        SubscriptionAlert.expiry_date == expiry_date,
        SubscriptionAlert.audience == audience,
    ).first() is not None


def _deliver(db, SubscriptionAlert, cafe, st, stage, audience, chat_id, send) -> bool:
    """Bitta xabar: tekshir -> yubor -> yoz.

    Yuborilmasa YOZUV YOZILMAYDI — keyingi soatlik yugurishda qayta uriniladi.
    """
    exp_date = effective_expiry(cafe).date()
    if _already_sent(db, SubscriptionAlert, cafe.id, stage, exp_date, audience):
        return False

    text = build_message(cafe, st, stage, audience)
    if not send(text, chat_id):
        logger.warning(
            "Obuna ogohlantirishi yuborilmadi (keyingi yugurishda qayta): "
            "tenant=%s stage=%s audience=%s", cafe.id, stage, audience)
        return False

    db.add(SubscriptionAlert(
        tenant_id=cafe.id, stage=stage, audience=audience,
        expiry_date=exp_date, sent_at=datetime.now(),
    ))
    try:
        db.commit()
    except Exception as e:
        # UNIQUE poygasi (boshqa jarayon ayni paytda yozgan) — zarar yo'q.
        db.rollback()
        logger.info("Ogohlantirish yozuvi yozilmadi (ehtimol takror): %s", e)
        return False
    logger.info("Obuna ogohlantirishi yuborildi: tenant=%s stage=%s audience=%s",
                cafe.id, stage, audience)
    return True


async def check_subscription_alerts():
    """Soatlik vazifa — muddati yaqinlashgan/tugagan tenantlar bo'yicha xabar.

    Hech qachon otmaydi: har tenant alohida `try` ichida, bitta do'kondagi
    nosozlik qolganlarni to'xtatmaydi.
    """
    if not settings.SUBSCRIPTION_ALERTS_ENABLED:
        return 0

    from database import SessionLocal
    from models import Cafe, SubscriptionAlert
    from core.alert import send_to_chat

    now = datetime.now()
    admin_chat = settings.ALERT_CHAT_ID
    grace = settings.SUBSCRIPTION_GRACE_DAYS
    yuborildi = 0

    db = SessionLocal()
    try:
        cafes = db.query(Cafe).filter(Cafe.is_active == True).all()  # noqa: E712
        for cafe in cafes:
            try:
                if effective_expiry(cafe) is None:
                    continue   # muddatsiz tenant — ogohlantiradigan sana yo'q
                st = subscription_state(cafe, now=now, grace_days=grace)
                stage = pick_stage(st)
                if not stage:
                    continue

                if admin_chat and _deliver(db, SubscriptionAlert, cafe, st,
                                           stage, "admin", admin_chat, send_to_chat):
                    yuborildi += 1

                owner_chat = getattr(cafe, "telegram_chat_id", None)
                if (stage in OWNER_STAGES and owner_chat
                        and _deliver(db, SubscriptionAlert, cafe, st,
                                     stage, "owner", owner_chat, send_to_chat)):
                    yuborildi += 1
            except Exception as e:
                logger.error("Obuna ogohlantirishi xato (tenant=%s): %s", cafe.id, e)
    except Exception as e:
        logger.error("check_subscription_alerts failed: %s", e)
    finally:
        db.close()

    if yuborildi:
        logger.info("Obuna ogohlantirishlari yuborildi: %d", yuborildi)
    return yuborildi
