import os
import secrets
from typing import List, Optional
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

# Dev'dagi test super-admin paroli. Production'da AYNAN shu qiymat bloklanadi
# (deploy'da .env'da o'zgartirilishi shart — pastdagi production_checks).
DEFAULT_SUPERUSER_PASSWORD = "admin4770"


class Settings(BaseSettings):
    # ── Loyiha ──────────────────────────────────────────────────────────────
    PROJECT_NAME: str = "RestoPOS"
    # Backend versiya — yagona manba. /health va / (root) shu qiymatni qaytaradi
    # (hardcoded literal emas). Frontend SW cache versiyasi bilan mos yuritiladi.
    VERSION: str = "1.0.4"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"  # development | staging | production
    TIMEZONE: str = "Asia/Tashkent"

    # ── Ma'lumotlar bazasi (BOSQICH 1.1) ────────────────────────────────────
    DATABASE_URL: str = "postgresql://pos_user:pos_pass123@localhost:5432/restaurant_pos"

    # ── Xavfsizlik ──────────────────────────────────────────────────────────
    SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720   # 12 soat — xodim smenasi buferi (uzoq sessiya)
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30       # xodim: 30 kun; access tugasa avtomatik yangilanadi

    # ── Boshlang'ich super-admin (deploy'da .env orqali beriladi) ────────────
    # Toza bazada startup'da avtomatik yaratiladi (qarang: database.py init_db).
    # DEV: standart qiymatlar ishlaydi — localhost buzilmaydi.
    # DEPLOY MAJBURIY: FIRST_SUPERUSER_PASSWORD ni O'ZGARTIR. Standart parol bilan
    # production ishga tushmaydi (pastdagi production_checks bloklaydi).
    FIRST_SUPERUSER_PHONE: str = "+998949974770"
    FIRST_SUPERUSER_PASSWORD: str = DEFAULT_SUPERUSER_PASSWORD
    FIRST_SUPERUSER_EMAIL: str = "admin@restaurant.uz"
    FIRST_SUPERUSER_NAME: str = "Administrator"
    FIRST_SUPERUSER_USERNAME: str = "admin"

    # ── CORS ────────────────────────────────────────────────────────────────
    # DEPLOY: production'da FAQAT o'z domeningni qo'sh (masalan https://xenora.uz).
    # "*" (hammaga ochiq) ISHLATMA — allow_credentials=True bilan xavfli.
    # .env'da BACKEND_CORS_ORIGINS=["https://xenora.uz","https://www.xenora.uz"] shaklida yoz.
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ]

    # ── Rate limiting (brute-force + DDoS himoya) ───────────────────────────
    # IP boshiga daqiqada. Auth qat'iy (parol/PIN terish), umumiy saxiy (SPA ko'p so'rov yuboradi).
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_AUTH_PER_MIN: int = 20        # login/pin-login/register/change-password
    RATE_LIMIT_GENERAL_PER_MIN: int = 600    # umumiy /api + /public ceiling

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors(cls, v):
        """CORS ro'yxatini .env satridan ham, Python listdan ham qabul qiladi."""
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except Exception:
                return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # ── Fayl yuklash ────────────────────────────────────────────────────────
    MAX_UPLOAD_SIZE: int = 5 * 1024 * 1024  # 5 MB
    UPLOAD_DIR: str = "static/uploads"

    # ── Printer ─────────────────────────────────────────────────────────────
    PRINTER_ENABLED: bool = False
    PRINTER_PORT: str = "COM1"
    PRINTER_BAUD_RATE: int = 9600

    # ── WebSocket ───────────────────────────────────────────────────────────
    WS_HEARTBEAT_INTERVAL: int = 30

    # ── To'lov tizimi — Click ───────────────────────────────────────────────
    CLICK_MERCHANT_ID: str = ""
    CLICK_SERVICE_ID: str = ""
    CLICK_SECRET_KEY: str = ""

    # ── To'lov tizimi — Payme ───────────────────────────────────────────────
    PAYME_MERCHANT_ID: str = ""
    PAYME_KEY: str = ""
    PAYME_TEST_MODE: bool = True

    # ── SMS xabarnomasi ─────────────────────────────────────────────────────
    SMS_API_KEY: str = ""
    SMS_SENDER_ID: str = ""

    # ── Email (SMTP) ────────────────────────────────────────────────────────
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@restopos.uz"

    # ── Zaxira nusxa ────────────────────────────────────────────────────────
    BACKUP_ENABLED: bool = True
    BACKUP_INTERVAL_HOURS: int = 24
    BACKUP_KEEP_DAYS: int = 30

    # ── Paginatsiya ─────────────────────────────────────────────────────────
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    @model_validator(mode="after")
    def production_checks(self) -> "Settings":
        """Production rejimida xavfli standart qiymatlarni bloklash."""
        if self.ENVIRONMENT == "production":
            # SECRET_KEY: kuchsiz/standart kalit bilan production ishga tushmasin
            # (aks holda hakker JWT soxtalashtira oladi). Kalit uzun + tasodifiy bo'lishi shart.
            _weak_markers = ("change", "your-secret", "your-super-secret", "changeme", "example", "secret-key-change")
            _key_low = self.SECRET_KEY.lower()
            if len(self.SECRET_KEY) < 32 or any(m in _key_low for m in _weak_markers):
                raise ValueError(
                    "Production'da SECRET_KEY .env faylida kuchli tasodifiy kalitga "
                    "o'zgartirilishi SHART (kamida 32 belgi). Yaratish: "
                    "python -c \"import secrets; print(secrets.token_hex(32))\""
                )
            if self.DEBUG:
                raise ValueError("Production'da DEBUG=False bo'lishi shart.")
            # FIRST_SUPERUSER_PASSWORD: standart/kuchsiz parol bilan production
            # ishga tushmasin (aks holda hamma biladigan parol bilan platforma egasi
            # akkaunti ochiq qoladi). .env'da kuchli parolga o'zgartirilishi SHART.
            _pwd = self.FIRST_SUPERUSER_PASSWORD or ""
            _weak_pwds = {DEFAULT_SUPERUSER_PASSWORD, "admin", "admin123", "password",
                          "changeme", "12345678", "administrator"}
            if len(_pwd) < 8 or _pwd.lower() in _weak_pwds:
                raise ValueError(
                    "Production'da FIRST_SUPERUSER_PASSWORD .env faylida kuchli parolga "
                    f"o'zgartirilishi SHART (standart '{DEFAULT_SUPERUSER_PASSWORD}' emas, "
                    "kamida 8 belgi, oddiy so'z emas)."
                )
        return self

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()
