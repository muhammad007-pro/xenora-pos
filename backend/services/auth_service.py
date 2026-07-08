from sqlalchemy.orm import Session
from sqlalchemy import or_
from datetime import datetime
from typing import Optional

from models import User
from schemas import UserCreate
from core.security import get_password_hash, verify_password, hash_pin
from utils.helpers import normalize_phone

class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def authenticate_by_pin(
        self,
        pin: str,
        branch_id: Optional[int] = None,
        tenant_id: Optional[int] = None,
    ) -> Optional[User]:
        """4 xonali PIN bilan foydalanuvchini topish.

        XAVFSIZLIK: PIN qidiruvi `tenant_id` (cafe) ichida cheklanadi — bir
        magazin kassiri boshqa magazin PIN bazasiga tushib qolmaydi. Tenant
        ko'rsatilmasa (None) — qidiruv rad etiladi (global qidiruv yo'q).
        """
        if not pin or len(pin) != 4 or not pin.isdigit():
            return None
        if tenant_id is None:
            # Tenant izolyatsiyasi majburiy — tenantsiz global qidiruvga yo'l yo'q
            return None
        pin_hash = hash_pin(pin)
        query = self.db.query(User).filter(
            User.hashed_pin == pin_hash,
            User.is_active == True,
            User.tenant_id == tenant_id,
        )
        if branch_id:
            # Filial aniqligi — lekin tenantga tegishli (null filialli xodimni ham qamrab)
            query = query.filter(or_(User.branch_id == branch_id, User.branch_id.is_(None)))
        return query.first()

    def authenticate_user(self, phone: str, password: str) -> Optional[User]:
        """Foydalanuvchini TELEFON RAQAM + parol bilan autentifikatsiya qilish (BOSQICH 38).

        Telefon normalize qilinadi (+998XXXXXXXXX) — saqlangani bilan bir xil formatda
        solishtirilsin. (Avval username bilan edi; endi telefon asosiy login kaliti.)
        """
        norm = normalize_phone(phone)
        if not norm:
            return None
        user = self.db.query(User).filter(User.phone == norm).first()
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    def get_user_by_phone(self, phone: str) -> Optional[User]:
        """Telefon bo'yicha foydalanuvchini topish (normalize qilingan)"""
        norm = normalize_phone(phone)
        if not norm:
            return None
        return self.db.query(User).filter(User.phone == norm).first()

    def create_user(self, user_data: UserCreate) -> User:
        """Yangi foydalanuvchi yaratish"""
        pin_hash = None
        if user_data.pin:
            if len(user_data.pin) == 4 and user_data.pin.isdigit():
                pin_hash = hash_pin(user_data.pin)
        user = User(
            username=user_data.username,
            email=user_data.email,
            full_name=user_data.full_name,
            phone=normalize_phone(user_data.phone),
            hashed_password=get_password_hash(user_data.password),
            hashed_pin=pin_hash,
            role_id=user_data.role_id,
            branch_id=user_data.branch_id,
            tenant_id=user_data.tenant_id,  # BOSQICH 2.1: tenant biriktiriladi
            is_active=True
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user
    
    def get_user_by_email(self, email: str) -> Optional[User]:
        """Email bo'yicha foydalanuvchini topish"""
        return self.db.query(User).filter(User.email == email).first()
    
    def get_user_by_username(self, username: str) -> Optional[User]:
        """Username bo'yicha foydalanuvchini topish"""
        return self.db.query(User).filter(User.username == username).first()
    
    def update_last_login(self, user: User):
        """Oxirgi login vaqtini yangilash"""
        user.last_login = datetime.now()
        self.db.commit()
    
    def change_password(self, user: User, new_password: str) -> bool:
        """Parolni o'zgartirish"""
        try:
            user.hashed_password = get_password_hash(new_password)
            self.db.commit()
            return True
        except Exception:
            return False
    
    def check_password(self, user: User, password: str) -> bool:
        """Parolni tekshirish"""
        return verify_password(password, user.hashed_password)