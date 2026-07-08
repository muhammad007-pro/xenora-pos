"""
Public endpoints — autentifikatsiyasiz (BOSQICH 5.1)

Mijoz QR kodni skanerlaydi → bu endpointdan menyu oladi → buyurtma beradi.
URL format: https://domain.com/menu/{cafe_code}?table={table_id}
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from database import get_db
from models import Cafe, Category, Product, Table, Order, OrderItem

router = APIRouter()


@router.get("/menu/{cafe_code}")
async def get_public_menu(
    cafe_code: str,
    category_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    QR-menyu: autentifikatsiyasiz menyu ko'rsatish.
    Mijoz QR skanerlaydi va bu endpoint menyu ma'lumotlarini qaytaradi.
    """
    cafe = db.query(Cafe).filter(Cafe.code == cafe_code, Cafe.is_active == True).first()
    if not cafe:
        raise HTTPException(status_code=404, detail="Kafe topilmadi")

    # Kategoriyalar
    cats = db.query(Category).filter(
        Category.tenant_id == cafe.id,
        Category.is_active == True
    ).order_by(Category.display_order, Category.name).all()

    # Mahsulotlar (faqat mavjud bo'lganlar)
    prod_q = db.query(Product).filter(
        Product.tenant_id == cafe.id,
        Product.is_active == True,
        Product.is_available == True,
    )
    if category_id:
        prod_q = prod_q.filter(Product.category_id == category_id)
    products = prod_q.order_by(Product.name).all()

    # Kategoriyalar bo'yicha mahsulotlarni guruhlash
    cat_map = {c.id: {"id": c.id, "name": c.name, "icon": None, "products": []} for c in cats}
    uncategorized = []

    for p in products:
        item = {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "price": p.price,
            "image_url": p.image_url,
            "sale_unit": p.sale_unit,
        }
        if p.category_id and p.category_id in cat_map:
            cat_map[p.category_id]["products"].append(item)
        else:
            uncategorized.append(item)

    menu = [v for v in cat_map.values() if v["products"]]
    if uncategorized:
        menu.append({"id": None, "name": "Boshqa", "icon": None, "products": uncategorized})

    return {
        "cafe": {
            "id":            cafe.id,
            "name":          cafe.name,
            "code":          cafe.code,
            "address":       cafe.address,
            "business_type": cafe.business_type,
        },
        "menu": menu,
        "currency": "UZS",
        "generated_at": datetime.now().isoformat(),
    }


@router.get("/table/{cafe_code}/{table_id}")
async def get_public_table_info(
    cafe_code: str,
    table_id: int,
    db: Session = Depends(get_db),
):
    """Stol ma'lumoti — QR skanerlanganda stol raqamini aniqlash"""
    cafe = db.query(Cafe).filter(Cafe.code == cafe_code).first()
    if not cafe:
        raise HTTPException(status_code=404, detail="Kafe topilmadi")

    table = db.query(Table).filter(
        Table.id == table_id,
        Table.tenant_id == cafe.id
    ).first()
    if not table:
        raise HTTPException(status_code=404, detail="Stol topilmadi")

    # Stolning faol buyurtmasini tekshirish
    active_order = db.query(Order).filter(
        Order.table_id == table_id,
        Order.tenant_id == cafe.id,
        Order.status.in_(["pending", "confirmed", "preparing", "ready", "served"])
    ).first()

    return {
        "table": {
            "id":       table.id,
            "number":   table.number,
            "section":  table.section,
            "capacity": table.capacity,
            "status":   table.status,
        },
        "active_order_id": active_order.id if active_order else None,
        "cafe_name":       cafe.name,
    }


