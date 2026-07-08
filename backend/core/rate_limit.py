"""IP bo'yicha rate limiting — brute-force va DDoS yumshatish (tashqi bog'liqliksiz).

Oddiy in-memory sliding-window (deque). Bir jarayonli deploy uchun mos.
Ko'p worker/instance'da umumiy hisoblagich uchun kelajakda Redis kerak — hozircha
har jarayon o'z hisobini yuritadi (baribir brute-force'ni sezilarli cheklaydi).

Ikki qatlam:
  - AUTH (login / pin-login / register / change-password): QAT'IY — parol/PIN terishni cheklaydi.
    PIN 4 xonali (10 000 variant) bo'lgani uchun bu himoya MUHIM.
  - UMUMIY (/api va /public): yumshoq ceiling — DDoS/flood yumshatish. SPA sahifa yuklanganda
    ko'p so'rov yuboradi, shuning uchun limit saxiy (mavjud ilova buzilmasin).
"""
import time
import logging
from collections import defaultdict, deque
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings

logger = logging.getLogger(__name__)

# Qat'iy cheklovli auth endpointlari (brute-force nishoni)
_AUTH_SUFFIXES = ("/auth/login", "/auth/pin-login", "/auth/register", "/auth/change-password")

# Cheklovdan ozod: statik fayllar, health, websocket, favicon
_SKIP_PREFIXES = ("/static", "/uploads", "/frontend", "/ws")
_SKIP_EXACT = {"/health", "/", "/favicon.ico"}

# Cheklovdan ozod IP'lar: TestClient (pytest) — testlar buzilmasin.
# request.client.host soket peer'i (header emas) → soxtalashtirib bo'lmaydi, xavfsiz.
_EXEMPT_IPS = {"testclient"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limit (IP boshiga, daqiqada)."""

    def __init__(self, app):
        super().__init__(app)
        self._auth_hits: dict[str, deque] = defaultdict(deque)
        self._gen_hits: dict[str, deque] = defaultdict(deque)

    @staticmethod
    def _client_ip(request: Request) -> str:
        # Proxy (nginx) ortida haqiqiy IP X-Forwarded-For'ning birinchi bo'g'inida
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    @staticmethod
    def _allow(bucket: deque, limit: int, now: float, window: float = 60.0) -> bool:
        cutoff = now - window
        while bucket and bucket[0] < cutoff:   # eskirgan yozuvlarni tozalash
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True

    async def dispatch(self, request: Request, call_next):
        # OPTIONS (CORS preflight) va o'chiq rejim — o'tkazib yuboriladi
        if not settings.RATE_LIMIT_ENABLED or request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        if path in _SKIP_EXACT or any(path.startswith(p) for p in _SKIP_PREFIXES):
            return await call_next(request)

        ip = self._client_ip(request)
        if ip in _EXEMPT_IPS:
            return await call_next(request)

        now = time.time()

        # 1) Auth endpointlari — qat'iy
        if any(path.endswith(s) for s in _AUTH_SUFFIXES):
            if not self._allow(self._auth_hits[ip], settings.RATE_LIMIT_AUTH_PER_MIN, now):
                logger.warning("RATE LIMIT (auth) %s %s ← %s", request.method, path, ip)
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Juda ko'p urinish. Iltimos, bir daqiqadan so'ng qayta urining."},
                    headers={"Retry-After": "60"},
                )

        # 2) Umumiy /api va /public ceiling — DDoS yumshatish
        if path.startswith(settings.API_V1_STR) or path.startswith("/public"):
            if not self._allow(self._gen_hits[ip], settings.RATE_LIMIT_GENERAL_PER_MIN, now):
                logger.warning("RATE LIMIT (general) %s %s ← %s", request.method, path, ip)
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Juda ko'p so'rov. Biroz kuting."},
                    headers={"Retry-After": "30"},
                )

        return await call_next(request)
