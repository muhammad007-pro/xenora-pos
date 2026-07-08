"""
Uchrashuvlar (Appointments) router — BOSQICH 4.4 + 23
Salon, fitnes, auto-servis, maktab, mehmonxona uchun vaqt bron tizimi.
BOSQICH 23: Bo'sh slot hisoblash, double-booking bloklash, komissiya hisoboti.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date as Date, datetime, timedelta
from typing import Optional, List

from database import get_db
from models import Appointment, Service, Employee, StaffSchedule, User
from schemas import (
    AppointmentCreate, AppointmentUpdate, AppointmentInDB,
    PaginatedResponse, MessageResponse,
    AvailableSlot, CommissionReport, EmployeeCommission, SalonServiceSummary,
)
from deps import resolve_tenant_id, get_current_user, get_current_active_user, apply_tenant_filter, has_permission

router = APIRouter()


def _enrich(apt: Appointment) -> dict:
    """Appointment'ga service_name va employee_name qo'shadi"""
    data = {
        "id":               apt.id,
        "customer_name":    apt.customer_name,
        "customer_phone":   apt.customer_phone,
        "customer_id":      apt.customer_id,
        "service_id":       apt.service_id,
        "employee_id":      apt.employee_id,
        "date":             str(apt.date),
        "start_time":       apt.start_time,
        "duration_minutes": apt.duration_minutes,
        "status":           apt.status,
        "notes":            apt.notes,
        "price":            apt.price,
        "created_at":       apt.created_at,
        "service_name":     apt.service.name  if apt.service  else None,
        "employee_name":    apt.employee.full_name if apt.employee else None,
    }
    return data


@router.get("/")
async def get_appointments(
    date:        Optional[str] = None,
    employee_id: Optional[int] = None,
    status:      Optional[str] = None,
    page:        int = Query(1, ge=1),
    page_size:   int = Query(50, ge=1, le=200),
    db:          Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Bronlar ro'yxati (kun, xodim, holat bo'yicha filtr)"""
    q = apply_tenant_filter(db.query(Appointment), Appointment, current_user)

    if date:
        q = q.filter(Appointment.date == date)
    if employee_id:
        q = q.filter(Appointment.employee_id == employee_id)
    if status:
        q = q.filter(Appointment.status == status)

    total = q.count()
    items = q.order_by(Appointment.date, Appointment.start_time) \
             .offset((page - 1) * page_size).limit(page_size).all()

    return {
        "items":       [_enrich(a) for a in items],
        "total":       total,
        "page":        page,
        "page_size":   page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.post("/")
async def create_appointment(
    data: AppointmentCreate,
    db:   Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Yangi bron yaratish"""
    # Narxni xizmatdan olamiz (agar ko'rsatilmagan bo'lsa)
    price = data.price
    if not price and data.service_id:
        svc = db.query(Service).filter(Service.id == data.service_id).first()
        if svc:
            price = svc.price

    apt = Appointment(
        tenant_id=resolve_tenant_id(db, current_user),
        **data.model_dump(exclude={"price"}),
        price=price,
    )
    db.add(apt)
    db.commit()
    db.refresh(apt)
    return _enrich(apt)


# ─── BOSQICH 23: Static paths MUST come before /{apt_id} ──────────────────────

def _time_to_minutes(t: str) -> int:
    """'09:30' → 570"""
    h, m = map(int, t.split(":"))
    return h * 60 + m


def _minutes_to_time(m: int) -> str:
    """570 → '09:30'"""
    return f"{m // 60:02d}:{m % 60:02d}"


@router.get("/available-slots", response_model=List[AvailableSlot])
async def available_slots(
    employee_id: int,
    date:        str,
    service_id:  Optional[int] = None,
    slot_minutes: int = Query(30, ge=15, le=120),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Berilgan usta va sanada bo'sh vaqt slotlarini qaytaradi."""
    duration = slot_minutes
    if service_id:
        svc = apply_tenant_filter(db.query(Service), Service, current_user) \
                  .filter(Service.id == service_id).first()
        if svc and svc.duration_minutes:
            duration = svc.duration_minutes

    try:
        day = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Sana formati: YYYY-MM-DD")

    weekday = day.weekday()
    sched = (
        apply_tenant_filter(db.query(StaffSchedule), StaffSchedule, current_user)
        .filter(StaffSchedule.employee_id == employee_id, StaffSchedule.weekday == weekday)
        .first()
    )
    if sched and not sched.is_working:
        return []

    work_start = _time_to_minutes(sched.work_start if sched else "09:00")
    work_end   = _time_to_minutes(sched.work_end   if sched else "18:00")

    booked = (
        apply_tenant_filter(db.query(Appointment), Appointment, current_user)
        .filter(
            Appointment.employee_id == employee_id,
            Appointment.date == date,
            Appointment.status.notin_(["cancelled", "no_show"]),
        )
        .all()
    )
    busy_ranges = []
    for b in booked:
        start = _time_to_minutes(b.start_time)
        end   = start + (b.duration_minutes or 30)
        busy_ranges.append((start, end))

    slots = []
    cur = work_start
    while cur + duration <= work_end:
        slot_end = cur + duration
        is_free  = not any(start < slot_end and cur < end for start, end in busy_ranges)
        slots.append(AvailableSlot(time=_minutes_to_time(cur), available=is_free))
        cur += 30

    return slots


@router.get("/commission-report", response_model=CommissionReport)
async def commission_report(
    date_from: str,
    date_to:   str,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports")),
):
    """Ustalar komissiya hisoboti (davr bo'yicha)"""
    apts = (
        apply_tenant_filter(db.query(Appointment), Appointment, current_user)
        .filter(
            Appointment.date >= date_from,
            Appointment.date <= date_to,
            Appointment.status == "completed",
            Appointment.employee_id.isnot(None),
        )
        .all()
    )

    emp_data: dict[int, dict] = {}
    for apt in apts:
        eid = apt.employee_id
        svc_name = apt.service.name if apt.service else "Boshqa"
        commission_pct = apt.service.commission_pct if apt.service else 0.0
        commission_amt = apt.price * commission_pct / 100.0

        if eid not in emp_data:
            emp_data[eid] = {
                "employee_id":   eid,
                "employee_name": apt.employee.full_name if apt.employee else f"ID:{eid}",
                "total_revenue": 0.0,
                "commission":    0.0,
                "count":         0,
                "services":      {},
            }
        emp_data[eid]["total_revenue"] += apt.price
        emp_data[eid]["commission"]    += commission_amt
        emp_data[eid]["count"]         += 1
        if svc_name not in emp_data[eid]["services"]:
            emp_data[eid]["services"][svc_name] = {"count": 0, "total": 0.0}
        emp_data[eid]["services"][svc_name]["count"] += 1
        emp_data[eid]["services"][svc_name]["total"] += apt.price

    employees_out = []
    for ed in emp_data.values():
        svcs = [
            SalonServiceSummary(service_name=k, count=v["count"], total=v["total"])
            for k, v in ed["services"].items()
        ]
        employees_out.append(EmployeeCommission(
            employee_id=ed["employee_id"],
            employee_name=ed["employee_name"],
            total_services=ed["count"],
            total_revenue=ed["total_revenue"],
            commission_amount=ed["commission"],
            services=svcs,
        ))

    grand_total      = sum(e.total_revenue     for e in employees_out)
    total_commission = sum(e.commission_amount for e in employees_out)

    return CommissionReport(
        period_start=date_from,
        period_end=date_to,
        employees=employees_out,
        grand_total=grand_total,
        total_commission=total_commission,
    )


@router.get("/customer/{customer_id}/salon-history")
async def salon_client_history(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Bitta mijozning salon tarixi: tashriflar, xizmatlar, usta, jami pul"""
    apts = (
        apply_tenant_filter(db.query(Appointment), Appointment, current_user)
        .filter(
            Appointment.customer_id == customer_id,
            Appointment.status.notin_(["cancelled", "no_show"]),
        )
        .order_by(Appointment.date.desc())
        .all()
    )

    if not apts:
        raise HTTPException(status_code=404, detail="Bu mijoz uchun tashrif topilmadi")

    customer    = apts[0].customer
    total_spent = sum(a.price for a in apts)
    last_visit  = str(apts[0].date) if apts else None

    svc_count: dict[str, dict] = {}
    emp_count: dict[str, int]  = {}
    for a in apts:
        sname = a.service.name if a.service else "Boshqa"
        if sname not in svc_count:
            svc_count[sname] = {"count": 0, "total": 0.0}
        svc_count[sname]["count"] += 1
        svc_count[sname]["total"] += a.price
        if a.employee:
            en = a.employee.full_name
            emp_count[en] = emp_count.get(en, 0) + 1

    favorite_emp = max(emp_count, key=emp_count.get) if emp_count else None
    services_out = [
        {"service_name": k, "count": v["count"], "total": v["total"]}
        for k, v in sorted(svc_count.items(), key=lambda x: -x[1]["count"])
    ]

    return {
        "customer_id":       customer_id,
        "customer_name":     customer.name if customer else f"ID:{customer_id}",
        "phone":             customer.phone if customer else None,
        "total_visits":      len(apts),
        "total_spent":       total_spent,
        "last_visit":        last_visit,
        "is_vip":            len(apts) >= 10 or total_spent >= 1_000_000,
        "favorite_employee": favorite_emp,
        "services":          services_out,
    }


# ─── Parameterized paths ───────────────────────────────────────────────────────

@router.get("/{apt_id}")
async def get_appointment(
    apt_id: int,
    db:     Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Bitta bron"""
    apt = apply_tenant_filter(db.query(Appointment), Appointment, current_user) \
              .filter(Appointment.id == apt_id).first()
    if not apt:
        raise HTTPException(status_code=404, detail="Bron topilmadi")
    return _enrich(apt)


@router.patch("/{apt_id}")
async def update_appointment(
    apt_id: int,
    data:   AppointmentUpdate,
    db:     Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Bron holatini yoki vaqtini yangilash"""
    apt = apply_tenant_filter(db.query(Appointment), Appointment, current_user) \
              .filter(Appointment.id == apt_id).first()
    if not apt:
        raise HTTPException(status_code=404, detail="Bron topilmadi")

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(apt, field, value)

    db.commit()
    db.refresh(apt)
    return _enrich(apt)


@router.delete("/{apt_id}", response_model=MessageResponse)
async def delete_appointment(
    apt_id: int,
    db:     Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Bronni o'chirish"""
    apt = apply_tenant_filter(db.query(Appointment), Appointment, current_user) \
              .filter(Appointment.id == apt_id).first()
    if not apt:
        raise HTTPException(status_code=404, detail="Bron topilmadi")

    db.delete(apt)
    db.commit()
    return MessageResponse(message="Bron o'chirildi")

