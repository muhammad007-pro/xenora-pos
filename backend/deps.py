from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import JWTError
from typing import Optional

from database import get_db
from models import User
from core.security import verify_access_token
from config import settings

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login",
    auto_error=False
)

async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Joriy foydalanuvchini olish"""
    if not token:
        return None

    payload = verify_access_token(token)
    if not payload:
        return None

    # BOSQICH 38: JWT `sub` endi user.id (telefon-login). user_id bo'yicha resolve.
    uid = payload.get("user_id") or payload.get("sub")
    if uid is None:
        return None
    try:
        user = db.query(User).filter(User.id == int(uid)).first()
    except (TypeError, ValueError):
        return None
    if not user or not user.is_active:
        return None

    # JWT dan active_branch_id ni user ob'ektiga vaqtincha o'rnating
    # (DB ga yozmaydi — faqat request davomida ishlatiladi)
    user._active_branch_id = payload.get("branch_id")

    return user

async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Faol foydalanuvchini tekshirish"""
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autentifikatsiya talab qilinadi",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user

async def get_current_superuser(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """Superuser tekshirish"""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu amal uchun admin huquqi kerak"
        )
    return current_user

async def get_tenant_id(
    current_user: User = Depends(get_current_active_user)
) -> Optional[int]:
    """
    Joriy foydalanuvchining tenant (kafe) identifikatori (BOSQICH 1.5).
    Superuser/platforma egasida tenant_id = NULL bo'ladi — u barcha
    tenantlarni ko'ra oladi (filtr qo'llanmaydi, qarang: apply_tenant_filter).
    """
    return current_user.tenant_id


def resolve_tenant_id(db: Session, current_user: User) -> Optional[int]:
    """
    Yangi yozuv yaratishda tenant_id ni aniqlash (super-admin tenant fix).

    - Oddiy foydalanuvchi — har doim o'z tenant'i.
    - Superuser/platforma egasi (tenant_id=NULL) yozuv yaratsa:
      tizimda YAGONA faol kafe bo'lsa — yozuv o'sha kafega biriktiriladi
      (aks holda NULL qoladi, chunki qaysi kafega tegishli ekani noma'lum —
      multi-kafe platformada yozuvlarni kafe admini yaratishi kerak).
    """
    if current_user.tenant_id is not None:
        return current_user.tenant_id
    from models import Cafe
    ids = db.query(Cafe.id).filter(Cafe.is_active == True).limit(2).all()
    return ids[0][0] if len(ids) == 1 else None


def apply_tenant_filter(query, model, current_user: User):
    """
    So'rovni joriy foydalanuvchi tenant'i bo'yicha cheklaydi (multi-tenant izolyatsiya).

    - Superuser yoki tenant_id=NULL (platforma egasi) — cheklanmaydi,
      barcha tenantlar ma'lumotini ko'radi.
    - Oddiy foydalanuvchi — faqat o'z tenant'iga (`model.tenant_id`) tegishli
      yozuvlarni ko'radi, boshqa tenant ma'lumotini KO'RA OLMAYDI (ARCHITECTURE.md, 6-bo'lim).
    """
    if current_user.is_superuser or current_user.tenant_id is None:
        return query
    return query.filter(model.tenant_id == current_user.tenant_id)


def apply_branch_filter(query, model, current_user: User):
    """
    So'rovni joriy foydalanuvchi aktiv filiali bo'yicha cheklaydi.

    - Ega/superuser va branch_id=None — hamma filiallar ko'rinadi.
    - Xodim yoki ega specific filial tanlagan — faqat shu filial ma'lumotlari.
    - JWT da saqlangan _active_branch_id ishlatiladi (login/switch-branch orqali o'rnatiladi).
    """
    if not hasattr(model, 'branch_id'):
        return query
    active_branch = getattr(current_user, '_active_branch_id', None)
    if active_branch is None:
        return query
    return query.filter(model.branch_id == active_branch)


def user_has_permission(user: User, permission_code: str) -> bool:
    """current_user'da ruxsat bor-yo'qligini tekshiradi (xato tashlamaydi).

    Runtime'da shartli RBAC uchun (masalan /export?report_type=profit yoki
    /inventory tannarxni faqat view_finance'li userga ko'rsatish). has_permission
    dependency bilan bir xil mantiq, lekin bool qaytaradi."""
    if user.is_superuser:
        return True
    if user.role:
        return permission_code in [p.code for p in user.role.permissions]
    return False


def has_permission(permission_code: str):
    """Ruxsat tekshirish decorator"""
    async def permission_checker(
        current_user: User = Depends(get_current_active_user)
    ) -> User:
        if current_user.is_superuser:
            return current_user
        
        if current_user.role:
            permissions = [p.code for p in current_user.role.permissions]
            if permission_code not in permissions:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"'{permission_code}' ruxsati yo'q"
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Ruxsatlar topilmadi"
            )
        
        return current_user
    
    return permission_checker