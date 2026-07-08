from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import qrcode
import io

from database import get_db
from models import Table, User, Cafe
from deps import get_current_active_user, apply_tenant_filter

router = APIRouter()


def _make_qr(data: str, fill: str = "#111111") -> io.BytesIO:
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color=fill, back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


@router.get("/table/{table_id}")
async def generate_table_qr(
    table_id: int,
    base_url: str = Query("", description="Frontend origin, e.g. http://localhost:5500"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Stol uchun QR kod yaratish — public-menu.html ga yo'naltiradi"""
    table = apply_tenant_filter(db.query(Table), Table, current_user).filter(Table.id == table_id).first()
    if not table:
        raise HTTPException(status_code=404, detail="Stol topilmadi")

    cafe = db.query(Cafe).filter(Cafe.id == current_user.tenant_id).first()
    cafe_code = cafe.code if cafe else "default"

    origin = base_url.rstrip("/") if base_url else ""
    qr_data = f"{origin}/public-menu.html?cafe={cafe_code}&table={table_id}"

    buf = _make_qr(qr_data)
    return StreamingResponse(
        buf,
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename=stol_{table.number}_qr.png"},
    )


@router.get("/payment/{order_id}")
async def generate_payment_qr(
    order_id: int,
    db: Session = Depends(get_db),
):
    """To'lov uchun QR kod"""
    from models import Order
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")

    buf = _make_qr(f"payment:{order_id}:{order.final_amount}")
    return StreamingResponse(buf, media_type="image/png")


@router.get("/menu")
async def generate_menu_qr(
    base_url: str = Query(""),
    db: Session = Depends(get_db),
):
    """Umumiy menyu QR"""
    origin = base_url.rstrip("/") if base_url else ""
    buf = _make_qr(f"{origin}/public-menu.html")
    return StreamingResponse(buf, media_type="image/png")
