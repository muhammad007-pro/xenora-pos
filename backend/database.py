from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from config import settings

# Engine yaratish — loyiha endi PostgreSQL ustida ishlaydi (BOSQICH 1.1).
# pool_pre_ping: ulanish "o'lik" bo'lib qolsa, avtomatik qayta tekshiradi
# pool_size/max_overflow: bir vaqtning o'zida nechta ulanish ochiq turishi mumkinligi
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    echo=settings.DEBUG,
    pool_size=10,
    max_overflow=20
)

# Session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class
Base = declarative_base()

def get_db() -> Generator[Session, None, None]:
    """Database session olish"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Boshlang'ich ma'lumotlarni qo'shish (sxema endi Alembic orqali boshqariladi — BOSQICH 1.2)"""
    from models import (
        User, Role, Permission, Category, Product, Table,
        Customer, Discount, Inventory, Shift
    )
    from core.security import get_password_hash
    from datetime import datetime

    # E'TIBOR: Base.metadata.create_all() endi ishlatilmaydi.
    # Jadvallar `alembic upgrade head` orqali yaratiladi/yangilanadi
    # (qarang: backend/migrations/). Bu ikki sxema manbai orasidagi
    # nomuvofiqlikning oldini oladi.

    db = SessionLocal()
    
    try:
        # Permissions yaratish
        permissions_data = [
            ("manage_users", "Foydalanuvchilarni boshqarish"),
            ("manage_roles", "Rollar boshqaruvi"),
            ("view_analytics", "Analitikani ko'rish"),
            ("manage_menu", "Menyuni boshqarish"),
            ("manage_tables", "Stollar boshqaruvi"),
            ("process_orders", "Buyurtmalarni qayta ishlash"),
            ("manage_inventory", "Omborni boshqarish"),
            ("manage_products", "Mahsulot / xizmat katalogini boshqarish"),
            ("view_reports", "Hisobotlarni ko'rish"),
            ("manage_settings", "Sozlamalar boshqaruvi"),
            ("manage_customers", "Mijozlar boshqaruvi"),
            ("manage_discounts", "Chegirmalar boshqaruvi"),
            ("process_payments", "To'lovlarni qayta ishlash"),
            ("manage_shifts", "Smenalar boshqaruvi"),
            ("manage_reservations", "Bronlar boshqaruvi"),
            ("view_finance", "Moliyaviy ma'lumotlarni ko'rish (sof foyda, xarajat)"),
        ]
        
        permissions = {}
        for code, desc in permissions_data:
            perm = db.query(Permission).filter(Permission.code == code).first()
            if not perm:
                perm = Permission(code=code, description=desc)
                db.add(perm)
                db.flush()
            permissions[code] = perm
        
        # Admin roli
        admin_role = db.query(Role).filter(Role.name == "admin").first()
        if not admin_role:
            admin_role = Role(name="admin", description="Administrator")
            db.add(admin_role)
            db.flush()
        # LOCKOUT OLDINI OLISH: admin roli HAR startup'da barcha permission'ga
        # sync qilinadi (guard'dan tashqarida). Yangi permission qo'shilsa,
        # mavjud admin rollar (jumladan superuser bo'lmagan kafe adminlari,
        # global rol orqali) avtomatik oladi. Idempotent.
        admin_role.permissions = list(permissions.values())
        
        # Ofitsiant roli
        waiter_role = db.query(Role).filter(Role.name == "waiter").first()
        if not waiter_role:
            waiter_role = Role(name="waiter", description="Ofitsiant")
            waiter_role.permissions = [
                permissions["process_orders"],
                permissions["view_reports"],
            ]
            db.add(waiter_role)
            db.flush()
        
        # Oshpaz roli
        kitchen_role = db.query(Role).filter(Role.name == "kitchen").first()
        if not kitchen_role:
            kitchen_role = Role(name="kitchen", description="Oshpaz")
            kitchen_role.permissions = []
            db.add(kitchen_role)
            db.flush()
        
        # Kassir roli
        cashier_role = db.query(Role).filter(Role.name == "cashier").first()
        if not cashier_role:
            cashier_role = Role(name="cashier", description="Kassir")
            cashier_role.permissions = [
                permissions["process_payments"],
                permissions["view_reports"],
            ]
            db.add(cashier_role)
            db.flush()

        # Menejer roli (admin va kassir orasida; nozik sozlamalarsiz — A variant, aynan 8 ruxsat).
        # BERILMAYDI: manage_settings, manage_users, manage_roles, manage_products,
        # process_orders, manage_discounts, manage_reservations, manage_tables.
        menejer_role = db.query(Role).filter(Role.name == "menejer").first()
        if not menejer_role:
            menejer_role = Role(name="menejer", description="Menejer")
            menejer_role.permissions = [
                permissions["view_finance"],
                permissions["process_payments"],
                permissions["view_analytics"],
                permissions["view_reports"],
                permissions["manage_menu"],
                permissions["manage_inventory"],
                permissions["manage_customers"],
                permissions["manage_shifts"],
            ]
            db.add(menejer_role)
            db.flush()
        
        # Super-admin foydalanuvchi (BOSQICH 38: telefon-login).
        # Telefon — login kaliti; username display/legacy uchun qoladi.
        # Ma'lumot .env orqali (settings.FIRST_SUPERUSER_*). DEV'da standart
        # qiymat, DEPLOY'da .env'dan (parol production'da MAJBUR o'zgartiriladi).
        # Mavjud super-admin (agar bazada bor) buzilmaydi — faqat yo'q bo'lsa yaratiladi.
        admin_user = db.query(User).filter(User.phone == settings.FIRST_SUPERUSER_PHONE).first()
        if not admin_user:
            admin_user = User(
                username=settings.FIRST_SUPERUSER_USERNAME,
                email=settings.FIRST_SUPERUSER_EMAIL,
                full_name=settings.FIRST_SUPERUSER_NAME,
                phone=settings.FIRST_SUPERUSER_PHONE,
                hashed_password=get_password_hash(settings.FIRST_SUPERUSER_PASSWORD),
                role_id=admin_role.id,
                is_active=True,
                is_superuser=True
            )
            db.add(admin_user)

        # Eslatma: avvalgi demo waiter/kitchen userlari endi avtomatik seed
        # QILINMAYDI (toza boshlash — faqat super-admin). Kerak bo'lsa frontenddan
        # telefon bilan yaratiladi (rollar quyida saqlanib qoladi).

        # Default kategoriyalar
        default_categories = [
            {"name": "Taomlar", "display_order": 1},
            {"name": "Salatlar", "display_order": 2},
            {"name": "Sho'rvalar", "display_order": 3},
            {"name": "Ichimliklar", "display_order": 4},
            {"name": "Desertlar", "display_order": 5},
            {"name": "Grill", "display_order": 6},
            {"name": "Fast Food", "display_order": 7},
        ]
        
        categories = {}
        for cat_data in default_categories:
            cat = db.query(Category).filter(Category.name == cat_data["name"]).first()
            if not cat:
                cat = Category(**cat_data)
                db.add(cat)
                db.flush()
            categories[cat_data["name"]] = cat
        
        # Default stollar
        table_count = db.query(Table).count()
        if table_count == 0:
            for i in range(1, 11):
                table = Table(
                    number=str(i),
                    name=f"Stol {i}",
                    capacity=4 if i <= 8 else 6,
                    section="Asosiy zal" if i <= 8 else "VIP",
                    status="free"
                )
                db.add(table)
        
        db.commit()
        print("✅ Ma'lumotlar bazasi va boshlang'ich ma'lumotlar yaratildi!")
        
    except Exception as e:
        print(f"❌ Xatolik: {e}")
        db.rollback()
    finally:
        db.close()