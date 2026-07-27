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

async def get_current_active_user_no_sub(
    current_user: User = Depends(get_current_user)
) -> User:
    """Faol foydalanuvchi — obuna ENFORCEMENT'siz (xom).

    Faqat autentifikatsiyani talab qiladi. Bloklangan tenant HAM o'ta oladi —
    shuning uchun FAQAT istisno endpointlar uchun (bloklangan do'kon sababni
    ko'rishi / o'z ma'lumotini eksport qilishi kerak bo'lganlar):
      • /cafes/my/subscription (nega bloklangan + qancha to'lash)
      • /backups/my-tenant (o'z ma'lumotini eksport)
    Oddiy endpointlar `get_current_active_user` (enforcement bilan) ishlatadi.
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autentifikatsiya talab qilinadi",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user


def _enforce_subscription(current_user: User, db: Session) -> None:
    """Obuna muddati/holatiga qarab kirishni bloklaydi (KILL-SWITCH ostida).

    - ENFORCE_SUBSCRIPTION=False → hech narsa qilmaydi (dark deploy, hozirgi xulq).
    - Super-admin (is_superuser) va tenant_id=None → HECH QACHON bloklanmaydi.
    - Cafe topilmasa → bloklamaymiz (xavfsizlik: noaniqlik uchun kirish yopilmasin).
    - Bloklangan bo'lsa → 403 {code: SUBSCRIPTION_EXPIRED} (frontend maxsus ekranga o'tadi).
    Arzon: cafe PK (indeksli) bo'yicha bitta so'rov.
    """
    if not settings.ENFORCE_SUBSCRIPTION:
        return
    if current_user.is_superuser or current_user.tenant_id is None:
        return
    from models import Cafe
    from core.subscription import subscription_state
    cafe = db.query(Cafe).filter(Cafe.id == current_user.tenant_id).first()
    if not cafe:
        return
    st = subscription_state(cafe, grace_days=settings.SUBSCRIPTION_GRACE_DAYS)
    if st["blocked"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "SUBSCRIPTION_EXPIRED",
                "message": st["message"],
                "state": st["state"],
            },
        )


async def get_current_active_user(
    current_user: User = Depends(get_current_active_user_no_sub),
    db: Session = Depends(get_db),
) -> User:
    """Faol foydalanuvchi + OBUNA ENFORCEMENT.

    227+ endpoint shu dependency'ni ishlatadi — obuna teshigi bir joyда yopiladi.
    Enforcement KILL-SWITCH ostida (ENFORCE_SUBSCRIPTION=False → ta'sir yo'q).
    """
    _enforce_subscription(current_user, db)
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
    # ILDIZ HIMOYA: current_user None bo'lsa (autentifikatsiyasiz/muddati o'tgan token —
    # get_current_user None qaytaradi) crash bo'lmasin. Tenant yo'q → None. Endpointlar
    # baribir auth talab qilishi kerak (401), bu — ikkinchi qatlam himoya.
    if current_user is None:
        return None
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


def require_feature(feature_code: str):
    """Funksiya (feature-flag) darajasида himoya — RBAC'dan ALOHIDA qatlam.

    Foydalanuvchi tenantиning biznes turи + tarifи shu funksiяни ochmаса 403.
    Ya'ni frontend'да yashiringan begona/PRO funksiянинг endpoint'и ham bloklanadi
    (O'ZGARISH 3: yashirish yetарли emas, backend ham himoyalayди).
    Super-admin bypass. Tenant majburiy."""
    async def feature_checker(
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db),
    ) -> User:
        if current_user.is_superuser:
            return current_user
        if not current_user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu amal uchun tenant kerak",
            )
        from models import Cafe
        from core.feature_flags import is_feature_enabled
        cafe = db.query(Cafe).filter(Cafe.id == current_user.tenant_id).first()
        if not cafe:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kafe topilmadi")
        try:
            ok = is_feature_enabled(
                cafe.business_type, feature_code,
                cafe.enabled_features, cafe.disabled_features, cafe.subscription_plan,
            )
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"Noma'lum funksiya: {feature_code}")
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu funksiya sizning biznes turingiz yoki tarifingizda mavjud emas",
            )
        return current_user

    return feature_checker