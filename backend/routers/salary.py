from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional

from database import get_db
from models import Salary, Employee, Attendance, Expense, User
from schemas import MessageResponse
from deps import resolve_tenant_id, get_current_user, get_current_active_user, has_permission, apply_tenant_filter

router = APIRouter()


def _salary_period_label(salary: Salary) -> str:
    """Maosh davri yorlig'i: '06/2026' ko'rinishida."""
    try:
        return f"{salary.period_start.month:02d}/{salary.period_start.year}"
    except Exception:
        return ""

@router.get("/")
async def get_salaries(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    employee_id: Optional[int] = None,
    is_paid: Optional[bool] = None,
    month: Optional[int] = None,
    year: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports"))
):
    """Ish haqi ro'yxatini olish"""
    query = db.query(Salary)
    # BOSQICH 1.5: tenant bo'yicha cheklash
    query = apply_tenant_filter(query, Salary, current_user)

    if employee_id:
        query = query.filter(Salary.employee_id == employee_id)
    
    if is_paid is not None:
        query = query.filter(Salary.is_paid == is_paid)
    
    if month and year:
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1)
        else:
            end_date = datetime(year, month + 1, 1)
        query = query.filter(Salary.period_start >= start_date, Salary.period_start < end_date)
    
    total = query.count()
    salaries = query.order_by(Salary.period_start.desc()).offset((page - 1) * page_size).limit(page_size).all()
    
    result = []
    for s in salaries:
        employee = db.query(Employee).filter(Employee.id == s.employee_id).first()
        result.append({
            "id": s.id,
            "employee_id": s.employee_id,
            "employee_name": employee.full_name if employee else None,
            "period_start": s.period_start,
            "period_end": s.period_end,
            "total_hours": s.total_hours,
            "hourly_rate": s.hourly_rate,
            "base_salary": s.base_salary,
            "bonus": s.bonus,
            "deduction": s.deduction,
            "total_salary": s.total_salary,
            "is_paid": s.is_paid,
            "paid_at": s.paid_at,
            "notes": s.notes,
            "created_at": s.created_at
        })
    
    return {
        "items": result,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }

@router.post("/calculate/{employee_id}")
async def calculate_salary(
    employee_id: int,
    month: Optional[int] = None,
    year: Optional[int] = None,
    bonus: float = 0.0,
    deduction: float = 0.0,
    notes: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_shifts"))
):
    """Xodim uchun ish haqi hisoblash"""
    # BOSQICH 1.5: tenant bo'yicha cheklash
    employee = apply_tenant_filter(db.query(Employee), Employee, current_user).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Xodim topilmadi")

    if not month:
        month = datetime.now().month
    if not year:
        year = datetime.now().year
    
    # Davr oralig'ini aniqlash
    period_start = datetime(year, month, 1)
    if month == 12:
        period_end = datetime(year + 1, 1, 1) - timedelta(seconds=1)
    else:
        period_end = datetime(year, month + 1, 1) - timedelta(seconds=1)
    
    # Shu davr uchun allaqachon hisoblanganmi?
    existing = db.query(Salary).filter(
        Salary.employee_id == employee_id,
        Salary.period_start == period_start
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Bu davr uchun ish haqi allaqachon hisoblangan")
    
    # Davomat ma'lumotlarini olish
    attendances = db.query(Attendance).filter(
        Attendance.employee_id == employee_id,
        Attendance.check_in >= period_start,
        Attendance.check_in <= period_end
    ).all()
    
    total_hours = sum(a.hours_worked or 0 for a in attendances)
    hourly_rate = employee.salary_rate or 0
    base_salary = total_hours * hourly_rate
    total_salary = base_salary + bonus - deduction
    
    salary = Salary(
        employee_id=employee_id,
        period_start=period_start,
        period_end=period_end,
        total_hours=total_hours,
        hourly_rate=hourly_rate,
        base_salary=base_salary,
        bonus=bonus,
        deduction=deduction,
        total_salary=total_salary,
        is_paid=False,
        notes=notes,
        tenant_id=resolve_tenant_id(db, current_user)
    )
    db.add(salary)
    db.commit()
    db.refresh(salary)
    
    return {
        "success": True,
        "salary_id": salary.id,
        "employee_name": employee.full_name,
        "period": f"{month:02d}/{year}",
        "total_hours": round(total_hours, 2),
        "hourly_rate": hourly_rate,
        "base_salary": round(base_salary, 2),
        "bonus": bonus,
        "deduction": deduction,
        "total_salary": round(total_salary, 2)
    }

@router.post("/{salary_id}/pay")
async def mark_as_paid(
    salary_id: int,
    notes: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("process_payments"))
):
    """Ish haqini to'langan deb belgilash"""
    # BOSQICH 1.5: tenant bo'yicha cheklash
    salary = apply_tenant_filter(db.query(Salary), Salary, current_user).filter(Salary.id == salary_id).first()
    if not salary:
        raise HTTPException(status_code=404, detail="Ish haqi topilmadi")
    
    if salary.is_paid:
        # IKKI MARTA HISOBLASH HIMOYASI #1: allaqachon to'langan maosh qayta to'lanmaydi
        raise HTTPException(status_code=400, detail="Ish haqi allaqachon to'langan")

    paid_at = datetime.now()
    salary.is_paid = True
    salary.paid_at = paid_at
    if notes:
        salary.notes = (salary.notes or "") + "\n" + notes

    # ── Avtomatik xarajat (BOSQICH 36): sof foydadan avtomatik ayrilsin ──────────
    # IKKI MARTA HISOBLASH HIMOYASI #2: shu maosh uchun xarajat allaqachon bormi?
    # (bo'lsa — yangisini yaratmaymiz; maosh ham, expense ham bitta tranzaksiyada)
    existing_exp = db.query(Expense).filter(Expense.salary_id == salary.id).first()
    if not existing_exp:
        employee = db.query(Employee).filter(Employee.id == salary.employee_id).first()
        emp_name = employee.full_name if employee else f"Xodim #{salary.employee_id}"
        label = _salary_period_label(salary)
        db.add(Expense(
            tenant_id    = salary.tenant_id or resolve_tenant_id(db, current_user),
            category     = "salary",
            name         = f"{emp_name} — {label} maoshi".strip(" —"),
            amount       = salary.total_salary or 0.0,
            expense_date = paid_at.date(),
            notes        = "Maosh to'lovidan avtomatik yaratilgan (salary modulida boshqariladi)",
            created_by   = current_user.id,
            salary_id    = salary.id,
        ))

    try:
        db.commit()
    except Exception:
        # Xatoda ikkalasi ham bekor — maosh ham, expense ham yaratilmaydi
        db.rollback()
        raise HTTPException(status_code=500, detail="Ish haqini to'lashda xatolik")

    return MessageResponse(message="Ish haqi to'landi")


