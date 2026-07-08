"""Audit log o'qish — xodimlar faoliyati jurnali (egasi/menejer ko'radi).

MUHIM: tenant-izolyatsiya — cafe admin FAQAT o'z tenant auditини ko'radi
(apply_tenant_filter). Superadmin/platforma egasi hammasini.
RBAC: view_reports (admin/manager — kassir/ofitsiantда yo'q).
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from database import get_db
from models import AuditLog, User
from deps import has_permission, apply_tenant_filter

router = APIRouter()


@router.get("")
@router.get("/")
async def list_audit_logs(
    user_id:   Optional[int] = Query(None, description="Xodim bo'yicha filtr"),
    resource:  Optional[str] = Query(None, description="orders|products|shifts|returns|auth"),
    action:    Optional[str] = Query(None, description="CREATE|UPDATE|DELETE|RETURN|LOGIN"),
    date_from: Optional[datetime] = Query(None),
    date_to:   Optional[datetime] = Query(None),
    page:      int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports")),
):
    """Audit yozuvlari — tenant-scoped, filtrlangan, sahifalangan."""
    q = apply_tenant_filter(db.query(AuditLog), AuditLog, current_user)

    if user_id is not None:
        q = q.filter(AuditLog.user_id == user_id)
    if resource:
        q = q.filter(AuditLog.resource == resource)
    if action:
        q = q.filter(AuditLog.action == action.upper())
    if date_from is not None:
        q = q.filter(AuditLog.created_at >= date_from)
    if date_to is not None:
        q = q.filter(AuditLog.created_at <= date_to)

    total = q.count()
    rows = (
        q.order_by(AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    # User ismlarini bir so'rovda olish (N+1 yo'q)
    uids = {r.user_id for r in rows if r.user_id is not None}
    names = {}
    if uids:
        for u in db.query(User.id, User.full_name, User.username).filter(User.id.in_(uids)).all():
            names[u.id] = u.full_name or u.username or f"#{u.id}"

    items = [{
        "id":          r.id,
        "user_id":     r.user_id,
        "user_name":   names.get(r.user_id, "—") if r.user_id else "—",
        "resource":    r.resource,
        "action":      r.action,
        "resource_id": r.resource_id,
        "detail":      r.detail,
        "ip_address":  r.ip_address,
        "created_at":  r.created_at.isoformat() if r.created_at else None,
    } for r in rows]

    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/staff")
async def audit_staff_list(
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports")),
):
    """Filtr uchun — audit yozган xodimlar ro'yxati (tenant-scoped)."""
    q = apply_tenant_filter(db.query(AuditLog.user_id), AuditLog, current_user)
    uids = {row[0] for row in q.distinct().all() if row[0] is not None}
    if not uids:
        return []
    users = db.query(User.id, User.full_name, User.username).filter(User.id.in_(uids)).all()
    return [{"id": u.id, "name": u.full_name or u.username or f"#{u.id}"} for u in users]
