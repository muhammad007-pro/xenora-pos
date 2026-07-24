"""Super Admin paneli — faqat is_superuser=True foydalanuvchilar uchun.

Tenant boshqaruvi, obuna/to'lov tarixi, SaaS daromad statistikasi.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional
import secrets
import string

from database import get_db
from models import Cafe, User, TenantPayment, Role
from deps import get_current_superuser
from core.subscription import VALID_PLANS, get_plan_info, subscription_state
from config import settings
from core.feature_flags import BusinessType, Feature, resolve_enabled_features, get_default_features
from core.security import get_password_hash
from core.password_policy import validate_password

# ── FUNKSIYA META — uzbekcha nom, ikonka, qaysi biznes turiga default ──────────
FEATURE_META: dict[str, dict] = {
    # Restoran / Kafe / Fast Food
    "kitchen_display":     {"name": "Oshxona displeyi (KDS)",      "icon": "🍽️",  "group": "Restoran"},
    "table_management":    {"name": "Stol boshqaruvi",              "icon": "🪑",  "group": "Restoran"},
    "waiter":              {"name": "Ofitsiant rejimi",             "icon": "🧑‍🍳", "group": "Restoran"},
    "table_reservation":   {"name": "Stol bron qilish",            "icon": "📅",  "group": "Restoran"},
    "recipe":              {"name": "Retsept (ombor chiqimi)",      "icon": "📋",  "group": "Restoran"},
    "modifiers":           {"name": "Modifikatorlar (o'lcham...)",  "icon": "🔧",  "group": "Restoran"},
    "combo":               {"name": "Kombo / Set menyu",            "icon": "🍱",  "group": "Restoran"},
    "happy_hour":          {"name": "Happy Hour chegirma",          "icon": "⏰",  "group": "Restoran"},
    "table_merge":         {"name": "Stol birlashtirish",           "icon": "🔗",  "group": "Restoran"},
    "courses":             {"name": "Kursli ovqat (1-2-ovqat)",     "icon": "🍜",  "group": "Restoran"},
    "waiter_call":         {"name": "Ofitsiant chaqirish (QR)",     "icon": "🔔",  "group": "Restoran"},
    "tips":                {"name": "Choy puli (tips)",             "icon": "💰",  "group": "Restoran"},
    "customer_history":    {"name": "Mijoz tarixi / sevimlilar",    "icon": "❤️",  "group": "Restoran"},
    "voice_order":         {"name": "Ovozli signal (oshxona)",      "icon": "📢",  "group": "Restoran"},
    "yield_tracking":      {"name": "Poteriya / Yield %",           "icon": "📉",  "group": "Restoran"},
    "staff_meal":          {"name": "Xodimlar ovqati",              "icon": "🥗",  "group": "Restoran"},
    # Umumiy
    "inventory":           {"name": "Ombor boshqaruvi",             "icon": "🏭",  "group": "Umumiy"},
    "loyalty":             {"name": "Sodiqlik dasturi (bonus)",      "icon": "⭐",  "group": "Umumiy"},
    "delivery":            {"name": "Yetkazib berish",              "icon": "🚚",  "group": "Umumiy"},
    "qr_menu":             {"name": "QR-menyu (mijoz buyurtmasi)",  "icon": "📱",  "group": "Umumiy"},
    "scale":               {"name": "Tarozi (kg/g o'lchov)",        "icon": "⚖️",  "group": "Umumiy"},
    # Magazin / Supermarket
    "barcode":             {"name": "Shtrix-kod skaneri",           "icon": "📦",  "group": "Magazin"},
    "credit_sales":        {"name": "Nasiya / Qarz daftar",         "icon": "💳",  "group": "Magazin"},
    "wholesale_pricing":   {"name": "Optom / Dona narx",            "icon": "🏷️",  "group": "Magazin"},
    "returns":             {"name": "Qaytarish tizimi",             "icon": "↩️",  "group": "Magazin"},
    "promotions":          {"name": "Aksiya / Murakkab chegirma",   "icon": "🎁",  "group": "Magazin"},
    "multi_barcode":       {"name": "Ko'p barcode (1 mahsulot)",    "icon": "🔢",  "group": "Magazin"},
    "quick_sell":          {"name": "Tez sotuv paneli",             "icon": "⚡",  "group": "Magazin"},
    "supplier_accounting": {"name": "Priyomka / Yetkazuvchi hisob", "icon": "🚛",  "group": "Magazin"},
    "price_history":       {"name": "Narx o'zgarish tarixi",        "icon": "📊",  "group": "Magazin"},
    "receipt_settings":    {"name": "Chek sozlamasi",               "icon": "🧾",  "group": "Magazin"},
    "cash_register":       {"name": "Kassa smena (kamomad/ortiq)",  "icon": "💵",  "group": "Magazin"},
    "departments":         {"name": "Bo'limlar (seksiya/dept)",     "icon": "🗂️",  "group": "Magazin"},
    # Dorixona
    "expiry_date":         {"name": "Yaroqlilik muddati nazorati",  "icon": "💊",  "group": "Dorixona"},
    # Salon / Fitnes / Boshqalar
    "time_booking":        {"name": "Vaqt bron (appointment)",      "icon": "🗓️",  "group": "Xizmat"},
    "services":            {"name": "Xizmatlar ro'yxati",           "icon": "💆",  "group": "Xizmat"},
}

router = APIRouter()

# Superadmin SaaS daromadi USD ($) da hisoblanadi (owner moliya dashboard).
# Tenant-facing tarif tanlash UZS'da qoladi (owner/cafes.html dropdown) — bular alohida.
# Kalit "free" o'zgarmaydi (DB/VALID_PLANS buzilmaydi) — ko'rinadigan nom "Lite".
PLAN_PRICES = {
    "free":       10,    # Lite — $10/oy
    "pro":        50,    # Pro  — $50/oy
    "enterprise": 0,     # ishlatilmaydi (ikki tarif tizimi)
}

WARN_DAYS = 7   # Muddat tugashiga necha kun qolganida ogohlantirish


def _effective_status(cafe: Cafe, now: datetime) -> str:
    """Saqlangan tenant_status + subscription_expires asosida haqiqiy holatni qaytaradi."""
    ts = cafe.tenant_status or "active"
    if ts == "blocked":
        return "blocked"
    if ts == "trial":
        if cafe.trial_expires and cafe.trial_expires < now:
            return "expired"
        return "trial"
    # active
    if cafe.subscription_expires and cafe.subscription_expires < now:
        return "expired"
    return "active"


def _tenant_dict(cafe: Cafe, now: datetime) -> dict:
    status = _effective_status(cafe, now)
    days_left = None
    if cafe.subscription_expires:
        days_left = (cafe.subscription_expires - now).days

    # Enforcement bilan AYNAN bir xil holat (grace/expiring ham) — panelда ko'rinsin.
    # tenant_status (yuqorida) O'ZGARMAYDI: filtr/statistika eski so'z boyligini saqlaydi;
    # sub_state — boyroq DISPLAY holati (active/expiring/grace/expired/blocked/inactive).
    st = subscription_state(cafe, now, settings.SUBSCRIPTION_GRACE_DAYS)

    return {
        "id":                  cafe.id,
        "name":                cafe.name,
        "code":                cafe.code,
        "access_code":         cafe.access_code,   # do'kon KIRISH kodi (login) — super-admin mijozga beradi
        "business_type":       cafe.business_type,
        "owner_name":          cafe.owner_name,
        "owner_phone":         cafe.owner_phone or cafe.phone,
        "phone":               cafe.phone,
        "email":               cafe.email,
        "subscription_plan":   cafe.subscription_plan or "free",
        "subscription_expires": cafe.subscription_expires,
        "days_left":           days_left,
        "is_active":           cafe.is_active,
        "tenant_status":       status,
        # Grace-aware DISPLAY (additive — eski maydonlar buzilmaydi):
        "sub_state":           st["state"],
        "in_grace":            st["in_grace"],
        "grace_days_left":     st["grace_days_left"],
        "trial_expires":       cafe.trial_expires,
        "blocked_at":          cafe.blocked_at,
        "blocked_reason":      cafe.blocked_reason,
        "created_at":          cafe.created_at,
    }


# ── STATISTIKA ───────────────────────────────────────────────────────────────

@router.get("/stats")
async def get_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """SaaS platformaning umumiy ko'rsatkichlari."""
    now = datetime.now()
    cafes = db.query(Cafe).all()

    statuses = [_effective_status(c, now) for c in cafes]
    active_count    = statuses.count("active")
    trial_count     = statuses.count("trial")
    blocked_count   = statuses.count("blocked")
    expired_count   = statuses.count("expired")

    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_payments = db.query(TenantPayment).filter(
        TenantPayment.created_at >= month_start
    ).all()
    month_revenue = sum(p.amount for p in month_payments)

    total_revenue = sum(p.amount for p in db.query(TenantPayment).all())

    plan_stats = {}
    for plan in ["free", "pro", "enterprise"]:
        cnt = sum(1 for c in cafes if (c.subscription_plan or "free") == plan)
        plan_stats[plan] = {
            "count":           cnt,
            "price":           PLAN_PRICES.get(plan, 0),
            "monthly_revenue": cnt * PLAN_PRICES.get(plan, 0),
        }

    return {
        "total":           len(cafes),
        "active":          active_count,
        "trial":           trial_count,
        "blocked":         blocked_count,
        "expired":         expired_count,
        "month_revenue":   month_revenue,
        "total_revenue":   total_revenue,
        "plan_stats":      plan_stats,
    }


