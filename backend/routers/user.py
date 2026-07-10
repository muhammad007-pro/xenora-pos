from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from database import get_db
from models import User, Role, Cafe
from schemas import UserCreate, UserUpdate, UserInDB, PaginatedResponse, MessageResponse
from deps import resolve_tenant_id, get_current_user, has_permission, get_current_active_user, apply_tenant_filter
from core.security import get_password_hash, hash_pin
from core.subscription import get_plan_limits, is_within_user_limit

router = APIRouter()

@router.get("/", response_model=PaginatedResponse)
async def get_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    search: Optional[str] = None,
    role_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_users"))
):
    """Barcha foydalanuvchilarni olish"""
    query = db.query(User)
    # BOSQICH 1.5: tenant bo'yicha cheklash
    query = apply_tenant_filter(query, User, current_user)

    if search:
        query = query.filter(
            User.full_name.ilike(f"%{search}%") |
            User.username.ilike(f"%{search}%") |
            User.email.ilike(f"%{search}%")
        )
    
    if role_id:
        query = query.filter(User.role_id == role_id)
    
    if is_active is not None:
        query = query.filter(User.is_active == is_active)
    
    total = query.count()
    users = query.order_by(User.full_name).offset((page - 1) * page_size).limit(page_size).all()
    
    return PaginatedResponse(
        items=[UserInDB.model_validate(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size
    )

@router.get("/me", response_model=UserInDB)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user)
):
    """Joriy foydalanuvchi ma'lumotlari"""
    return UserInDB.model_validate(current_user)

@router.post("/", response_model=UserInDB)
async def create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_users"))
):
    """Yangi foydalanuvchi yaratish.

    Xodim (kassir/ofitsiant) faqat ISM + PIN bilan qo'shilishi mumkin — telefon/login/parol
    ixtiyoriy. Telefon berilmasa server sintetik unikal qiymat yaratadi (xodim access_code + PIN
    bilan kiradi), parol berilmasa tasodifiy parol qo'yiladi.
    """
    import secrets
    from utils.helpers import normalize_phone

    # Telefon — berilgan bo'lsa normalize + unikal; berilmasa keyinroq sintetik qiymat.
    norm_phone = normalize_phone(user_data.phone) if user_data.phone else None
    if norm_phone and db.query(User).filter(User.phone == norm_phone).first():
        raise HTTPException(status_code=400, detail="Bu telefon band")

    # Tenant biriktirishni oldinroq aniqlaymiz (username tenant-scoped tekshiruvi uchun kerak)
    if current_user.is_superuser or current_user.tenant_id is None:
        if not user_data.tenant_id:
            raise HTTPException(status_code=400, detail="Super-admin user yaratishda tenant_id (kafe) majburiy")
        cafe = db.query(Cafe).filter(Cafe.id == user_data.tenant_id, Cafe.is_active == True).first()
        if not cafe:
            raise HTTPException(status_code=400, detail="Bunday faol kafe yo'q")
        tenant_id = user_data.tenant_id
    else:
        tenant_id = resolve_tenant_id(db, current_user)  # yaratuvchi tenant'iga biriktiriladi

    # Username — ixtiyoriy; unikallik TENANT ICHIDA tekshiriladi (global emas).
    # Shu tufayli har do'konda "admin"/"cashier" kabi nomlar takrorlanishi mumkin.
    if user_data.username and db.query(User).filter(
        User.username == user_data.username,
        User.tenant_id == tenant_id,
    ).first():
        raise HTTPException(status_code=400, detail="Bu username shu do'konda band")

    # Email — ixtiyoriy; berilgan bo'lsa unikallik tekshiriladi
    if user_data.email and db.query(User).filter(User.email == user_data.email).first():
        raise HTTPException(status_code=400, detail="Bu email band")

    # Rol tekshirish
    if user_data.role_id:
        role = db.query(Role).filter(Role.id == user_data.role_id).first()
        if not role:
            raise HTTPException(status_code=404, detail="Rol topilmadi")

    # BOSQICH 2.2: tarif limiti tekshirish (superuser cheksiz)
    if not current_user.is_superuser and current_user.tenant_id is not None:
        cafe = db.query(Cafe).filter(Cafe.id == current_user.tenant_id).first()
        if cafe:
            user_count = db.query(User).filter(User.tenant_id == current_user.tenant_id).count()
            if not is_within_user_limit(user_count, cafe.subscription_plan):
                limits = get_plan_limits(cafe.subscription_plan)
                raise HTTPException(
                    status_code=402,
                    detail=f"'{cafe.subscription_plan}' tarifi faqat {limits.max_users} ta foydalanuvchiga ruxsat beradi. "
                           f"Tarifni yangilang: /api/v1/cafes/{cafe.id}/subscription/upgrade"
                )

    if user_data.pin and (not user_data.pin.isdigit() or len(user_data.pin) != 4):
        raise HTTPException(status_code=400, detail="PIN 4 xonali raqam bo'lishi kerak")

    # ISM + PIN yetarli: telefon/parol berilmasa — kamida bittasi (parol yoki PIN) bo'lishi shart.
    if not user_data.password and not user_data.pin:
        raise HTTPException(status_code=400, detail="Parol yoki PIN kod kiritilishi shart")

    # Telefon berilmagan bo'lsa — sintetik unikal placeholder (phone NOT NULL + unique cheklovi uchun).
    # Bu login kaliti EMAS; xodim access_code + PIN bilan kiradi. Ko'rinishда "-" sifatida chiqadi.
    if not norm_phone:
        for _ in range(20):
            candidate = f"pin-{tenant_id}-{secrets.randbelow(10**7):07d}"
            if not db.query(User).filter(User.phone == candidate).first():
                norm_phone = candidate
                break
        else:
            raise HTTPException(status_code=500, detail="Xodim uchun ichki identifikator yaratib bo'lmadi")

    # Parol berilmasa (faqat PIN bilan kiruvchi xodim) — tasodifiy kuchli parol.
    effective_password = user_data.password or secrets.token_urlsafe(16)

    user = User(
        username=user_data.username,
        email=user_data.email,
        full_name=user_data.full_name,
        phone=norm_phone,
        hashed_password=get_password_hash(effective_password),
        hashed_pin=hash_pin(user_data.pin) if user_data.pin else None,
        role_id=user_data.role_id,
        branch_id=user_data.branch_id,
        is_active=True,
        tenant_id=tenant_id
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    return UserInDB.model_validate(user)

@router.get("/{user_id}", response_model=UserInDB)
async def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_users"))
):
    """Foydalanuvchi ma'lumotlarini olish"""
    user = apply_tenant_filter(db.query(User), User, current_user).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
    
    return UserInDB.model_validate(user)

