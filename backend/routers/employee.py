from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional

from database import get_db
from models import User, Shift, Employee, Cafe
from schemas import UserInDB, ShiftInDB, PaginatedResponse, MessageResponse
from deps import get_current_user, has_permission, apply_tenant_filter, resolve_tenant_id
from core.security import hash_pin, verify_pin
from core.password_policy import validate_pin

router = APIRouter()


def _assert_cafe_access(current_user: User, cafe_id: Optional[int]) -> None:
    """Tenant izolyatsiya: oddiy foydalanuvchi faqat o'z tenantiga ruxsat oladi.
    Boshqa tenant cafe_id so'ralsa 403. Super-admin (yoki tenant_id=NULL) bypass."""
    if cafe_id is not None and not current_user.is_superuser \
            and current_user.tenant_id is not None and cafe_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Boshqa tenant ma'lumotiga ruxsat yo'q")

# ============== User orqali xodimlar ==============

@router.get("/", response_model=PaginatedResponse)
async def get_employees(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    is_active: Optional[bool] = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_users"))
):
    """Xodimlarni olish (User modeli) — faqat joriy tenant"""
    query = apply_tenant_filter(db.query(User), User, current_user)

    if is_active is not None:
        query = query.filter(User.is_active == is_active)
    
    total = query.count()
    employees = query.order_by(User.full_name).offset((page - 1) * page_size).limit(page_size).all()
    
    return PaginatedResponse(
        items=[UserInDB.model_validate(e) for e in employees],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size
    )

