"""
Avtomobillar va xizmat buyurtmalari router вЂ” BOSQICH 4.4
Auto servis va kimyoviy tozalash uchun.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional

from database import get_db
from models import Vehicle, ServiceOrder, User
from schemas import (
    VehicleCreate, VehicleUpdate, VehicleInDB,
    ServiceOrderCreate, ServiceOrderUpdate, ServiceOrderInDB,
    PaginatedResponse, MessageResponse,
)
from deps import resolve_tenant_id, get_current_active_user, has_permission, apply_tenant_filter

router = APIRouter()


# в”Ђв”Ђ Avtomobillar в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

@router.get("/", response_model=PaginatedResponse)
async def get_vehicles(
    customer_id: Optional[int] = None,
    search:      Optional[str] = None,
    page:        int = Query(1, ge=1),
    page_size:   int = Query(30, ge=1, le=1000),
    db:          Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Avtomobillar ro'yxati"""
    q = apply_tenant_filter(db.query(Vehicle), Vehicle, current_user)

    if customer_id:
        q = q.filter(Vehicle.customer_id == customer_id)
    if search:
        q = q.filter(
            Vehicle.plate_number.ilike(f"%{search}%") |
            Vehicle.brand.ilike(f"%{search}%") |
            Vehicle.model.ilike(f"%{search}%")
        )

    total = q.count()
    items = q.order_by(Vehicle.plate_number) \
             .offset((page - 1) * page_size).limit(page_size).all()

    return PaginatedResponse(
        items=[VehicleInDB.model_validate(v) for v in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.post("/", response_model=VehicleInDB)
async def create_vehicle(
    data: VehicleCreate,
    db:   Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Yangi avtomobil qo'shish"""
    v = Vehicle(tenant_id=resolve_tenant_id(db, current_user), **data.model_dump())
    db.add(v)
    db.commit()
    db.refresh(v)
    return VehicleInDB.model_validate(v)


@router.get("/{v_id}", response_model=VehicleInDB)
async def get_vehicle(
    v_id: int,
    db:   Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    v = apply_tenant_filter(db.query(Vehicle), Vehicle, current_user) \
            .filter(Vehicle.id == v_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="Avtomobil topilmadi")
    return VehicleInDB.model_validate(v)


@router.patch("/{v_id}", response_model=VehicleInDB)
async def update_vehicle(
    v_id: int,
    data: VehicleUpdate,
    db:   Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    v = apply_tenant_filter(db.query(Vehicle), Vehicle, current_user) \
            .filter(Vehicle.id == v_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="Avtomobil topilmadi")

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(v, field, value)

    db.commit()
    db.refresh(v)
    return VehicleInDB.model_validate(v)


@router.delete("/{v_id}", response_model=MessageResponse)
async def delete_vehicle(
    v_id: int,
    db:   Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_products")),
):
    v = apply_tenant_filter(db.query(Vehicle), Vehicle, current_user) \
            .filter(Vehicle.id == v_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="Avtomobil topilmadi")

    db.delete(v)
    db.commit()
    return MessageResponse(message="Avtomobil o'chirildi")


# в”Ђв”Ђ Xizmat buyurtmalari в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

@router.get("/orders/", response_model=PaginatedResponse)
async def get_service_orders(
    status:      Optional[str] = None,
    vehicle_id:  Optional[int] = None,
    customer_id: Optional[int] = None,
    page:        int = Query(1, ge=1),
    page_size:   int = Query(30, ge=1, le=1000),
    db:          Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Xizmat buyurtmalari ro'yxati"""
    q = apply_tenant_filter(db.query(ServiceOrder), ServiceOrder, current_user)

    if status:
        q = q.filter(ServiceOrder.status == status)
    if vehicle_id:
        q = q.filter(ServiceOrder.vehicle_id == vehicle_id)
    if customer_id:
        q = q.filter(ServiceOrder.customer_id == customer_id)

    total = q.count()
    items = q.order_by(ServiceOrder.created_at.desc()) \
             .offset((page - 1) * page_size).limit(page_size).all()

    return PaginatedResponse(
        items=[ServiceOrderInDB.model_validate(o) for o in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.post("/orders/", response_model=ServiceOrderInDB)
async def create_service_order(
    data: ServiceOrderCreate,
    db:   Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Yangi xizmat buyurtmasi"""
    count = db.query(ServiceOrder).filter(
        ServiceOrder.tenant_id == current_user.tenant_id
    ).count()
    order_number = f"SO-{(count + 1):04d}"

    order = ServiceOrder(
        tenant_id=resolve_tenant_id(db, current_user),
        order_number=order_number,
        **data.model_dump(),
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return ServiceOrderInDB.model_validate(order)


@router.patch("/orders/{order_id}", response_model=ServiceOrderInDB)
async def update_service_order(
    order_id: int,
    data:     ServiceOrderUpdate,
    db:       Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    order = apply_tenant_filter(db.query(ServiceOrder), ServiceOrder, current_user) \
                .filter(ServiceOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(order, field, value)

    db.commit()
    db.refresh(order)
    return ServiceOrderInDB.model_validate(order)

