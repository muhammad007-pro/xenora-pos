"""
Ombor (Inventory) router — BOSQICH 16

Qo'shilganlar:
  • StockMovement — kelim/chiqim tarixi DB da saqlanadi
  • Writeoff — qo'lda hisobdan o'chirish (buzilgan, yo'qolgan, ichki ishlatish)
  • Movements list — filtr + pagination bilan kelim-chiqim tarixi
  • Inventory value — ombor umumiy qiymati
  • Report summary — hisobot (kelim/chiqim jami, o'lik tovar)
  • InventoryCount — inventarizatsiya (sanash, tasdiqlash, farq)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import datetime, date
from typing import Optional, List

from database import get_db
from models import (
    Inventory, Product, User, StockMovement, Supplier,
    InventoryCount, InventoryCountItem
)
from schemas import (
    InventoryCreate, InventoryUpdate, InventoryInDB,
    PaginatedResponse, MessageResponse,
    StockMovementInDB, StockInCreate, WriteoffCreate,
    InventoryCountCreate, InventoryCountItemUpdate,
    InventoryCountInDB, InventoryCountItemInDB, InventoryValueResponse,
)
from deps import (
    resolve_tenant_id, get_current_user, get_current_active_user,
    has_permission, apply_tenant_filter, apply_branch_filter,
)

router = APIRouter()


# ─── helpers ──────────────────────────────────────────────────────────────────

def _get_inv(db, inv_id, current_user) -> Inventory:
    inv = (
        apply_tenant_filter(db.query(Inventory), Inventory, current_user)
        .filter(Inventory.id == inv_id).first()
    )
    if not inv:
        raise HTTPException(status_code=404, detail="Ombor elementi topilmadi")
    return inv


def _save_movement(
    db: Session,
    inv: Inventory,
    movement_type: str,
    quantity: float,
    current_user: User,
    *,
    unit_cost: float = 0.0,
    supplier_id: int | None = None,
    batch_number: str | None = None,
    expiry_date: date | None = None,
    reason: str | None = None,
    reference_id: int | None = None,
    reference_type: str | None = None,
    notes: str | None = None,
) -> StockMovement:
    mv = StockMovement(
        tenant_id=inv.tenant_id,
        branch_id=inv.branch_id,
        inventory_id=inv.id,
        product_id=inv.product_id,
        movement_type=movement_type,
        quantity=quantity,
        unit=inv.unit,
        unit_cost=unit_cost,
        total_cost=round(quantity * unit_cost, 2),
        supplier_id=supplier_id,
        batch_number=batch_number,
        expiry_date=expiry_date,
        reason=reason,
        reference_id=reference_id,
        reference_type=reference_type,
        notes=notes,
        user_id=current_user.id,
    )
    db.add(mv)
    return mv


def _mv_to_schema(mv: StockMovement) -> dict:
    return {
        "id": mv.id,
        "tenant_id": mv.tenant_id,
        "branch_id": mv.branch_id,
        "inventory_id": mv.inventory_id,
        "product_id": mv.product_id,
        "movement_type": mv.movement_type,
        "quantity": mv.quantity,
        "unit": mv.unit,
        "unit_cost": mv.unit_cost,
        "total_cost": mv.total_cost,
        "supplier_id": mv.supplier_id,
        "batch_number": mv.batch_number,
        "expiry_date": mv.expiry_date.isoformat() if mv.expiry_date else None,
        "reason": mv.reason,
        "reference_id": mv.reference_id,
        "reference_type": mv.reference_type,
        "notes": mv.notes,
        "user_id": mv.user_id,
        "created_at": mv.created_at.isoformat() if mv.created_at else None,
        "product_name": mv.product.name if mv.product else None,
        "supplier_name": mv.supplier.name if mv.supplier else None,
        "user_name": mv.user.full_name or mv.user.username if mv.user else None,
    }


# ─── existing endpoints (enhanced) ───────────────────────────────────────────

@router.get("/", response_model=PaginatedResponse)
async def get_inventory_items(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    low_stock_only: bool = False,
    category_id: Optional[int] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    query = db.query(Inventory).join(Product)
    query = apply_tenant_filter(query, Inventory, current_user)
    query = apply_branch_filter(query, Inventory, current_user)

    if low_stock_only:
        query = query.filter(Inventory.quantity <= Inventory.min_threshold)
    if category_id:
        query = query.filter(Product.category_id == category_id)
    if search:
        query = query.filter(Product.name.ilike(f"%{search}%"))

    total = query.count()
    items = query.order_by(Product.name).offset((page - 1) * page_size).limit(page_size).all()

    return PaginatedResponse(
        items=[InventoryInDB.model_validate(i) for i in items],
        total=total, page=page, page_size=page_size,
        total_pages=(total + page_size - 1) // page_size
    )


@router.get("/low-stock", response_model=list[InventoryInDB])
async def get_low_stock_items(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    query = apply_tenant_filter(db.query(Inventory), Inventory, current_user)
    query = apply_branch_filter(query, Inventory, current_user)
    items = (
        query.join(Product)
        .filter(Inventory.quantity <= Inventory.min_threshold)
        .order_by(Product.name).all()
    )
    return [InventoryInDB.model_validate(i) for i in items]


@router.get("/product/{product_id}", response_model=InventoryInDB)
async def get_inventory_by_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    inventory = (
        apply_tenant_filter(db.query(Inventory), Inventory, current_user)
        .filter(Inventory.product_id == product_id).first()
    )
    if not inventory:
        product = apply_tenant_filter(db.query(Product), Product, current_user).filter(Product.id == product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail="Mahsulot topilmadi")
        # Ombor birligi mahsulotning sotuv birligidan (kg hardcode emas); pcs → dona (o'qilishi uchun)
        _u = product.sale_unit or "dona"
        _u = "dona" if _u == "pcs" else _u
        inventory = Inventory(
            product_id=product_id, quantity=0, unit=_u,
            min_threshold=5, max_threshold=100,
            tenant_id=resolve_tenant_id(db, current_user)
        )
        db.add(inventory)
        db.commit()
        db.refresh(inventory)
    return InventoryInDB.model_validate(inventory)


@router.get("/value")
async def get_inventory_value(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Ombor umumiy qiymati"""
    q = apply_tenant_filter(db.query(Inventory), Inventory, current_user)
    q = apply_branch_filter(q, Inventory, current_user)
    results = q.join(Product).with_entities(
        func.sum(Inventory.quantity * Product.cost_price).label('total_cost'),
        func.sum(Inventory.quantity * Product.price).label('total_retail'),
        func.count(Inventory.id).label('item_count'),
    ).first()

    tc = float(results.total_cost or 0)
    tr = float(results.total_retail or 0)
    return {
        "total_cost": tc,
        "total_retail": tr,
        "potential_profit": round(tr - tc, 2),
        "item_count": results.item_count or 0,
    }


