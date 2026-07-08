"""
Xizmatlar (Services) router — BOSQICH 4.4
Salon, fitnes, auto-servis uchun xizmatlar katalogi.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from database import get_db
from models import Service, User
from schemas import ServiceCreate, ServiceUpdate, ServiceInDB, PaginatedResponse, MessageResponse
from deps import resolve_tenant_id, get_current_active_user, has_permission, apply_tenant_filter

router = APIRouter()


@router.get("/", response_model=PaginatedResponse)
async def get_services(
    category:  Optional[str]  = None,
    is_active: Optional[bool] = None,
    search:    Optional[str]  = None,
    page:      int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db:        Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Xizmatlar ro'yxati"""
    q = apply_tenant_filter(db.query(Service), Service, current_user)

    if category:
        q = q.filter(Service.category == category)
    if is_active is not None:
        q = q.filter(Service.is_active == is_active)
    if search:
        q = q.filter(Service.name.ilike(f"%{search}%"))

    total = q.count()
    items = q.order_by(Service.name) \
             .offset((page - 1) * page_size).limit(page_size).all()

    return PaginatedResponse(
        items=[ServiceInDB.model_validate(s) for s in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.post("/", response_model=ServiceInDB)
async def create_service(
    data: ServiceCreate,
    db:   Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_products")),
):
    """Yangi xizmat qo'shish"""
    svc = Service(tenant_id=resolve_tenant_id(db, current_user), **data.model_dump())
    db.add(svc)
    db.commit()
    db.refresh(svc)
    return ServiceInDB.model_validate(svc)


@router.get("/{svc_id}", response_model=ServiceInDB)
async def get_service(
    svc_id: int,
    db:     Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Bitta xizmat"""
    svc = apply_tenant_filter(db.query(Service), Service, current_user) \
              .filter(Service.id == svc_id).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Xizmat topilmadi")
    return ServiceInDB.model_validate(svc)


@router.patch("/{svc_id}", response_model=ServiceInDB)
async def update_service(
    svc_id: int,
    data:   ServiceUpdate,
    db:     Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_products")),
):
    """Xizmatni yangilash"""
    svc = apply_tenant_filter(db.query(Service), Service, current_user) \
              .filter(Service.id == svc_id).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Xizmat topilmadi")

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(svc, field, value)

    db.commit()
    db.refresh(svc)
    return ServiceInDB.model_validate(svc)


@router.delete("/{svc_id}", response_model=MessageResponse)
async def delete_service(
    svc_id: int,
    db:     Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_products")),
):
    """Xizmatni o'chirish"""
    svc = apply_tenant_filter(db.query(Service), Service, current_user) \
              .filter(Service.id == svc_id).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Xizmat topilmadi")

    db.delete(svc)
    db.commit()
    return MessageResponse(message="Xizmat o'chirildi")
