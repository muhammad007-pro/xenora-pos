"""Tenant-scoped zaxira — har do'kon FAQAT o'z ma'lumotini (tenant_id) eksport qiladi.

KRITIK IZOLYATSIYA: boshqa tenant qatori YOKI global jadvallar (roles/permissions)
backupга CHIQMAYDI. Usul — SQLAlchemy introspeksiya: `tenant_id` ustuni bor har
jadval avtomatik `WHERE tenant_id = T` bilan olinadi (yangi jadval qo'shilса ham
avtomatik qamraladi). tenant_id'siz child jadvallar parent (tenant-filtrlangan) orqali.
"""
import gzip
import json
import enum
from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import select, DateTime, Date

from database import Base
import models  # noqa: F401 — barcha modellar registrga yuklansin

# Global (barcha tenantга umumiy) — hech qachon backupга CHIQMAYDI
_GLOBAL_EXCLUDE = {"permissions", "roles"}

# tenant_id ustuni YO'Q child jadvallar → parent (tenant-filtrlangan) orqali olinadi.
#   child_table: (parent_table, child_fk_column)
_CHILD_VIA_PARENT = {
    "combo_set_items":         ("combo_sets",          "combo_id"),
    "debt_payments":           ("customer_debts",      "debt_id"),
    "goods_regrade_items":     ("goods_regrades",      "regrade_id"),
    "internal_transfer_items": ("internal_transfers",  "transfer_id"),
    "inventory_count_items":   ("inventory_counts",    "count_id"),
    "order_item_modifiers":    ("order_items",         "order_item_id"),
    "purchase_receipt_items":  ("purchase_receipts",   "receipt_id"),
    "return_items":            ("returns",             "return_id"),
    "write_off_items":         ("write_offs",          "write_off_id"),
}


def _json_safe(v):
    """SQLAlchemy qiymatlarini JSON'га mos holatga keltiradi."""
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, enum.Enum):
        return v.value
    if isinstance(v, (bytes, bytearray, memoryview)):
        return None   # ikkilik (masalan rasm baytlari) — o'tkazib yuboriladi
    return v


def _mappers_by_table() -> dict:
    return {m.class_.__tablename__: m for m in Base.registry.mappers}


def _rows_to_dicts(mapper, objs) -> list:
    keys = [c.key for c in mapper.column_attrs]
    return [{k: _json_safe(getattr(o, k)) for k in keys} for o in objs]


def build_tenant_backup(db, tenant_id: int, meta_extra: dict | None = None):
    """tenant_id ga tegishli BARCHA qatorlarni yig'ib gzip'langan JSON qaytaradi.

    Return: (gzip_bytes, meta_dict)
    """
    from models import Cafe

    mappers = _mappers_by_table()
    tables: dict = {}
    counts: dict = {}

    # 1) tenant_id ustuni bor har jadval — WHERE tenant_id == T  (IZOLYATSIYA KAFOLATI)
    for tname, mapper in mappers.items():
        if tname in _GLOBAL_EXCLUDE:
            continue
        cls = mapper.class_
        if not hasattr(cls, "tenant_id"):
            continue
        objs = db.query(cls).filter(cls.tenant_id == tenant_id).all()
        tables[tname] = _rows_to_dicts(mapper, objs)
        counts[tname] = len(objs)

    # 2) Do'konning O'Z cafes qatori (id == T) — global jadval, faqat shu do'kon
    cafe = db.query(Cafe).filter(Cafe.id == tenant_id).first()
    tables["cafes"] = _rows_to_dicts(mappers["cafes"], [cafe] if cafe else [])
    counts["cafes"] = 1 if cafe else 0

    # 3) tenant_id'siz child jadvallar — parent (tenant-filtrlangan) orqali
    for child, (parent, fk) in _CHILD_VIA_PARENT.items():
        cmap = mappers.get(child)
        pmap = mappers.get(parent)
        if not cmap or not pmap:
            continue
        ccls, pcls = cmap.class_, pmap.class_
        parent_ids = select(pcls.id).where(pcls.tenant_id == tenant_id)
        objs = db.query(ccls).filter(getattr(ccls, fk).in_(parent_ids)).all()
        tables[child] = _rows_to_dicts(cmap, objs)
        counts[child] = len(objs)

    meta = {
        "format":        "xenora-tenant-backup",
        "version":       1,
        "tenant_id":     tenant_id,
        "cafe_name":     getattr(cafe, "name", None),
        "access_code":   getattr(cafe, "access_code", None),
        "business_type": getattr(cafe, "business_type", None),
        "generated_at":  datetime.utcnow().isoformat() + "Z",
        "table_counts":  counts,
        "total_rows":    sum(counts.values()),
    }
    if meta_extra:
        meta.update(meta_extra)

    payload = {"_meta": meta, "tables": tables}
    raw = json.dumps(payload, ensure_ascii=False, default=_json_safe).encode("utf-8")
    gz = gzip.compress(raw, compresslevel=6)
    return gz, meta