@router.post("/{salary_id}/unpay")
async def mark_as_unpaid(
    salary_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("process_payments"))
):
    """Ish haqi to'lovini bekor qilish — bog'langan avtomatik xarajat ham o'chiriladi.

    Mantiq: maosh "to'langan" bo'lsa unga bog'langan Expense bor; to'lov bekor
    qilinsa, sof foyda noto'g'ri bo'lmasligi uchun bog'langan xarajat ham
    o'chiriladi (invariant: maosh to'langan ⇔ bog'langan xarajat mavjud).
    Hammasi bitta tranzaksiyada.
    """
    salary = apply_tenant_filter(db.query(Salary), Salary, current_user).filter(Salary.id == salary_id).first()
    if not salary:
        raise HTTPException(status_code=404, detail="Ish haqi topilmadi")

    if not salary.is_paid:
        raise HTTPException(status_code=400, detail="Ish haqi to'lanmagan")

    salary.is_paid = False
    salary.paid_at = None
    # Bog'langan avtomatik xarajat(lar)ni o'chir — ikki marta hisoblanmasin
    db.query(Expense).filter(Expense.salary_id == salary.id).delete(synchronize_session=False)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="To'lovni bekor qilishda xatolik")

    return MessageResponse(message="Ish haqi to'lovi bekor qilindi")

@router.get("/employee/{employee_id}/history")
async def get_employee_salary_history(
    employee_id: int,
    limit: int = Query(12, ge=1, le=24),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports"))
):
    """Xodim ish haqi tarixi"""
    # BOSQICH 1.5: tenant bo'yicha cheklash
    salaries = apply_tenant_filter(db.query(Salary), Salary, current_user).filter(
        Salary.employee_id == employee_id
    ).order_by(Salary.period_start.desc()).limit(limit).all()
    
    return [
        {
            "id": s.id,
            "period_start": s.period_start,
            "period_end": s.period_end,
            "total_hours": s.total_hours,
            "total_salary": s.total_salary,
            "is_paid": s.is_paid,
            "paid_at": s.paid_at
        }
        for s in salaries
    ]

@router.get("/summary")
async def get_salary_summary(
    month: Optional[int] = None,
    year: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports"))
):
    """Umumiy ish haqi xulosasi"""
    if not month:
        month = datetime.now().month
    if not year:
        year = datetime.now().year
    
    period_start = datetime(year, month, 1)
    if month == 12:
        period_end = datetime(year + 1, 1, 1)
    else:
        period_end = datetime(year, month + 1, 1)
    
    # BOSQICH 1.5: tenant bo'yicha cheklash
    salaries = apply_tenant_filter(db.query(Salary), Salary, current_user).filter(
        Salary.period_start >= period_start,
        Salary.period_start < period_end
    ).all()
    
    total_salary = sum(s.total_salary for s in salaries)
    paid_count = len([s for s in salaries if s.is_paid])
    unpaid_count = len(salaries) - paid_count
    total_hours = sum(s.total_hours for s in salaries)
    
    return {
        "period": f"{month:02d}/{year}",
        "total_employees": len(salaries),
        "total_hours": round(total_hours, 2),
        "total_salary": round(total_salary, 2),
        "paid_count": paid_count,
        "unpaid_count": unpaid_count
    }
