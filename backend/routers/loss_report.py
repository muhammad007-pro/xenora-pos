"""
Zarar Hisoboti router — BOSQICH 25
Utilizatsiya + brak tovarlar bo'yicha jami zarar hisoboti.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import date as Date
from typing import Optional
from collections import defaultdict

from database import get_db
from models import WriteOff, WriteOffItem, User
from schemas import LossReportSummary, LossReportItem
from deps import get_current_active_user, apply_tenant_filter, has_permission

from deps import require_feature  # funksiya-flag himoyasi (O'ZGARISH 3)
router = APIRouter(dependencies=[Depends(require_feature("loss_report"))])


@router.get("/", response_model=LossReportSummary)
async def get_loss_report(
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    reason:    Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports")),
):
    today = Date.today()
    d_from = Date.fromisoformat(date_from) if date_from else Date(today.year, today.month, 1)
    d_to   = Date.fromisoformat(date_to)   if date_to   else today

    q = apply_tenant_filter(db.query(WriteOff), WriteOff, current_user) \
            .filter(WriteOff.status == "confirmed") \
            .filter(WriteOff.write_off_date >= d_from) \
            .filter(WriteOff.write_off_date <= d_to)
    if reason:
        q = q.filter(WriteOff.reason == reason)

    write_offs = q.all()

    total_loss = 0.0
    by_reason: dict = defaultdict(float)
    items: list[LossReportItem] = []

    for wo in write_offs:
        for item in wo.items:
            total_loss += item.total_loss
            by_reason[wo.reason] += item.total_loss
            items.append(LossReportItem(
                product_id   = item.product_id,
                product_name = item.product.name if item.product else f"#{item.product_id}",
                reason       = wo.reason,
                quantity     = item.quantity,
                total_loss   = item.total_loss,
                date         = wo.write_off_date,
            ))

    items.sort(key=lambda x: x.total_loss, reverse=True)

    return LossReportSummary(
        period_from = d_from,
        period_to   = d_to,
        total_loss  = total_loss,
        by_reason   = dict(by_reason),
        items       = items,
    )