# ── OGOHLANTIRISHLAR ─────────────────────────────────────────────────────────

@router.get("/alerts")
async def get_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """Qarzdorlar va muddat tugashiga yaqin tenantlar."""
    now = datetime.now()
    warn_deadline = now + timedelta(days=WARN_DAYS)
    cafes = db.query(Cafe).filter(Cafe.is_active == True).all()

    expired = []
    expiring_soon = []
    for c in cafes:
        st = _effective_status(c, now)
        if st == "expired":
            expired.append(_tenant_dict(c, now))
        elif st == "active" and c.subscription_expires and c.subscription_expires <= warn_deadline:
            expiring_soon.append(_tenant_dict(c, now))

    return {
        "expired":       expired,
        "expiring_soon": expiring_soon,
        "expired_count":       len(expired),
        "expiring_soon_count": len(expiring_soon),
    }


# ── TENANT RO'YXATI ──────────────────────────────────────────────────────────

@router.get("/tenants")
async def list_tenants(
    search:    Optional[str] = None,
    status:    Optional[str] = None,   # active | trial | blocked | expired
    plan:      Optional[str] = None,
    page:      int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """Barcha tenantlar ro'yxati (filter + qidiruv)."""
    now = datetime.now()
    query = db.query(Cafe)

    if search:
        like = f"%{search}%"
        query = query.filter(
            Cafe.name.ilike(like)
            | Cafe.owner_name.ilike(like)
            | Cafe.phone.ilike(like)
            | Cafe.owner_phone.ilike(like)
            | Cafe.code.ilike(like)
        )
    if plan:
        query = query.filter(Cafe.subscription_plan == plan)

    cafes = query.order_by(Cafe.created_at.desc()).all()

    result = []
    for c in cafes:
        d = _tenant_dict(c, now)
        if status and d["tenant_status"] != status:
            continue
        result.append(d)

    total = len(result)
    start = (page - 1) * page_size
    return {
        "items":      result[start: start + page_size],
        "total":      total,
        "page":       page,
        "page_size":  page_size,
    }


# ── TENANT YARATISH ──────────────────────────────────────────────────────────

@router.post("/tenants")
async def create_tenant(
    # Biznes ma'lumotlari
    name:             str = Body(...),
    business_type:    str = Body("cafe"),
    owner_name:       str = Body(...),
    owner_phone:      str = Body(...),
    phone:            Optional[str] = Body(None),
    email:            Optional[str] = Body(None),
    address:          Optional[str] = Body(None),
    subscription_plan: str = Body("free"),
    trial_days:       int = Body(0),       # 0 = sinov muddati yo'q
    months:           int = Body(0),       # obuna muddati (oylar)
    # Admin foydalanuvchi uchun
    admin_username:   str = Body(...),
    admin_email:      Optional[str] = Body(None),
    admin_password:   Optional[str] = Body(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """Yangi tenant ro'yxatdan o'tkazish va uning admin foydalanuvchisini yaratish."""
    # Biznes turi tekshirish
    try:
        btype = BusinessType(business_type).value
    except ValueError:
        raise HTTPException(400, "Noto'g'ri biznes turi")

    if subscription_plan not in VALID_PLANS:
        raise HTTPException(400, f"Noto'g'ri tarif: {VALID_PLANS}")

    # Kod yaratish (noyob slug — QR-menyu/URL uchun)
    base_code = "".join(c for c in name.lower() if c.isalnum())[:8] or "biz"
    code = base_code
    suffix = 1
    while db.query(Cafe).filter(Cafe.code == code).first():
        code = f"{base_code}{suffix}"
        suffix += 1

    # Do'kon KIRISH kodi (login uchun): 100.200.N — N keyingi ketma-ket raqam (avto).
    _max_n = 0
    for (ac,) in db.query(Cafe.access_code).filter(Cafe.access_code.like("100.200.%")).all():
        try:
            _n = int(ac.rsplit(".", 1)[1])
            if _n > _max_n:
                _max_n = _n
        except (ValueError, IndexError, AttributeError):
            continue
    _max_n += 1
    access_code = f"100.200.{_max_n}"
    while db.query(Cafe).filter(Cafe.access_code == access_code).first():  # noyoblik kafolati
        _max_n += 1
        access_code = f"100.200.{_max_n}"

    # Tenant_status va muddatlar
    now = datetime.now()
    if trial_days > 0:
        tenant_status = "trial"
        trial_expires = now + timedelta(days=trial_days)
        subscription_expires = None
    else:
        tenant_status = "active"
        trial_expires = None
        subscription_expires = now + timedelta(days=30 * months) if months > 0 else None

    cafe = Cafe(
        name=name,
        code=code,
        access_code=access_code,
        business_type=btype,
        owner_name=owner_name,
        owner_phone=owner_phone,
        phone=phone or owner_phone,
        email=email or admin_email,
        address=address,
        subscription_plan=subscription_plan,
        subscription_expires=subscription_expires,
        tenant_status=tenant_status,
        trial_expires=trial_expires,
        is_active=True,
        enabled_features=[],   # business_type matritsasidan avtomatik olinadi (JWT da)
        disabled_features=[],
    )
    db.add(cafe)
    db.flush()  # cafe.id olish uchun

    # Admin username YANGI tenant ICHIDA unikal bo'lsin (GLOBAL emas) — ildiz (xato #2
    # takroriy). username composite unique (tenant_id, username) [[v1.0.1]], shuning
    # uchun har do'konda "admin" mumkin. Yangi tenant bo'sh → bu amalda doim o'tadi;
    # tenant-scoped tekshiruv faqat izchillik uchun (kelajakda 2-admin qo'shilsa).
    if db.query(User).filter(
        User.username == admin_username,
        User.tenant_id == cafe.id,
    ).first():
        raise HTTPException(400, f"Bu do'konda '{admin_username}' username band")

    # Admin email — KIRISH himoyasi: yaroqsiz bo'lsa rad etamiz (aniq xato),
    # berilmasa username'dan toza email avto-generatsiya qilamiz (bazaga yaroqsiz
    # email umuman tushmasin → /auth/me hech qachon sinmaydi).
    import re as _re
    clean_uname = _re.sub(r'[^a-z0-9]', '', (admin_username or '').lower()) or f"biz{cafe.id}"
    if admin_email:
        if not _is_valid_email(admin_email):
            raise HTTPException(400, f"Email formati noto'g'ri: '{admin_email}'")
        resolved_email = admin_email
    else:
        resolved_email = f"{clean_uname}@restopos.uz"
    # Unikal: band bo'lsa cafe.id bilan (avto-generatsiya holatida)
    if db.query(User).filter(User.email == resolved_email).first():
        if admin_email:
            raise HTTPException(400, f"'{admin_email}' email allaqachon mavjud. Boshqa email kiriting.")
        resolved_email = f"{clean_uname}{cafe.id}@restopos.uz"

    # Rollar GLOBAL (Role.name unique, tenant_id yo'q) — yangi tenant admin'iga
    # "admin" rolini biriktiramiz. Aks holda role_id=None bo'lib qoladi va login
    # redirect uni POS'ga yuboradi (tenant izolyatsiyaga ta'sir yo'q — rol global).
    admin_role = db.query(Role).filter(Role.name == "admin").first()

    if admin_password:
        validate_password(admin_password)   # superadmin kiritgan parolga siyosat (avto emas)
    password = admin_password or _random_password()
    admin_user = User(
        username=admin_username,
        email=resolved_email,
        full_name=owner_name,
        phone=owner_phone,
        hashed_password=get_password_hash(password),
        is_active=True,
        is_superuser=False,
        tenant_id=cafe.id,
        role_id=admin_role.id if admin_role else None,
    )
    db.add(admin_user)
    db.commit()
    db.refresh(cafe)

    return {
        "success":        True,
        "tenant_id":      cafe.id,
        "tenant_code":    cafe.code,
        "access_code":    cafe.access_code,   # do'kon KIRISH kodi (login) — mijozga beriladi
        "admin_username": admin_username,
        "admin_password": password if not admin_password else "***",
        "message":        f"Tenant '{name}' yaratildi",
    }


def _random_password(length: int = 10) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _is_valid_email(e: str) -> bool:
    """EmailStr (pydantic) bilan AYNAN bir xil validator — agar bu o'tsa, /auth/me va
    UserCreate ham qabul qiladi (izchillik)."""
    try:
        from email_validator import validate_email
        validate_email(e, check_deliverability=False)
        return True
    except Exception:
        return False


# ── TENANT YANGILASH ─────────────────────────────────────────────────────────

@router.patch("/tenants/{tenant_id}")
async def update_tenant(
    tenant_id:         int,
    name:              Optional[str]  = Body(None),
    owner_name:        Optional[str]  = Body(None),
    owner_phone:       Optional[str]  = Body(None),
    phone:             Optional[str]  = Body(None),
    email:             Optional[str]  = Body(None),
    address:           Optional[str]  = Body(None),
    business_type:     Optional[str]  = Body(None),
    subscription_plan: Optional[str]  = Body(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    cafe = db.query(Cafe).filter(Cafe.id == tenant_id).first()
    if not cafe:
        raise HTTPException(404, "Tenant topilmadi")

    if name:            cafe.name        = name
    if owner_name:      cafe.owner_name  = owner_name
    if owner_phone:     cafe.owner_phone = owner_phone
    if phone:           cafe.phone       = phone
    if email:           cafe.email       = email
    if address:         cafe.address     = address
    if business_type:
        try:
            cafe.business_type = BusinessType(business_type).value
        except ValueError:
            raise HTTPException(400, "Noto'g'ri biznes turi")
    if subscription_plan:
        if subscription_plan not in VALID_PLANS:
            raise HTTPException(400, f"Noto'g'ri tarif")
        cafe.subscription_plan = subscription_plan

    cafe.updated_at = datetime.now()
    db.commit()
    return {"success": True, "message": "Tenant yangilandi"}


# ── DO'KON ADMIN LOGIN/PAROL (super-admin) ───────────────────────────────────

def _tenant_admin(db: Session, tenant_id: int) -> Optional[User]:
    """Do'kon (tenant) asosiy admin foydalanuvchisini topadi.

    Avval 'admin' rolli foydalanuvchi (eng eski), bo'lmasa tenantning istalgan
    eng eski oddiy foydalanuvchisi. Super-admin (is_superuser) hisobga olinmaydi."""
    q = db.query(User).filter(User.tenant_id == tenant_id, User.is_superuser == False)
    admin = (
        q.join(Role, User.role_id == Role.id)
         .filter(Role.name == "admin")
         .order_by(User.id.asc())
         .first()
    )
    if not admin:
        admin = q.order_by(User.id.asc()).first()
    return admin


@router.get("/tenants/{tenant_id}/admin")
async def get_tenant_admin(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """Do'kon admin login ma'lumotlari (telefon = login kaliti). Super-admin ko'radi."""
    cafe = db.query(Cafe).filter(Cafe.id == tenant_id).first()
    if not cafe:
        raise HTTPException(404, "Tenant topilmadi")
    admin = _tenant_admin(db, tenant_id)
    if not admin:
        return {"admin": None}
    return {"admin": {
        "id":        admin.id,
        "username":  admin.username,
        "phone":     admin.phone,
        "email":     admin.email,
        "full_name": admin.full_name,
    }}


class AdminUpdateBody(BaseModel):
    phone:          Optional[str] = None   # login telefonini o'zgartirish (ixtiyoriy)
    password:       Optional[str] = None   # aniq yangi parol (ixtiyoriy)
    reset_password: bool = False           # True + password bo'sh → avto-generatsiya


@router.patch("/tenants/{tenant_id}/admin")
async def update_tenant_admin(
    tenant_id: int,
    body: AdminUpdateBody = Body(default=AdminUpdateBody()),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """Do'kon admin loginini tahrirlash: telefon o'zgartirish va/yoki parol reset.

    Parol yangilansa qaytariladi (super-admin mijozga beradi). Telefon — login
    kaliti, noyoblik tekshiriladi. is_active o'zgarmaydi (mavjud sessiya buzilmaydi)."""
    cafe = db.query(Cafe).filter(Cafe.id == tenant_id).first()
    if not cafe:
        raise HTTPException(404, "Tenant topilmadi")
    admin = _tenant_admin(db, tenant_id)
    if not admin:
        raise HTTPException(404, "Bu do'konda admin foydalanuvchi topilmadi")

    if body.phone:
        from utils.helpers import normalize_phone
        norm = normalize_phone(body.phone)
        if not norm:
            raise HTTPException(400, "Telefon raqam noto'g'ri")
        clash = db.query(User).filter(User.phone == norm, User.id != admin.id).first()
        if clash:
            raise HTTPException(400, "Bu telefon boshqa foydalanuvchida band")
        admin.phone = norm

    new_pw = None
    if body.password:
        validate_password(body.password)   # kiritilgan parolga siyosat
        new_pw = body.password
    elif body.reset_password:
        new_pw = _random_password()        # avto-generatsiya — kuchli, tekshiruv shart emas
    if new_pw is not None:
        admin.hashed_password = get_password_hash(new_pw)

    admin.updated_at = datetime.now()
    db.commit()

    out = {"success": True, "username": admin.username, "phone": admin.phone}
    if new_pw is not None:
        out["password"] = new_pw   # faqat reset qilinganda qaytadi
    return out


# ── BLOKLASH / QULFDAN CHIQARISH ─────────────────────────────────────────────

class BlockBody(BaseModel):
    reason: str = ""

@router.post("/tenants/{tenant_id}/block")
async def block_tenant(
    tenant_id: int,
    body: BlockBody = Body(default=BlockBody()),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    cafe = db.query(Cafe).filter(Cafe.id == tenant_id).first()
    if not cafe:
        raise HTTPException(404, "Tenant topilmadi")

    cafe.tenant_status  = "blocked"
    cafe.blocked_at     = datetime.now()
    cafe.blocked_reason = body.reason or "Super admin tomonidan bloklandi"
    cafe.is_active      = False
    cafe.updated_at     = datetime.now()
    db.commit()
    return {"success": True, "message": "Tenant bloklandi"}


@router.post("/tenants/{tenant_id}/unblock")
async def unblock_tenant(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    cafe = db.query(Cafe).filter(Cafe.id == tenant_id).first()
    if not cafe:
        raise HTTPException(404, "Tenant topilmadi")

    cafe.tenant_status  = "active"
    cafe.blocked_at     = None
    cafe.blocked_reason = None
    cafe.is_active      = True
    cafe.updated_at     = datetime.now()
    db.commit()
    return {"success": True, "message": "Tenant qulfdan chiqarildi"}


# ── TO'LOV QOSHISH ────────────────────────────────────────────────────────────

@router.post("/tenants/{tenant_id}/payment")
async def add_payment(
    tenant_id:      int,
    amount:         float        = Body(...),
    months:         int          = Body(1),
    payment_method: str          = Body("cash"),
    note:           Optional[str] = Body(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """To'lov qo'shish va obunani avtomatik yangilash."""
    cafe = db.query(Cafe).filter(Cafe.id == tenant_id).first()
    if not cafe:
        raise HTTPException(404, "Tenant topilmadi")

    now = datetime.now()

    # Obunani yangilash
    if cafe.subscription_expires and cafe.subscription_expires > now:
        period_start = cafe.subscription_expires
    else:
        period_start = now
    period_end = period_start + timedelta(days=30 * months)

    payment = TenantPayment(
        tenant_id      = tenant_id,
        amount         = amount,
        months         = months,
        payment_method = payment_method,
        period_start   = period_start,
        period_end     = period_end,
        note           = note,
        created_by_id  = current_user.id,
    )
    db.add(payment)

    # Tenant holati va obuna muddatini yangilash
    cafe.subscription_expires = period_end
    if cafe.tenant_status in ("trial", "blocked", "expired", None):
        cafe.tenant_status  = "active"
        cafe.blocked_at     = None
        cafe.blocked_reason = None
    cafe.is_active  = True
    cafe.updated_at = now

    db.commit()
    return {
        "success":              True,
        "subscription_expires": cafe.subscription_expires,
        "message":              f"To'lov qabul qilindi. Obuna {period_end.strftime('%d.%m.%Y')} gacha",
    }


# ── TO'LOV TARIXI ─────────────────────────────────────────────────────────────

@router.get("/tenants/{tenant_id}/payments")
async def get_tenant_payments(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    cafe = db.query(Cafe).filter(Cafe.id == tenant_id).first()
    if not cafe:
        raise HTTPException(404, "Tenant topilmadi")

    payments = (
        db.query(TenantPayment)
        .filter(TenantPayment.tenant_id == tenant_id)
        .order_by(TenantPayment.created_at.desc())
        .all()
    )
    return {
        "tenant_id":   tenant_id,
        "tenant_name": cafe.name,
        "items": [
            {
                "id":             p.id,
                "amount":         p.amount,
                "months":         p.months,
                "payment_method": p.payment_method,
                "period_start":   p.period_start,
                "period_end":     p.period_end,
                "note":           p.note,
                "created_by":     p.created_by.full_name if p.created_by else None,
                "created_at":     p.created_at,
            }
            for p in payments
        ],
    }


# ── BARCHA TO'LOVLAR TARIXI ───────────────────────────────────────────────────

@router.get("/payments")
async def get_all_payments(
    page:      int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """Barcha tenantlarning to'lov tarixi (oxirgi to'lovlar)."""
    total = db.query(TenantPayment).count()
    payments = (
        db.query(TenantPayment)
        .order_by(TenantPayment.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "items": [
            {
                "id":             p.id,
                "tenant_id":      p.tenant_id,
                "tenant_name":    p.tenant.name if p.tenant else "—",
                "amount":         p.amount,
                "months":         p.months,
                "payment_method": p.payment_method,
                "period_end":     p.period_end,
                "note":           p.note,
                "created_at":     p.created_at,
            }
            for p in payments
        ],
    }


# ── OBUNANI YANGILASH (to'lovsiz) ────────────────────────────────────────────

@router.post("/tenants/{tenant_id}/renew")
async def renew_subscription(
    tenant_id: int,
    months:    int = Body(1),
    plan:      Optional[str] = Body(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """To'lovsiz obunani uzaytirish (test/manual)."""
    cafe = db.query(Cafe).filter(Cafe.id == tenant_id).first()
    if not cafe:
        raise HTTPException(404, "Tenant topilmadi")

    now = datetime.now()
    base = cafe.subscription_expires if (cafe.subscription_expires and cafe.subscription_expires > now) else now
    cafe.subscription_expires = base + timedelta(days=30 * months)

    if plan and plan in VALID_PLANS:
        cafe.subscription_plan = plan
    if cafe.tenant_status in ("trial", "expired", None):
        cafe.tenant_status = "active"
    cafe.is_active  = True
    cafe.updated_at = now
    db.commit()
    return {
        "success":              True,
        "subscription_expires": cafe.subscription_expires,
        "message":              f"Obuna {months} oyga uzaytirildi",
    }


# ── FUNKSIYA TOGGLE (super-admin) ─────────────────────────────────────────────

@router.get("/tenants/{tenant_id}/features")
async def get_tenant_features(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """
    Tenant uchun barcha mavjud funksiyalar ro'yxati.
    Har birida: is_default (biznes turi default), is_enabled (hozirgi holat).
    """
    cafe = db.query(Cafe).filter(Cafe.id == tenant_id).first()
    if not cafe:
        raise HTTPException(404, "Tenant topilmadi")

    default_features  = {f.value for f in get_default_features(cafe.business_type)}
    enabled_now       = resolve_enabled_features(
        cafe.business_type, cafe.enabled_features, cafe.disabled_features,
        cafe.subscription_plan,   # PRO tarif → PRO flaglar ochiq (xato #8 ildiz)
    )
    enabled_overrides  = set(cafe.enabled_features  or [])
    disabled_overrides = set(cafe.disabled_features or [])

    features = []
    for key, meta in FEATURE_META.items():
        features.append({
            "key":        key,
            "name":       meta["name"],
            "icon":       meta["icon"],
            "group":      meta["group"],
            "is_default": key in default_features,
            "is_enabled": key in enabled_now,
            "is_forced_on":  key in enabled_overrides,
            "is_forced_off": key in disabled_overrides,
        })

    # Guruh tartibini saqlash uchun saralash
    group_order = {"Restoran": 0, "Umumiy": 1, "Magazin": 2, "Dorixona": 3, "Xizmat": 4}
    features.sort(key=lambda f: (group_order.get(f["group"], 9), f["key"]))

    return {
        "tenant_id":    tenant_id,
        "business_type": cafe.business_type,
        "features":     features,
    }


class FeatureToggleBody(BaseModel):
    enabled:  list[str] = []   # bu funksiyalarni majburiy ON qil
    disabled: list[str] = []   # bu funksiyalarni majburiy OFF qil


@router.patch("/tenants/{tenant_id}/features")
async def update_tenant_features(
    tenant_id: int,
    body: FeatureToggleBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """
    Tenant funksiyalarini yoqish/o'chirish.
    - enabled  → cafe.enabled_features  (default ustiga qo'shimcha yoqilganlar)
    - disabled → cafe.disabled_features (default dan o'chirilganlar)
    Ikkala listda ham bo'lsa, enabled ustunlik qiladi.
    """
    cafe = db.query(Cafe).filter(Cafe.id == tenant_id).first()
    if not cafe:
        raise HTTPException(404, "Tenant topilmadi")

    valid_keys = set(FEATURE_META.keys())

    # Validatsiya
    bad = (set(body.enabled) | set(body.disabled)) - valid_keys
    if bad:
        raise HTTPException(400, f"Noto'g'ri funksiya kaliti: {', '.join(sorted(bad))}")

    # enabled va disabled kesishmasin — enabled ustunlik qiladi
    disabled_clean = [k for k in body.disabled if k not in body.enabled]

    cafe.enabled_features  = list(set(body.enabled))
    cafe.disabled_features = list(set(disabled_clean))
    cafe.updated_at        = datetime.now()
    db.commit()

    enabled_now = resolve_enabled_features(
        cafe.business_type, cafe.enabled_features, cafe.disabled_features
    )
    return {
        "success":         True,
        "enabled_features": list(enabled_now),
        "message":         "Funksiyalar yangilandi",
    }
