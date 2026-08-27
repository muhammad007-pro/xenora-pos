from fastapi import APIRouter, Depends, HTTPException, status, Body
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta, datetime
from typing import Optional, List

from database import get_db
from models import User, Branch, Cafe
from schemas import UserCreate, UserLogin, Token, UserInDB, MessageResponse, PinLoginRequest
from core.security import (
    verify_password, get_password_hash,
    create_access_token, create_refresh_token,
    verify_refresh_token
)
from core.exceptions import InvalidCredentialsError, UserNotFoundError
from core.password_policy import validate_password
from core.feature_flags import resolve_enabled_features
from core.subscription import get_plan_limits, is_within_user_limit
from core.audit import log_audit  # xodim harakatlarini yozish (audit)
from core.role_guard import (
    resolve_target_tenant, assert_can_assign_role, assert_branch_in_tenant,
)
from services.auth_service import AuthService
from deps import get_current_user, get_current_active_user, has_permission


def _build_token_data(user: User, db: Session, branch_id=None) -> dict:
    """JWT uchun to'liq payload: user_id, branch_id, tenant_id, features.

    BOSQICH 38: `sub` endi user.id (barqaror — username/telefon o'zgarsa ham buzilmaydi).
    """
    data: dict = {
        "sub":       str(user.id),
        "user_id":   user.id,
        "branch_id": branch_id,
    }
    if user.tenant_id:
        cafe = db.query(Cafe).filter(Cafe.id == user.tenant_id).first()
        if cafe:
            data["tenant_id"]     = cafe.id
            data["business_type"] = cafe.business_type
            data["features"]      = list(resolve_enabled_features(
                cafe.business_type,
                cafe.enabled_features,
                cafe.disabled_features,
                cafe.subscription_plan,   # PRO tarif → PRO flaglar ochiq (xato #8 ildiz)
            ))
    return data

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

@router.post("/register", response_model=UserInDB)
async def register(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_users")),
):
    """Yangi foydalanuvchi yaratish (telefon + parol bilan kiruvchi hisob).

    ⚠️ XAVFSIZLIK (2026-08-27): bu endpoint ILGARI autentifikatsiyasiz OCHIQ edi va
    tanadagi `tenant_id` + `role_id` ni to'g'ridan-to'g'ri ishlatardi. Natijada
    istalgan odam istalgan do'konga admin bo'lib qo'shila olardi. Endi:
      • `manage_users` ruxsati MAJBURIY (autentifikatsiyasiz → 401, ruxsatsiz → 403);
      • `tenant_id` tanadan OLINMAYDI — server tokendan aniqlaydi (super-admin
        bundan mustasno, u aniq kafe ko'rsatishi shart);
      • `role_id` yaratuvchining ruxsat darajasidan oshib keta olmaydi;
      • `branch_id` faqat o'sha tenant'ning filiali bo'lishi mumkin.

    Mavjud foydalanuvchilarning KIRISHIGA (`/auth/login`, `/auth/pin-login`) ta'sir yo'q —
    faqat YANGI hisob yaratish yopildi. Yangi do'kon (tenant) ochish yo'li o'zgarmadi:
    `POST /super-admin/tenants` (owner paneli, `owner/cafes.html`).
    """
    from utils.helpers import normalize_phone
    auth_service = AuthService(db)

    # 1) Tenant — SERVER aniqlaydi (tanadagi qiymat e'tiborsiz qoldiriladi).
    tenant_id = resolve_target_tenant(db, current_user, user_data.tenant_id)

    # 2) Rol — yaratuvchi o'zidan kuchliroq rol bera olmaydi (imtiyoz oshirish yo'q).
    assert_can_assign_role(db, current_user, user_data.role_id)

    # 3) Filial — faqat shu tenant'niki.
    assert_branch_in_tenant(db, user_data.branch_id, tenant_id)

    # 4) Tarif limiti — `POST /users/` bilan izchil. Aks holda bu endpoint
    #    FREE tarifning foydalanuvchi cheklovini chetlab o'tish yo'li bo'lib qolardi.
    if not current_user.is_superuser:
        cafe = db.query(Cafe).filter(Cafe.id == tenant_id).first()
        if cafe:
            user_count = db.query(User).filter(User.tenant_id == tenant_id).count()
            if not is_within_user_limit(user_count, cafe.subscription_plan):
                limits = get_plan_limits(cafe.subscription_plan)
                raise HTTPException(
                    status_code=402,
                    detail=f"'{cafe.subscription_plan}' tarifi faqat {limits.max_users} ta "
                           f"foydalanuvchiga ruxsat beradi. Tarifni yangilang.",
                )

    # Parol siyosati (8+ belgi, harf+raqam, zaif emas). FAQAT yaratishда — login'da emas.
    validate_password(user_data.password)

    # Telefon — asosiy login kaliti: majburiy + unikal
    norm_phone = normalize_phone(user_data.phone)
    if not norm_phone:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Telefon raqam majburiy")
    if db.query(User).filter(User.phone == norm_phone).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bu telefon band")

    # Username — unikallik TENANT ICHIDA (composite unique: tenant_id + username),
    # `POST /users/` bilan izchil. Ilgari GLOBAL tekshirilardi → boshqa do'konda
    # "admin" bor bo'lsa noto'g'ri "band" xatosi berardi.
    if user_data.username and db.query(User).filter(
        User.username == user_data.username,
        User.tenant_id == tenant_id,
    ).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bu username shu do'konda band")
    if user_data.email and db.query(User).filter(User.email == user_data.email).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bu email band")

    # Tenant'ni tanadan EMAS, server aniqlagan qiymatdan biriktiramiz.
    safe_data = user_data.model_copy(update={"tenant_id": tenant_id})
    user = auth_service.create_user(safe_data)

    log_audit(current_user, "users", "CREATE", user.id, tenant_id=tenant_id, detail={
        "created_username": user.username, "created_phone": user.phone,
        "role_id": user.role_id, "via": "auth/register",
    })
    return user

