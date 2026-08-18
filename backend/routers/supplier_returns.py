"""
Firmaga qaytarish (vozvrat) router — BOSQICH 24 (B2B)
Qaytarilganда: ombor -qty, firma qarzidan -summa.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date as Date
from typing import Optional

from database import get_db
from models import SupplierReturn, Supplier, Product, Inventory, StockMovement, User
from schemas import (
    SupplierReturnCreate, SupplierReturnInDB,
    PaginatedResponse, MessageResponse,
)
from deps import resolve_tenant_id, get_current_active_user, apply_tenant_filter, has_permission
from core.audit import log_audit

router = APIRouter()


def _enrich_return(r: SupplierReturn) -> dict:
    return {
        "id":           r.id,
        "tenant_id":    r.tenant_id,
        "supplier_id":  r.supplier_id,
        "product_id":   r.product_id,
        "product_name": r.product.name if r.product else None,
        "quantity":     r.quantity,
        "unit_price":   r.unit_price,
        "total_amount": r.total_amount,
        "return_date":  str(r.return_date),
        "reason":       r.reason,
        "notes":        r.notes,
        "created_at":   r.created_at,
    }


@router.get("/")
async def list_returns(
    supplier_id: Optional[int] = None,
    date_from:   Optional[str] = None,
    date_to:     Optional[str] = None,
    page:        int = Query(1, ge=1),
    page_size:   int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    q = apply_tenant_filter(db.query(SupplierReturn), SupplierReturn, current_user)
    if supplier_id:
        q = q.filter(SupplierReturn.supplier_id == supplier_id)
    if date_from:
        q = q.filter(SupplierReturn.return_date >= date_from)
    if date_to:
        q = q.filter(SupplierReturn.return_date <= date_to)
    total = q.count()
    rows  = q.order_by(SupplierReturn.return_date.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items":       [_enrich_return(r) for r in rows],
        "total":       total,
        "page":        page,
        "page_size":   page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.post("/")
async def create_return(
    data: SupplierReturnCreate,
    db:   Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_inventory")),
):
    """Firmaga vozvrat: ombor kamayadi, firma qarzidan ayriladi"""
    supplier = apply_tenant_filter(db.query(Supplier), Supplier, current_user) \
                   .filter(Supplier.id == data.supplier_id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Firma topilmadi")

    product = db.query(Product).filter(Product.id == data.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")

    tid = resolve_tenant_id(db, current_user)

    # Ombordan kamaytirish
    inv = db.query(Inventory).filter(
        Inventory.product_id == data.product_id,
        Inventory.tenant_id == tid,
    ).first()
    if inv:
        if inv.quantity < data.quantity:
            raise HTTPException(status_code=400, detail=f"Omborda yetarli miqdor yo'q (mavjud: {inv.quantity})")
        inv.quantity -= data.quantity

    # Sana MATN sifatida keladi ("2026-08-18"). PostgreSQL uni o'zi o'giradi,
    # sqlite esa YO'Q — shuning uchun aniq `date` qilamiz (dialektga bog'liqlik
    # yo'qoladi; xuddi shu tuzatish purchase_receipts.py da ham bor).
    _fields = data.model_dump()
    if isinstance(_fields.get("return_date"), str):
        _fields["return_date"] = Date.fromisoformat(_fields["return_date"])

    ret = SupplierReturn(
        tenant_id=tid,
        created_by=current_user.id,
        total_amount=data.quantity * data.unit_price,
        **_fields,
    )
    db.add(ret)
    db.flush()   # ret.id — StockMovement havolasi uchun

    # B6 TUZATISH: ombor HARAKATI yozuvi. Ilgari vozvratda faqat `Inventory.quantity`
    # kamayardi, StockMovement esa YOZILMASDI — natijada tovar ombordan "sababsiz"
    # kamayib qolardi: harakat tarixida ham, hisobotlarda ham izi yo'q edi.
    # Priyomka qanday yozsa (purchase_receipts.py), shunga o'xshab yoziladi.
    db.add(StockMovement(
        tenant_id=tid,
        product_id=data.product_id,
        inventory_id=inv.id if inv else None,
        movement_type="return",          # firmaga qaytarish
        quantity=data.quantity,
        unit_cost=data.unit_price,
        total_cost=round(data.quantity * data.unit_price, 2),
        supplier_id=data.supplier_id,
        reason="supplier_return",
        reference_id=ret.id,
        reference_type="supplier_return",
        user_id=current_user.id,
        notes=data.reason,
    ))

    db.commit()
    db.refresh(ret)

    # AUDIT: vozvrat ham pul/tovar harakati — kim, qachon, qancha
    log_audit(current_user, "supplier_returns", "CREATE", ret.id, tenant_id=tid,
              detail={"supplier_id": ret.supplier_id, "product_id": ret.product_id,
                      "quantity": ret.quantity, "total_amount": ret.total_amount})
    return _enrich_return(ret)


@router.get("/{return_id}")
async def get_return(
    return_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    r = apply_tenant_filter(db.query(SupplierReturn), SupplierReturn, current_user) \
          .filter(SupplierReturn.id == return_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Vozvrat topilmadi")
    return _enrich_return(r)


@router.delete("/{return_id}", response_model=MessageResponse)
async def delete_return(
    return_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_inventory")),
):
    r = apply_tenant_filter(db.query(SupplierReturn), SupplierReturn, current_user) \
          .filter(SupplierReturn.id == return_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Vozvrat topilmadi")

    _sup_id, _prod_id, _qty = r.supplier_id, r.product_id, float(r.quantity or 0)
    _amount, _tid = float(r.total_amount or 0), r.tenant_id

    # B6 TUZATISH: vozvrat o'chirilsa TOVAR OMBORGA QAYTADI. Ilgari yozuv
    # o'chirilar, ombor miqdori esa kamaygan holda QOLAVERARDI — har o'chirish
    # omborda abadiy kamomad qoldirardi.
    inv = db.query(Inventory).filter(
        Inventory.product_id == _prod_id,
        Inventory.tenant_id == _tid,
    ).first()
    if inv and _qty:
        inv.quantity += _qty
        # Teskari harakat — tarixda "nega qaytdi" ko'rinib tursin
        db.add(StockMovement(
            tenant_id=_tid,
            product_id=_prod_id,
            inventory_id=inv.id,
            movement_type="in",
            quantity=_qty,
            unit_cost=float(r.unit_price or 0),
            total_cost=_amount,
            supplier_id=_sup_id,
            reason="supplier_return_cancel",
            reference_id=return_id,
            reference_type="supplier_return",
            user_id=current_user.id,
            notes="Vozvrat o'chirildi — tovar omborga qaytarildi",
        ))

    db.delete(r)
    db.commit()

    log_audit(current_user, "supplier_returns", "DELETE", return_id, tenant_id=_tid,
              detail={"supplier_id": _sup_id, "product_id": _prod_id,
                      "quantity": _qty, "total_amount": _amount})
    return MessageResponse(message="Vozvrat o'chirildi — tovar omborga qaytarildi")
