"""
Happy Hour routeri (BOSQICH 9.5)
Vaqtga va konga qarab avtomatik chegirma.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel

from database import get_db
from models import HappyHour, User
from deps import resolve_tenant_id, get_current_active_user, apply_tenant_filter

router = APIRouter()


class HappyHourCreate(BaseModel):
    name: str
    discount_type: str = "percentage"   # percentage | fixed
    discount_value: float
    weekdays: List[int] = [0, 1, 2, 3, 4]   # 0=Dush, 6=Yakshanba
    time_from: str                            # "12:00"
    time_to: str                              # "14:00"
    applies_to: str = "all"                  # all | category | product
    category_id: Optional[int] = None
    product_id: Optional[int] = None


class HappyHourOut(BaseModel):
    id: int
    name: str
    discount_type: str
    discount_value: float
    weekdays: list
    time_from: str
    time_to: str
    applies_to: str
    category_id: Optional[int]
    product_id: Optional[int]
    is_active: bool
    is_now_active: bool = False
    model_config = {"from_attributes": True}


def _is_active_now(hh: HappyHour) -> bool:
    """Hozirgi vaqt happy hour doirasida ekanini tekshirish"""
    now = datetime.now()
    weekday = now.weekday()   # 0=Dushanba, 6=Yakshanba
    if weekday not in (hh.weekdays or []):
        return False
    now_str = now.strftime("%H:%M")
    return hh.time_from <= now_str <= hh.time_to


def _out(hh: HappyHour) -> dict:
    return {
        "id": hh.id,
        "name": hh.name,
        "discount_type": hh.discount_type,
        "discount_value": hh.discount_value,
        "weekdays": hh.weekdays or [],
        "time_from": hh.time_from,
        "time_to": hh.time_to,
        "applies_to": hh.applies_to,
        "category_id": hh.category_id,
        "product_id": hh.product_id,
        "is_active": hh.is_active,
        "is_now_active": _is_active_now(hh),
    }


@router.get("/")
async def get_happy_hours(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Barcha happy hourlarni olish"""
    q = db.query(HappyHour)
    q = apply_tenant_filter(q, HappyHour, current_user)
    return [_out(h) for h in q.all()]


@router.get("/active-now")
async def get_active_happy_hours(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Hozir amal qilayotgan happy hourlarni olish (POS da chegirma qo'llash uchun)"""
    q = db.query(HappyHour).filter(HappyHour.is_active == True)
    q = apply_tenant_filter(q, HappyHour, current_user)
    return [_out(h) for h in q.all() if _is_active_now(h)]


@router.post("/")
async def create_happy_hour(
    data: HappyHourCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    hh = HappyHour(
        tenant_id=resolve_tenant_id(db, current_user),
        name=data.name,
        discount_type=data.discount_type,
        discount_value=data.discount_value,
        weekdays=data.weekdays,
        time_from=data.time_from,
        time_to=data.time_to,
        applies_to=data.applies_to,
        category_id=data.category_id,
        product_id=data.product_id,
    )
    db.add(hh)
    db.commit()
    db.refresh(hh)
    return _out(hh)


@router.patch("/{hh_id}")
async def update_happy_hour(
    hh_id: int,
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    hh = db.query(HappyHour).filter(HappyHour.id == hh_id).first()
    if not hh:
        raise HTTPException(404, "Happy Hour topilmadi")
    allowed = {"name", "discount_type", "discount_value", "weekdays",
               "time_from", "time_to", "applies_to", "category_id", "product_id", "is_active"}
    for k, v in data.items():
        if k in allowed:
            setattr(hh, k, v)
    db.commit()
    db.refresh(hh)
    return _out(hh)


@router.delete("/{hh_id}")
async def delete_happy_hour(
    hh_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    hh = db.query(HappyHour).filter(HappyHour.id == hh_id).first()
    if not hh:
        raise HTTPException(404, "Happy Hour topilmadi")
    db.delete(hh)
    db.commit()
    return {"success": True}
