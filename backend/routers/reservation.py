from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional

from database import get_db
from models import Reservation, Table, Customer, User
from schemas import ReservationCreate, ReservationUpdate, ReservationInDB, PaginatedResponse, MessageResponse
from deps import resolve_tenant_id, get_current_user, get_current_active_user, apply_tenant_filter

router = APIRouter()

@router.get("/", response_model=PaginatedResponse)
async def get_reservations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    date: Optional[str] = None,
    status: Optional[str] = None,
    table_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Bronlarni olish"""
    query = db.query(Reservation)
    # BOSQICH 1.5: tenant bo'yicha cheklash
    query = apply_tenant_filter(query, Reservation, current_user)

    if date:
        target_date = datetime.strptime(date, "%Y-%m-%d")
        query = query.filter(
            Reservation.reservation_time >= target_date,
            Reservation.reservation_time < target_date + timedelta(days=1)
        )
    
    if status:
        query = query.filter(Reservation.status == status)
    
    if table_id:
        query = query.filter(Reservation.table_id == table_id)
    
    total = query.count()
    reservations = query.order_by(Reservation.reservation_time).offset((page - 1) * page_size).limit(page_size).all()
    
    return PaginatedResponse(
        items=[ReservationInDB.model_validate(r) for r in reservations],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size
    )

@router.post("/", response_model=ReservationInDB)
async def create_reservation(
    reservation_data: ReservationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Yangi bron yaratish"""
    # Stol tekshirish (BOSQICH 1.5: tenant bo'yicha cheklash)
    table = apply_tenant_filter(db.query(Table), Table, current_user).filter(Table.id == reservation_data.table_id).first()
    if not table:
        raise HTTPException(status_code=404, detail="Stol topilmadi")

    # Mijoz tekshirish
    customer = apply_tenant_filter(db.query(Customer), Customer, current_user).filter(Customer.id == reservation_data.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")

    # Vaqt bandligini tekshirish
    end_time = reservation_data.reservation_time + timedelta(minutes=reservation_data.duration_minutes)
    
    conflicting = db.query(Reservation).filter(
        Reservation.table_id == reservation_data.table_id,
        Reservation.status.in_(["pending", "confirmed"]),
        Reservation.reservation_time < end_time,
        Reservation.reservation_time + timedelta(minutes=Reservation.duration_minutes) > reservation_data.reservation_time
    ).first()
    
    if conflicting:
        raise HTTPException(status_code=400, detail="Bu vaqt oralig'ida stol band")
    
    # BOSQICH 1.5: yangi bron yaratuvchi tenant'iga biriktiriladi
    reservation = Reservation(**reservation_data.model_dump(), tenant_id=resolve_tenant_id(db, current_user))
    db.add(reservation)
    db.commit()
    db.refresh(reservation)
    
    return ReservationInDB.model_validate(reservation)

@router.patch("/{reservation_id}/status")
async def update_reservation_status(
    reservation_id: int,
    status: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Bron holatini yangilash"""
    reservation = apply_tenant_filter(db.query(Reservation), Reservation, current_user).filter(Reservation.id == reservation_id).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Bron topilmadi")
    
    valid_statuses = ["pending", "confirmed", "cancelled", "completed"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Noto'g'ri holat. Ruxsat etilgan: {valid_statuses}")
    
    reservation.status = status
    db.commit()
    
    return MessageResponse(message=f"Bron holati yangilandi: {status}")

@router.delete("/{reservation_id}")
async def cancel_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Bronni bekor qilish"""
    reservation = apply_tenant_filter(db.query(Reservation), Reservation, current_user).filter(Reservation.id == reservation_id).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Bron topilmadi")
    
    reservation.status = "cancelled"
    db.commit()
    
    return MessageResponse(message="Bron bekor qilindi")
