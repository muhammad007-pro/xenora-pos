from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional

from database import get_db
from models import Cafe, Employee, User
from schemas import MessageResponse
from deps import get_current_user, has_permission
from core.feature_flags import (
    BusinessType, Feature, resolve_enabled_features,
    is_pro_feature, get_feature_tier, FeatureTier, get_default_features,
    get_business_pro_features, get_all_business_features
)
from pydantic import BaseModel
from core.subscription import get_plan_info, VALID_PLANS

router = APIRouter()


class MyCafeFeatureBody(BaseModel):
    enabled:  list[str] = []
    disabled: list[str] = []


@router.get("/my/features")
async def get_my_cafe_features(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Joriy tenant uchun barcha flaglar + tier ma'lumoti."""
    if not current_user or not current_user.tenant_id:
        raise HTTPException(403, "Bu amal uchun tenant kerak")
    cafe = db.query(Cafe).filter(Cafe.id == current_user.tenant_id).first()
    if not cafe:
        raise HTTPException(404, "Kafe topilmadi")

    enabled_now = resolve_enabled_features(
        cafe.business_type, cafe.enabled_features, cafe.disabled_features,
        cafe.subscription_plan,   # PRO tarif → SHU biznesning PRO flaglari
    )
    # O'ZGARISH 3: FAQAT shu biznes turiga tegishli funksiyalar (FREE default + PRO)
    # qaytariladi — begona biznes funksiyasi UMUMAN kelmaydi (DOM'da ham chiqmaydi).
    default_set     = {f.value for f in get_default_features(cafe.business_type)}       # FREE default
    business_set    = get_all_business_features(cafe.business_type)                     # FREE + PRO (shu biznes)
    business_values = {f.value for f in business_set}
    # Super-admin enabled_overrides orqali bergan begona istisnolar ham ko'rinsin.
    extra_enabled   = {str(f) for f in (cafe.enabled_features or [])} & {f.value for f in Feature}
    visible_values  = business_values | extra_enabled
    features = [
        {
            "flag":        f.value,
            "tier":        get_feature_tier(f).value,
            "is_pro":      is_pro_feature(f),
            "is_enabled":  f.value in enabled_now,
            "in_business": f.value in business_values,
        }
        for f in Feature
        if f.value in visible_values
    ]
    return {
        "subscription_plan": cafe.subscription_plan,
        "enabled_features":  cafe.enabled_features  or [],
        "disabled_features": cafe.disabled_features or [],
        "features":          features,
    }


@router.patch("/my/features")
async def update_my_cafe_features(
    body: MyCafeFeatureBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_settings")),
):
    """Tenant egasi o'z kafe uchun faqat FREE flaglarni sozlaydi.
    PRO flag so'ralsa 403 qaytariladi."""
    if not current_user or not current_user.tenant_id:
        raise HTTPException(403, "Bu amal uchun tenant kerak")
    cafe = db.query(Cafe).filter(Cafe.id == current_user.tenant_id).first()
    if not cafe:
        raise HTTPException(404, "Kafe topilmadi")

    # Superuser hamma flagni o'zgartira oladi.
    # Oddiy tenant egasi uchun (O'ZGARISH 2+3):
    #   • PRO flag — (a) tarif PRO bo'lishi VA (b) shu biznes turining PRO to'plamida
    #     bo'lishi shart. Lite tarif → bloklangan; begona biznes PRO → rad.
    #   • FREE flag — shu biznes turining FREE default'ida bo'lishi shart (begona FREE rad).
    #   • O'chirish (disabled) — har doim ruxsat (eski override'larni tozalash uchun).
    if not current_user.is_superuser:
        plan = (cafe.subscription_plan or "free").lower()
        is_pro_plan = plan != "free"   # free(Lite)'dan boshqasi (pro) — PRO darajali
        default_set     = {f.value for f in get_default_features(cafe.business_type)}       # FREE (shu biznes)
        business_pro    = {f.value for f in get_business_pro_features(cafe.business_type)}   # PRO (shu biznes)

        blocked_pro     = []   # PRO flag, lekin tarif Lite
        foreign_pro     = []   # PRO flag, lekin begona biznes turi
        foreign_free    = []   # begona FREE flag
        for flag_str in body.enabled:
            try:
                pro = is_pro_feature(flag_str)
            except ValueError:
                raise HTTPException(422, f"Noma'lum flag: {flag_str}")
            if pro:
                if not is_pro_plan:
                    blocked_pro.append(flag_str)
                elif flag_str not in business_pro:
                    foreign_pro.append(flag_str)   # PRO tarif bor, lekin begona biznes PRO
            elif flag_str not in default_set:
                foreign_free.append(flag_str)

        if blocked_pro:
            raise HTTPException(
                403,
                f"Bu funksiyalar PRO tarifda. Tarifni PRO ga o'tkazing yoki Super Admin bilan bog'laning: {', '.join(blocked_pro)}"
            )
        if foreign_pro or foreign_free:
            raise HTTPException(
                403,
                f"Bu funksiyalar sizning biznes turingizga ({cafe.business_type}) tegishli emas: {', '.join(foreign_pro + foreign_free)}"
            )

    cur_enabled  = set(cafe.enabled_features  or [])
    cur_disabled = set(cafe.disabled_features or [])

    for flag_str in body.enabled:
        try:
            Feature(flag_str)
        except ValueError:
            raise HTTPException(422, f"Noma'lum flag: {flag_str}")
        cur_enabled.add(flag_str)
        cur_disabled.discard(flag_str)

    for flag_str in body.disabled:
        try:
            Feature(flag_str)
        except ValueError:
            raise HTTPException(422, f"Noma'lum flag: {flag_str}")
        cur_disabled.add(flag_str)
        cur_enabled.discard(flag_str)

    cafe.enabled_features  = list(cur_enabled)
    cafe.disabled_features = list(cur_disabled)
    db.commit()
    return {"ok": True, "message": "Funksiyalar saqlandi"}

@router.get("/")
async def get_cafes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_settings"))
):
    """Kafelarni olish. Super-admin — hammasi; tenant-admin — FAQAT o'z kafesi.

    ILDIZ (tenant izolyatsiya + xato #8): ilgari bu endpoint har qanday
    manage_settings foydalanuvchiga BARCHA kafelarni qaytarardi (izolyatsiya
    tuynugi), va frontend items[0] ni "joriy kafe" deb olardi — bu nom bo'yicha
    BIRINCHI kafe (ko'pincha boshqa tenant) edi. Endi tenant-admin faqat o'zini
    ko'radi → items[0] doim o'z kafesi. Cafe.id = tenant, shuning uchun
    apply_tenant_filter emas, to'g'ridan Cafe.id bo'yicha cheklaymiz."""
    query = db.query(Cafe)

    if not current_user.is_superuser and current_user.tenant_id:
        query = query.filter(Cafe.id == current_user.tenant_id)

    if is_active is not None:
        query = query.filter(Cafe.is_active == is_active)
    
    if search:
        query = query.filter(
            Cafe.name.ilike(f"%{search}%") | 
            Cafe.code.ilike(f"%{search}%")
        )
    
    total = query.count()
    cafes = query.order_by(Cafe.name).offset((page - 1) * page_size).limit(page_size).all()
    
    result = []
    for c in cafes:
        employees_count = db.query(Employee).filter(Employee.tenant_id == c.id).count()
        result.append({
            "id": c.id,
            "name": c.name,
            "code": c.code,
            "address": c.address,
            "phone": c.phone,
            "email": c.email,
            "business_type": c.business_type,
            "is_active": c.is_active,
            "subscription_plan": c.subscription_plan,
            "subscription_expires": c.subscription_expires,
            "employees_count": employees_count,
            "created_at": c.created_at
        })
    
    return {
        "items": result,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }

