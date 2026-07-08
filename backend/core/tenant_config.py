"""Tenant-scoped konfiguratsiya accessor qatlami (BOSQICH 40, 1-qadam).

Eski global `config_loader` (core/config_loader.py) yonida turadi va uni
o'zgartirmaydi. Bu qatlam DB sessiyasi + tenant_id qabul qiladi — global
singleton EMAS, har so'rovda tenant bo'yicha ishlaydi.

Ko'chirish yumshoq: agar tenant uchun yozuv bo'lmasa, eski global
config_loader qiymati DEFAULT sifatida qaytariladi. Shunday qilib mavjud
global sozlamalar yangi tenantlar uchun boshlang'ich standart bo'lib qoladi.
"""
import copy
from typing import Any, Dict

from sqlalchemy.orm import Session

from models import TenantSettings
from core.config_loader import config_loader


def get_tenant_config(db: Session, tenant_id: int, config_name: str) -> Dict[str, Any]:
    """Tenant config'ini o'qish.

    - tenant_settings'da yozuv bo'lsa — uning `data` dict'i (nusxa).
    - Bo'lmasa — eski global config_loader qiymati DEFAULT sifatida (nusxa).
    """
    row = (
        db.query(TenantSettings)
        .filter(
            TenantSettings.tenant_id == tenant_id,
            TenantSettings.config_name == config_name,
        )
        .first()
    )
    if row is not None and row.data is not None:
        return copy.deepcopy(row.data)
    # Fallback: eski global qiymat boshlang'ich standart bo'lib qoladi
    return copy.deepcopy(config_loader.get(config_name) or {})


def set_tenant_config(db: Session, tenant_id: int, config_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Tenant config'ini yozish (upsert: bor bo'lsa update, yo'q bo'lsa insert)."""
    row = (
        db.query(TenantSettings)
        .filter(
            TenantSettings.tenant_id == tenant_id,
            TenantSettings.config_name == config_name,
        )
        .first()
    )
    if row is None:
        row = TenantSettings(tenant_id=tenant_id, config_name=config_name, data=dict(data))
        db.add(row)
    else:
        row.data = dict(data)
    db.commit()
    db.refresh(row)
    return copy.deepcopy(row.data)


def get_tenant_config_value(
    db: Session, tenant_id: int, config_name: str, key: str, default: Any = None
) -> Any:
    """Bitta kalitni o'qish qulayligi. Nuqtali ('a.b.c') kirib borishni qo'llab-quvvatlaydi."""
    config = get_tenant_config(db, tenant_id, config_name)
    value: Any = config
    for k in key.split("."):
        if isinstance(value, dict):
            value = value.get(k)
        else:
            return default
    return value if value is not None else default