# ─── movements (tarixi) ───────────────────────────────────────────────────────

@router.get("/movements")
async def get_movements(
    movement_type: Optional[str] = None,   # in | out | writeoff | adjustment | sale
    product_id: Optional[int] = None,
    supplier_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Kelim-chiqim tarixi"""
    q = apply_tenant_filter(db.query(StockMovement), StockMovement, current_user)
    q = apply_branch_filter(q, StockMovement, current_user)

    if movement_type:
        q = q.filter(StockMovement.movement_type == movement_type)
    if product_id:
        q = q.filter(StockMovement.product_id == product_id)
    if supplier_id:
        q = q.filter(StockMovement.supplier_id == supplier_id)
    if date_from:
        q = q.filter(func.date(StockMovement.created_at) >= date_from)
    if date_to:
        q = q.filter(func.date(StockMovement.created_at) <= date_to)

    total = q.count()
    rows = q.order_by(StockMovement.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "items": [_mv_to_schema(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


# ─── report ───────────────────────────────────────────────────────────────────

@router.get("/report/summary")
async def get_report_summary(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports"))
):
    """Ombor hisoboti: kelim, chiqim, o'lik tovar"""
    from sqlalchemy import text
    from datetime import timedelta

    since = datetime.now() - timedelta(days=days)

    q_mv = apply_tenant_filter(db.query(StockMovement), StockMovement, current_user)
    q_mv = apply_branch_filter(q_mv, StockMovement, current_user)
    q_mv = q_mv.filter(StockMovement.created_at >= since)

    # Kelim jami
    in_result = q_mv.filter(StockMovement.movement_type == 'in').with_entities(
        func.coalesce(func.sum(StockMovement.quantity), 0).label('qty'),
        func.coalesce(func.sum(StockMovement.total_cost), 0).label('cost'),
        func.count(StockMovement.id).label('cnt'),
    ).first()

    # Chiqim jami (sotuv + writeoff + manual)
    out_result = q_mv.filter(StockMovement.movement_type.in_(['out', 'sale', 'writeoff'])).with_entities(
        func.coalesce(func.sum(StockMovement.quantity), 0).label('qty'),
        func.count(StockMovement.id).label('cnt'),
    ).first()

    # O'lik tovar: 30 kunda harakati bo'lmagan mahsulotlar
    q_inv = apply_tenant_filter(db.query(Inventory), Inventory, current_user)
    q_inv = apply_branch_filter(q_inv, Inventory, current_user)
    all_inv = q_inv.join(Product).all()

    moved_product_ids = {
        r[0] for r in q_mv.with_entities(StockMovement.product_id).distinct().all()
        if r[0]
    }

    dead_stock = [
        {
            "product_id": inv.product_id,
            "product_name": inv.product.name if inv.product else "—",
            "quantity": inv.quantity,
            "unit": inv.unit,
            "last_restock": inv.last_restock.isoformat() if inv.last_restock else None,
        }
        for inv in all_inv
        if inv.quantity > 0 and inv.product_id not in moved_product_ids
    ]

    # Top kelim mahsulotlar
    top_in = (
        q_mv.filter(StockMovement.movement_type == 'in')
        .with_entities(
            StockMovement.product_id,
            func.sum(StockMovement.quantity).label('total_qty'),
            func.sum(StockMovement.total_cost).label('total_cost'),
        )
        .group_by(StockMovement.product_id)
        .order_by(func.sum(StockMovement.total_cost).desc())
        .limit(10).all()
    )
    top_in_list = []
    for row in top_in:
        prod = db.query(Product).filter(Product.id == row.product_id).first()
        top_in_list.append({
            "product_id": row.product_id,
            "product_name": prod.name if prod else "—",
            "total_qty": float(row.total_qty or 0),
            "total_cost": float(row.total_cost or 0),
        })

    return {
        "period_days": days,
        "incoming": {
            "count": in_result.cnt,
            "total_qty": float(in_result.qty),
            "total_cost": float(in_result.cost),
        },
        "outgoing": {
            "count": out_result.cnt,
            "total_qty": float(out_result.qty),
        },
        "dead_stock": dead_stock,
        "dead_stock_count": len(dead_stock),
        "top_incoming": top_in_list,
    }


# ─── stock-in (enhanced add-stock) ───────────────────────────────────────────

@router.post("/{inventory_id}/add-stock")
async def add_stock(
    inventory_id: int,
    data: StockInCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_inventory"))
):
    """Omborga mahsulot kiritish (kelim)"""
    if data.quantity <= 0:
        raise HTTPException(status_code=400, detail="Miqdor musbat bo'lishi kerak")

    inv = _get_inv(db, inventory_id, current_user)

    inv.quantity += data.quantity
    inv.last_restock = datetime.now()
    inv.updated_at = datetime.now()

    # Yetkazib beruvchi balansini yangilash
    if data.supplier_id:
        supplier = db.query(Supplier).filter(Supplier.id == data.supplier_id).first()
        if supplier:
            supplier.balance += round(data.quantity * data.unit_cost, 2)

    mv = _save_movement(
        db, inv, movement_type='in', quantity=data.quantity,
        current_user=current_user,
        unit_cost=data.unit_cost,
        supplier_id=data.supplier_id,
        batch_number=data.batch_number,
        expiry_date=data.expiry_date,
        reason='manual',
        reference_type='manual',
        notes=data.notes,
    )

    db.commit()
    db.refresh(inv)

    return {
        "message": f"{data.quantity} {inv.unit} qo'shildi. Yangi miqdor: {inv.quantity} {inv.unit}",
        "new_quantity": inv.quantity,
        "movement_id": mv.id,
    }


@router.post("/{inventory_id}/remove-stock")
async def remove_stock(
    inventory_id: int,
    quantity: float,
    reason: Optional[str] = None,
    notes: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_inventory"))
):
    """Omborni qo'lda kamaytirish"""
    if quantity <= 0:
        raise HTTPException(status_code=400, detail="Miqdor musbat bo'lishi kerak")

    inv = _get_inv(db, inventory_id, current_user)

    if inv.quantity < quantity:
        raise HTTPException(
            status_code=400,
            detail=f"Yetarli miqdor yo'q. Mavjud: {inv.quantity} {inv.unit}"
        )

    inv.quantity -= quantity
    inv.updated_at = datetime.now()

    _save_movement(
        db, inv, movement_type='out', quantity=quantity,
        current_user=current_user,
        reason=reason or 'manual',
        reference_type='manual',
        notes=notes,
    )

    db.commit()
    db.refresh(inv)

    return MessageResponse(message=f"{quantity} {inv.unit} chiqarildi. Qoldiq: {inv.quantity} {inv.unit}")


# ─── writeoff ─────────────────────────────────────────────────────────────────

@router.post("/writeoff")
async def writeoff_stock(
    data: WriteoffCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_inventory"))
):
    """Hisobdan o'chirish: buzilgan, yo'qolgan, ichki ishlatish, muddati o'tgan"""
    inv = _get_inv(db, data.inventory_id, current_user)

    if data.quantity <= 0:
        raise HTTPException(status_code=400, detail="Miqdor musbat bo'lishi kerak")
    if inv.quantity < data.quantity:
        raise HTTPException(
            status_code=400,
            detail=f"Yetarli miqdor yo'q. Mavjud: {inv.quantity} {inv.unit}"
        )

    inv.quantity -= data.quantity
    inv.updated_at = datetime.now()

    _save_movement(
        db, inv, movement_type='writeoff', quantity=data.quantity,
        current_user=current_user,
        batch_number=data.batch_number,
        reason=data.reason,
        reference_type='manual',
        notes=data.notes,
    )

    db.commit()
    db.refresh(inv)

    reason_labels = {
        'spoiled': 'Buzilgan', 'lost': "Yo'qolgan",
        'internal_use': 'Ichki ishlatish', 'expired': 'Muddati o\'tgan', 'other': 'Boshqa',
    }
    label = reason_labels.get(data.reason, data.reason)

    return {
        "message": f"{data.quantity} {inv.unit} hisobdan o'chirildi ({label}). Qoldiq: {inv.quantity} {inv.unit}",
        "new_quantity": inv.quantity,
    }


# ─── existing CRUD (unchanged) ────────────────────────────────────────────────

@router.get("/{inventory_id}", response_model=InventoryInDB)
async def get_inventory_item(
    inventory_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    inv = apply_tenant_filter(db.query(Inventory), Inventory, current_user).filter(Inventory.id == inventory_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Ombor elementi topilmadi")
    return InventoryInDB.model_validate(inv)


@router.post("/", response_model=InventoryInDB)
async def create_inventory_item(
    inventory_data: InventoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_inventory"))
):
    product = db.query(Product).filter(Product.id == inventory_data.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")

    existing = db.query(Inventory).filter(Inventory.product_id == inventory_data.product_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Bu mahsulot uchun ombor elementi allaqachon mavjud")

    # Ombor birligi mahsulotning sotuv birligidan (kg hardcode emas); pcs → dona
    _data = inventory_data.model_dump()
    _u = product.sale_unit or "dona"
    _data["unit"] = "dona" if _u == "pcs" else _u
    inventory = Inventory(**_data, tenant_id=resolve_tenant_id(db, current_user))
    db.add(inventory)
    db.commit()
    db.refresh(inventory)
    return InventoryInDB.model_validate(inventory)


@router.patch("/{inventory_id}", response_model=InventoryInDB)
async def update_inventory_item(
    inventory_id: int,
    inventory_data: InventoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_inventory"))
):
    inventory = apply_tenant_filter(db.query(Inventory), Inventory, current_user).filter(Inventory.id == inventory_id).first()
    if not inventory:
        raise HTTPException(status_code=404, detail="Ombor elementi topilmadi")

    update_data = inventory_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(inventory, field, value)

    inventory.updated_at = datetime.now()
    db.commit()
    db.refresh(inventory)
    return InventoryInDB.model_validate(inventory)


# ─── inventarizatsiya (count) ──────────────────────────────────────────────────

@router.post("/count/start")
async def start_inventory_count(
    data: InventoryCountCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_inventory"))
):
    """Yangi inventarizatsiya boshlash — hozirgi qoldiqlar snapshot olinadi"""
    tenant_id = resolve_tenant_id(db, current_user)
    branch_id = getattr(current_user, '_active_branch_id', None)

    count = InventoryCount(
        tenant_id=tenant_id,
        branch_id=branch_id,
        status='draft',
        notes=data.notes,
        user_id=current_user.id,
    )
    db.add(count)
    db.flush()

    # Barcha ombor elementlarini snapshot qilish
    q_inv = apply_tenant_filter(db.query(Inventory), Inventory, current_user)
    q_inv = apply_branch_filter(q_inv, Inventory, current_user)
    inventories = q_inv.join(Product).order_by(Product.name).all()

    for inv in inventories:
        item = InventoryCountItem(
            count_id=count.id,
            inventory_id=inv.id,
            product_id=inv.product_id,
            product_name=inv.product.name if inv.product else "—",
            unit=inv.unit,
            system_qty=inv.quantity,
            actual_qty=None,
            difference=None,
        )
        db.add(item)

    db.commit()
    db.refresh(count)

    return {
        "id": count.id,
        "status": count.status,
        "item_count": len(inventories),
        "message": f"Inventarizatsiya boshlandi. {len(inventories)} ta mahsulot ro'yxatga olindi.",
    }


@router.get("/count/list")
async def list_inventory_counts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Inventarizatsiyalar ro'yxati"""
    q = apply_tenant_filter(db.query(InventoryCount), InventoryCount, current_user)
    q = apply_branch_filter(q, InventoryCount, current_user)
    total = q.count()
    counts = q.order_by(InventoryCount.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    result = []
    for c in counts:
        filled = sum(1 for i in c.items if i.actual_qty is not None)
        result.append({
            "id": c.id,
            "status": c.status,
            "notes": c.notes,
            "total_items": len(c.items),
            "filled_items": filled,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "confirmed_at": c.confirmed_at.isoformat() if c.confirmed_at else None,
        })

    return {"items": result, "total": total, "page": page, "total_pages": (total + page_size - 1) // page_size}


@router.get("/count/{count_id}")
async def get_inventory_count(
    count_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Inventarizatsiya tafsiloti"""
    count = apply_tenant_filter(db.query(InventoryCount), InventoryCount, current_user).filter(InventoryCount.id == count_id).first()
    if not count:
        raise HTTPException(status_code=404, detail="Inventarizatsiya topilmadi")

    items_data = [
        {
            "id": it.id,
            "count_id": it.count_id,
            "inventory_id": it.inventory_id,
            "product_id": it.product_id,
            "product_name": it.product_name,
            "unit": it.unit,
            "system_qty": it.system_qty,
            "actual_qty": it.actual_qty,
            "difference": it.difference,
            "notes": it.notes,
        }
        for it in count.items
    ]

    return {
        "id": count.id,
        "status": count.status,
        "notes": count.notes,
        "created_at": count.created_at.isoformat() if count.created_at else None,
        "confirmed_at": count.confirmed_at.isoformat() if count.confirmed_at else None,
        "items": items_data,
    }


@router.patch("/count/{count_id}/items/{item_id}")
async def update_count_item(
    count_id: int,
    item_id: int,
    data: InventoryCountItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_inventory"))
):
    """Haqiqiy sanalgan miqdorni kiritish"""
    count = apply_tenant_filter(db.query(InventoryCount), InventoryCount, current_user).filter(InventoryCount.id == count_id).first()
    if not count:
        raise HTTPException(status_code=404, detail="Inventarizatsiya topilmadi")
    if count.status != 'draft':
        raise HTTPException(status_code=400, detail="Tasdiqlangan inventarizatsiyani o'zgartirish mumkin emas")

    item = db.query(InventoryCountItem).filter(
        InventoryCountItem.id == item_id,
        InventoryCountItem.count_id == count_id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Element topilmadi")

    item.actual_qty = data.actual_qty
    item.difference = round(data.actual_qty - item.system_qty, 4)
    if data.notes:
        item.notes = data.notes

    db.commit()
    return {"id": item.id, "actual_qty": item.actual_qty, "difference": item.difference}


@router.post("/count/{count_id}/confirm")
async def confirm_inventory_count(
    count_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_inventory"))
):
    """Inventarizatsiyani tasdiqlash — farqlar omborga adjustment sifatida yoziladi"""
    count = apply_tenant_filter(db.query(InventoryCount), InventoryCount, current_user).filter(InventoryCount.id == count_id).first()
    if not count:
        raise HTTPException(status_code=404, detail="Inventarizatsiya topilmadi")
    if count.status != 'draft':
        raise HTTPException(status_code=400, detail="Faqat 'draft' holatdagi inventarizatsiyani tasdiqlash mumkin")

    unfilled = [it for it in count.items if it.actual_qty is None]
    if unfilled:
        raise HTTPException(
            status_code=400,
            detail=f"{len(unfilled)} ta mahsulot sanalmagan. Avval barchasini kiriting."
        )

    adjustments = 0
    for item in count.items:
        if item.difference == 0 or item.inventory_id is None:
            continue

        inv = db.query(Inventory).filter(Inventory.id == item.inventory_id).first()
        if not inv:
            continue

        inv.quantity = item.actual_qty
        inv.updated_at = datetime.now()
        adjustments += 1

        mv_type = 'adjustment'
        _save_movement(
            db, inv, movement_type=mv_type, quantity=abs(item.difference),
            current_user=current_user,
            reason='inventory_adjustment',
            reference_id=count.id,
            reference_type='inventory_count',
            notes=f"Inventarizatsiya #{count.id}: farq {item.difference:+.2f} {item.unit}",
        )

    count.status = 'confirmed'
    count.confirmed_by = current_user.id
    count.confirmed_at = datetime.now()

    db.commit()

    return {
        "message": f"Inventarizatsiya tasdiqlandi. {adjustments} ta mahsulot qoldig'i to'g'irlandi.",
        "adjustments": adjustments,
    }


@router.delete("/count/{count_id}", response_model=MessageResponse)
async def delete_inventory_count(
    count_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_inventory"))
):
    """Draft inventarizatsiyani o'chirish"""
    count = apply_tenant_filter(db.query(InventoryCount), InventoryCount, current_user).filter(InventoryCount.id == count_id).first()
    if not count:
        raise HTTPException(status_code=404, detail="Inventarizatsiya topilmadi")
    if count.status != 'draft':
        raise HTTPException(status_code=400, detail="Faqat 'draft' holatdagi inventarizatsiyani o'chirish mumkin")

    db.delete(count)
    db.commit()
    return MessageResponse(message="Inventarizatsiya o'chirildi")