@router.post("/order/{cafe_code}")
async def place_public_order(
    cafe_code: str,
    order_data: dict,
    db: Session = Depends(get_db),
):
    """
    Mijoz QR-menyu orqali buyurtma beradi (autentifikatsiyasiz).
    `order_data`: { table_id, items: [{product_id, quantity, notes}], customer_name?, notes? }
    """
    cafe = db.query(Cafe).filter(Cafe.code == cafe_code, Cafe.is_active == True).first()
    if not cafe:
        raise HTTPException(status_code=404, detail="Kafe topilmadi")

    table_id = order_data.get("table_id")
    items    = order_data.get("items", [])

    if not items:
        raise HTTPException(status_code=400, detail="Buyurtma bo'sh bo'lishi mumkin emas")

    table = db.query(Table).filter(Table.id == table_id, Table.tenant_id == cafe.id).first()
    if not table:
        raise HTTPException(status_code=404, detail="Stol topilmadi")

    # Buyurtma raqami
    from services.order_service import OrderService
    order_service = OrderService(db)
    order_number  = order_service.generate_order_number()

    # Yangi buyurtma
    total = 0.0
    order_items = []
    for item_data in items:
        product = db.query(Product).filter(
            Product.id == item_data["product_id"],
            Product.tenant_id == cafe.id,
            Product.is_available == True,
        ).first()
        if not product:
            continue
        qty        = max(1, int(item_data.get("quantity", 1)))
        line_total = product.price * qty
        total     += line_total
        from services.cost_service import get_product_cost
        order_items.append(OrderItem(
            product_id  = product.id,
            quantity    = qty,
            unit_price  = product.price,
            unit_cost   = get_product_cost(db, product.id),
            total_price = line_total,
            notes       = item_data.get("notes", ""),
        ))

    if not order_items:
        raise HTTPException(status_code=400, detail="Hech bir mahsulot topilmadi")

    order = Order(
        order_number  = order_number,
        daily_number  = order_service._next_daily_number(cafe.id),  # kunlik chek raqami (shu kafe)
        table_id      = table_id,
        tenant_id     = cafe.id,
        status        = "pending",
        order_type    = "dine-in",
        total_amount  = total,
        final_amount  = total,
        notes         = order_data.get("notes", ""),
        source        = "qr_menu",              # qayerdan kelganligini belgilash
    )
    db.add(order)
    db.flush()

    for oi in order_items:
        oi.order_id = order.id
        db.add(oi)

    table.status = "occupied"
    db.commit()
    db.refresh(order)

    # WebSocket orqali oshxona va adminlarga yuborish
    try:
        from websocket.manager import manager
        msg = {
            "type":         "new_order",
            "order_id":     order.id,
            "order_number": order.order_number,
            "table":        table.number,
            "source":       "qr_menu",
            "items":        [{"name": oi.product.name, "quantity": oi.quantity} for oi in order.items],
        }
        await manager.broadcast_to_kitchen(msg, tenant_id=cafe.id)
        await manager.broadcast_to_admins(msg, tenant_id=cafe.id)
    except Exception:
        pass  # WebSocket xatoligi buyurtmani bekor qilmasin

    return {
        "order_id":     order.id,
        "order_number": order.order_number,
        "status":       order.status,
        "total":        order.final_amount,
        "message":      "Buyurtmangiz qabul qilindi! Tez orada xizmat ko'rsatiladi.",
    }


@router.get("/order/{cafe_code}/{order_id}/status")
async def get_public_order_status(
    cafe_code: str,
    order_id: int,
    db: Session = Depends(get_db),
):
    """Mijoz o'z buyurtmasining holatini kuzatadi"""
    cafe = db.query(Cafe).filter(Cafe.code == cafe_code).first()
    if not cafe:
        raise HTTPException(status_code=404, detail="Kafe topilmadi")

    order = db.query(Order).filter(
        Order.id == order_id,
        Order.tenant_id == cafe.id
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")

    status_labels = {
        "pending":    "Qabul qilindi",
        "confirmed":  "Tasdiqlandi",
        "preparing":  "Tayyorlanmoqda",
        "ready":      "Tayyor!",
        "served":     "Xizmat qilindi",
        "completed":  "Yakunlandi",
        "cancelled":  "Bekor qilindi",
    }

    return {
        "order_id":     order.id,
        "order_number": order.order_number,
        "status":       order.status,
        "status_label": status_labels.get(order.status, order.status),
        "total":        order.final_amount,
        "items": [
            {
                "name":     oi.product.name,
                "quantity": oi.quantity,
                "status":   oi.status,
            }
            for oi in order.items
        ],
    }
