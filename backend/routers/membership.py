"""
A'zoliklar (Memberships) router вЂ” BOSQICH 4.4
Fitnes klub, kurs/maktab uchun obuna/a'zolik tizimi.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date
from typing import Optional

from database import get_db
from models import Membership, Customer, User
from schemas import MembershipCreate, MembershipUpdate, MembershipInDB, PaginatedResponse, MessageResponse
from deps import resolve_tenant_id, get_current_active_user, has_permission, apply_tenant_filter

router = APIRouter()


@router.get("/", response_model=PaginatedResponse)
async def get_memberships(
    customer_id: Optional[int]  = None,
    status:      Optional[str]  = None,
    expiring:    Optional[bool] = None,   # 7 kun ichida muddati tugaydigan
    page:        int = Query(1, ge=1),
    page_size:   int = Query(30, ge=1, le=1000),
    db:          Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """A'zoliklar ro'yxati"""
    q = apply_tenant_filter(db.query(Membership), Membership, current_user)

    if customer_id:
        q = q.filter(Membership.customer_id == customer_id)
    if status:
        q = q.filter(Membership.status == status)
    if expiring:
        from datetime import timedelta
        soon = date.today() + timedelta(days=7)
        q = q.filter(Membership.end_date <= str(soon), Membership.status == "active")

    total = q.count()
    items = q.order_by(Membership.end_date) \
             .offset((page - 1) * page_size).limit(page_size).all()

    return PaginatedResponse(
        items=[MembershipInDB.model_validate(m) for m in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.post("/", response_model=MembershipInDB)
async def create_membership(
    data: MembershipCreate,
    db:   Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_customers")),
):
    """Yangi a'zolik yaratish"""
    cust = db.query(Customer).filter(Customer.id == data.customer_id).first()
    if not cust:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")

    m = Membership(tenant_id=resolve_tenant_id(db, current_user), **data.model_dump())
    db.add(m)
    db.commit()
    db.refresh(m)
    return MembershipInDB.model_validate(m)


@router.get("/{m_id}", response_model=MembershipInDB)
async def get_membership(
    m_id: int,
    db:   Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Bitta a'zolik"""
    m = apply_tenant_filter(db.query(Membership), Membership, current_user) \
            .filter(Membership.id == m_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="A'zolik topilmadi")
    return MembershipInDB.model_validate(m)


@router.patch("/{m_id}", response_model=MembershipInDB)
async def update_membership(
    m_id: int,
    data: MembershipUpdate,
    db:   Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_customers")),
):
    """A'zolikni yangilash (holat, tashrif, muddat)"""
    m = apply_tenant_filter(db.query(Membership), Membership, current_user) \
            .filter(Membership.id == m_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="A'zolik topilmadi")

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(m, field, value)

    db.commit()
    db.refresh(m)
    return MembershipInDB.model_validate(m)


@router.post("/{m_id}/visit", response_model=MembershipInDB)
async def record_visit(
    m_id: int,
    db:   Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Tashrif qo'shish (fitnes klub uchun)"""
    m = apply_tenant_filter(db.query(Membership), Membership, current_user) \
            .filter(Membership.id == m_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="A'zolik topilmadi")
    if m.status != "active":
        raise HTTPException(status_code=400, detail="A'zolik faol emas")
    if m.visits_total > 0 and m.visits_used >= m.visits_total:
        raise HTTPException(status_code=400, detail="Tashriflar tugadi")

    m.visits_used += 1

    # Barcha tashriflar tugasa вЂ” expired
    if m.visits_total > 0 and m.visits_used >= m.visits_total:
        m.status = "expired"

    db.commit()
    db.refresh(m)
    return MembershipInDB.model_validate(m)


@router.delete("/{m_id}", response_model=MessageResponse)
async def delete_membership(
    m_id: int,
    db:   Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_customers")),
):
    """A'zolikni o'chirish"""
    m = apply_tenant_filter(db.query(Membership), Membership, current_user) \
            .filter(Membership.id == m_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="A'zolik topilmadi")

    db.delete(m)
    db.commit()
    return MessageResponse(message="A'zolik o'chirildi")

