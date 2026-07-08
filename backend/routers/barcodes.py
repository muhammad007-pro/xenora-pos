"""Ko'p barcode — bir mahsulotga bir nechta barcode va tarozi barcode (PLU)"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from database import get_db
from models import ProductBarcode, Product, User
from deps import resolve_tenant_id, get_current_active_user, has_permission, apply_tenant_filter

router = APIRouter()


@router.get("/lookup/{barcode}")
async def lookup_barcode(
    barcode: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Barcode bo'yicha mahsulot topish (asosiy yoki qo'shimcha barcode)"""
    tid = resolve_tenant_id(db, current_user)

    # Avval product_barcodes jadvalidan qidirish
    pb = db.query(ProductBarcode).filter(
        ProductBarcode.barcode == barcode,
        ProductBarcode.tenant_id == tid,
    ).first()

    if pb:
        product = db.query(Product).filter(Product.id == pb.product_id).first()
        if product:
            return _product_dict(product, pb)

    # Asosiy barcode (products.barcode ustuni)
    product = db.query(Product).filter(
        Product.barcode == barcode,
        Product.tenant_id == tid,
    ).first()
    if product:
        return _product_dict(product, None)

    # Tarozi barcode: format "21PPPPWWWWWC" yoki "20PPPPWWWWWC" (PLU)
    if len(barcode) == 13 and barcode[:2] in ("20", "21", "22", "23", "29"):
        weight_g = _parse_weight_barcode(barcode)
        plu_code = barcode[2:7]
        pb2 = db.query(ProductBarcode).filter(
            ProductBarcode.weight_variable == True,
            ProductBarcode.barcode == plu_code,
            ProductBarcode.tenant_id == tid,
        ).first()
        if pb2:
            product = db.query(Product).filter(Product.id == pb2.product_id).first()
            if product:
                result = _product_dict(product, pb2)
                result["weight_kg"] = weight_g / 1000
                result["calculated_price"] = round(product.price * weight_g / 1000, 0)
                return result

    raise HTTPException(status_code=404, detail="Barcode topilmadi")


@router.get("/product/{product_id}")
async def get_product_barcodes(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Mahsulotning barcha barcodelari"""
    tid = resolve_tenant_id(db, current_user)
    barcodes = db.query(ProductBarcode).filter(
        ProductBarcode.product_id == product_id,
        ProductBarcode.tenant_id == tid,
    ).all()
    return [_bc_dict(b) for b in barcodes]


@router.post("/")
async def add_barcode(
    product_id: int,
    barcode: str,
    barcode_type: str = "CODE128",
    is_primary: bool = False,
    weight_variable: bool = False,
    notes: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu")),
):
    """Mahsulotga yangi barcode qo'shish"""
    tid = resolve_tenant_id(db, current_user)

    # BOSQICH 39: tekshiruv faqat shu tenant ichida (boshqa do'kon kodi to'sib qo'ymasin)
    existing = db.query(ProductBarcode).filter(
        ProductBarcode.tenant_id == tid,
        ProductBarcode.barcode == barcode,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Bu barcode allaqachon mavjud")

    if is_primary:
        db.query(ProductBarcode).filter(
            ProductBarcode.product_id == product_id,
            ProductBarcode.tenant_id == tid,
        ).update({"is_primary": False})

    pb = ProductBarcode(
        tenant_id=tid,
        product_id=product_id,
        barcode=barcode,
        barcode_type=barcode_type,
        is_primary=is_primary,
        weight_variable=weight_variable,
        notes=notes,
    )
    db.add(pb)
    db.commit()
    db.refresh(pb)
    return _bc_dict(pb)


@router.delete("/{barcode_id}")
async def delete_barcode(
    barcode_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_menu")),
):
    """Barcodeni o'chirish"""
    tid = resolve_tenant_id(db, current_user)
    pb = db.query(ProductBarcode).filter(
        ProductBarcode.id == barcode_id,
        ProductBarcode.tenant_id == tid,
    ).first()
    if not pb:
        raise HTTPException(status_code=404, detail="Barcode topilmadi")
    db.delete(pb)
    db.commit()
    return {"ok": True}


def _parse_weight_barcode(barcode: str) -> float:
    """EAN-13 tarozi barcode'dan gramm olish (PPPPWWWWW format)"""
    try:
        return float(barcode[7:12])
    except Exception:
        return 0.0


def _product_dict(p: Product, pb: Optional[ProductBarcode]) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "price": p.price,
        "cost_price": p.cost_price,
        "barcode": p.barcode,
        "unit": p.sale_unit,
        "image_url": p.image_url,
        "barcode_type": pb.barcode_type if pb else "CODE128",
        "weight_variable": pb.weight_variable if pb else False,
    }


def _bc_dict(b: ProductBarcode) -> dict:
    return {
        "id": b.id,
        "product_id": b.product_id,
        "barcode": b.barcode,
        "barcode_type": b.barcode_type,
        "is_primary": b.is_primary,
        "weight_variable": b.weight_variable,
        "notes": b.notes,
    }