@router.get("/all")
async def get_all_cafes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Kafelar ro'yxati. Super-admin — barchasi; oddiy tenant — faqat o'z kafesi
    (tenant izolyatsiya: boshqa tenantlar ko'rinmaydi)."""
    query = db.query(Cafe).filter(Cafe.is_active == True)
    if not current_user.is_superuser and current_user.tenant_id is not None:
        query = query.filter(Cafe.id == current_user.tenant_id)
    cafes = query.order_by(Cafe.name).all()

    return [
        {
            "id": c.id,
            "name": c.name,
            "code": c.code,
            "address": c.address
        }
        for c in cafes
    ]

@router.post("/")
async def create_cafe(
    name: str,
    code: str,
    business_type: str = BusinessType.CAFE.value,
    address: Optional[str] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    subscription_plan: str = "free",
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_settings"))
):
    """Yangi kafe yaratish"""
    # Kod mavjudligini tekshirish
    existing = db.query(Cafe).filter(Cafe.code == code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Bu kod allaqachon mavjud")

    # Biznes turi to'g'riligini tekshirish
    try:
        business_type = BusinessType(business_type).value
    except ValueError:
        raise HTTPException(status_code=400, detail="Noto'g'ri biznes turi")

    cafe = Cafe(
        name=name,
        code=code,
        business_type=business_type,
        address=address,
        phone=phone,
        email=email,
        subscription_plan=subscription_plan,
        is_active=True
    )
    db.add(cafe)
    db.commit()
    db.refresh(cafe)
    
    return {
        "success": True,
        "cafe_id": cafe.id,
        "message": "Kafe yaratildi"
    }

@router.get("/{cafe_id}")
async def get_cafe(
    cafe_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Kafe ma'lumotlarini olish. Tenant izolyatsiya: oddiy user faqat o'z kafesini
    ko'ra oladi; boshqa tenant so'ralsa 403 (super-admin bypass)."""
    if not current_user.is_superuser and current_user.tenant_id is not None \
            and cafe_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Boshqa tenant ma'lumotiga ruxsat yo'q")
    cafe = db.query(Cafe).filter(Cafe.id == cafe_id).first()
    if not cafe:
        raise HTTPException(status_code=404, detail="Kafe topilmadi")

    employees = db.query(Employee).filter(Employee.tenant_id == cafe_id).all()
    
    return {
        "id": cafe.id,
        "name": cafe.name,
        "code": cafe.code,
        "address": cafe.address,
        "phone": cafe.phone,
        "email": cafe.email,
        "business_type": cafe.business_type,
        "enabled_features": list(resolve_enabled_features(
            cafe.business_type, cafe.enabled_features, cafe.disabled_features,
            cafe.subscription_plan,   # PRO tarif → PRO flaglar ochiq (xato #8 ildiz)
        )),
        "is_active": cafe.is_active,
        "subscription_plan": cafe.subscription_plan,
        "subscription_expires": cafe.subscription_expires,
        "subscription_limits": get_plan_info(cafe.subscription_plan),  # BOSQICH 2.2
        "created_at": cafe.created_at,
        "employees": [
            {
                "id": e.id,
                "full_name": e.full_name,
                "position": e.position,
                "phone": e.phone,
                "is_active": e.is_active
            }
            for e in employees
        ]
    }

@router.patch("/{cafe_id}")
async def update_cafe(
    cafe_id: int,
    name: Optional[str] = None,
    address: Optional[str] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    business_type: Optional[str] = None,
    subscription_plan: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_settings"))
):
    """Kafe ma'lumotlarini yangilash"""
    cafe = db.query(Cafe).filter(Cafe.id == cafe_id).first()
    if not cafe:
        raise HTTPException(status_code=404, detail="Kafe topilmadi")

    if name:
        cafe.name = name
    if address:
        cafe.address = address
    if phone:
        cafe.phone = phone
    if email:
        cafe.email = email
    if business_type:
        try:
            cafe.business_type = BusinessType(business_type).value
        except ValueError:
            raise HTTPException(status_code=400, detail="Noto'g'ri biznes turi")
    if subscription_plan:
        cafe.subscription_plan = subscription_plan
    if is_active is not None:
        cafe.is_active = is_active

    cafe.updated_at = datetime.now()
    db.commit()
    
    return MessageResponse(message="Kafe yangilandi")

@router.delete("/{cafe_id}")
async def delete_cafe(
    cafe_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_settings"))
):
    """Kafeni o'chirish (soft delete)"""
    cafe = db.query(Cafe).filter(Cafe.id == cafe_id).first()
    if not cafe:
        raise HTTPException(status_code=404, detail="Kafe topilmadi")
    
    cafe.is_active = False
    db.commit()

    return MessageResponse(message="Kafe o'chirildi")

@router.get("/{cafe_id}/features")
async def get_cafe_features(
    cafe_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Kafe uchun yoqilgan funksiyalar ro'yxati (frontend shu bo'yicha
    sidebar/sahifalarni moslaydi вЂ” qarang: BOSQICH 4.1)
    """
    cafe = db.query(Cafe).filter(Cafe.id == cafe_id).first()
    if not cafe:
        raise HTTPException(status_code=404, detail="Kafe topilmadi")

    return {
        "business_type": cafe.business_type,
        "enabled_features": list(resolve_enabled_features(
            cafe.business_type, cafe.enabled_features, cafe.disabled_features,
            cafe.subscription_plan,   # PRO tarif → PRO flaglar ochiq (xato #8 ildiz)
        )),
    }

@router.put("/{cafe_id}/features")
async def set_cafe_features(
    cafe_id: int,
    enabled_features: Optional[list[str]] = None,
    disabled_features: Optional[list[str]] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_settings"))
):
    """
    Standart to'plamga qo'shimcha qo'lda yoqish/o'chirish.
    ESLATMA: bu funksiyalarni butunlay o'chirmaydi вЂ” faqat shu kafe uchun
    UI'da ko'rinish-ko'rinmasligini boshqaradi (ARCHITECTURE.md, bo'lim 2A).
    """
    cafe = db.query(Cafe).filter(Cafe.id == cafe_id).first()
    if not cafe:
        raise HTTPException(status_code=404, detail="Kafe topilmadi")

    try:
        if enabled_features is not None:
            cafe.enabled_features = list({Feature(f).value for f in enabled_features})
        if disabled_features is not None:
            cafe.disabled_features = list({Feature(f).value for f in disabled_features})
    except ValueError:
        raise HTTPException(status_code=400, detail="Noto'g'ri funksiya nomi")

    cafe.updated_at = datetime.now()
    db.commit()

    return {
        "success": True,
        "enabled_features": list(resolve_enabled_features(
            cafe.business_type, cafe.enabled_features, cafe.disabled_features,
            cafe.subscription_plan,   # PRO tarif → PRO flaglar ochiq (xato #8 ildiz)
        )),
    }

@router.get("/code/{code}")
async def get_cafe_by_code(
    code: str,
    db: Session = Depends(get_db)
):
    """Kod bo'yicha kafe ma'lumotlarini olish (PIN login uchun)"""
    cafe = db.query(Cafe).filter(Cafe.code == code, Cafe.is_active == True).first()
    if not cafe:
        raise HTTPException(status_code=404, detail="Kafe topilmadi")
    
    return {
        "id": cafe.id,
        "name": cafe.name,
        "code": cafe.code,
        "is_active": cafe.is_active
    }

@router.post("/{cafe_id}/subscription/upgrade")
async def upgrade_subscription(
    cafe_id: int,
    plan: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_settings"))
):
    """Obuna tarifini o'zgartirish (BOSQICH 2.2)"""
    if plan not in VALID_PLANS:
        raise HTTPException(status_code=400, detail=f"Noto'g'ri tarif. Mumkin: {', '.join(VALID_PLANS)}")

    cafe = db.query(Cafe).filter(Cafe.id == cafe_id).first()
    if not cafe:
        raise HTTPException(status_code=404, detail="Kafe topilmadi")

    old_plan = cafe.subscription_plan
    cafe.subscription_plan = plan
    cafe.updated_at = datetime.now()
    db.commit()

    return {
        "success": True,
        "cafe_id": cafe_id,
        "old_plan": old_plan,
        "new_plan": plan,
        "subscription_limits": get_plan_info(plan),
    }


@router.post("/{cafe_id}/subscription/renew")
async def renew_subscription(
    cafe_id: int,
    months: int = 1,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_settings"))
):
    """Obunani yangilash"""
    cafe = db.query(Cafe).filter(Cafe.id == cafe_id).first()
    if not cafe:
        raise HTTPException(status_code=404, detail="Kafe topilmadi")
    
    if cafe.subscription_expires and cafe.subscription_expires > datetime.now():
        cafe.subscription_expires = cafe.subscription_expires + timedelta(days=30 * months)
    else:
        cafe.subscription_expires = datetime.now() + timedelta(days=30 * months)
    
    db.commit()
    
    return {
        "success": True,
        "subscription_expires": cafe.subscription_expires,
        "message": f"Obuna {months} oyga yangilandi"
    }
