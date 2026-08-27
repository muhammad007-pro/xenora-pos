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
    """Request'dan mijoz IP manzilini ajratib oladi (yo'q bo'lsa None).

    ⚠️ SOXTALASHTIRISHGA CHIDAMLILIK — tartib TASODIFIY EMAS:

    1. `X-Real-IP` — bizning nginx uni `$remote_addr` bilan **QAYTA YOZADI**
       (`proxy_set_header X-Real-IP $remote_addr`). Mijoz yuborgan qiymat
       o'chib ketadi → ISHONCHLI. Shuning uchun birinchi o'rinda.

    2. `X-Forwarded-For` — nginx `$proxy_add_x_forwarded_for` ishlatadi, u
       mijoz sarlavhasiga haqiqiy IP ni **QO'SHIB QO'YADI**:
           mijoz "X-Forwarded-For: 1.2.3.4" yuborsa → "1.2.3.4, <haqiqiy_ip>"
       Ya'ni **BIRINCHI bo'g'in mijoz nazoratida** — uni olish audit jurnalini
       soxtalashtirish imkonini berardi (eski kod aynan shunday qilardi).
       Shu sababli **OXIRGI** bo'g'in olinadi — uni bizning nginx qo'ygan.

    3. `request.client.host` — proxy sarlavhalari bo'lmasa (to'g'ridan-to'g'ri
       ulanish, testlar).
    """
    try:
        if request is None:
            return None

        real = request.headers.get("x-real-ip")
        if real and real.strip():
            return real.strip()[:45]

        xff = request.headers.get("x-forwarded-for")
        if xff:
            hops = [h.strip() for h in xff.split(",") if h.strip()]
            if hops:
                return hops[-1][:45]   # OXIRGI — nginx qo'shgani; birinchisi soxta bo'lishi mumkin

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
    user_agent: Optional[str] = None,
) -> None:
    """Audit yozuvini ALOHIDA sessiyada saqlaydi (asosiy amalni buzmaydi).

    `user` — User obyekti (yoki None). tenant_id berilmasa user.tenant_id olinadi.

    IP va User-Agent AVTOMATIK to'ldiriladi (RequestIDMiddleware o'rnatgan
    ContextVar'dan) — chaqiruvchi hech narsa uzatishi shart emas. Aynan shu
    sababli 2026-08-27 gacha `ip_address` hamma joyda NULL edi: `client_ip()`
    yozilgan-u, 18 ta chaqiruv joyining birortasi uni uzatmasdi.
    Aniq qiymat uzatilsa — u ustun turadi.
    """
    try:
        from database import SessionLocal
        from models import AuditLog
        from core.logger import client_ip_var, user_agent_var

        uid = getattr(user, "id", None) if user is not None else None
        tid = tenant_id
        if tid is None and user is not None:
            tid = getattr(user, "tenant_id", None)

        # So'rov konteksti (middleware o'rnatgan). Fon vazifasi/CLI da — None.
        if ip_address is None:
            ip_address = client_ip_var.get(None)
        if user_agent is None:
            user_agent = user_agent_var.get(None)

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
                user_agent=(user_agent[:255] if user_agent else None),
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
