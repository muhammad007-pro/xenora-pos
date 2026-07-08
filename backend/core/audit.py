"""
Audit log — kim qaysi resurs ustida qanday amal bajarganini yozib boradi.

MUHIM (xavfsizlik): audit yozuvi ALOHIDA DB sessiyasida yoziladi — shuning uchun
audit xatosi yoki commiti asosiy endpoint tranzaksiyasiga TA'SIR QILMAYDI
(asosiy amal har doim davom etadi). Hech qachon chaqiruvchini buzmaydi.

Foydalanish:
    from core.audit import log_audit

    @router.delete("/{order_id}")
    async def delete_order(order_id, request: Request, db, current_user):
        ...
        log_audit(current_user, "orders", "DELETE", order_id,
                  detail={"total": order.final_amount}, ip_address=client_ip(request))
"""
import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)


def client_ip(request) -> Optional[str]:
    """Request'dan IP manzilni xavfsiz ajratib oladi (yo'q bo'lsa None)."""
    try:
        if request is None:
            return None
        # reverse-proxy orqasida bo'lsa X-Forwarded-For birinchi IP
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()[:45]
        return (request.client.host if request.client else None)
    except Exception:
        return None


def log_audit(
    user: Any,
    resource: str,
    action: str,                       # CREATE | UPDATE | DELETE | LOGIN | LOGOUT | RETURN
    resource_id: Optional[Any] = None,
    detail: Optional[dict] = None,
    ip_address: Optional[str] = None,
    tenant_id: Optional[int] = None,
) -> None:
    """Audit yozuvini ALOHIDA sessiyada saqlaydi (asosiy amalni buzmaydi).

    `user` — User obyekti (yoki None). tenant_id berilmasa user.tenant_id olinadi.
    """
    try:
        from database import SessionLocal
        from models import AuditLog

        uid = getattr(user, "id", None) if user is not None else None
        tid = tenant_id
        if tid is None and user is not None:
            tid = getattr(user, "tenant_id", None)

        adb = SessionLocal()
        try:
            adb.add(AuditLog(
                tenant_id=tid,
                user_id=uid,
                resource=resource,
                action=action,
                resource_id=str(resource_id) if resource_id is not None else None,
                detail=detail,
                ip_address=ip_address,
            ))
            adb.commit()
        finally:
            adb.close()
    except Exception:
        # Audit hech qachon asosiy amalni buzmasligi kerak
        logger.exception("Audit yozishda xato (asosiy amal davom etadi)")


async def audit_log(
    db,
    user_id: int,
    resource: str,
    action: str,
    resource_id: Optional[Any] = None,
    detail: Optional[dict] = None,
) -> None:
    """Eski imzo bilan moslik uchun yupqa o'ramcha (alohida sessiyaga delegatsiya).

    `db` argumenti e'tiborga olinmaydi (audit endi alohida sessiyada yoziladi)."""
    class _U:
        id = user_id
        tenant_id = None
    log_audit(_U(), resource, action, resource_id, detail)