@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """Tizimga kirish"""
    auth_service = AuthService(db)
    
    user = auth_service.authenticate_user(form_data.username, form_data.password)
    if not user:
        raise InvalidCredentialsError()
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Hisob faol emas"
        )
    
    # Oxirgi login vaqtini yangilash
    user.last_login = datetime.now()
    db.commit()

    # Audit: kim tizimga kirdi
    log_audit(user, "auth", "LOGIN", user.id, tenant_id=user.tenant_id, detail={
        "username": user.username, "phone": user.phone,
    })

    # Filial: xodim o'z filialiga, ega hamma filialga (None)
    branch_id  = user.branch_id
    token_data = _build_token_data(user, db, branch_id)

    access_token  = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data=token_data)

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )

@router.post("/refresh", response_model=Token)
async def refresh_token(
    refresh_token: str = Body(..., embed=True),
    db: Session = Depends(get_db)
):
    """Tokenni yangilash — refresh token bilan yangi access token (JSON body: {"refresh_token": "..."}).

    Frontend access muddati tuganda (401) shu endpointга avtomatik murojaat qiladi —
    xodim qayta login qilmaydi. is_active=False bo'lsa bu yerda ham rad etiladi (admin nazorati).
    """
    payload = verify_refresh_token(refresh_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Yaroqsiz refresh token"
        )
    
    # BOSQICH 38: sub endi user.id
    uid = payload.get("user_id") or payload.get("sub")
    user = db.query(User).filter(User.id == int(uid)).first() if uid else None

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Foydalanuvchi topilmadi yoki faol emas"
        )

    branch_id = user.branch_id
    token_data = _build_token_data(user, db, branch_id)
    access_token = create_access_token(data=token_data)
    new_refresh_token = create_refresh_token(data=token_data)

    return Token(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer"
    )

@router.post("/logout", response_model=MessageResponse)
async def logout(
    current_user: User = Depends(get_current_user)
):
    """Tizimdan chiqish"""
    # Token blacklist qilish logikasi
    return MessageResponse(message="Muvaffaqiyatli chiqildi")

@router.get("/me", response_model=UserInDB)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user)
):
    """Joriy foydalanuvchi ma'lumotlari. Auth TALAB qilinadi — token'siz/muddati
    o'tgan → get_current_active_user toza 401 beradi (ilgari None→500 edi)."""
    return current_user

