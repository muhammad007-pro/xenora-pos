from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from config import settings
import hashlib
import hmac as _hmac

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Parolni tekshirish"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Parolni hash qilish"""
    return pwd_context.hash(password)

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Access token yaratish"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: Dict[str, Any]) -> str:
    """Refresh token yaratish"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def verify_token(token: str, token_type: str = "access") -> Optional[Dict[str, Any]]:
    """Tokenni tekshirish"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != token_type:
            return None
        return payload
    except JWTError:
        return None

def verify_access_token(token: str) -> Optional[Dict[str, Any]]:
    return verify_token(token, "access")

def verify_refresh_token(token: str) -> Optional[Dict[str, Any]]:
    return verify_token(token, "refresh")

def hash_pin(pin: str) -> str:
    """4 xonali PIN ni HMAC-SHA256 bilan hash qilish"""
    h = _hmac.new(settings.SECRET_KEY.encode(), pin.encode(), hashlib.sha256)
    return h.hexdigest()

def verify_pin(plain_pin: str, stored_hash: str) -> bool:
    """PIN to'g'riligini tekshirish"""
    return _hmac.compare_digest(hash_pin(plain_pin), stored_hash)