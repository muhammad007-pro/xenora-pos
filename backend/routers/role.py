from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from database import get_db
from models import Role, Permission, User
from schemas import RoleCreate, RoleUpdate, RoleInDB, PermissionInDB, PaginatedResponse, MessageResponse
from deps import get_current_user, has_permission, get_current_superuser

router = APIRouter()

# DIQQAT: Rollar global (tenant_id ustuni yo'q) — barcha tenantlar bitta
# rol jadvalidan foydalanadi. Shu sababli rolni O'ZGARTIRISH amallari
# (yaratish/tahrirlash/o'chirish, ruxsat qo'shish/olib tashlash) faqat
# platforma egasiga (super-admin) ruxsat etiladi. Aks holda `manage_roles`
# ruxsatli tenant-admin global rolni o'zgartirsa, o'zgarish BARCHA tenantga
# ta'sir qilardi (izolyatsiya buzilishi). Tenant-admin rollarni faqat
# KO'RA oladi va xodimga TAYINLAY oladi (routers/user.py), lekin
# rolning o'zini o'zgartira olmaydi.

@router.get("/", response_model=List[RoleInDB])
async def get_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_roles"))
):
    """Barcha rollarni olish"""
    roles = db.query(Role).order_by(Role.name).all()
    return [RoleInDB.model_validate(r) for r in roles]

@router.post("/", response_model=RoleInDB)
async def create_role(
    role_data: RoleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
):
    """Yangi rol yaratish (faqat super-admin — rollar global)"""
    existing = db.query(Role).filter(Role.name == role_data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Bu nomdagi rol mavjud")
    
    role = Role(**role_data.model_dump())
    db.add(role)
    db.commit()
    db.refresh(role)
    
    return RoleInDB.model_validate(role)

@router.get("/{role_id}", response_model=RoleInDB)
async def get_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_roles"))
):
    """Rol ma'lumotlarini olish"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Rol topilmadi")
    
    return RoleInDB.model_validate(role)

@router.patch("/{role_id}", response_model=RoleInDB)
async def update_role(
    role_id: int,
    role_data: RoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
):
    """Rolni yangilash (faqat super-admin — rollar global)"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Rol topilmadi")
    
    update_data = role_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(role, field, value)
    
    db.commit()
    db.refresh(role)
    
    return RoleInDB.model_validate(role)

@router.delete("/{role_id}", response_model=MessageResponse)
async def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
):
    """Rolni o'chirish (faqat super-admin — rollar global)"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Rol topilmadi")
    
    # Rolga biriktirilgan foydalanuvchilarni tekshirish
    if role.users:
        raise HTTPException(status_code=400, detail="Bu rolda foydalanuvchilar mavjud")
    
    db.delete(role)
    db.commit()
    
    return MessageResponse(message="Rol o'chirildi")

@router.get("/permissions/all", response_model=List[PermissionInDB])
async def get_all_permissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_roles"))
):
    """Barcha ruxsatlarni olish"""
    permissions = db.query(Permission).order_by(Permission.code).all()
    return [PermissionInDB.model_validate(p) for p in permissions]

@router.post("/{role_id}/permissions/{permission_id}")
async def add_permission_to_role(
    role_id: int,
    permission_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
):
    """Rolga ruxsat qo'shish (faqat super-admin — rollar global)"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Rol topilmadi")
    
    permission = db.query(Permission).filter(Permission.id == permission_id).first()
    if not permission:
        raise HTTPException(status_code=404, detail="Ruxsat topilmadi")
    
    if permission not in role.permissions:
        role.permissions.append(permission)
        db.commit()
    
    return MessageResponse(message="Ruxsat qo'shildi")

@router.delete("/{role_id}/permissions/{permission_id}")
async def remove_permission_from_role(
    role_id: int,
    permission_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
):
    """Roldan ruxsatni o'chirish (faqat super-admin — rollar global)"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Rol topilmadi")
    
    permission = db.query(Permission).filter(Permission.id == permission_id).first()
    if not permission:
        raise HTTPException(status_code=404, detail="Ruxsat topilmadi")
    
    if permission in role.permissions:
        role.permissions.remove(permission)
        db.commit()
    
    return MessageResponse(message="Ruxsat o'chirildi")