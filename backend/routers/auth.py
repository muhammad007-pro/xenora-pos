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
from core.feature_flags import resolve_enabled_features
from core.audit import log_audit  # xodim harakatlarini yozish (audit)
from services.auth_service import AuthService
from deps import get_current_user, get_current_active_user


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
    db: Session = Depends(get_db)
):
    """Yangi foydalanuvchi ro'yxatdan o'tkazish (BOSQICH 38: telefon majburiy + unikal)"""
    from utils.helpers import normalize_phone
    auth_service = AuthService(db)

    # Parol — minimal uzunlik (change-password bilan bir xil qoida)
    if not user_data.password or len(user_data.password) < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Parol kamida 6 belgidan iborat bo'lishi kerak")

    # Telefon — asosiy login kaliti: majburiy + unikal
    norm_phone = normalize_phone(user_data.phone)
    if not norm_phone:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Telefon raqam majburiy")
    if db.query(User).filter(User.phone == norm_phone).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bu telefon band")

    # Username/email — ixtiyoriy; berilgan bo'lsa unikallik tekshiriladi
    if user_data.username and db.query(User).filter(User.username == user_data.username).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bu username band")
    if user_data.email and db.query(User).filter(User.email == user_data.email).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bu email band")

    user = auth_service.create_user(user_data)
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
    current_user: User = Depends(get_current_user)
):
    """Joriy foydalanuvchi ma'lumotlari"""
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Parolni o'zgartirish"""
    if not verify_password(old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Eski parol noto'g'ri"
        )
    
    if len(new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Yangi parol kamida 6 belgidan iborat bo'lishi kerak"
        )
    
    current_user.hashed_password = get_password_hash(new_password)
    db.commit()
    
    return MessageResponse(message="Parol muvaffaqiyatli o'zgartirildi")