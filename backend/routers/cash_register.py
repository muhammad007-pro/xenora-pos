"""Kassa nuqtalari (multi-register) — CRUD router (BOSQICH 30).

`cash_register` feature flagi yoqilgan tenant uchun ishlaydi. Flag o'chiq bo'lsa
endpointlar 403 qaytaradi (frontend ham nav itemni yashiradi). Tenant-scoped:
har kim faqat o'z cafe kassalarini ko'radi/boshqaradi.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from models import CashRegister, Branch, Cafe, User
from schemas import CashRegisterCreate, CashRegisterUpdate, CashRegisterInDB
from deps import get_current_active_user, apply_tenant_filter, resolve_tenant_id
from core.feature_flags import resolve_enabled_features, Feature

router = APIRouter()


def require_cash_register(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> User:
    """`cash_register` flagi yoqilgan tenant uchun ruxsat (super-admin bypass)."""
    if current_user.is_superuser:
        return current_user
    cafe = db.query(Cafe).filter(Cafe.id == current_user.tenant_id).first()
    if not cafe:
        raise HTTPException(status_code=403, detail="Tenant aniqlanmadi")
    enabled = resolve_enabled_features(
        cafe.business_type, cafe.enabled_features, cafe.disabled_features
    )
    if Feature.CASH_REGISTER.value not in enabled:
        raise HTTPException(status_code=403, detail="Kassa funksiyasi yoqilmagan")
    return current_user


def _ensure_admin(user: User) -> None:
    """Faqat ega/admin/menejer kassani boshqara oladi (kassir/ofitsiant emas).
    Tenant egalarida rol biriktirilmagan bo'lishi mumkin — ular ham ega hisobi."""
    if user.is_superuser or user.role is None:
        return
    if (user.role.name or "").lower() in ("admin", "manager"):
        return
    raise HTTPException(status_code=403, detail="Faqat admin kassani boshqaradi")


def _get_register_or_404(reg_id: int, current_user: User, db: Session) -> CashRegister:
    reg = apply_tenant_filter(db.query(CashRegister), CashRegister, current_user).filter(
        CashRegister.id == reg_id
    ).first()
    if not reg:
        raise HTTPException(status_code=404, detail="Kassa topilmadi")
    return reg


def _validate_branch(branch_id, tenant_id, current_user, db) -> None:
    """Berilgan filial shu tenantga tegishlimi tekshiradi."""
    if branch_id is None:
        return
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Filial topilmadi")
    if not current_user.is_superuser and branch.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Filial boshqa tenantga tegishli")


@router.get("/", response_model=List[CashRegisterInDB])
def list_registers(
    branch_id: int = None,
    is_active: bool = None,
    current_user: User = Depends(require_cash_register),
    db: Session = Depends(get_db),
):
    """Joriy tenant kassalari ro'yxati (ixtiyoriy filial/holat bo'yicha filtr)."""
    q = apply_tenant_filter(db.query(CashRegister), CashRegister, current_user)
    if branch_id is not None:
        q = q.filter(CashRegister.branch_id == branch_id)
    if is_active is not None:
        q = q.filter(CashRegister.is_active == is_active)
    return q.order_by(CashRegister.id).all()


@router.post("/", response_model=CashRegisterInDB, status_code=201)
def create_register(
    data: CashRegisterCreate,
    current_user: User = Depends(require_cash_register),
    db: Session = Depends(get_db),
):
    """Yangi kassa qo'shish (faqat ega/admin)."""
    _ensure_admin(current_user)
    tenant_id = resolve_tenant_id(db, current_user)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant aniqlanmadi")
    _validate_branch(data.branch_id, tenant_id, current_user, db)

    reg = CashRegister(
        tenant_id=tenant_id,
        branch_id=data.branch_id,
        name=data.name,
        is_active=True,
    )
    db.add(reg)
    db.commit()
    db.refresh(reg)
    return reg


@router.patch("/{reg_id}", response_model=CashRegisterInDB)
def update_register(
    reg_id: int,
    data: CashRegisterUpdate,
    current_user: User = Depends(require_cash_register),
    db: Session = Depends(get_db),
):
    """Kassani tahrirlash / faol-nofaol qilish (faqat ega/admin)."""
    _ensure_admin(current_user)
    reg = _get_register_or_404(reg_id, current_user, db)

    if data.name is not None:
        reg.name = data.name
    if data.branch_id is not None:
        _validate_branch(data.branch_id, reg.tenant_id, current_user, db)
        reg.branch_id = data.branch_id
    if data.is_active is not None:
        reg.is_active = data.is_active

    db.commit()
    db.refresh(reg)
    return reg


@router.delete("/{reg_id}", status_code=204)
def delete_register(
    reg_id: int,
    current_user: User = Depends(require_cash_register),
    db: Session = Depends(get_db),
):
    """Kassani o'chirish (faqat ega/admin)."""
    _ensure_admin(current_user)
    reg = _get_register_or_404(reg_id, current_user, db)
    db.delete(reg)
    db.commit()
