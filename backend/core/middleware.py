import time
import uuid
import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from core.logger import request_id_var, client_ip_var, user_agent_var

logger = logging.getLogger(__name__)

# Logga tushmaydigan tez-tez so'raladigan endpointlar
_SKIP_LOG = {"/health", "/", "/favicon.ico"}


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Har so'rovga X-Request-ID header qo'shadi va context'ga yozadi."""

    async def dispatch(self, request: Request, call_next):
        from core.audit import client_ip   # kech import — aylanma bog'liqlik bo'lmasin

        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        token = request_id_var.set(rid)
        # Audit jurnali uchun mijoz IP + User-Agent (chaqiruv joylari tegilmasin).
        ip_token = client_ip_var.set(client_ip(request))
        ua_token = user_agent_var.set((request.headers.get("user-agent") or None))
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
            client_ip_var.reset(ip_token)
            user_agent_var.reset(ua_token)
        response.headers["X-Request-ID"] = rid
        return response


class LoggingMiddleware(BaseHTTPMiddleware):
    """So'rov/javob loglovchi — jarayon vaqti bilan."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _SKIP_LOG:
            return await call_next(request)

        t0 = time.perf_counter()
        response = await call_next(request)
        ms = (time.perf_counter() - t0) * 1000

        level = logging.WARNING if response.status_code >= 400 else logging.INFO
        logger.log(
            level,
            "%s %s → %d  %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            ms,
        )
        response.headers["X-Process-Time"] = f"{ms:.1f}ms"
        return response


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Tutilmagan istisnolarni JSON javobga aylantiradi."""

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            logger.exception(
                "Unhandled exception on %s %s", request.method, request.url.path
            )
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"},
                headers={"X-Request-ID": request_id_var.get("-")},
            )
