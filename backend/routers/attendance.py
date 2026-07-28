from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional

from database import get_db
from models import Attendance, Employee, User
from schemas import MessageResponse
from deps import get_current_user, get_current_active_user, apply_tenant_filter
from core.security import verify_pin

router = APIRouter()

@router.get("/")
async def get_attendances(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    employee_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Davomat ro'yxatini olish"""
    query = db.query(Attendance)
    # BOSQICH 1.5: tenant bo'yicha cheklash
    query = apply_tenant_filter(query, Attendance, current_user)

    if employee_id:
        query = query.filter(Attendance.employee_id == employee_id)

    if date_from:
        from_date = datetime.fromisoformat(date_from.split('T')[0])
        query = query.filter(Attendance.check_in >= from_date)

    if date_to:
        to_date = datetime.fromisoformat(date_to.split('T')[0]) + timedelta(days=1)
        query = query.filter(Attendance.check_in < to_date)

    total = query.count()
    attendances = query.order_by(Attendance.check_in.desc()).offset((page - 1) * page_size).limit(page_size).all()

    result = []
    for a in attendances:
        employee = db.query(Employee).filter(Employee.id == a.employee_id).first()
        result.append({
            "id": a.id,
            "employee_id": a.employee_id,
            "employee_name": employee.full_name if employee else None,
            "check_in": a.check_in,
            "check_out": a.check_out,
            "hours_worked": a.hours_worked,
            "status": a.status,
            "notes": a.notes,
            "created_at": a.created_at
        })

    return {
        "items": result,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }

@router.post("/check-in")
async def check_in(
    employee_id: int,
    pin_code: Optional[str] = None,
    notes: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Ishga kelish (PIN orqali autentifikatsiya, JWT ixtiyoriy)"""
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Xodim topilmadi")

    if employee.hashed_pin and not verify_pin(pin_code or "", employee.hashed_pin):
        raise HTTPException(status_code=400, detail="Noto'g'ri PIN kod")

    today = datetime.now().date()
    existing = db.query(Attendance).filter(
        Attendance.employee_id == employee_id,
        Attendance.check_in >= today,
        Attendance.check_in < today + timedelta(days=1)
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Bugun allaqachon check-in qilingan")

    # BOSQICH 1.5: tenant_id xodimdan olinadi (JWT bo'lmasa ham to'g'ri birikadi)
    attendance = Attendance(
        employee_id=employee_id,
        check_in=datetime.now(),
        status="present",
        notes=notes,
        tenant_id=employee.tenant_id
    )
    db.add(attendance)
    db.commit()
    db.refresh(attendance)

    return {
        "success": True,
        "attendance_id": attendance.id,
        "check_in": attendance.check_in,
        "message": "Check-in muvaffaqiyatli"
    }

@router.post("/check-out")
async def check_out(
    employee_id: int,
    pin_code: Optional[str] = None,
    notes: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Ishdan ketish (PIN orqali autentifikatsiya, JWT ixtiyoriy)"""
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Xodim topilmadi")

    if employee.hashed_pin and not verify_pin(pin_code or "", employee.hashed_pin):
        raise HTTPException(status_code=400, detail="Noto'g'ri PIN kod")

    today = datetime.now().date()
    attendance = db.query(Attendance).filter(
        Attendance.employee_id == employee_id,
        Attendance.check_in >= today,
        Attendance.check_in < today + timedelta(days=1),
        Attendance.check_out.is_(None)
    ).first()

    if not attendance:
        raise HTTPException(status_code=400, detail="Bugungi check-in topilmadi")

    attendance.check_out = datetime.now()
    delta = attendance.check_out - attendance.check_in
    attendance.hours_worked = round(delta.total_seconds() / 3600, 2)
    if notes:
        attendance.notes = (attendance.notes or "") + "\n" + notes

    db.commit()

    return {
        "success": True,
        "check_out": attendance.check_out,
        "hours_worked": attendance.hours_worked,
        "message": "Check-out muvaffaqiyatli"
    }

@router.get("/today")
async def get_today_attendance(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Bugungi davomat"""
    today = datetime.now().date()
    query = db.query(Attendance).filter(
        Attendance.check_in >= today,
        Attendance.check_in < today + timedelta(days=1)
    )
    # BOSQICH 1.5: tenant bo'yicha cheklash
    query = apply_tenant_filter(query, Attendance, current_user)
    attendances = query.all()

    result = []
    for a in attendances:
        employee = db.query(Employee).filter(Employee.id == a.employee_id).first()
        result.append({
            "id": a.id,
            "employee_id": a.employee_id,
            "employee_name": employee.full_name if employee else None,
            "check_in": a.check_in,
            "check_out": a.check_out,
            "hours_worked": a.hours_worked,
            "status": a.status
        })

    return result

@router.get("/employee/{employee_id}/summary")
async def get_employee_summary(
    employee_id: int,
    month: Optional[int] = None,
    year: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Xodim oylik hisoboti"""
    if not month:
        month = datetime.now().month
    if not year:
        year = datetime.now().year

    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1)
    else:
        end_date = datetime(year, month + 1, 1)

    query = db.query(Attendance).filter(
        Attendance.employee_id == employee_id,
        Attendance.check_in >= start_date,
        Attendance.check_in < end_date
    )
    # BOSQICH 1.5: tenant bo'yicha cheklash
    query = apply_tenant_filter(query, Attendance, current_user)
    attendances = query.all()

    total_hours = sum(a.hours_worked or 0 for a in attendances)
    days_present = len([a for a in attendances if a.status == "present"])
    days_late = len([a for a in attendances if a.status == "late"])
    days_absent = 0

    return {
        "employee_id": employee_id,
        "month": month,
        "year": year,
        "total_hours": round(total_hours, 2),
        "days_present": days_present,
        "days_late": days_late,
        "days_absent": days_absent
    }

