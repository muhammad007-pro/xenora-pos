"""Xodim bonusi sozlamasi — "bonusli kategoriyalar" + har millionga stavka.

MANHATTAN (2026-10): egasi sotuvchiga bonus to'laydi — har 1 000 000 so'm
sof savdoga 50 000. Bonus FAQAT ba'zi kategoriyalardan (kiyim ha, atir yo'q).

Sozlama tenant_settings'da (`staff_bonus`):
    {"category_ids": [3, 7], "rate_per_million": 50000}

QOIDALAR:
  • `category_ids` BO'SH → HAMMA savdo bonusli (sozlanmagan do'kon uchun
    hisobot "hammasi bonusli" ko'rinadi, "hammasi boshqa" emas).
  • Tanlangan kategoriyaning ICHKI kategoriyalari ham bonusli (Kiyim →
    Ko'ylak, Shim) — egasi har birini alohida belgilashi shart emas.
  • Kategoriyasiz mahsulot — "Boshqa" (sozlama bo'sh bo'lmasa).
"""
from core.tenant_config import get_tenant_config, set_tenant_config

CONFIG_NAME = "staff_bonus"
DEFAULT_RATE = 50_000.0
MAX_RATE = 1_000_000.0      # millionga milliondan ortiq bonus — xato kiritish


def get_config(db, tenant_id) -> dict:
    """{"category_ids": [int], "rate_per_million": float} — har doim to'liq shakl."""
    raw = (get_tenant_config(db, tenant_id, CONFIG_NAME) or {}) if tenant_id is not None else {}
    ids = []
    for x in raw.get("category_ids") or []:
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            continue
    rate = raw.get("rate_per_million")
    try:
        rate = float(rate) if rate is not None else DEFAULT_RATE
    except (TypeError, ValueError):
        rate = DEFAULT_RATE
    return {"category_ids": sorted(set(ids)), "rate_per_million": rate}


def save_config(db, tenant_id, category_ids, rate_per_million) -> dict:
    data = {"category_ids": sorted({int(x) for x in category_ids}),
            "rate_per_million": float(rate_per_million)}
    set_tenant_config(db, tenant_id, CONFIG_NAME, data)
    return data


def tenant_categories(db, tenant_id) -> list:
    """Do'kon kategoriyalari [(id, name, parent_id)] — nom bo'yicha."""
    from models import Category
    return (
        db.query(Category.id, Category.name, Category.parent_id)
        .filter(Category.tenant_id == tenant_id)
        .order_by(Category.name)
        .all()
    )


def expand_with_children(selected, categories) -> set:
    """Tanlangan kategoriyalar + ularning BARCHA ichki kategoriyalari."""
    children: dict = {}
    for cid, _name, parent in categories:
        if parent is not None:
            children.setdefault(parent, []).append(cid)
    out, stack = set(), list(selected)
    while stack:
        c = stack.pop()
        if c in out:
            continue        # sikl himoyasi (buzilgan parent_id zanjiri)
        out.add(c)
        stack.extend(children.get(c, ()))
    return out


def bonus_amount(base: float, rate_per_million: float) -> float:
    """Bonus = sof bonusli savdo × stavka / 1 000 000 (proporsional).

    Manfiy baza (davrda vozvrat sotuvdan ko'p) → 0: bonus ushlab qolinmaydi,
    lekin baza hisobotda manfiy ko'rinib turadi.
    """
    return max(base, 0.0) * rate_per_million / 1_000_000.0
