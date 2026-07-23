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

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

UNLIMITED = 0  # 0 qiymati = cheksiz

# Muddatga necha kun qolganда UI ogohlantirishi boshlanadi (banner: "N kundan keyin tugaydi").
WARN_DAYS = 7


@dataclass(frozen=True)
class PlanLimits:
    max_users: int         # 0 = cheksiz
    max_branches: int      # 0 = cheksiz
    max_orders_month: int  # 0 = cheksiz


PLAN_LIMITS: dict[str, PlanLimits] = {
    "free":       PlanLimits(max_users=3,  max_branches=1, max_orders_month=100),
    "basic":      PlanLimits(max_users=3,  max_branches=1, max_orders_month=100),
    "pro":        PlanLimits(max_users=20, max_branches=5, max_orders_month=UNLIMITED),
    "premium":    PlanLimits(max_users=20, max_branches=5, max_orders_month=UNLIMITED),
    "enterprise": PlanLimits(max_users=UNLIMITED, max_branches=UNLIMITED, max_orders_month=UNLIMITED),
}

VALID_PLANS = ("free", "pro", "enterprise")


def get_plan_limits(plan: str) -> PlanLimits:
    """Tarif nomi bo'yicha cheklovlarni qaytaradi; noma'lum tarif -> FREE cheklovlari."""
    return PLAN_LIMITS.get(plan.lower(), PLAN_LIMITS["free"])


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

    # ── Qattiq bloklar (super-admin qo'lda / faolsizlantirilgan) ──
    if getattr(cafe, "is_active", True) is False:
        return out("inactive", True,
                   message="Hisob faolsizlantirilgan. Davom etish uchun bog'laning.")
    status = (getattr(cafe, "tenant_status", None) or "active").lower()
    if status == "blocked":
        return out("blocked", True,
                   message=(getattr(cafe, "blocked_reason", None)
                            or "Hisob bloklangan. Davom etish uchun bog'laning."))
    if status == "expired":
        return out("expired", True,
                   message="Obuna muddati tugagan. Davom etish uchun bog'laning.")

    exp = effective_expiry(cafe)
    if exp is None:
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
