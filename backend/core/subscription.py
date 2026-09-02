"""
Obuna tariflar va cheklovlar (BOSQICH 2.2)

ARCHITECTURE.md bo'lim 6 dan:
  FREE       — 1 filial, 3 foydalanuvchi, 100 buyurtma/oy  (bepul)
  PRO        — 5 filial, 20 foydalanuvchi, cheksiz buyurtma
  ENTERPRISE — cheksiz hamma narsa

Eski nom mos kelishi (backward compat):
  basic   -> FREE cheklovlari
  premium -> PRO cheklovlari
"""

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

UNLIMITED = 0  # 0 qiymati = cheksiz

# Muddatga necha kun qolganда UI ogohlantirishi boshlanadi (banner: "N kundan keyin tugaydi").
WARN_DAYS = 7


@dataclass(frozen=True)
class PlanLimits:
    max_users: int         # 0 = cheksiz
    max_branches: int      # 0 = cheksiz
    max_orders_month: int  # 0 = cheksiz


PLAN_LIMITS: dict[str, PlanLimits] = {
    # ── Ko'rinadigan uch tarif ────────────────────────────────────────────────
    "free":       PlanLimits(max_users=3,  max_branches=1, max_orders_month=100),        # Boshlang'ich
    "standart":   PlanLimits(max_users=10, max_branches=2, max_orders_month=UNLIMITED),  # Standart
    "pro":        PlanLimits(max_users=20, max_branches=5, max_orders_month=UNLIMITED),  # Pro
    # ── Eski nomlar (backward compat; UI'da ko'rinmaydi) ─────────────────────
    "basic":      PlanLimits(max_users=3,  max_branches=1, max_orders_month=100),
    "premium":    PlanLimits(max_users=20, max_branches=5, max_orders_month=UNLIMITED),
    "enterprise": PlanLimits(max_users=UNLIMITED, max_branches=UNLIMITED, max_orders_month=UNLIMITED),
}

# UI'da ko'rinadigan nom — kod (DB qiymati) bilan ATAYLAB ajratilgan.
# Nomni o'zgartirish uchun bazaga tegish SHART EMAS.
PLAN_DISPLAY_NAMES: dict[str, str] = {
    "free":       "Boshlang'ich",
    "standart":   "Standart",
    "pro":        "Pro",
    "enterprise": "Enterprise",
}

# ── NARX — YAGONA MANBA (UZS/oy) ──────────────────────────────────────────────
# Ilgari ikki ZID jadval bor edi: routers/super_admin.py PLAN_PRICES (USD,
# free=$10) va frontend/owner/subscriptions.html (UZS, free=0 "bepul").
# Moliya paneli LITE'ni pullik, mijoz ekrani bepul deb ko'rsatardi. Endi ikkalasi
# ham SHU YERDAN o'qiydi (frontend `GET /super-admin/plans` orqali).
PLAN_PRICES_UZS: dict[str, int] = {
    "free":       249_000,
    "standart":   449_000,
    "pro":        749_000,
    "enterprise": 0,        # ko'rinmaydi; narx kelishuv asosida
}

VALID_PLANS = ("free", "standart", "pro", "enterprise")

# UI dropdownida ko'rsatiladigan tariflar (enterprise ataylab yo'q — u
# kelishuv asosidagi maxsus holat, o'z-o'zidan tanlanmaydi).
PUBLIC_PLANS = ("free", "standart", "pro")


