from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from models import Branch, Cafe
from schemas import BranchCreate, BranchUpdate, BranchInDB
from deps import get_current_active_user, apply_tenant_filter, resolve_tenant_id
from models import User

router = APIRouter()


def _get_branch_or_404(branch_id: int, current_user: User, db: Session) -> Branch:
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Filial topilmadi")
    if not current_user.is_superuser and branch.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")
    return branch


@router.get("/", response_model=List[BranchInDB])
def list_branches(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Joriy tenant filiallari ro'yxati"""
    q = db.query(Branch)
    if not current_user.is_superuser:
        q = q.filter(Branch.tenant_id == current_user.tenant_id)
    return q.order_by(Branch.is_default.desc(), Branch.id).all()


@router.post("/", response_model=BranchInDB, status_code=201)
def create_branch(
    data: BranchCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Yangi filial yaratish (faqat ega/admin)"""
    tenant_id = resolve_tenant_id(db, current_user)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant aniqlanmadi")

    # Bu tenantda birinchi filialmи — default qilish
    existing = db.query(Branch).filter(Branch.tenant_id == tenant_id).count()
    branch = Branch(
        tenant_id=tenant_id,
        name=data.name,
        address=data.address,
        phone=data.phone,
        is_default=(existing == 0),
    )
    db.add(branch)
    db.commit()
    db.refresh(branch)
    return branch


@router.patch("/{branch_id}", response_model=BranchInDB)
def update_branch(
    branch_id: int,
    data: BranchUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    branch = _get_branch_or_404(branch_id, current_user, db)

    if data.name is not None:
        branch.name = data.name
    if data.address is not None:
        branch.address = data.address
    if data.phone is not None:
        branch.phone = data.phone
    if data.is_active is not None:
        branch.is_active = data.is_active

    # Default o'rnatilsa — eski defaultni olib tashlash
    if data.is_default:
        db.query(Branch).filter(
            Branch.tenant_id == branch.tenant_id,
            Branch.id != branch_id
        ).update({"is_default": False})
        branch.is_default = True

    db.commit()
    db.refresh(branch)
    return branch


@router.delete("/{branch_id}", status_code=204)
def deactivate_branch(
    branch_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Filialni o'chirib bo'lmaydi — faqat deaktivlash"""
    branch = _get_branch_or_404(branch_id, current_user, db)
    if branch.is_default:
        raise HTTPException(status_code=400, detail="Asosiy filial o'chirilmaydi")
    branch.is_active = False
    db.commit()
