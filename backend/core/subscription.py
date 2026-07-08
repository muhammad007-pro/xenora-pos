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

from dataclasses import dataclass

UNLIMITED = 0  # 0 qiymati = cheksiz


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


def get_plan_info(plan: str) -> dict:
    """Tarif haqida to'liq ma'lumot (API javobi uchun)."""
    limits = get_plan_limits(plan)
    return {
        "plan": plan,
        "max_users": limits.max_users if limits.max_users != UNLIMITED else None,
        "max_branches": limits.max_branches if limits.max_branches != UNLIMITED else None,
        "max_orders_month": limits.max_orders_month if limits.max_orders_month != UNLIMITED else None,
    }
