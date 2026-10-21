"""Xodim hisoboti uchun "alohida hisoblanadigan kategoriyalar" sozlamasi.

MANHATTAN (2026-10): egasi kiyim savdosini atir va boshqa tovarlardan ALOHIDA
ko'rishi kerak (xodim bo'yicha). Hisob-kitobni egasining o'zi qiladi —
tizim faqat ikki ustun beradi: "Asosiy" va "Alohida".

Sozlama tenant_settings'da (`staff_split`):
    {"category_ids": [3, 7]}

QOIDALAR:
  • Tanlangan kategoriyalar (va ularning ICHKI kategoriyalari: Kiyim →
    Ko'ylak, Shim) — "Alohida"; qolgan hamma savdo — "Asosiy".
  • `category_ids` BO'SH → hamma savdo "Asosiy", ajratish yo'q.
  • Kategoriyasiz mahsulot — "Asosiy".
"""
from core.tenant_config import get_tenant_config, set_tenant_config

CONFIG_NAME = "staff_split"


def get_category_ids(db, tenant_id) -> list:
    """Tanlangan kategoriya id'lari (saralangan, takrorsiz)."""
    raw = (get_tenant_config(db, tenant_id, CONFIG_NAME) or {}) if tenant_id is not None else {}
    ids = set()
    for x in raw.get("category_ids") or []:
        try:
            ids.add(int(x))
        except (TypeError, ValueError):
            continue
    return sorted(ids)


def save_category_ids(db, tenant_id, category_ids) -> list:
    ids = sorted({int(x) for x in category_ids})
    set_tenant_config(db, tenant_id, CONFIG_NAME, {"category_ids": ids})
    return ids


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
