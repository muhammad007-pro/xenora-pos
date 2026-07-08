from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from database import get_db
from models import Table, User, Order
from schemas import TableCreate, TableUpdate, TableInDB, PaginatedResponse, MessageResponse
from deps import resolve_tenant_id, get_current_user, get_current_active_user, has_permission, apply_tenant_filter

router = APIRouter()

@router.get("/", response_model=PaginatedResponse)
async def get_tables(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=1000),
    section: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Barcha stollarni olish"""
    query = db.query(Table)
    # BOSQICH 1.5: tenant bo'yicha cheklash
    query = apply_tenant_filter(query, Table, current_user)

    if section:
        query = query.filter(Table.section == section)
    
    if status:
        query = query.filter(Table.status == status)
    
    total = query.count()
    tables = query.order_by(Table.number).offset((page - 1) * page_size).limit(page_size).all()
    
    return PaginatedResponse(
        items=[TableInDB.model_validate(t) for t in tables],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size
    )

@router.get("/all", response_model=list[TableInDB])
async def get_all_tables(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Barcha stollarni paginatsiyasiz olish"""
    query = apply_tenant_filter(db.query(Table), Table, current_user)
    tables = query.order_by(Table.number).all()
    return [TableInDB.model_validate(t) for t in tables]

@router.post("/", response_model=TableInDB)
async def create_table(
    table_data: TableCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_tables"))
):
    """Yangi stol yaratish"""
    existing = db.query(Table).filter(Table.number == table_data.number).first()
    if existing:
        raise HTTPException(status_code=400, detail="Bu raqamli stol mavjud")

    # BOSQICH 1.5: yangi yozuv yaratuvchi tenant'iga biriktiriladi
    table = Table(**table_data.model_dump(), tenant_id=resolve_tenant_id(db, current_user))
    db.add(table)
    db.commit()
    db.refresh(table)
    
    return TableInDB.model_validate(table)

@router.get("/{table_id}", response_model=TableInDB)
async def get_table(
    table_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Stol ma'lumotlarini olish"""
    table = apply_tenant_filter(db.query(Table), Table, current_user).filter(Table.id == table_id).first()
    if not table:
        raise HTTPException(status_code=404, detail="Stol topilmadi")
    
    return TableInDB.model_validate(table)

@router.patch("/{table_id}", response_model=TableInDB)
async def update_table(
    table_id: int,
    table_data: TableUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Stolni yangilash"""
    table = apply_tenant_filter(db.query(Table), Table, current_user).filter(Table.id == table_id).first()
    if not table:
        raise HTTPException(status_code=404, detail="Stol topilmadi")
    
    update_data = table_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(table, field, value)
    
    db.commit()
    db.refresh(table)
    
    return TableInDB.model_validate(table)

@router.delete("/{table_id}", response_model=MessageResponse)
async def delete_table(
    table_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_tables"))
):
    """Stolni o'chirish"""
    table = apply_tenant_filter(db.query(Table), Table, current_user).filter(Table.id == table_id).first()
    if not table:
        raise HTTPException(status_code=404, detail="Stol topilmadi")
    
    # Buyurtmalar mavjudligini tekshirish
    active_orders = db.query(Order).filter(
        Order.table_id == table_id,
        Order.status.in_(["pending", "confirmed", "preparing", "ready"])
    ).count()
    
    if active_orders > 0:
        raise HTTPException(status_code=400, detail="Bu stolda faol buyurtmalar mavjud")
    
    db.delete(table)
    db.commit()
    
    return MessageResponse(message="Stol o'chirildi")

@router.get("/{table_id}/orders")
async def get_table_orders(
    table_id: int,
    active_only: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Stolga tegishli buyurtmalarni olish"""
    from schemas import OrderInDB

    table = apply_tenant_filter(db.query(Table), Table, current_user).filter(Table.id == table_id).first()
    if not table:
        raise HTTPException(status_code=404, detail="Stol topilmadi")

    query = db.query(Order).filter(Order.table_id == table_id)
    # BOSQICH 1.5: tenant bo'yicha cheklash
    query = apply_tenant_filter(query, Order, current_user)

    if active_only:
        query = query.filter(Order.status.in_(["pending", "confirmed", "preparing", "ready", "served"]))
    
    orders = query.order_by(Order.created_at.desc()).all()
    
    return [OrderInDB.model_validate(o) for o in orders]

@router.post("/{table_id}/free")
async def free_table(
    table_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Stolni bo'shatish"""
    table = apply_tenant_filter(db.query(Table), Table, current_user).filter(Table.id == table_id).first()
    if not table:
        raise HTTPException(status_code=404, detail="Stol topilmadi")

    table.status = "free"
    db.commit()

    return MessageResponse(message="Stol bo'shatildi")


@router.post("/{table_id}/merge")
async def merge_tables(
    table_id: int,
    target_table_ids: list[int],
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Stollarni birlashtirish (BOSQICH 9.6).
    table_id вЂ” asosiy stol, target_table_ids вЂ” qo'shiladigan stollar.
    order_id вЂ” asosiy buyurtma (barcha stollar shu hisobga birlashadi).
    """
    from models import Order
    main_table = apply_tenant_filter(db.query(Table), Table, current_user).filter(Table.id == table_id).first()
    if not main_table:
        raise HTTPException(404, "Asosiy stol topilmadi")

    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Buyurtma topilmadi")

    merged = []
    for tid in target_table_ids:
        t = apply_tenant_filter(db.query(Table), Table, current_user).filter(Table.id == tid).first()
        if t and t.id != table_id:
            t.status = "occupied"
            merged.append(tid)

    # Birlashtirilgan stollar ro'yxatini buyurtmaga saqlash
    existing = order.merged_table_ids or []
    order.merged_table_ids = list(set(existing + merged))
    db.commit()

    return {"success": True, "merged_table_ids": order.merged_table_ids}


@router.post("/{table_id}/unmerge")
async def unmerge_tables(
    table_id: int,
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Birlashtirilgan stollarni ajratish"""
    from models import Order
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Buyurtma topilmadi")

    for tid in (order.merged_table_ids or []):
        t = apply_tenant_filter(db.query(Table), Table, current_user).filter(Table.id == tid).first()
        if t:
            t.status = "free"

    order.merged_table_ids = []
    db.commit()
    return {"success": True}
