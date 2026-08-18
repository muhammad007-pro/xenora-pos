"""
Priyomka (qabul akti) router — BOSQICH 24 (B2B)
Nakladnoy kiritish, tovarlar ro'yxati, tasdiqlash → ombor avtomatik to'ldiriladi.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date as Date
from typing import Optional

from database import get_db
from models import PurchaseReceipt, PurchaseReceiptItem, Supplier, Product, Inventory, StockMovement, ProductBatch, SupplierPayment, User
from schemas import (
    PurchaseReceiptCreate, PurchaseReceiptUpdate,
    PurchaseReceiptInDB, PurchaseReceiptItemInDB,
    PaginatedResponse, MessageResponse,
)
from deps import resolve_tenant_id, get_current_active_user, apply_tenant_filter, has_permission

router = APIRouter()


def _enrich(rec: PurchaseReceipt) -> dict:
    items_out = []
    for it in rec.items:
        items_out.append({
            "id":           it.id,
            "receipt_id":   it.receipt_id,
            "product_id":   it.product_id,
            "product_name": it.product.name if it.product else None,
            "quantity":     it.quantity,
            "unit_price":   it.unit_price,
            "total_price":  it.total_price,
            "brak_qty":     it.brak_qty,
            "accepted_qty": it.accepted_qty,
            "notes":        it.notes,
        })
    return {
        "id":              rec.id,
        "tenant_id":       rec.tenant_id,
        "supplier_id":     rec.supplier_id,
        "supplier_name":   rec.supplier.name if rec.supplier else None,
        "invoice_number":  rec.invoice_number,
        "receipt_date":    str(rec.receipt_date),
        "total_amount":    rec.total_amount,
        "discount_amount": rec.discount_amount,
        "net_amount":      rec.net_amount,
        "status":          rec.status,
        "paid_now":        float(rec.paid_now or 0),
        "notes":           rec.notes,
        "created_at":      rec.created_at,
        "items":           items_out,
    }


@router.get("/")
async def list_receipts(
    supplier_id: Optional[int] = None,
    status:      Optional[str] = None,
    date_from:   Optional[str] = None,
    date_to:     Optional[str] = None,
    page:        int = Query(1, ge=1),
    page_size:   int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    q = apply_tenant_filter(db.query(PurchaseReceipt), PurchaseReceipt, current_user)
    if supplier_id:
        q = q.filter(PurchaseReceipt.supplier_id == supplier_id)
    if status:
        q = q.filter(PurchaseReceipt.status == status)
    if date_from:
        q = q.filter(PurchaseReceipt.receipt_date >= date_from)
    if date_to:
        q = q.filter(PurchaseReceipt.receipt_date <= date_to)
    total = q.count()
    rows  = q.order_by(PurchaseReceipt.receipt_date.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items":       [_enrich(r) for r in rows],
        "total":       total,
        "page":        page,
        "page_size":   page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.post("/")
async def create_receipt(
    data: PurchaseReceiptCreate,
    db:   Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_finance")),
):
    """Yangi priyomka yaratish (draft holat — omborga kirmagunча)"""
    supplier = apply_tenant_filter(db.query(Supplier), Supplier, current_user) \
                   .filter(Supplier.id == data.supplier_id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Firma topilmadi")

    tid = resolve_tenant_id(db, current_user)

    # Jami hisoblash
    total = 0.0
    for it in data.items:
        acc = it.quantity - it.brak_qty
        total += acc * it.unit_price
    net = max(0.0, total - data.discount_amount)

    rec = PurchaseReceipt(
        tenant_id=tid,
        supplier_id=data.supplier_id,
        invoice_number=data.invoice_number,
        # Sana MATN sifatida keladi ("2026-08-18"). PostgreSQL uni o'zi
        # o'giradi, sqlite esa YO'Q — shuning uchun bu yerda aniq date qilamiz
        # (dialektga bog'liqlik yo'qoladi, testlar ham xuddi shu yo'ldan yuradi).
        receipt_date=Date.fromisoformat(data.receipt_date) if isinstance(data.receipt_date, str) else data.receipt_date,
        total_amount=total,
        discount_amount=data.discount_amount,
        net_amount=net,
        notes=data.notes,
        created_by=current_user.id,
        status="draft",
        # FAZA 4: "Hozir to'landi" — to'lov yozuvi TASDIQLANGANDA yaratiladi
        # (draft hali qarz emas; unga to'lov bog'lash "avans" bo'lib ko'rinardi).
        paid_now=data.paid_now or 0,
    )
    db.add(rec)
    db.flush()

    for it in data.items:
        acc = it.quantity - it.brak_qty
        item = PurchaseReceiptItem(
            receipt_id=rec.id,
            product_id=it.product_id,
            quantity=it.quantity,
            unit_price=it.unit_price,
            total_price=acc * it.unit_price,
            brak_qty=it.brak_qty,
            accepted_qty=acc,
            notes=it.notes,
            batch_number=it.batch_number,
            expiry_date=it.expiry_date,
            manufacture_date=it.manufacture_date,
        )
        db.add(item)

    db.commit()
    db.refresh(rec)
    return _enrich(rec)


@router.get("/{receipt_id}")
async def get_receipt(
    receipt_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    rec = apply_tenant_filter(db.query(PurchaseReceipt), PurchaseReceipt, current_user) \
              .filter(PurchaseReceipt.id == receipt_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Priyomka topilmadi")
    return _enrich(rec)


@router.patch("/{receipt_id}")
async def update_receipt(
    receipt_id: int,
    data: PurchaseReceiptUpdate,
    db:   Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_finance")),
):
    rec = apply_tenant_filter(db.query(PurchaseReceipt), PurchaseReceipt, current_user) \
              .filter(PurchaseReceipt.id == receipt_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Priyomka topilmadi")
    if rec.status == "confirmed":
        raise HTTPException(status_code=400, detail="Tasdiqlangan priyomkani o'zgartirish mumkin emas")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(rec, k, v)
    db.commit()
    db.refresh(rec)
    return _enrich(rec)


@router.post("/{receipt_id}/confirm")
async def confirm_receipt(
    receipt_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_finance")),
):
    """Priyomkani tasdiqlash → ombordagi qoldiqlar avtomatik oshadi"""
    from datetime import datetime
    rec = apply_tenant_filter(db.query(PurchaseReceipt), PurchaseReceipt, current_user) \
              .filter(PurchaseReceipt.id == receipt_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Priyomka topilmadi")
    if rec.status != "draft":
        raise HTTPException(status_code=400, detail="Faqat draft holатdagi priyomka tasdiqlanadi")

    tid = resolve_tenant_id(db, current_user)

    # Ombor yangilash
    #
    # MUHIM: Inventory.quantity = umumiy ombor qoldig'i (HAQIQAT MANBAI — POS shundan o'qiydi).
    #        ProductBatch.quantity = partiya detali (expiry-report shundan o'qiydi).
    # Ikkalasi PARALLEL va bir xil qty yoziladi, AMMO hech qaysi joyda
    # Inventory + ProductBatch QO'SHILMASLIGI kerak (aks holda miqdor ikki marta sanaladi).
    for it in rec.items:
        qty = it.accepted_qty or (it.quantity - it.brak_qty)

        # Ombor qoldig'i (Inventory) — bir marta oshadi
        inv = db.query(Inventory).filter(
            Inventory.product_id == it.product_id,
            Inventory.tenant_id == tid,
        ).with_for_update().first()   # ROW-LOCK: priyomka kirimi atomik
        if inv:
            inv.quantity += qty
        else:
            inv = Inventory(
                tenant_id=tid,
                product_id=it.product_id,
                quantity=qty,
            )
            db.add(inv)
        inv.last_restock = datetime.now()

        # Kelish narxini (cost_price) yangilash — faqat haqiqiy narx bo'lsa
        if it.unit_price and it.unit_price > 0:
            product = db.query(Product).filter(
                Product.id == it.product_id,
                Product.tenant_id == tid,
            ).first()
            if product:
                product.cost_price = it.unit_price

        # Partiya (ProductBatch) — FAQAT expiry bo'lsa. Inventory'ni IKKINCHI marta oshirmaydi.
        if it.expiry_date:
            batch = db.query(ProductBatch).filter(
                ProductBatch.tenant_id == tid,
                ProductBatch.product_id == it.product_id,
                ProductBatch.batch_number == it.batch_number,
                ProductBatch.expiry_date == it.expiry_date,
            ).first()
            if batch:
                # Duplicate (bir xil product+batch_number+expiry) → mavjudni yangilash
                batch.quantity         += qty
                batch.initial_quantity += qty
            else:
                db.add(ProductBatch(
                    tenant_id=tid,
                    branch_id=getattr(current_user, "branch_id", None),
                    product_id=it.product_id,
                    batch_number=it.batch_number,
                    manufacture_date=it.manufacture_date,
                    expiry_date=it.expiry_date,
                    quantity=qty,
                    initial_quantity=qty,
                    cost_price=it.unit_price or 0.0,
                ))

        # Ombor harakati tarixi (StockMovement) — partiya ma'lumoti bilan
        db.add(StockMovement(
            tenant_id=tid,
            product_id=it.product_id,
            movement_type="in",
            quantity=qty,
            unit_cost=it.unit_price,
            total_cost=qty * (it.unit_price or 0),
            supplier_id=rec.supplier_id,
            batch_number=it.batch_number,
            expiry_date=it.expiry_date,
            reason="purchase",
            reference_id=rec.id,
            reference_type="purchase_receipt",
            user_id=current_user.id,
        ))

    rec.status       = "confirmed"
    rec.confirmed_by = current_user.id
    rec.confirmed_at = datetime.now()

    # FAZA 4: "Hozir to'landi" — nakladnoy bilan birga berilgan pul endi HAQIQIY
    # to'lov yozuviga aylanadi (receipt_id bilan bog'langan → tarixda "Nakladnoy
    # uchun" turi bo'lib ko'rinadi va qarzdan ayriladi).
    # IDEMPOTENT: confirm faqat `draft` dan ishlaydi (yuqorida tekshirilgan),
    # ya'ni bu blok bir marta bajariladi.
    _paid_now = float(rec.paid_now or 0)
    if _paid_now > 0:
        db.add(SupplierPayment(
            tenant_id=tid,
            supplier_id=rec.supplier_id,
            receipt_id=rec.id,
            amount=_paid_now,
            payment_date=rec.receipt_date,
            payment_method="cash",
            notes="Priyomka bilan birga to'landi",
            user_id=current_user.id,
            created_by=current_user.id,
        ))
        # To'liq to'langan bo'lsa — holat darhol `paid`
        if _paid_now >= float(rec.net_amount or 0):
            rec.status = "paid"

    db.commit()
    db.refresh(rec)
    return _enrich(rec)


@router.delete("/{receipt_id}", response_model=MessageResponse)
async def delete_receipt(
    receipt_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_finance")),
):
    rec = apply_tenant_filter(db.query(PurchaseReceipt), PurchaseReceipt, current_user) \
              .filter(PurchaseReceipt.id == receipt_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Priyomka topilmadi")
    if rec.status == "confirmed":
        raise HTTPException(status_code=400, detail="Tasdiqlangan priyomkani o'chirish mumkin emas")
    db.delete(rec)
    db.commit()
    return MessageResponse(message="Priyomka o'chirildi")
