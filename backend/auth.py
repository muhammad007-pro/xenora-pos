from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta, datetime
from typing import Optional

from database import get_db
from models import User
from schemas import UserCreate, UserLogin, Token, UserInDB, MessageResponse
from core.security import (
    verify_password, get_password_hash,
    create_access_token, create_refresh_token,
    verify_refresh_token
)
from core.exceptions import InvalidCredentialsError, UserNotFoundError
from services.auth_service import AuthService

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

@router.post("/register", response_model=UserInDB)
async def register(
    user_data: UserCreate,
    db: Session = Depends(get_db)
):
    """Yangi foydalanuvchi ro'yxatdan o'tkazish"""
    auth_service = AuthService(db)
    
    # Username tekshirish
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bu username band"
        )
    
    # Email tekshirish
    existing_email = db.query(User).filter(User.email == user_data.email).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bu email band"
        )
    
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
    
    # Token yaratish
    access_token = create_access_token(
        data={"sub": user.username, "user_id": user.id}
    )
    refresh_token = create_refresh_token(
        data={"sub": user.username, "user_id": user.id}
    )
    
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )

@router.post("/refresh", response_model=Token)
async def refresh_token(
    refresh_token: str,
    db: Session = Depends(get_db)
):
    """Tokenni yangilash"""
    payload = verify_refresh_token(refresh_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Yaroqsiz refresh token"
        )
    
    username = payload.get("sub")
    user = db.query(User).filter(User.username == username).first()
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Foydalanuvchi topilmadi yoki faol emas"
        )
    
    access_token = create_access_token(
        data={"sub": user.username, "user_id": user.id}
    )
    new_refresh_token = create_refresh_token(
        data={"sub": user.username, "user_id": user.id}
    )
    
    return Token(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer"
    )

@router.post("/logout", response_model=MessageResponse)
async def logout(
    current_user: User = Depends(get_db)
):
    """Tizimdan chiqish"""
    return MessageResponse(message="Muvaffaqiyatli chiqildi")

@router.get("/me", response_model=UserInDB)
async def get_current_user_info(
    current_user: User = Depends(get_db)
):
    """Joriy foydalanuvchi ma'lumotlari"""
    return current_user

@router.post("/change-password")
async def change_password(
    old_password: str,
    new_password: str,
    current_user: User = Depends(get_db),
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

@router.post("/forgot-password")
async def forgot_password(
    email: str,
    db: Session = Depends(get_db)
):
    """Parolni tiklash so'rovi"""
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
    
    # TODO: Email yuborish logikasi
    reset_token = "123456"  # 6 xonali kod
    
    return MessageResponse(message="Parol tiklash kodi emailga yuborildi")

@router.post("/reset-password")
async def reset_password(
    token: str,
    new_password: str,
    db: Session = Depends(get_db)
):
    """Parolni tiklash"""
    # TODO: Token tekshirish
    if len(new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Parol kamida 6 belgidan iborat bo'lishi kerak"
        )
    
    return MessageResponse(message="Parol muvaffaqiyatli o'zgartirildi")