def get_plan_limits(plan: str) -> PlanLimits:
    """Tarif nomi bo'yicha cheklovlarni qaytaradi.

    ⚠️ NOMA'LUM TARIF — JIMGINA emas, OGOHLANTIRISH bilan FREE'ga tushadi.
    Ilgari bu jim edi va XAVFLI natija berardi: tarif nomida xato bo'lsa
    (masalan "standard" vs "standart") mijoz sababsiz 3 foydalanuvchi va
    100 buyurtma/oy limitiga tushib qolardi va HECH KIM sezmasdi.
    Endi logda aniq WARNING chiqadi.

    Xato (exception) ATAYLAB tashlanmaydi: bu funksiya sotuv/login yo'lida
    chaqiriladi, bitta noto'g'ri yozuv butun do'konni to'xtatib qo'ymasligi kerak.
    """
    key = (plan or "").strip().lower()
    limits = PLAN_LIMITS.get(key)
    if limits is None:
        logger.warning(
            "[TARIF] Noma'lum tarif '%s' — FREE cheklovlari qo'llanildi "
            "(max_users=%d, max_orders_month=%d). Ma'lum tariflar: %s",
            plan, PLAN_LIMITS["free"].max_users,
            PLAN_LIMITS["free"].max_orders_month, sorted(PLAN_LIMITS),
        )
        return PLAN_LIMITS["free"]
    return limits


def is_within_branch_limit(current_count: int, plan: str) -> bool:
    """Hozirgi filiallar soni tarif limitiga sig'adimi?

    2026-08-27 gacha `max_branches` E'LON QILINGAN-u, hech qayerda
    TEKSHIRILMASDI — "1 filial" va'dasi bo'sh gap edi. `routers/branch.py`
    endi shu funksiyani ishlatadi.
    """
    limits = get_plan_limits(plan)
    return limits.max_branches == UNLIMITED or current_count < limits.max_branches


def is_within_user_limit(current_count: int, plan: str) -> bool:
    """Hozirgi foydalanuvchilar soni tarif limitiga sig'adimi?"""
    limits = get_plan_limits(plan)
    return limits.max_users == UNLIMITED or current_count < limits.max_users


def is_within_order_limit(monthly_count: int, plan: str) -> bool:
    """Oylik buyurtmalar soni tarif limitiga sig'adimi?"""
    limits = get_plan_limits(plan)
    return limits.max_orders_month == UNLIMITED or monthly_count < limits.max_orders_month


def _days_ceil(delta: timedelta) -> int:
    """Kunlarni YUQORIGA yaxlitlaydi (23 soat qolsa ham "1 kun") — foydalanuvchiga tushunarli."""
    return math.ceil(delta.total_seconds() / 86400)


def effective_expiry(cafe):
    """Bloklashni boshqaradigan ASOSIY muddat.

    trial holatida trial_expires; aks holda subscription_expires. Ikkalasi ham
    None bo'lsa — muddat belgilanmagan (bepul/cheksiz) → hech qachon bloklanmaydi.
    """
    ts = (getattr(cafe, "tenant_status", None) or "active")
    if ts == "trial" and getattr(cafe, "trial_expires", None):
        return cafe.trial_expires
    return getattr(cafe, "subscription_expires", None)