# ══════════════════ RESTORE (tiklash) — ENG NOZIK ══════════════════════════════
# Restore'да SAQLANADIGAN (tiklanmaydigan) jadvallar — identity / struktura / platforma.
# Sabab: (1) users'ни tiklаш joriy adminни o'chirib qo'yiши mumkin (login yo'qoladi);
# (2) cafes/tenant_payments platforma boshqaruvida (obuna/access_code/billing);
# (3) audit_logs append-only (o'chirilmasin). Bular DELETE ham, INSERT ham qilinmaydi.
# FK-xavfsiz: bu jadvallar wiped jadvallarга FK bermaydi (faqat ular saqlanadiga tayanadi).
_RESTORE_PRESERVE = {
    "cafes", "users", "branches", "tenant_payments", "audit_logs",
    "permissions", "roles",
}


def _coerce_value(col, v):
    """JSON string'ni ustun turiga qaytaradi (datetime/date). Qolganlar o'zgarmaydi."""
    if v is None or not isinstance(v, str):
        return v
    t = col.type
    try:
        if isinstance(t, DateTime):
            return datetime.fromisoformat(v)
        if isinstance(t, Date):
            return date.fromisoformat(v)
    except Exception:
        return v
    return v


def restore_tenant_backup(db, tenant_id: int, payload: dict) -> dict:
    """tenant_id ma'lumotini backup'дан tiklaydi — BIR TRANZAKSIYA ичида.

    IZOLYATSIYA: faqat shu tenant qatorlari o'chiriladi/qo'shiladi; INSERT'да har
    qatorга tenant_id = T MAJBURAN o'rnatiladi (buzilган backup ham boshqa tenantга yoza olmaydi).
    Chaqiruvchi commit/rollback'ни o'zi qilmaydi — bu funksiya muvaffaqiyатда commit qiladi,
    xatoда exception ko'taradi (chaqiruvchi rollback qiladi).
    """
    meta = payload.get("_meta") or {}
    if meta.get("format") != "xenora-tenant-backup":
        raise ValueError("Noto'g'ri zaxira formati")
    if meta.get("tenant_id") != tenant_id:
        raise ValueError("Bu zaxira boshqa do'konга tegишли")

    tables_data = payload.get("tables") or {}
    mappers = _mappers_by_table()
    sorted_tables = Base.metadata.sorted_tables   # parent → child tartib

    def _restorable(tname: str) -> bool:
        return (tname in tables_data and tname in mappers
                and tname not in _RESTORE_PRESERVE)

    # 1) DELETE — CHILD avval (reversed), FAQAT shu tenant
    deleted = {}
    for tbl in reversed(sorted_tables):
        tname = tbl.name
        if not _restorable(tname):
            continue
        cls = mappers[tname].class_
        if hasattr(cls, "tenant_id"):
            n = db.query(cls).filter(cls.tenant_id == tenant_id).delete(synchronize_session=False)
        elif tname in _CHILD_VIA_PARENT:
            parent, fk = _CHILD_VIA_PARENT[tname]
            pcls = mappers[parent].class_
            parent_ids = select(pcls.id).where(pcls.tenant_id == tenant_id)
            n = db.query(cls).filter(getattr(cls, fk).in_(parent_ids)).delete(synchronize_session=False)
        else:
            continue
        deleted[tname] = n

    # 2) INSERT — PARENT avval, tenant_id MAJBURAN = T
    inserted = {}
    for tbl in sorted_tables:
        tname = tbl.name
        if not _restorable(tname):
            continue
        rows = tables_data.get(tname) or []
        if not rows:
            inserted[tname] = 0
            continue
        colmap = {c.key: c for c in tbl.columns}
        has_tenant = "tenant_id" in colmap
        out_rows = []
        for row in rows:
            d = {}
            for k, v in row.items():
                col = colmap.get(k)
                if col is None:      # sxema o'zgargan — yo'q ustunни o'tkazamiz
                    continue
                d[k] = _coerce_value(col, v)
            if has_tenant:
                d["tenant_id"] = tenant_id   # ← IZOLYATSIYA KAFOLATI
            out_rows.append(d)
        if out_rows:
            db.execute(tbl.insert(), out_rows)
        inserted[tname] = len(out_rows)

    db.commit()
    return {
        "deleted_rows": sum(deleted.values()),
        "inserted_rows": sum(inserted.values()),
        "tables_restored": len([t for t in tables_data if _restorable(t)]),
        "preserved": sorted(t for t in _RESTORE_PRESERVE if t in tables_data),
    }
