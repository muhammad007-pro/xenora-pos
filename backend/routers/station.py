from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from database import get_db
from models import Station, User
from schemas import StationCreate, StationUpdate, StationInDB
from deps import get_current_active_user, apply_tenant_filter, resolve_tenant_id, has_permission

router = APIRouter()


@router.get("/public", response_model=List[StationInDB])
def list_stations_public(
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Kitchen ekrani uchun stansiyalar (autentifikatsiya shart emas)"""
    q = db.query(Station).filter(Station.is_active == True, Station.has_display == True)
    if branch_id:
        q = q.filter(Station.branch_id == branch_id)
    return q.order_by(Station.display_order, Station.id).all()


@router.get("/", response_model=List[StationInDB])
def list_stations(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    q = db.query(Station).filter(Station.is_active == True)
    if not current_user.is_superuser:
        q = q.filter(Station.tenant_id == current_user.tenant_id)
    return q.order_by(Station.display_order, Station.id).all()


@router.post("/", response_model=StationInDB, status_code=201)
def create_station(
    data: StationCreate,
    current_user: User = Depends(has_permission("manage_menu")),
    db: Session = Depends(get_db)
):
    tenant_id = resolve_tenant_id(db, current_user)
    station = Station(
        tenant_id=tenant_id,
        branch_id=data.branch_id,
        name=data.name,
        color=data.color,
        has_display=data.has_display,
        display_order=data.display_order,
    )
    db.add(station)
    db.commit()
    db.refresh(station)
    return station


@router.get("/{station_id}", response_model=StationInDB)
def get_station(
    station_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Stansiya topilmadi")
    if not current_user.is_superuser and station.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")
    return station


@router.patch("/{station_id}", response_model=StationInDB)
def update_station(
    station_id: int,
    data: StationUpdate,
    current_user: User = Depends(has_permission("manage_menu")),
    db: Session = Depends(get_db)
):
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Stansiya topilmadi")
    if not current_user.is_superuser and station.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(station, field, value)
    db.commit()
    db.refresh(station)
    return station


@router.delete("/{station_id}", status_code=204)
def delete_station(
    station_id: int,
    current_user: User = Depends(has_permission("manage_menu")),
    db: Session = Depends(get_db)
):
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Stansiya topilmadi")
    if not current_user.is_superuser and station.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")
    station.is_active = False
    db.commit()