@router.patch("/{user_id}", response_model=UserInDB)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_users"))
):
    """Foydalanuvchini yangilash"""
    user = apply_tenant_filter(db.query(User), User, current_user).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
    
    update_data = user_data.model_dump(exclude_unset=True)

    # Parol alohida yangilanadi
    if "password" in update_data:
        user.hashed_password = get_password_hash(update_data.pop("password"))

    # PIN alohida yangilanadi
    if "pin" in update_data:
        pin = update_data.pop("pin")
        if pin is None or pin == "":
            user.hashed_pin = None
        else:
            if not pin.isdigit() or len(pin) != 4:
                raise HTTPException(status_code=400, detail="PIN 4 xonali raqam bo'lishi kerak")
            user.hashed_pin = hash_pin(pin)

    # Telefon o'zgarsa — normalize + unikallik (BOSQICH 38)
    if "phone" in update_data:
        from utils.helpers import normalize_phone
        norm_phone = normalize_phone(update_data.pop("phone"))
        if not norm_phone:
            raise HTTPException(status_code=400, detail="Telefon raqam majburiy")
        clash = db.query(User).filter(User.phone == norm_phone, User.id != user.id).first()
        if clash:
            raise HTTPException(status_code=400, detail="Bu telefon band")
        user.phone = norm_phone

    for field, value in update_data.items():
        setattr(user, field, value)
    
    db.commit()
    db.refresh(user)
    
    return UserInDB.model_validate(user)

@router.patch("/me", response_model=UserInDB)
async def update_current_user(
    user_data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Joriy foydalanuvchi profilini yangilash"""
    update_data = user_data.model_dump(exclude_unset=True)
    
    # Oddiy foydalanuvchi rolini o'zgartira olmaydi
    update_data.pop("role_id", None)
    update_data.pop("is_active", None)
    update_data.pop("is_superuser", None)
    
    for field, value in update_data.items():
        setattr(current_user, field, value)
    
    db.commit()
    db.refresh(current_user)
    
    return UserInDB.model_validate(current_user)

@router.delete("/{user_id}", response_model=MessageResponse)
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_users"))
):
    """Foydalanuvchini o'chirish"""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="O'zingizni o'chira olmaysiz")

    user = apply_tenant_filter(db.query(User), User, current_user).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
    
    # Soft delete - faqat nofaol qilish
    user.is_active = False
    db.commit()
    
    return MessageResponse(message="Foydalanuvchi o'chirildi")

@router.get("/{user_id}/stats")
async def get_user_stats(
    user_id: int,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Xodim statistikasi (buyurtmalar, daromad, smenalar, o'rtacha chek)"""
    from models import Order, Shift, OrderStatus
    from datetime import datetime, timedelta
    dt_from = datetime.fromisoformat(date_from) if date_from else (datetime.now() - timedelta(days=30))
    dt_to   = datetime.fromisoformat(date_to)   if date_to   else datetime.now()

    orders = db.query(Order).filter(
        Order.waiter_id == user_id,
        Order.created_at >= dt_from,
        Order.created_at <= dt_to,
        Order.status == OrderStatus.COMPLETED
    ).all()
    total_orders  = len(orders)
    total_revenue = sum(o.final_amount for o in orders)

    total_shifts = db.query(Shift).filter(
        Shift.user_id  == user_id,
        Shift.start_time >= dt_from,
        Shift.start_time <= dt_to
    ).count()

    return {
        "total_orders":  total_orders,
        "total_revenue": round(total_revenue, 2),
        "avg_check":     round(total_revenue / total_orders, 2) if total_orders else 0,
        "total_shifts":  total_shifts,
        "period_days":   (dt_to - dt_from).days,
    }

@router.post("/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    new_password: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_users"))
):
    """Foydalanuvchi parolini tiklash (admin uchun)"""
    user = apply_tenant_filter(db.query(User), User, current_user).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
    
    user.hashed_password = get_password_hash(new_password)
    db.commit()
    
    return MessageResponse(message="Parol yangilandi")