@router.post("/switch-branch/{branch_id}", response_model=Token)
async def switch_branch(
    branch_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Filial almashtirish — yangi JWT qaytaradi (branch_id = 0 → hamma filial)"""
    active_branch_id: Optional[int] = None

    if branch_id != 0:
        branch = db.query(Branch).filter(Branch.id == branch_id).first()
        if not branch:
            raise HTTPException(status_code=404, detail="Filial topilmadi")
        if branch.tenant_id != current_user.tenant_id and not current_user.is_superuser:
            raise HTTPException(status_code=403, detail="Bu filial sizniki emas")
        active_branch_id = branch_id

    token_data    = _build_token_data(current_user, db, active_branch_id)
    access_token  = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data=token_data)

    return Token(access_token=access_token, refresh_token=refresh_token, token_type="bearer")


# BOSQICH 4: eski ochiq GET /auth/branches endpointи O'CHIRILDI.
# U autentifikatsiyasiz BARCHA tenantlarning filiallarini qaytarardi (maxfiylik teshigi:
# klientlar bir-birini ko'rardi). Frontend endi kod-asosli login ishlatadi (resolve-code +
# pin-login), bu ro'yxatga ehtiyoj yo'q. Bir tenant ichидаги filiallar autentifikatsiyali,
# tenant-scoped /api/v1/branches/ (routers/branch.py) orqali beriladi — u tegilmagan.


@router.get("/resolve-code")
async def resolve_code(code: str, db: Session = Depends(get_db)):
    """Do'kon KIRISH kodi (100.200.N) → bitta do'kon (id, nomi, turi).

    Login sahifasi kod to'g'riligini tekshirib do'kon nomini ko'rsatish uchun.
    RO'YXAT YO'Q — faqat aniq kod bitta do'konni qaytaradi (klientlar bir-birini
    ko'rmaydi). Maxfiy ma'lumot qaytarilmaydi. Kod noto'g'ri → 404."""
    ac = (code or "").strip()
    cafe = db.query(Cafe).filter(Cafe.access_code == ac, Cafe.is_active == True).first() if ac else None
    if not cafe:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Do'kon topilmadi")
    return {"id": cafe.id, "name": cafe.name, "business_type": cafe.business_type}


@router.post("/pin-login", response_model=Token)
async def pin_login(
    data: PinLoginRequest,
    db: Session = Depends(get_db)
):
    """4 xonali PIN kod bilan tizimga kirish (tenant ichida izolyatsiyalangan)"""
    auth_service = AuthService(db)

    # XAVFSIZLIK: tenant (do'kon) aniqlanadi, PIN faqat shu tenant ichida qidiriladi.
    # Yangi usul — do'kon KIRISH kodi (100.200.N); eski usul — branch_id (orqaga moslik).
    tenant_id = None
    branch_id_for_pin = data.branch_id
    if data.access_code:
        cafe = db.query(Cafe).filter(
            Cafe.access_code == data.access_code.strip(), Cafe.is_active == True
        ).first()
        if not cafe:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Do'kon kodi noto'g'ri")
        tenant_id = cafe.id
        branch_id_for_pin = None   # kod bilan — filial ro'yxatisiz
    elif data.branch_id:
        branch = db.query(Branch).filter(Branch.id == data.branch_id).first()
        if not branch:
            raise InvalidCredentialsError()
        tenant_id = branch.tenant_id
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Do'kon kodi yoki filial tanlanishi shart",
        )

    user = auth_service.authenticate_by_pin(
        data.pin, branch_id=branch_id_for_pin, tenant_id=tenant_id
    )
    if not user:
        raise InvalidCredentialsError()
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Hisob faol emas")

    user.last_login = datetime.now()
    db.commit()

    branch_id = user.branch_id
    token_data = _build_token_data(user, db, branch_id)
    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data=token_data)

    return Token(access_token=access_token, refresh_token=refresh_token, token_type="bearer")


@router.post("/change-password")
async def change_password(
    old_password: str,
    new_password: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Parolni o'zgartirish. Auth TALAB — token'siz → 401 (ilgari None→500)."""
    if not verify_password(old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Eski parol noto'g'ri"
        )
    
    validate_password(new_password)   # parol siyosati (yangi parolga)

    current_user.hashed_password = get_password_hash(new_password)
    db.commit()
    
    return MessageResponse(message="Parol muvaffaqiyatli o'zgartirildi")