@router.get("/{employee_id}/shifts")
async def get_employee_shifts(
    employee_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports"))
):
    """Xodim smenalari — faqat joriy tenant xodimi"""
    emp = apply_tenant_filter(db.query(User), User, current_user).filter(User.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Xodim topilmadi")
    query = apply_tenant_filter(db.query(Shift), Shift, current_user).filter(Shift.user_id == employee_id)

    total = query.count()
    shifts = query.order_by(Shift.start_time.desc()).offset((page - 1) * page_size).limit(page_size).all()
    
    return PaginatedResponse(
        items=[ShiftInDB.model_validate(s) for s in shifts],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size
    )

@router.get("/{employee_id}/performance")
async def get_employee_performance(
    employee_id: int,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports"))
):
    """Xodim samaradorligi — faqat joriy tenant xodimi"""
    from services.analytics_service import AnalyticsService

    emp = apply_tenant_filter(db.query(User), User, current_user).filter(User.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Xodim topilmadi")

    if not date_from:
        date_from = (datetime.now() - timedelta(days=30)).isoformat()
    if not date_to:
        date_to = datetime.now().isoformat()
    
    analytics_service = AnalyticsService(db)
    return analytics_service.get_employee_performance(
        datetime.fromisoformat(date_from),
        datetime.fromisoformat(date_to)
    )

# ============== Employee modeli orqali xodimlar ==============

@router.get("/list")
async def list_employees(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    cafe_id: Optional[int] = None,
    position: Optional[str] = None,
    is_active: Optional[bool] = True,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Xodimlar ro'yxati (Employee modeli) — faqat joriy tenant"""
    _assert_cafe_access(current_user, cafe_id)
    query = apply_tenant_filter(db.query(Employee), Employee, current_user)

    if cafe_id:
        query = query.filter(Employee.tenant_id == cafe_id)
    if position:
        query = query.filter(Employee.position == position)
    if is_active is not None:
        query = query.filter(Employee.is_active == is_active)
    if search:
        query = query.filter(
            Employee.full_name.ilike(f"%{search}%") | 
            Employee.phone.ilike(f"%{search}%")
        )
    
    total = query.count()
    employees = query.order_by(Employee.full_name).offset((page - 1) * page_size).limit(page_size).all()
    
    result = []
    for e in employees:
        cafe = db.query(Cafe).filter(Cafe.id == e.tenant_id).first() if e.tenant_id else None
        result.append({
            "id": e.id,
            "user_id": e.user_id,
            "full_name": e.full_name,
            "phone": e.phone,
            "position": e.position,
            "cafe_id": e.tenant_id,
            "cafe_name": cafe.name if cafe else None,
            "salary_rate": e.salary_rate,
            "has_pin": bool(e.hashed_pin),   # PIN o'rnatilganmi (ochiq matn qaytarilmaydi)
            "hire_date": e.hire_date,
            "is_active": e.is_active,
            "created_at": e.created_at
        })
    
    return {
        "items": result,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }

@router.get("/{emp_id}")
async def get_employee(
    emp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Bitta xodim ma'lumotlarini olish — faqat joriy tenant"""
    employee = apply_tenant_filter(db.query(Employee), Employee, current_user).filter(Employee.id == emp_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Xodim topilmadi")

    cafe = db.query(Cafe).filter(Cafe.id == employee.tenant_id).first() if employee.tenant_id else None

    return {
        "id": employee.id,
        "user_id": employee.user_id,
        "full_name": employee.full_name,
        "phone": employee.phone,
        "position": employee.position,
        "cafe_id": employee.tenant_id,
        "cafe_name": cafe.name if cafe else None,
        "salary_rate": employee.salary_rate,
        "has_pin": bool(employee.hashed_pin),   # ochiq matn qaytarilmaydi
        "hire_date": employee.hire_date,
        "is_active": employee.is_active,
        "created_at": employee.created_at,
        "updated_at": employee.updated_at
    }

@router.post("/create")
async def create_employee(
    full_name: str,
    phone: Optional[str] = None,
    position: str = "waiter",
    cafe_id: Optional[int] = None,
    salary_rate: float = 0.0,
    pin_code: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_users"))
):
    """Yangi xodim yaratish (Employee modeli) — joriy tenantга biriktiriladi"""
    # Tenant izolyatsiya: oddiy user faqat o'z tenantiga; cafe_id berilmasa — o'z tenanti
    _assert_cafe_access(current_user, cafe_id)
    effective_cafe = cafe_id if cafe_id is not None else resolve_tenant_id(db, current_user)

    if effective_cafe:
        cafe = db.query(Cafe).filter(Cafe.id == effective_cafe).first()
        if not cafe:
            raise HTTPException(status_code=404, detail="Kafe topilmadi")

    # PIN kod band emasligini tekshirish (shu tenant ichida) — hash bilan
    hashed = None
    if pin_code:
        validate_pin(pin_code)   # davomat PIN siyosati (4–6, takroriy/ketma-ket emas)
        hashed = hash_pin(pin_code)
        existing = db.query(Employee).filter(
            Employee.hashed_pin == hashed,
            Employee.tenant_id == effective_cafe,
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Bu PIN-kod band")

    employee = Employee(
        full_name=full_name,
        phone=phone,
        position=position,
        tenant_id=effective_cafe,
        salary_rate=salary_rate,
        hashed_pin=hashed,
        hire_date=datetime.now(),
        is_active=True
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)
    
    return {
        "success": True,
        "employee_id": employee.id,
        "message": "Xodim yaratildi"
    }

@router.patch("/{emp_id}")
async def update_employee(
    emp_id: int,
    full_name: Optional[str] = None,
    phone: Optional[str] = None,
    position: Optional[str] = None,
    cafe_id: Optional[int] = None,
    salary_rate: Optional[float] = None,
    pin_code: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_users"))
):
    """Xodim ma'lumotlarini yangilash — faqat joriy tenant"""
    employee = apply_tenant_filter(db.query(Employee), Employee, current_user).filter(Employee.id == emp_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Xodim topilmadi")

    if full_name:
        employee.full_name = full_name
    if phone:
        employee.phone = phone
    if position:
        employee.position = position
    if cafe_id:
        # Boshqa tenantga ko'chirish faqat super-admin uchun
        _assert_cafe_access(current_user, cafe_id)
        cafe = db.query(Cafe).filter(Cafe.id == cafe_id).first()
        if not cafe:
            raise HTTPException(status_code=404, detail="Kafe topilmadi")
        employee.tenant_id = cafe_id
    if salary_rate is not None:
        employee.salary_rate = salary_rate
    if pin_code:
        validate_pin(pin_code)   # davomat PIN siyosati (4–6, takroriy/ketma-ket emas)
        # PIN kod band emasligini tekshirish (shu tenant ichida) — hash bilan
        hashed = hash_pin(pin_code)
        existing = db.query(Employee).filter(
            Employee.hashed_pin == hashed,
            Employee.tenant_id == employee.tenant_id,
            Employee.id != emp_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Bu PIN-kod band")
        employee.hashed_pin = hashed
    if is_active is not None:
        employee.is_active = is_active
        # Uzoq sessiya nazorati (3-bosqich): xodimni faolsizlantirsa bog'langan
        # User ham faolsiz bo'lsin → keyingi so'rov/refresh 401 → sessiyadan chiqadi.
        if employee.user:
            employee.user.is_active = is_active

    employee.updated_at = datetime.now()
    db.commit()
    db.refresh(employee)
    
    return MessageResponse(message="Xodim yangilandi")

@router.delete("/{emp_id}")
async def delete_employee(
    emp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_users"))
):
    """Xodimni o'chirish (soft delete) — faqat joriy tenant"""
    employee = apply_tenant_filter(db.query(Employee), Employee, current_user).filter(Employee.id == emp_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Xodim topilmadi")

    employee.is_active = False
    # Uzoq sessiya nazorati (3-bosqich): o'chirilgan xodim bog'langan User ham
    # faolsiz bo'lsin → ochiq sessiya keyingi so'rov/refreshда 401 → chiqadi.
    if employee.user:
        employee.user.is_active = False
    db.commit()

    return MessageResponse(message="Xodim o'chirildi")

@router.get("/by-pin/{pin_code}")
async def get_employee_by_pin(
    pin_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """PIN-kod bo'yicha xodimni topish (hash bo'yicha) — faqat joriy tenant ichida"""
    employee = apply_tenant_filter(db.query(Employee), Employee, current_user).filter(
        Employee.hashed_pin == hash_pin(pin_code),
        Employee.is_active == True
    ).first()

    if not employee:
        return None
    
    cafe = db.query(Cafe).filter(Cafe.id == employee.tenant_id).first() if employee.tenant_id else None

    return {
        "id": employee.id,
        "full_name": employee.full_name,
        "position": employee.position,
        "cafe_id": employee.tenant_id,
        "cafe_name": cafe.name if cafe else None,
        "cafe_code": cafe.code if cafe else None
    }

@router.get("/cafe/{cafe_id}/staff")
async def get_cafe_staff(
    cafe_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Kafe xodimlari ro'yxati — faqat joriy tenant (yoki super-admin)"""
    _assert_cafe_access(current_user, cafe_id)
    cafe = db.query(Cafe).filter(Cafe.id == cafe_id).first()
    if not cafe:
        raise HTTPException(status_code=404, detail="Kafe topilmadi")

    employees = db.query(Employee).filter(
        Employee.tenant_id == cafe_id,
        Employee.is_active == True
    ).order_by(Employee.position, Employee.full_name).all()
    
    return [
        {
            "id": e.id,
            "full_name": e.full_name,
            "position": e.position,
            "phone": e.phone,
            "has_pin": bool(e.hashed_pin),   # ochiq matn qaytarilmaydi
            "salary_rate": e.salary_rate
        }
        for e in employees
    ]