def subscription_state(cafe, now: datetime = None, grace_days: int = 0) -> dict:
    """Obuna holatining YAGONA haqiqat manbai.

    Enforcement (deps._enforce_subscription), tenant-facing status endpointi
    (/cafes/my/subscription) va super-admin paneli — HAMMASI shu funksiyani
    ishlatadi (izchillik: server bloklagan holat UI bilan aynan bir xil).

    Qaytadi:
      state: active | expiring | grace | expired | blocked | inactive
      blocked (bool)   — True bo'lsa 403 (kirish yopiq)
      expiry           — hisobga olingan muddat (datetime | None)
      days_left        — muddatgacha qolgan kun (grace/expired'da manfiy)
      in_grace (bool)  — muhlat davri
      grace_days_left  — muhlatda qolgan kun (>=0) yoki None
      plan, message
    """
    now = now or datetime.now()
    plan = (getattr(cafe, "subscription_plan", None) or "free")

    def out(state, blocked, expiry=None, days_left=None,
            in_grace=False, grace_days_left=None, message=""):
        return {
            "state": state, "blocked": blocked, "expiry": expiry,
            "days_left": days_left, "in_grace": in_grace,
            "grace_days_left": grace_days_left, "plan": plan, "message": message,
        }

    # ── QO'LDA qo'yiladigan qattiq bloklar ────────────────────────────────────
    # Bular super-admin AMALI, obuna sanasi bilan aloqasi yo'q:
    #   is_active=False          — do'kon o'chirilgan
    #   tenant_status='blocked'  — qo'lda bloklangan (sabab bilan)
    # Shuning uchun ular sanadan QAT'IY NAZAR blok bo'lib qoladi — aks holda
    # "do'konni o'chirish" tugmasi ma'nosini yo'qotardi.
    # DIQQAT: `tasks/scheduler.check_expired_tenants` 2026-09-02 dan boshlab
    # `is_active` ga TEGMAYDI (u kirish yo'lida — resolve-code/pin-login da —
    # tekshiriladi va muddat tugashi bilan kassirni "Do'kon topilmadi" ga
    # olib borardi).
    if getattr(cafe, "is_active", True) is False:
        return out("inactive", True,
                   message="Hisob faolsizlantirilgan. Davom etish uchun bog'laning.")
    status = (getattr(cafe, "tenant_status", None) or "active").lower()
    if status == "blocked":
        return out("blocked", True,
                   message=(getattr(cafe, "blocked_reason", None)
                            or "Hisob bloklangan. Davom etish uchun bog'laning."))

    exp = effective_expiry(cafe)

    # ── SANA — ASOSIY MANBA; `expired` esa faqat BELGI ────────────────────────
    # Ilgari `status == 'expired'` shu yerdan OLDIN tekshirilardi va darhol
    # qattiq blok qaytarardi. Natijada quyidagi MUHLAT (grace) shoxiga navbat
    # HECH QACHON kelmasdi — `SUBSCRIPTION_GRACE_DAYS` amalda o'lik edi.
    # Endi belgi bilan sana zid bo'lsa SANA yutadi. Bu ikki holatni tuzatadi:
    #   • muhlat ichidagi tenant "expired" belgisi tufayli muhlatidan mahrum
    #     bo'lmaydi;
    #   • to'lov muddatni uzaytirgan-u status yangilanmay qolgan bo'lsa
    #     (`cafe.renew_subscription` tuzog'i) mijoz bekorga bloklanmaydi.
    if exp is None:
        # Sana yo'q — hukm faqat belgiga qoladi.
        if status == "expired":
            return out("expired", True,
                       message="Obuna muddati tugagan. Davom etish uchun bog'laning.")
        return out("active", False)   # muddat yo'q — bloklanmaydi

    if now <= exp:
        d = _days_ceil(exp - now)
        if d <= WARN_DAYS:
            return out("expiring", False, expiry=exp, days_left=d,
                       message=f"Obuna {d} kundan keyin tugaydi.")
        return out("active", False, expiry=exp, days_left=d)

    # ── Muddat o'tdi — MUHLAT (grace) tekshiruvi ──
    grace_end = exp + timedelta(days=max(0, grace_days))
    if now <= grace_end:
        gl = max(0, _days_ceil(grace_end - now))
        return out("grace", False, expiry=exp, days_left=_days_ceil(exp - now),
                   in_grace=True, grace_days_left=gl,
                   message=(f"Obuna muddati tugadi. To'lov uchun {gl} kun muhlat qoldi, "
                            "aks holda hisob bloklanadi."))

    # ── Muhlat ham tugadi → TO'LIQ BLOK ──
    return out("expired", True, expiry=exp, days_left=_days_ceil(exp - now),
               message="Obuna muddati tugagan. Davom etish uchun bog'laning.")


def get_plan_info(plan: str) -> dict:
    """Tarif haqida to'liq ma'lumot (API javobi uchun)."""
    limits = get_plan_limits(plan)
    return {
        "plan": plan,
        "max_users": limits.max_users if limits.max_users != UNLIMITED else None,
        "max_branches": limits.max_branches if limits.max_branches != UNLIMITED else None,
        "max_orders_month": limits.max_orders_month if limits.max_orders_month != UNLIMITED else None,
    }
