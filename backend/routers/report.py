from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional
import os

from database import get_db
from models import User, Branch
from deps import get_current_user, get_current_active_user, has_permission, apply_tenant_filter, user_has_permission
from services.report_service import ReportService
from core.timeutils import day_bounds, tenant_now

router = APIRouter()

def _dates(date_from, date_to):
    """Hisobot oralig'i → (boshlanish 00:00.000, tugash 23:59:59.999999) MAHALLIY zonada.

    ═══ TUZATILGAN XATO (P0-3) ═══
    Avval ikkala chegara ham `strptime(...)` = o'sha kun 00:00:00 edi. Chaqiruvchi
    servislar `created_at <= date_to` filtri bilan ishlaydi, ya'ni TUGASH KUNINING
    O'ZI QAMRALMASDI. `report.html` standart holatda `date_from = date_to = bugun`
    yuboradi → "Bugun" foyda/savdo hisoboti HAR DOIM BO'SH (0 so'm) chiqardi va
    buni hech kim xato deb tushunmasdi ("bugun savdo yo'q ekan" deb o'ylanardi).

    Ikkinchi xato: naive `datetime` — server UTC, shuning uchun kun chegarasi
    Toshkent kunidan 5 soat siljirdi. Endi `day_bounds()` (tenant mahalliy,
    aware) ishlatiladi — `/reports/daily` allaqachon shu naqshda ishlaydi.
    """
    today_local = tenant_now().date()
    d_from = (datetime.strptime(date_from, "%Y-%m-%d").date()
              if date_from else today_local - timedelta(days=30))
    d_to   = (datetime.strptime(date_to, "%Y-%m-%d").date()
              if date_to else today_local)

    start, _        = day_bounds(d_from)   # d_from 00:00 (mahalliy)
    _, next_day     = day_bounds(d_to)     # d_to + 1 kun 00:00 (mahalliy)
    # Servislar `<=` ishlatadi → ertangi yarim tunni QAMRAMASLIK uchun 1 mks orqaga.
    return start, next_day - timedelta(microseconds=1)


@router.get("/branches")
async def get_branches_for_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    q = db.query(Branch)
    q = apply_tenant_filter(q, Branch, current_user)
    return [{"id": b.id, "name": b.name} for b in q.all()]


@router.get("/daily")
async def get_daily_report(
    date: Optional[str] = None,
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports"))
):
    svc = ReportService(db)
    # Kunlik chegara TENANT MAHALLIY zonasida (Toshkent) — daily_number bilan izchil.
    # naive datetime.now() UTC yarim tunini berardi (=Toshkent 05:00), kun 5 soat siljirdi.
    target = datetime.strptime(date, "%Y-%m-%d") if date else None
    start, end = day_bounds(target)
    return svc.generate_sales_report(start, end, branch_id, current_user)


@router.get("/sales")
async def get_sales_report(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports"))
):
    svc = ReportService(db)
    df, dt = _dates(date_from, date_to)
    return svc.generate_sales_report(df, dt, branch_id, current_user)


@router.get("/profit")
async def get_profit_report(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_finance"))  # sof foyda/tannarx — faqat egasi (profit.py bilan izchil)
):
    svc = ReportService(db)
    df, dt = _dates(date_from, date_to)
    return svc.generate_profit_report(df, dt, branch_id, current_user)


@router.get("/inventory")
async def get_inventory_report(
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports"))
):
    svc = ReportService(db)
    report = svc.generate_inventory_report(branch_id, current_user)
    # Tannarx (cost) — faqat view_finance'li user ko'radi. Sotuvchi qoldiqni ko'radi,
    # lekin tannarx-qiymat (value/total_value) yashiriladi.
    if not user_has_permission(current_user, "view_finance"):
        report.pop("total_value", None)
        for key in ("items", "low_stock"):
            for it in report.get(key, []):
                it.pop("value", None)
    return report


@router.get("/customers")
async def get_customers_report(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports"))
):
    svc = ReportService(db)
    df, dt = _dates(date_from, date_to)
    return svc.generate_customers_report(df, dt, branch_id, current_user)


@router.get("/products")
async def get_products_report(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports"))
):
    svc = ReportService(db)
    df, dt = _dates(date_from, date_to)
    return svc.generate_products_report(df, dt, limit, branch_id, current_user)


@router.get("/staff")
async def get_staff_report(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports"))
):
    svc = ReportService(db)
    df, dt = _dates(date_from, date_to)
    return svc.generate_staff_report(df, dt, branch_id, current_user)


@router.get("/tax")
async def get_tax_report(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports"))
):
    svc = ReportService(db)
    df, dt = _dates(date_from, date_to)
    return svc.generate_tax_report(df, dt, branch_id, current_user)


@router.get("/shift")
async def get_shift_report(
    shift_id: Optional[int] = None,
    user_id: Optional[int] = None,
    date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports"))
):
    svc = ReportService(db)
    return svc.generate_shift_report(shift_id, user_id, date, current_user)


@router.get("/export")
async def export_report(
    report_type: str = Query(...),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    format: str = Query("excel", pattern="^(csv|excel|pdf)$"),
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports"))
):
    # Foyda hisobotini eksport — faqat view_finance (sof foyda/tannarx). Boshqa
    # turlar (sales/inventory/products/daily) view_reports bilan ishlaydi.
    if report_type == "profit" and not user_has_permission(current_user, "view_finance"):
        raise HTTPException(status_code=403, detail="'view_finance' ruxsati yo'q (foyda hisoboti)")
    svc = ReportService(db)
    df, dt = _dates(date_from, date_to)
    file_path = svc.export_report(report_type, df, dt, format, branch_id, current_user)
    abs_path = os.path.join(os.path.dirname(__file__), '..', file_path.lstrip('/'))
    abs_path = os.path.normpath(abs_path)
    if os.path.exists(abs_path):
        ext = "xlsx" if format == "excel" else format
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if format == "excel" else \
                "application/pdf" if format == "pdf" else "text/csv"
        fname = os.path.basename(abs_path)
        return FileResponse(abs_path, media_type=media, filename=fname)
    return {"file_url": file_path, "report_type": report_type, "format": format}

