"""
Mehmonxona xonalari va bronlar routeri вЂ” BOSQICH 14i
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from datetime import date
from typing import Optional

from database import get_db
from models import Room, RoomBooking, User
from schemas import (
    RoomCreate, RoomUpdate, RoomInDB,
    RoomBookingCreate, RoomBookingUpdate, RoomBookingInDB,
    PaginatedResponse, MessageResponse,
)
from deps import resolve_tenant_id, get_current_active_user, apply_tenant_filter, has_permission

router = APIRouter()


# в”Ђв”Ђ Xonalar в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

@router.get("/", response_model=PaginatedResponse)
async def get_rooms(
    status:    Optional[str] = None,
    floor:     Optional[int] = None,
    room_type: Optional[str] = None,
    page:      int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db:        Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    q = apply_tenant_filter(db.query(Room), Room, current_user).filter(Room.is_active == True)
    if status:    q = q.filter(Room.status == status)
    if floor:     q = q.filter(Room.floor == floor)
    if room_type: q = q.filter(Room.room_type == room_type)
    total = q.count()
    items = q.order_by(Room.floor, Room.number).offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedResponse(
        items=[RoomInDB.model_validate(r) for r in items],
        total=total, page=page, page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.post("/", response_model=RoomInDB)
async def create_room(
    data: RoomCreate,
    db:   Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_settings")),
):
    room = Room(tenant_id=resolve_tenant_id(db, current_user), **data.model_dump())
    db.add(room)
    db.commit()
    db.refresh(room)
    return RoomInDB.model_validate(room)


@router.patch("/{room_id}", response_model=RoomInDB)
async def update_room(
    room_id: int,
    data:    RoomUpdate,
    db:      Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_settings")),
):
    room = apply_tenant_filter(db.query(Room), Room, current_user).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Xona topilmadi")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(room, field, value)
    db.commit()
    db.refresh(room)
    return RoomInDB.model_validate(room)


@router.delete("/{room_id}", response_model=MessageResponse)
async def delete_room(
    room_id: int,
    db:      Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_settings")),
):
    room = apply_tenant_filter(db.query(Room), Room, current_user).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Xona topilmadi")
    room.is_active = False
    db.commit()
    return MessageResponse(message="Xona o'chirildi")


# в”Ђв”Ђ Bronlar в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

@router.get("/bookings/", response_model=PaginatedResponse)
async def get_bookings(
    status:     Optional[str]  = None,
    room_id:    Optional[int]  = None,
    date_from:  Optional[str]  = None,
    date_to:    Optional[str]  = None,
    search:     Optional[str]  = None,
    page:       int = Query(1, ge=1),
    page_size:  int = Query(20, ge=1, le=1000),
    db:         Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    q = apply_tenant_filter(db.query(RoomBooking), RoomBooking, current_user) \
        .options(joinedload(RoomBooking.room))
    if status:    q = q.filter(RoomBooking.status == status)
    if room_id:   q = q.filter(RoomBooking.room_id == room_id)
    if date_from: q = q.filter(RoomBooking.check_out >= date_from)
    if date_to:   q = q.filter(RoomBooking.check_in  <= date_to)
    if search:
        s = f"%{search}%"
        q = q.filter(
            RoomBooking.guest_name.ilike(s) |
            RoomBooking.guest_phone.ilike(s)
        )
    total = q.count()
    items = q.order_by(RoomBooking.check_in.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedResponse(
        items=[RoomBookingInDB.model_validate(b) for b in items],
        total=total, page=page, page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.post("/bookings/", response_model=RoomBookingInDB)
async def create_booking(
    data: RoomBookingCreate,
    db:   Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    room = apply_tenant_filter(db.query(Room), Room, current_user).filter(Room.id == data.room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Xona topilmadi")
    booking = RoomBooking(tenant_id=resolve_tenant_id(db, current_user), **data.model_dump())
    db.add(booking)
    if data.status if hasattr(data, 'status') else True:
        room.status = "occupied"
    db.commit()
    db.refresh(booking)
    return RoomBookingInDB.model_validate(booking)


@router.patch("/bookings/{booking_id}", response_model=RoomBookingInDB)
async def update_booking(
    booking_id: int,
    data:       RoomBookingUpdate,
    db:         Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    booking = apply_tenant_filter(db.query(RoomBooking), RoomBooking, current_user) \
                  .filter(RoomBooking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Bron topilmadi")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(booking, field, value)
    if data.status in ("checked_out", "cancelled") and booking.room:
        active = db.query(RoomBooking).filter(
            RoomBooking.room_id == booking.room_id,
            RoomBooking.status == "checked_in",
            RoomBooking.id != booking_id,
        ).count()
        if active == 0:
            booking.room.status = "available"
    db.commit()
    db.refresh(booking)
    return RoomBookingInDB.model_validate(booking)


@router.delete("/bookings/{booking_id}", response_model=MessageResponse)
async def cancel_booking(
    booking_id: int,
    db:         Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    booking = apply_tenant_filter(db.query(RoomBooking), RoomBooking, current_user) \
                  .filter(RoomBooking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Bron topilmadi")
    booking.status = "cancelled"
    db.commit()
    return MessageResponse(message="Bron bekor qilindi")


# в”Ђв”Ђ Bugungi holat в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

@router.get("/overview/")
async def rooms_overview(
    db:           Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Xonalar + bugungi aktiv bron ma'lumoti"""
    today = date.today().isoformat()
    rooms = apply_tenant_filter(db.query(Room), Room, current_user) \
                .filter(Room.is_active == True).order_by(Room.floor, Room.number).all()
    result = []
    for room in rooms:
        active_booking = db.query(RoomBooking).filter(
            RoomBooking.room_id == room.id,
            RoomBooking.status.in_(["confirmed", "checked_in"]),
            RoomBooking.check_in  <= today,
            RoomBooking.check_out >  today,
        ).first()
        result.append({
            "id":              room.id,
            "number":          room.number,
            "name":            room.name,
            "floor":           room.floor,
            "room_type":       room.room_type,
            "capacity":        room.capacity,
            "price_per_night": room.price_per_night,
            "status":          room.status,
            "booking": {
                "id":          active_booking.id,
                "guest_name":  active_booking.guest_name,
                "guest_phone": active_booking.guest_phone,
                "check_in":    active_booking.check_in,
                "check_out":   active_booking.check_out,
                "nights":      active_booking.nights,
                "total":       active_booking.total_amount,
                "paid":        active_booking.paid_amount,
                "status":      active_booking.status,
            } if active_booking else None,
        })
    return result

