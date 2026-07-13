"""
Usta Haftalik Ish Jadvali — BOSQICH 23 (Salon)
Har usta uchun weekday bo'yicha ish vaqti (09:00-18:00), dam olish kunlari.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from database import get_db
from models import StaffSchedule, Employee, User
from schemas import (
    StaffScheduleCreate, StaffScheduleUpdate, StaffScheduleInDB, MessageResponse,
)
from deps import get_current_active_user, apply_tenant_filter, resolve_tenant_id

from deps import require_feature  # funksiya-flag himoyasi (O'ZGARISH 3)
router = APIRouter(dependencies=[Depends(require_feature("staff_schedule"))])

WEEKDAY_NAMES = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]


def _get_schedule(db: Session, schedule_id: int, current_user: User) -> StaffSchedule:
    s = (
        apply_tenant_filter(db.query(StaffSchedule), StaffSchedule, current_user)
        .filter(StaffSchedule.id == schedule_id)
        .first()
    )
    if not s:
        raise HTTPException(status_code=404, detail="Jadval topilmadi")
    return s


@router.get("/employee/{employee_id}", response_model=List[StaffScheduleInDB])
async def get_employee_schedule(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Bitta usta uchun haftalik jadval (7 kun)"""
    rows = (
        apply_tenant_filter(db.query(StaffSchedule), StaffSchedule, current_user)
        .filter(StaffSchedule.employee_id == employee_id)
        .order_by(StaffSchedule.weekday)
        .all()
    )
    return [StaffScheduleInDB.model_validate(r) for r in rows]


@router.get("/weekly")
async def get_weekly_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Barcha ustalar haftalik jadvali — bir ko'rinishda"""
    employees = (
        apply_tenant_filter(db.query(Employee), Employee, current_user)
        .filter(Employee.is_active == True)
        .order_by(Employee.full_name)
        .all()
    )
    schedules = (
        apply_tenant_filter(db.query(StaffSchedule), StaffSchedule, current_user)
        .all()
    )
    sched_map: dict[tuple, StaffSchedule] = {
        (s.employee_id, s.weekday): s for s in schedules
    }

    result = []
    for emp in employees:
        week = []
        for day in range(7):
            s = sched_map.get((emp.id, day))
            week.append({
                "weekday": day,
                "day_name": WEEKDAY_NAMES[day],
                "is_working": s.is_working if s else True,
                "work_start": s.work_start if s else "09:00",
                "work_end":   s.work_end   if s else "18:00",
            })
        result.append({
            "employee_id":   emp.id,
            "employee_name": emp.full_name,
            "position":      emp.position,
            "schedule":      week,
        })
    return result


@router.post("/", response_model=StaffScheduleInDB, status_code=201)
async def set_schedule(
    data: StaffScheduleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Usta kun jadvalini o'rnatish yoki yangilash (upsert)"""
    tenant_id = resolve_tenant_id(db, current_user)
    existing = (
        apply_tenant_filter(db.query(StaffSchedule), StaffSchedule, current_user)
        .filter(
            StaffSchedule.employee_id == data.employee_id,
            StaffSchedule.weekday == data.weekday,
        )
        .first()
    )
    if existing:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(existing, field, value)
        db.commit()
        db.refresh(existing)
        return StaffScheduleInDB.model_validate(existing)

    schedule = StaffSchedule(tenant_id=tenant_id, **data.model_dump())
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return StaffScheduleInDB.model_validate(schedule)


@router.post("/bulk", response_model=List[StaffScheduleInDB])
async def set_bulk_schedule(
    employee_id: int,
    schedules: List[StaffScheduleUpdate],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Usta uchun butun haftani bir vaqtda saqlash (7 kun)"""
    tenant_id = resolve_tenant_id(db, current_user)
    result = []
    for idx, sched_data in enumerate(schedules):
        if idx > 6:
            break
        existing = (
            apply_tenant_filter(db.query(StaffSchedule), StaffSchedule, current_user)
            .filter(StaffSchedule.employee_id == employee_id, StaffSchedule.weekday == idx)
            .first()
        )
        if existing:
            for field, value in sched_data.model_dump(exclude_unset=True).items():
                setattr(existing, field, value)
            result.append(existing)
        else:
            new_s = StaffSchedule(
                tenant_id=tenant_id, employee_id=employee_id, weekday=idx,
                **sched_data.model_dump(exclude_unset=True),
            )
            db.add(new_s)
            result.append(new_s)

    db.commit()
    for r in result:
        db.refresh(r)
    return [StaffScheduleInDB.model_validate(r) for r in result]


@router.patch("/{schedule_id}", response_model=StaffScheduleInDB)
async def update_schedule(
    schedule_id: int,
    data: StaffScheduleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    s = _get_schedule(db, schedule_id, current_user)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(s, field, value)
    db.commit()
    db.refresh(s)
    return StaffScheduleInDB.model_validate(s)


@router.delete("/{schedule_id}", response_model=MessageResponse)
async def delete_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    s = _get_schedule(db, schedule_id, current_user)
    db.delete(s)
    db.commit()
    return MessageResponse(message="Jadval o'chirildi")
