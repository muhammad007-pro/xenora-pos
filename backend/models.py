from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date, Numeric,
    ForeignKey, Text, Enum, JSON, BigInteger, Table, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql import func
from database import Base
from datetime import datetime

import enum
import sqlalchemy
# Many-to-Many association tables
role_permissions = sqlalchemy.Table(
    'role_permissions',
    Base.metadata,
    Column('role_id', Integer, ForeignKey('roles.id'), primary_key=True),
    Column('permission_id', Integer, ForeignKey('permissions.id'), primary_key=True)
)

class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    BLOCKED = "blocked"

class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PREPARING = "preparing"
    READY = "ready"
    SERVED = "served"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    PARTIAL = "partial"
    REFUNDED = "refunded"
    FAILED = "failed"

class PaymentMethod(str, enum.Enum):
    CASH = "cash"
    CARD = "card"
    CLICK = "click"
    PAYME = "payme"
    QR = "qr"
    # v1.9.1: POS'da tugmasi BOR edi, enumda YO'Q edi -> nasiya bilan sotuv
    # `invalid input value for enum paymentmethod: "credit"` berib 500 qilardi
    # va BUTUN sotuv rollback bo'lardi (jonli, Fazza Parfum).
    # DIQQAT: `credit` — pul KELMAGAN tender. To'lov yozuvi PENDING holatda
    # yaratiladi, ya'ni "paid" bo'yicha filtrlaydigan naqd hisobotlariga
    # KIRMAYDI (qarang: services/payment_service.py, routers/shift.py).
    CREDIT = "credit"            # nasiya (qarzga)
    ROOM_CHARGE = "room_charge"  # mehmonxona: xona hisobiga

class TableStatus(str, enum.Enum):
    FREE = "free"
    OCCUPIED = "occupied"
    RESERVED = "reserved"
    CLEANING = "cleaning"

class ReservationStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"

# ============== ASOSIY MODELLAR ==============

class Permission(Base):
    __tablename__ = "permissions"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False)
    description = Column(String(200))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(String(200))
    permissions = relationship("Permission", secondary=role_permissions, backref="roles")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    users = relationship("User", back_populates="role")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True, index=True)
    # BOSQICH 38: login telefon raqam bilan → phone majburiy + unikal (global).
    # username/email endi ixtiyoriy (display/legacy uchun qoladi, login kaliti emas).
    # username unikalligi TENANT ICHIDA (composite unique, quyida __table_args__) — global emas,
    # shu tufayli har do'konda "admin"/"cashier" kabi nomlar takrorlanishi mumkin.
    username = Column(String(50), nullable=True, index=True)
    email = Column(String(100), unique=True, nullable=True)
    full_name = Column(String(100))
    phone = Column(String(20), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    hashed_pin = Column(String(64), nullable=True, index=True)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    status = Column(Enum(UserStatus), default=UserStatus.ACTIVE)
    role_id = Column(Integer, ForeignKey("roles.id"))
    role = relationship("Role", back_populates="users")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_login = Column(DateTime(timezone=True))
    
    # username unikalligi tenant ichida (global emas) — tenant izolyatsiya buzilmaydi.
    __table_args__ = (
        UniqueConstraint("tenant_id", "username", name="uq_users_tenant_username"),
    )

    # Relationships
    orders = relationship("Order", back_populates="waiter")
    shifts = relationship("Shift", back_populates="user")
    payments = relationship("Payment", back_populates="cashier")

class Station(Base):
    __tablename__ = "stations"
    id           = Column(Integer, primary_key=True, index=True)
    tenant_id    = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    branch_id    = Column(Integer, ForeignKey("branches.id"), nullable=True, index=True)
    name         = Column(String(100), nullable=False)
    color        = Column(String(20), default="#d4af37")
    has_display  = Column(Boolean, default=True)   # False = displeysiz (suv, salfetka)
    display_order= Column(Integer, default=0)
    is_active    = Column(Boolean, default=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    products = relationship("Product", back_populates="station")

class Department(Base):
    """Bo'lim / Seksiya — magazin/supermarket uchun fizik bo'lim (BOSQICH 21)"""
    __tablename__ = "departments"
    id           = Column(Integer, primary_key=True, index=True)
    tenant_id    = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    name         = Column(String(100), nullable=False)
    description  = Column(Text, nullable=True)
    color        = Column(String(20), default="#6366f1")
    icon         = Column(String(50), nullable=True)   # emoji: 🍎 yoki lucide icon nomi
    display_order = Column(Integer, default=0)
    is_active    = Column(Boolean, default=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    updated_at   = Column(DateTime(timezone=True), onupdate=func.now())

    categories = relationship("Category", back_populates="department")
    products   = relationship("Product",  back_populates="department")


class Category(Base):
    __tablename__ = "categories"
    id            = Column(Integer, primary_key=True, index=True)
    tenant_id     = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    name          = Column(String(100), nullable=False)
    description   = Column(Text)
    image_url     = Column(String(500))
    parent_id     = Column(Integer, ForeignKey("categories.id"), nullable=True)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    color         = Column(String(20), nullable=True)
    icon          = Column(String(50), nullable=True)
    is_active     = Column(Boolean, default=True)
    display_order = Column(Integer, default=0)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), onupdate=func.now())

    products   = relationship("Product", back_populates="category")
    children   = relationship("Category", backref=backref("parent", remote_side=[id]))
    department = relationship("Department", back_populates="categories")

class Product(Base):
    __tablename__ = "products"
    # BOSQICH 39: barcode/sku endi GLOBAL emas, har TENANT ichida unikal
    # (ikki do'kon bir xil zavod barcode'ini saqlay olishi uchun)
    __table_args__ = (
        UniqueConstraint("tenant_id", "barcode", name="uq_products_tenant_barcode"),
        UniqueConstraint("tenant_id", "sku", name="uq_products_tenant_sku"),
        # Katalogni kategoriya bo'yicha filtrlash (tenant ichida) tez ishlashi uchun.
        Index("ix_products_tenant_category", "tenant_id", "category_id"),
    )
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)  # BOSQICH 1.5
    name = Column(String(200), nullable=False)
    description = Column(Text)
    price = Column(Float, nullable=False)
    cost_price = Column(Float, default=0.0)
    barcode = Column(String(100))
    sku = Column(String(50))
    image_url = Column(String(500))
    category_id   = Column(Integer, ForeignKey("categories.id"))
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    station_id    = Column(Integer, ForeignKey("stations.id"), nullable=True, index=True)
    sale_unit    = Column(String(20), default="pcs")  # BOSQICH 2.3: savdo o'lchov birligi
    expiry_date  = Column(Date, nullable=True)         # BOSQICH 4.5: yaroqlilik muddati (dorixona)
    batch_number = Column(String(50), nullable=True)   # BOSQICH 4.5: partiya raqami
    yield_pct         = Column(Float, nullable=True)   # BOSQICH 17: chiqim foizi
    wholesale_price   = Column(Float, nullable=True)   # BOSQICH 19: ko'tara (optom) narxi
    wholesale_min_qty = Column(Integer, default=10)    # BOSQICH 19: optom minimal miqdori
    # BOSQICH B0 (pachka/dona): 1 mahsulot ham pachka, ham dona sotiladi.
    # price = DONA narxi; pack_price = 1 PACHKA narxi; pack_size = 1 pachkadagi dona soni.
    # NULL yoki pack_size<2 → mahsulot pachkasiz (oddiy). Ombor base birligi = dona.
    # DIQQAT: bu maydonlar B0'da faqat poydevor — hali hech qaysi kod ishlatmaydi.
    pack_size  = Column(Integer, nullable=True)   # 1 pachka = nechta dona (NULL/<2 = pachkasiz)
    pack_price = Column(Float, nullable=True)      # 1 pachka narxi
    # BOSQICH 22: dorixona maxsus maydonlar
    active_ingredient     = Column(String(300), nullable=True)  # faol modda (analog topish uchun)
    dosage                = Column(String(100), nullable=True)  # dozaj: "500mg", "250ml"
    drug_form             = Column(String(50),  nullable=True)  # shakl: tablet/syrup/ampule/cream/drops
    dosing_schedule       = Column(String(300), nullable=True)  # kuniga 3 mahal ovqatdan keyin
    requires_prescription = Column(Boolean, default=False)      # retsept talab qiladimi
    is_active = Column(Boolean, default=True)
    is_available = Column(Boolean, default=True)
    preparation_time = Column(Integer, default=10)  # minutes
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    category   = relationship("Category", back_populates="products")
    department = relationship("Department", back_populates="products")
    station    = relationship("Station", back_populates="products")
    order_items = relationship("OrderItem", back_populates="product")
    inventory_items = relationship("Inventory", back_populates="product")
    discounts = relationship("Discount", back_populates="product")

class Table(Base):
    __tablename__ = "tables"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True, index=True)
    number = Column(String(20), nullable=False)
    name = Column(String(50))
    capacity = Column(Integer, default=4)
    section = Column(String(50))  # Main hall, Terrace, VIP etc.
    status = Column(Enum(TableStatus), default=TableStatus.FREE)
    position_x = Column(Integer, nullable=True)  # For floor plan
    position_y = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    orders = relationship("Order", back_populates="table")
    reservations = relationship("Reservation", back_populates="table")

class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        # Hisobot (sana oralig'i) va status bo'yicha filtr tenant ichida tez ishlashi uchun.
        # order_by created_at DESC ham shu indeksdan foydalanadi.
        Index("ix_orders_tenant_created", "tenant_id", "created_at"),
        Index("ix_orders_tenant_status", "tenant_id", "status"),
    )
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True, index=True)
    order_number = Column(String(20), unique=True, nullable=False)
    # Ko'rinadigan kunlik chek raqami — har tenant + har kun bo'yicha 1 dan ketma-ket.
    # order_number ichki unikal id bo'lib qoladi; daily_number — kassir/mijoz ko'radigan raqam.
    daily_number = Column(Integer, nullable=True, index=True)
    table_id = Column(Integer, ForeignKey("tables.id"))
    waiter_id = Column(Integer, ForeignKey("users.id"))
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    status = Column(Enum(OrderStatus), default=OrderStatus.PENDING)
    total_amount = Column(Float, default=0.0)
    discount_amount = Column(Float, default=0.0)
    tax_amount = Column(Float, default=0.0)
    final_amount = Column(Float, default=0.0)
    notes = Column(Text)
    order_type = Column(String(20), default="dine-in")   # dine-in | takeaway | delivery
    source     = Column(String(20), default="pos")       # pos | qr_menu | telegram | online
    # Delivery ma'lumotlari
    delivery_address = Column(Text, nullable=True)
    delivery_phone = Column(String(20), nullable=True)
    delivery_note = Column(Text, nullable=True)
    # Servis haqi va choy puli
    service_charge = Column(Float, default=0.0)
    # Kursli ovqat uchun
    courses_enabled = Column(Boolean, default=False)
    # Birlashtirilgan stol
    merged_table_ids = Column(JSON, default=list)      # [table_id, ...] boshqa qo'shilgan stollar
    # Biznes-turi xususiy ma'lumotlar (pharmacy rx, auto_service car, school student, dry_cleaning)
    biz_meta = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True))
    preparing_started_at = Column(DateTime(timezone=True), nullable=True)  # KDS timer
    # Oshxona 2-bosqich: retsept inventar chiqimi bir marta bo'lsin (reopen→qayta-ready ikki marta chiqim qilmasin)
    ingredients_deducted = Column(Boolean, default=False)
    # Refund/qaytarishda ombor bir marta tiklansin (idempotent — ikki marta refund
    # bir xil zaxirani ikki marta qaytarib qo'ymasin). deduct ning teskarisi.
    ingredients_restored = Column(Boolean, default=False)
    # OFD fiskal integratsiya
    fiscal_number   = Column(Integer,  nullable=True, index=True)   # OFD dan kelgan chek raqami
    fiscal_qr_url   = Column(String(500), nullable=True)             # consumer.invoice.uz QR URL
    fiscal_sent_at  = Column(DateTime(timezone=True), nullable=True) # OFD ga yuborilgan vaqt
    # Z-hisobot: buyurtma qaysi smenada yaratilgani (nullable — smena ochiq
    # bo'lmaganda yoki eski buyurtmalarda NULL). Yaratish paytida joriy ochiq
    # smena id si yoziladi → Z-hisobot sotuvlarni aniq shu smenaga yig'adi.
    shift_id        = Column(Integer, ForeignKey("shifts.id"), nullable=True, index=True)

    # Relationships
    table = relationship("Table", back_populates="orders")
    waiter = relationship("User", back_populates="orders")
    customer = relationship("Customer", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="order")
    applied_discounts = relationship("Discount", secondary="order_discounts")
    shift = relationship("Shift", foreign_keys=[shift_id])   # Z-hisobot/kassa nomi uchun

    @property
    def service_amount(self) -> float:
        return self.service_charge or 0.0

class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)  # BOSQICH 1.5
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"))
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(Float, nullable=False)
    unit_cost = Column(Float, default=0.0)  # BOSQICH 15: sotuv paytidagi tan narx (snapshot)
    total_price = Column(Float, nullable=False)
    # BOSQICH B0 (pachka/dona): quantity — ko'rinadigan soni (pachka soni yoki dona soni).
    # base_qty — ombordan ayiriladigan DONA miqdori (pachka: pack_size×quantity; dona: quantity).
    # unit_sold — chek yorlig'i + hisobot uchun. NULL → eski/oddiy (base_qty ham NULL → quantity).
    # DIQQAT: B0'da faqat poydevor — hali hech qaysi kod ishlatmaydi.
    base_qty  = Column(Float, nullable=True)       # ombordan ayiriladigan dona miqdori
    unit_sold = Column(String(20), nullable=True)  # "pachka" | "dona" | NULL
    notes = Column(Text)
    status = Column(String(20), default="pending")  # pending, preparing, ready, served
    course_number = Column(Integer, default=1)       # 1=Birinchi ovqat, 2=Ikkinchi ovqat...
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    order = relationship("Order", back_populates="items")
    product = relationship("Product", back_populates="order_items")

    @property
    def product_name(self) -> str:
        return self.product.name if self.product else ""

class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    cashier_id = Column(Integer, ForeignKey("users.id"))
    amount = Column(Float, nullable=False)
    method = Column(Enum(PaymentMethod), nullable=False)
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING)
    transaction_id = Column(String(100))
    reference = Column(String(200))
    tip_amount = Column(Float, default=0.0)         # Choy puli (tips)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    order = relationship("Order", back_populates="payments")
    cashier = relationship("User", back_populates="payments")

class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)  # BOSQICH 1.5
    name = Column(String(100), nullable=False)
    phone = Column(String(20), unique=True)
    email = Column(String(100))
    birthday = Column(DateTime)
    total_visits  = Column(Integer, default=0)
    total_spent   = Column(Float, default=0.0)
    points        = Column(Integer, default=0)
    # BOSQICH 19: nasiya tizimi
    credit_limit  = Column(Float, nullable=True)          # maksimal qarz limiti (None=cheksiz)
    customer_type = Column(String(20), default="retail")  # retail|wholesale
    total_debt    = Column(Float, default=0.0)            # joriy umumiy qarz
    # BOSQICH S0 (sodiqlik): doimiy mijoz avtomatik % chegirmasi (0-100). NULL/0 = chegirma yo'q.
    # DIQQAT: S0'da faqat poydevor — POS/forma/chek HALI ishlatmaydi (S1/S2).
    discount_percent = Column(Float, nullable=True, default=0)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    orders       = relationship("Order", back_populates="customer")
    reservations = relationship("Reservation", back_populates="customer")
    debts        = relationship("CustomerDebt", back_populates="customer")

class Reservation(Base):
    __tablename__ = "reservations"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    table_id = Column(Integer, ForeignKey("tables.id"))
    reservation_time = Column(DateTime, nullable=False)
    duration_minutes = Column(Integer, default=120)
    guests_count = Column(Integer, default=2)
    status = Column(Enum(ReservationStatus), default=ReservationStatus.PENDING)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    customer = relationship("Customer", back_populates="reservations")
    table = relationship("Table", back_populates="reservations")

class DailySpecial(Base):
    """Kunlik maxsus taom — restoran/kafe uchun (BOSQICH 14)"""
    __tablename__ = "daily_specials"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    date = Column(Date, nullable=False)
    special_price = Column(Float, nullable=True)           # None = asl narx
    special_description = Column(String(300), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    product = relationship("Product")

class Inventory(Base):
    __tablename__ = "inventory"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Float, default=0.0)
    unit = Column(String(20), default="kg")
    min_threshold = Column(Float, default=5.0)
    max_threshold = Column(Float, default=100.0)
    last_restock = Column(DateTime)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    product = relationship("Product", back_populates="inventory_items")

class Discount(Base):
    __tablename__ = "discounts"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)  # BOSQICH 1.5
    name = Column(String(100), nullable=False)
    type = Column(String(20), nullable=False)  # percentage, fixed
    value = Column(Float, nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    min_order_amount = Column(Float, default=0.0)
    valid_from = Column(DateTime)
    valid_to = Column(DateTime)
    is_active = Column(Boolean, default=True)
    usage_limit = Column(Integer, nullable=True)
    used_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    product = relationship("Product", back_populates="discounts")

# Association table for order discounts
order_discounts = sqlalchemy.Table(
    'order_discounts',
    Base.metadata,
    Column('order_id', Integer, ForeignKey('orders.id')),
    Column('discount_id', Integer, ForeignKey('discounts.id'))
)

class Shift(Base):
    __tablename__ = "shifts"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    start_time    = Column(DateTime, nullable=False)
    end_time      = Column(DateTime)
    starting_cash = Column(Float, default=0.0)
    ending_cash   = Column(Float)
    total_sales   = Column(Float, default=0.0)
    cash_sales    = Column(Float, default=0.0)
    card_sales    = Column(Float, default=0.0)
    credit_total  = Column(Float, default=0.0)   # nasiya summasi
    counted_cash  = Column(Float, nullable=True)  # kassir hisoblagan naqd
    shortage      = Column(Float, default=0.0)    # kamomad (-)/ ortiqcha (+)
    notes         = Column(Text)
    # Multi-register: smena qaysi kassada ochilgani (nullable — orqaga moslik:
    # cash_register flagi o'chiq bo'lsa NULL qoladi, eski oddiy smena ishlaydi)
    register_id   = Column(Integer, ForeignKey("cash_registers.id"), nullable=True, index=True)

    # Relationships
    user = relationship("User", back_populates="shifts")
    register = relationship("CashRegister")

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)  # BOSQICH 1.5
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    type = Column(String(50))  # order, kitchen, payment, system
    is_read = Column(Boolean, default=False)
    data = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # ============== YANGI MODELLAR (Professional funksiyalar) ==============

class Recipe(Base):
    """Retseptlar (taomlar uchun mahsulotlar ro'yxati)"""
    __tablename__ = "recipes"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)  # BOSQICH 1.5
    product_id = Column(Integer, ForeignKey("products.id"), unique=True)  # Qaysi taom uchun
    name = Column(String(200), nullable=False)
    description = Column(Text)
    preparation_time = Column(Integer, default=15)  # daqiqa
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    product = relationship("Product", backref="recipe")
    items = relationship("RecipeItem", back_populates="recipe", cascade="all, delete-orphan")


class RecipeItem(Base):
    """Retsept elementlari (taom uchun kerakli mahsulotlar)"""
    __tablename__ = "recipe_items"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)  # BOSQICH 1.5
    recipe_id = Column(Integer, ForeignKey("recipes.id", ondelete="CASCADE"))
    ingredient_id = Column(Integer, ForeignKey("products.id"))  # Ombor mahsuloti
    quantity = Column(Float, nullable=False, default=0)
    unit = Column(String(20), default="kg")
    notes = Column(Text)
    
    # Relationships
    recipe = relationship("Recipe", back_populates="items")
    ingredient = relationship("Product", foreign_keys=[ingredient_id])


class StaffMeal(Base):
    """Xodimlar ovqati — bepul berilgan taomlar (BOSQICH 18)"""
    __tablename__ = "staff_meals"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Float, nullable=False, default=1.0)
    cost_price = Column(Float, default=0.0)   # birlik tan narx (snapshot)
    total_cost = Column(Float, default=0.0)   # = quantity × cost_price
    notes = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    employee = relationship("Employee")
    product = relationship("Product")
    creator = relationship("User", foreign_keys=[created_by])


class Expense(Base):
    """Operatsion xarajatlar — ijara, oylik, kommunal va h.k. (BOSQICH 15: sof foyda hisobi)"""
    __tablename__ = "expenses"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    category = Column(String(30), nullable=False, default="other")  # rent | salary | utility | supplies | marketing | other
    name = Column(String(200), nullable=False)
    amount = Column(Float, nullable=False)
    expense_date = Column(Date, nullable=False)
    notes = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # BOSQICH 36: maosh to'langanda avtomatik yaratilgan xarajat shu maoshga bog'lanadi
    # (ikki marta hisoblamaslik uchun — bitta maoshga bitta xarajat)
    salary_id = Column(Integer, ForeignKey("salaries.id"), nullable=True, index=True)
    # BOSQICH 37: takroriy/oylik xarajatlar (ijara har oy avtomatik)
    is_recurring = Column(Boolean, nullable=False, default=False)        # True = shablon (har oy/hafta takrorlanadi)
    recurrence_period = Column(String(10), nullable=False, default="monthly")  # monthly | weekly
    recurrence_day = Column(Integer, nullable=True)                      # oyning kuni (monthly uchun, 1-31)
    recurrence_parent_id = Column(Integer, ForeignKey("expenses.id"), nullable=True, index=True)  # generatsiya qilingan nusxa -> shablon


class Employee(Base):
    """Xodimlar"""
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True, index=True)
    full_name = Column(String(100), nullable=False)
    phone = Column(String(20))
    position = Column(String(50))  # Lavozim: ofitsiant, oshpaz, admin
    hire_date = Column(DateTime, default=datetime.now)
    salary_rate = Column(Float, default=0.0)  # Soatlik ish haqi
    is_active = Column(Boolean, default=True)
    hashed_pin = Column(String(64), nullable=True, index=True)  # davomat PIN (HMAC-SHA256, ochiq matn emas)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", backref="employee")
    cafe = relationship("Cafe", back_populates="employees")
    salaries = relationship("Salary", back_populates="employee")
    attendances = relationship("Attendance", back_populates="employee")


class Branch(Base):
    """Filiallar — bir tenant ichida bir nechta tochka/do'kon"""
    __tablename__ = "branches"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    address = Column(Text, nullable=True)
    phone = Column(String(20), nullable=True)
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    cafe = relationship("Cafe", back_populates="branches")


class CashRegister(Base):
    """Kassa nuqtalari (multi-register) — bir filialda bir nechta kassa
    (1-kassa, 2-kassa...). `cash_register` feature flagi bilan boshqariladi
    (FREE tier). Flag o'chiq bo'lsa ishlatilmaydi — eski oddiy smena qoladi."""
    __tablename__ = "cash_registers"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True, index=True)
    name = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    branch = relationship("Branch")


class Cafe(Base):
    """Kafelar (ko'p filial uchun)"""
    __tablename__ = "cafes"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    code = Column(String(20), unique=True, nullable=False)  # Kafe kodi (slug, masalan "bdokon" — QR-menyu/URL uchun)
    access_code = Column(String(20), unique=True, nullable=True, index=True)  # Do'kon KIRISH kodi (login): 100.200.N
    address = Column(Text)
    phone = Column(String(20))
    email = Column(String(100))

    # Biznes turi (BOSQICH 1.3) — qaysi standart funksiyalar yoqilishini
    # belgilaydi (qarang: core/feature_flags.py BUSINESS_FEATURE_MATRIX).
    business_type = Column(String(30), nullable=False, default="cafe")

    # Standart to'plamga qo'shimcha qo'lda yoqilgan/o'chirilgan funksiyalar.
    # Funksiyalar hech qachon butunlay o'chirilmaydi — faqat yashiriladi,
    # shuning uchun bu yerda faqat UI ko'rinish sozlamasi saqlanadi.
    enabled_features = Column(JSON, default=list)
    disabled_features = Column(JSON, default=list)

    is_active = Column(Boolean, default=True)
    subscription_plan = Column(String(50), default="free")  # free, pro, enterprise (BOSQICH 2.2)
    subscription_expires = Column(DateTime, nullable=True)

    # Super admin tenant boshqaruvi
    owner_name    = Column(String(100), nullable=True)
    owner_phone   = Column(String(20),  nullable=True)
    tenant_status = Column(String(20),  default="active")  # active, trial, blocked
    trial_expires = Column(DateTime,    nullable=True)
    blocked_at    = Column(DateTime,    nullable=True)
    blocked_reason = Column(Text,       nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    employees = relationship("Employee", back_populates="cafe")
    orders = relationship("Order", backref="cafe")
    payments_history = relationship("TenantPayment", back_populates="tenant")
    branches = relationship("Branch", back_populates="cafe")


class Salary(Base):
    """Ish haqi hisob-kitobi"""
    __tablename__ = "salaries"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)  # BOSQICH 1.5
    employee_id = Column(Integer, ForeignKey("employees.id"))
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    total_hours = Column(Float, default=0.0)
    hourly_rate = Column(Float, default=0.0)
    base_salary = Column(Float, default=0.0)
    bonus = Column(Float, default=0.0)
    deduction = Column(Float, default=0.0)
    total_salary = Column(Float, default=0.0)
    is_paid = Column(Boolean, default=False)
    paid_at = Column(DateTime, nullable=True)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    employee = relationship("Employee", back_populates="salaries")


class Attendance(Base):
    """Davomat (smenalar)"""
    __tablename__ = "attendances"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)  # BOSQICH 1.5
    employee_id = Column(Integer, ForeignKey("employees.id"))
    check_in = Column(DateTime, nullable=False)
    check_out = Column(DateTime, nullable=True)
    hours_worked = Column(Float, default=0.0)
    status = Column(String(20), default="present")  # present, absent, late, early_leave
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    employee = relationship("Employee", back_populates="attendances")


# NOTE: Eski `PinCode` modeli (pin_codes jadvali) olib tashlandi — u faqat
# ishlatilmaydigan `/pin/*` auth yo'liga tegishli edi. Tezkor kirish endi
# `User.hashed_pin` (sha256) orqali `/auth/pin-login` da amalga oshiriladi.
# DB jadvali `pin_codes` qoladi (zararsiz); keyinchalik migratsiya bilan
# tashlash mumkin.


# ============== UNIVERSAL BIZNES MODELLARI ==============

class Service(Base):
    """Xizmatlar (salon, fitnes, auto servis, maktab uchun)"""
    __tablename__ = "services"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    price = Column(Float, nullable=False, default=0.0)
    duration_minutes = Column(Integer, default=30)
    category = Column(String(50))  # hair, nail, massage, fitness, repair, course...
    color = Column(String(10), default="#c9a84c")  # Kalendarда rang
    cost_price = Column(Float, default=0.0)      # Material xarajati (soch bo'yog'i, ehtiyot qism...)
    commission_pct = Column(Float, default=0.0)  # Usta komissiyasi % (0-100)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    appointments = relationship("Appointment", back_populates="service")


class Appointment(Base):
    """Uchrashuvlar/Bronlar (salon, fitnes, auto servis, maktab, mehmonxona)"""
    __tablename__ = "appointments"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True, index=True)
    customer_name = Column(String(100), nullable=False)
    customer_phone = Column(String(20))
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    date = Column(Date, nullable=False)
    start_time = Column(String(5), nullable=False)  # "09:30"
    duration_minutes = Column(Integer, default=30)
    status = Column(String(20), default="pending")  # pending, confirmed, completed, cancelled, no_show
    notes = Column(Text)
    price = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    customer = relationship("Customer", backref="appointments")
    service = relationship("Service", back_populates="appointments")
    employee = relationship("Employee", backref="appointments")


class StaffSchedule(Base):
    """Usta haftalik ish jadvali — BOSQICH 23 (Salon)"""
    __tablename__ = "staff_schedules"
    id          = Column(Integer, primary_key=True, index=True)
    tenant_id   = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    weekday     = Column(Integer, nullable=False)   # 0=Du 1=Se 2=Ch 3=Pa 4=Ju 5=Sh 6=Ya
    work_start  = Column(String(5), nullable=False, default="09:00")
    work_end    = Column(String(5), nullable=False, default="18:00")
    is_working  = Column(Boolean, default=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())

    employee = relationship("Employee", backref="schedules")

    __table_args__ = (
        UniqueConstraint("employee_id", "weekday", name="uq_employee_weekday"),
    )


class ClientPhoto(Base):
    """Mijoz oldin/keyin fotosuratlari — BOSQICH 23 (Salon)"""
    __tablename__ = "client_photos"
    id             = Column(Integer, primary_key=True, index=True)
    tenant_id      = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    customer_id    = Column(Integer, ForeignKey("customers.id"), nullable=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=True)
    photo_type     = Column(String(10), nullable=False)   # before | after
    image_url      = Column(String(500), nullable=False)
    service_name   = Column(String(100), nullable=True)
    notes          = Column(Text, nullable=True)
    created_by     = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    customer    = relationship("Customer", backref="photos")
    appointment = relationship("Appointment", backref="photos")
    creator     = relationship("User")


class PurchaseReceipt(Base):
    """Priyomka (qabul akti / nakladnoy) — BOSQICH 24 (B2B)"""
    __tablename__ = "purchase_receipts"
    id              = Column(Integer, primary_key=True, index=True)
    tenant_id       = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    supplier_id     = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    invoice_number  = Column(String(50), nullable=True)
    receipt_date    = Column(Date, nullable=False)
    total_amount    = Column(Float, default=0.0)
    discount_amount = Column(Float, default=0.0)
    net_amount      = Column(Float, default=0.0)
    status          = Column(String(20), default="draft")   # draft, confirmed, paid
    # FAZA 4: "Hozir to'landi" — nakladnoy kiritilayotganda darhol berilgan pul.
    # Yaratishda SAQLANADI, to'lov yozuvi (SupplierPayment) esa TASDIQLANGANDA
    # yaratiladi: draft hali qarz emas, unga to'lov yozish "avans" bo'lib
    # ko'rinardi. Shu sabab qiymat oraliqda shu ustunda turadi.
    paid_now        = Column(Numeric(14, 2), nullable=False, server_default="0")
    notes           = Column(Text, nullable=True)
    confirmed_by    = Column(Integer, ForeignKey("users.id"), nullable=True)
    confirmed_at    = Column(DateTime(timezone=True), nullable=True)
    created_by      = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())

    supplier  = relationship("Supplier", back_populates="purchase_receipts")
    items     = relationship("PurchaseReceiptItem", back_populates="receipt", cascade="all, delete-orphan")
    confirmer = relationship("User", foreign_keys=[confirmed_by])
    creator   = relationship("User", foreign_keys=[created_by])


class PurchaseReceiptItem(Base):
    """Priyomka qatorlari — BOSQICH 24 (B2B)"""
    __tablename__ = "purchase_receipt_items"
    id           = Column(Integer, primary_key=True, index=True)
    receipt_id   = Column(Integer, ForeignKey("purchase_receipts.id"), nullable=False)
    product_id   = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity     = Column(Float, nullable=False)
    unit_price   = Column(Float, nullable=False)
    total_price  = Column(Float, nullable=False)
    brak_qty     = Column(Float, default=0.0)     # brak / kam kelgan
    accepted_qty = Column(Float, nullable=True)   # qabul qilingan = quantity - brak_qty
    notes        = Column(String(200), nullable=True)
    # BOSQICH 34: partiya (ProductBatch) confirm'da yaratish uchun
    batch_number     = Column(String(100), nullable=True)  # seriya / partiya raqami
    expiry_date      = Column(Date, nullable=True)         # yaroqlilik muddati
    manufacture_date = Column(Date, nullable=True)         # ishlab chiqarilgan sana

    receipt = relationship("PurchaseReceipt", back_populates="items")
    product = relationship("Product", backref="receipt_items")


class SupplierReturn(Base):
    """Firmaga qaytarish (vozvrat) — BOSQICH 24 (B2B)"""
    __tablename__ = "supplier_returns"
    id           = Column(Integer, primary_key=True, index=True)
    tenant_id    = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    supplier_id  = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    product_id   = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity     = Column(Float, nullable=False)
    unit_price   = Column(Float, nullable=False)
    total_amount = Column(Float, nullable=False)
    return_date  = Column(Date, nullable=False)
    reason       = Column(String(200), nullable=True)
    notes        = Column(Text, nullable=True)
    created_by   = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    supplier = relationship("Supplier", back_populates="supplier_returns")
    product  = relationship("Product", backref="supplier_return_items")
    creator  = relationship("User")


class Membership(Base):
    """A'zoliklar (fitnes, kurs/maktab uchun)"""
    __tablename__ = "memberships"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    plan_name = Column(String(50), nullable=False)  # basic, standard, premium
    price = Column(Float, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    visits_total = Column(Integer, default=0)  # 0 = cheksiz
    visits_used = Column(Integer, default=0)
    status = Column(String(20), default="active")  # active, expired, cancelled, frozen
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    customer = relationship("Customer", backref="memberships")


class Vehicle(Base):
    """Avtomobillar (auto servis uchun)"""
    __tablename__ = "vehicles"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    plate_number = Column(String(20), nullable=False)
    brand = Column(String(50))
    model = Column(String(50))
    year = Column(Integer)
    color = Column(String(30))
    vin = Column(String(17))
    mileage = Column(Integer, default=0)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    customer = relationship("Customer", backref="vehicles")
    service_orders = relationship("ServiceOrder", back_populates="vehicle")


class ServiceOrder(Base):
    """Xizmat buyurtmalari (auto servis, kimyoviy tozalash uchun)"""
    __tablename__ = "service_orders"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True, index=True)
    order_number = Column(String(20))
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    description = Column(Text, nullable=False)
    status = Column(String(20), default="pending")  # pending, in_progress, done, delivered
    total_amount = Column(Float, default=0.0)
    paid_amount = Column(Float, default=0.0)
    intake_date = Column(DateTime, nullable=False)
    completion_date = Column(DateTime, nullable=True)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    vehicle = relationship("Vehicle", back_populates="service_orders")
    customer = relationship("Customer", backref="service_orders")


class Room(Base):
    """Xonalar (mehmonxona uchun)"""
    __tablename__ = "rooms"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True, index=True)
    number = Column(String(20), nullable=False)
    name = Column(String(50))
    floor = Column(Integer, default=1)
    room_type = Column(String(30), default="standard")  # standard, deluxe, suite, vip
    capacity = Column(Integer, default=2)
    price_per_night = Column(Float, nullable=False, default=0.0)
    cost_per_night = Column(Float, default=0.0)   # Xona xarajati (tozalash, kommunal, amortizatsiya)
    amenities = Column(JSON, default=list)  # ["wifi", "tv", "minibar"]
    status = Column(String(20), default="available")  # available, occupied, cleaning, maintenance
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    bookings = relationship("RoomBooking", back_populates="room")


class RoomBooking(Base):
    """Xona bronlash (mehmonxona uchun)"""
    __tablename__ = "room_bookings"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True, index=True)
    room_id = Column(Integer, ForeignKey("rooms.id"))
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    guest_name = Column(String(100), nullable=False)
    guest_phone = Column(String(20))
    guest_count = Column(Integer, default=1)
    check_in = Column(Date, nullable=False)
    check_out = Column(Date, nullable=False)
    nights = Column(Integer, default=1)
    total_amount = Column(Float, default=0.0)
    paid_amount = Column(Float, default=0.0)
    status = Column(String(20), default="pending")  # pending, confirmed, checked_in, checked_out, cancelled
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    room = relationship("Room", back_populates="bookings")
    customer = relationship("Customer", backref="room_bookings")


class LoyaltyTransaction(Base):
    """Sodiqlik ball operatsiyalari"""
    __tablename__ = "loyalty_transactions"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    type = Column(String(20), nullable=False)  # earn, redeem, bonus, expire
    points = Column(Integer, nullable=False)   # + yoki - miqdor
    description = Column(String(200))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    customer = relationship("Customer", backref="loyalty_transactions")
    order = relationship("Order", backref="loyalty_txns")


class Supplier(Base):
    """Yetkazib beruvchilar (magazin, dorixona, ombor uchun)"""
    __tablename__ = "suppliers"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    name = Column(String(100), nullable=False)
    contact_person = Column(String(100))
    phone = Column(String(20))
    email = Column(String(100))
    address = Column(Text)
    tax_id = Column(String(20))  # INN
    is_active = Column(Boolean, default=True)
    balance = Column(Float, default=0.0)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    # BOSQICH 24: B2B yangi maydonlar
    contract_number    = Column(String(50), nullable=True)
    payment_delay_days = Column(Integer, default=0)
    # FAZA 3: BOSHLANG'ICH QARZ — tizimga o'tishdan OLDINGI qarz.
    # Do'kon XENORA'ni yangi o'rnatganda firmaga allaqachon qarzi bo'ladi, lekin
    # unga mos priyomka hujjati yo'q. Ilgari uni kiritish joyi umuman yo'q edi.
    # `balance` ustuni ATAYIN ishlatilmadi: uning tarixi iflos (Ombor kirimlari
    # o'sha yerga yozilgan, B2 ga qarang) — semantikani chalkashtirmaslik uchun.
    # Numeric: pul ustuni (float yaxlitlash qoldig'i bo'lmasin). Hisobda
    # float()'ga o'tkaziladi — qolgan summalar (net_amount, amount) Float.
    opening_debt       = Column(Numeric(14, 2), nullable=False, server_default="0")

    purchase_receipts = relationship("PurchaseReceipt", back_populates="supplier")
    supplier_returns  = relationship("SupplierReturn", back_populates="supplier")


# ============== OMBOR HARAKATI MODELLARI (BOSQICH 16) ==============

class StockMovement(Base):
    """Ombor harakatlari tarixi — kelim, chiqim, hisobdan o'chirish"""
    __tablename__ = "stock_movements"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True, index=True)
    inventory_id = Column(Integer, ForeignKey("inventory.id"), nullable=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    # movement_type: in=kelim, out=chiqim, sale=sotuv, writeoff=hisobdan o'chirish,
    #                adjustment=inventarizatsiya farqi, return=qaytarish
    movement_type = Column(String(20), nullable=False, index=True)
    quantity = Column(Float, nullable=False)       # har doim musbat
    unit = Column(String(20), default="dona")
    unit_cost = Column(Float, default=0.0)         # kelish narxi (birlik)
    total_cost = Column(Float, default=0.0)        # quantity * unit_cost
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    batch_number = Column(String(50), nullable=True)
    expiry_date = Column(Date, nullable=True)
    reason = Column(String(200), nullable=True)    # 'sale','manual','spoiled','lost','internal_use','inventory_adjustment'
    reference_id = Column(Integer, nullable=True)  # order_id yoki count_id
    reference_type = Column(String(50), nullable=True)  # 'order','inventory_count','manual'
    notes = Column(Text, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    product = relationship("Product")
    supplier = relationship("Supplier")
    user = relationship("User")


class InventoryCount(Base):
    """Inventarizatsiya — omborni jismoniy sanab tekshirish"""
    __tablename__ = "inventory_counts"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True, index=True)
    status       = Column(String(20), default="draft")   # draft | confirmed | cancelled
    count_type   = Column(String(20), default="full")    # full | partial
    category_id  = Column(Integer, ForeignKey("categories.id"), nullable=True)  # qisman inventarizatsiya
    notes        = Column(Text, nullable=True)
    user_id      = Column(Integer, ForeignKey("users.id"), nullable=True)
    confirmed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    items    = relationship("InventoryCountItem", back_populates="count", cascade="all, delete-orphan")
    category = relationship("Category")


class InventoryCountItem(Base):
    """Inventarizatsiya elementi — har bir mahsulot uchun alohida qator"""
    __tablename__ = "inventory_count_items"
    id = Column(Integer, primary_key=True, index=True)
    count_id = Column(Integer, ForeignKey("inventory_counts.id", ondelete="CASCADE"), nullable=False)
    inventory_id = Column(Integer, ForeignKey("inventory.id"), nullable=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    product_name = Column(String(200), nullable=True)  # snapshot
    unit = Column(String(20), default="dona")
    system_qty = Column(Float, default=0.0)    # tizim bo'yicha qoldiq
    actual_qty = Column(Float, nullable=True)   # haqiqiy sanalgan
    difference = Column(Float, nullable=True)   # actual_qty - system_qty
    notes = Column(String(300), nullable=True)

    count = relationship("InventoryCount", back_populates="items")
    product = relationship("Product")


# ============== PRO FUNKSIYALAR MODELLARI (BOSQICH 9) ==============

class ProductModifierGroup(Base):
    """Modifikator guruhlari (o'lcham, o'tkirlik, qo'shimchalar)"""
    __tablename__ = "modifier_groups"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)  # NULL = barcha mahsulotlar
    name = Column(String(100), nullable=False)         # "O'lcham", "O'tkirlik", "Qo'shimcha"
    type = Column(String(20), default="single")        # single | multiple
    is_required = Column(Boolean, default=False)
    min_select = Column(Integer, default=0)
    max_select = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    display_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    modifiers = relationship("ProductModifier", back_populates="group", cascade="all, delete-orphan")
    product = relationship("Product", backref="modifier_groups")


class ProductModifier(Base):
    """Modifikator variantlari (katta, kichik, o'tkir, muzsiz...)"""
    __tablename__ = "modifiers"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    group_id = Column(Integer, ForeignKey("modifier_groups.id", ondelete="CASCADE"))
    name = Column(String(100), nullable=False)     # "Katta porsiya", "O'tkir", "Muzsiz"
    price_delta = Column(Float, default=0.0)       # Narxga qo'shimcha (+/-)
    is_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    display_order = Column(Integer, default=0)

    group = relationship("ProductModifierGroup", back_populates="modifiers")


class OrderItemModifier(Base):
    """Buyurtma elementiga tanlangan modifikatorlar"""
    __tablename__ = "order_item_modifiers"
    id = Column(Integer, primary_key=True, index=True)
    order_item_id = Column(Integer, ForeignKey("order_items.id", ondelete="CASCADE"))
    modifier_id = Column(Integer, ForeignKey("modifiers.id"))
    name = Column(String(100))        # Saqlash vaqtidagi nom (o'zgarishdan himoya)
    price_delta = Column(Float, default=0.0)

    order_item = relationship("OrderItem", backref="modifiers")
    modifier = relationship("ProductModifier")


class ComboSet(Base):
    """Kombo/Set menyular (bir nechta taom bitta narxda)"""
    __tablename__ = "combo_sets"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    name = Column(String(100), nullable=False)    # "Oilaviy set", "Biznes lunch"
    description = Column(Text)
    price = Column(Float, nullable=False)          # Umumiy narx (odatda individual narxlardan arzon)
    image_url = Column(String(500))
    is_active = Column(Boolean, default=True)
    valid_from = Column(DateTime, nullable=True)
    valid_to = Column(DateTime, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    items = relationship("ComboSetItem", back_populates="combo", cascade="all, delete-orphan")


class ComboSetItem(Base):
    """Kombo tarkibidagi mahsulotlar"""
    __tablename__ = "combo_set_items"
    id = Column(Integer, primary_key=True, index=True)
    combo_id = Column(Integer, ForeignKey("combo_sets.id", ondelete="CASCADE"))
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer, default=1)
    is_replaceable = Column(Boolean, default=False)  # Mijoz almashtira oladimi

    combo = relationship("ComboSet", back_populates="items")
    product = relationship("Product")


class HappyHour(Base):
    """Vaqtga qarab avtomatik chegirma (Happy Hour)"""
    __tablename__ = "happy_hours"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    name = Column(String(100), nullable=False)     # "Tushlik chegirmasi", "Kechki Happy Hour"
    discount_type = Column(String(20), default="percentage")  # percentage | fixed
    discount_value = Column(Float, nullable=False)
    weekdays = Column(JSON, default=list)           # [0,1,2,3,4] = Dush-Juma (0=Dush, 6=Yak)
    time_from = Column(String(5), nullable=False)   # "12:00"
    time_to = Column(String(5), nullable=False)     # "14:00"
    applies_to = Column(String(20), default="all")  # all | category | product
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class AuditLog(Base):
    """Kim, qaysi resurs ustida, qanday amal bajardi — o'zgarmas jurnal."""
    __tablename__ = "audit_logs"

    id          = Column(Integer, primary_key=True, index=True)
    tenant_id   = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)  # multi-tenant izolyatsiya
    user_id     = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    resource    = Column(String(50), nullable=False, index=True)   # "products", "orders", ...
    action      = Column(String(20), nullable=False)                # CREATE | UPDATE | DELETE | LOGIN
    resource_id = Column(String(50), nullable=True)
    detail      = Column(JSON, nullable=True)
    ip_address  = Column(String(45), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User", backref=backref("audit_logs", lazy="dynamic"))


class TenantPayment(Base):
    """Platforma egasining tenant (mijoz) dan olgan to'lovlari tarixi."""
    __tablename__ = "tenant_payments"

    id             = Column(Integer, primary_key=True, index=True)
    tenant_id      = Column(Integer, ForeignKey("cafes.id"), nullable=False, index=True)
    amount         = Column(Float, nullable=False)
    months         = Column(Integer, default=1)
    payment_method = Column(String(20), default="cash")  # cash, card, click, payme
    period_start   = Column(DateTime, nullable=True)
    period_end     = Column(DateTime, nullable=True)
    note           = Column(Text, nullable=True)
    created_by_id  = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    tenant = relationship("Cafe", back_populates="payments_history")
    created_by = relationship("User")


# ============== POTERIYA MODELI (BOSQICH 17) ==============

class WasteLog(Base):
    """Poteriya (chiqindi) jurnali — retsept chiqindisi va qo'lda utilizatsiya"""
    __tablename__ = "waste_logs"
    id          = Column(Integer, primary_key=True, index=True)
    tenant_id   = Column(Integer, ForeignKey("cafes.id"),    nullable=True,  index=True)
    branch_id   = Column(Integer, ForeignKey("branches.id"), nullable=True,  index=True)
    product_id  = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    quantity    = Column(Float,   nullable=False)
    unit        = Column(String(20), nullable=False, default="kg")
    unit_cost   = Column(Float, default=0.0)    # Birlik tan narxi (snapshot)
    total_cost  = Column(Float, default=0.0)    # Umumiy yo'qotish qiymati
    # Tur: recipe=avtomatik (retseptdan), manual=qo'lda chiqarish, expired=muddati o'tgan
    waste_type  = Column(String(20), nullable=False, index=True)
    order_id    = Column(Integer, ForeignKey("orders.id"),   nullable=True)
    user_id     = Column(Integer, ForeignKey("users.id"),    nullable=True)
    notes       = Column(Text, nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    product = relationship("Product", backref="waste_logs")
    user    = relationship("User", foreign_keys=[user_id])


# ============== BOSQICH 19 — STORE PRO MODELLARI ==============

class CustomerDebt(Base):
    """Nasiya/qarz daftar — mijozga qarzga berilgan tovar hisobi"""
    __tablename__ = "customer_debts"
    id          = Column(Integer, primary_key=True, index=True)
    tenant_id   = Column(Integer, ForeignKey("cafes.id"),     nullable=True, index=True)
    branch_id   = Column(Integer, ForeignKey("branches.id"), nullable=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    order_id    = Column(Integer, ForeignKey("orders.id"),    nullable=True)
    amount      = Column(Float, nullable=False)           # dastlabki qarz miqdori
    paid_amount = Column(Float, default=0.0)              # to'langan qism
    remaining   = Column(Float, nullable=False)           # qolgan qarz
    due_date    = Column(Date, nullable=True)             # muddati (ixtiyoriy)
    # status: open=ochiq, partial=qisman to'langan, paid=to'liq yopilgan
    status      = Column(String(20), default="open", index=True)
    notes       = Column(Text, nullable=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())

    customer    = relationship("Customer", back_populates="debts")
    order       = relationship("Order", foreign_keys=[order_id])
    user        = relationship("User", foreign_keys=[user_id])
    payments    = relationship("DebtPayment", back_populates="debt", cascade="all, delete-orphan")


class DebtPayment(Base):
    """Qarzni to'lash yozuvi — har qisman/to'liq to'lov"""
    __tablename__ = "debt_payments"
    id             = Column(Integer, primary_key=True, index=True)
    debt_id        = Column(Integer, ForeignKey("customer_debts.id", ondelete="CASCADE"), nullable=False, index=True)
    amount         = Column(Float, nullable=False)
    payment_method = Column(String(20), default="cash")  # cash|card|click|payme
    notes          = Column(Text, nullable=True)
    user_id        = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    debt = relationship("CustomerDebt", back_populates="payments")
    user = relationship("User", foreign_keys=[user_id])


class Return(Base):
    """Qaytarish/almashtirish — mijoz tovarni qaytargan holat"""
    __tablename__ = "returns"
    id               = Column(Integer, primary_key=True, index=True)
    tenant_id        = Column(Integer, ForeignKey("cafes.id"),     nullable=True, index=True)
    branch_id        = Column(Integer, ForeignKey("branches.id"), nullable=True, index=True)
    return_number    = Column(String(30), unique=True, nullable=False)
    order_id         = Column(Integer, ForeignKey("orders.id"),    nullable=True)
    customer_id      = Column(Integer, ForeignKey("customers.id"), nullable=True)
    # reason: broken=buzuq, dislike=yoqmadi, expired=muddati o'tgan,
    #         wrong_item=noto'g'ri tovar, other=boshqa
    reason           = Column(String(50), default="other", nullable=False)
    total_amount     = Column(Float, default=0.0)
    # refund_method: cash=naqd, card=karta, credit=balansdaga
    # BOSQICH D: `exchange` (almashtirish) olib tashlandi — `ReturnCreate` uni rad
    # etadi (pul harakati yo'q edi, jimgina "tasdiqlangan" vozvrat qolardi).
    refund_method    = Column(String(20), default="cash", nullable=False)
    # status: pending=kutilmoqda, approved=tasdiqlandi, rejected=rad etildi
    status           = Column(String(20), default="pending", index=True)
    # ESKIRGAN (BOSQICH D): almashtirish olib tashlangach ishlatilmaydi. Ustun
    # BAZADA QOLADI (migratsiya yo'q) — hech qayerda yozilmaydi/o'qilmaydi.
    exchange_order_id = Column(Integer, ForeignKey("orders.id"),  nullable=True)
    notes            = Column(Text, nullable=True)
    user_id          = Column(Integer, ForeignKey("users.id"),    nullable=True)
    approved_by      = Column(Integer, ForeignKey("users.id"),    nullable=True)
    approved_at      = Column(DateTime(timezone=True), nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    customer     = relationship("Customer", foreign_keys=[customer_id])
    order        = relationship("Order", foreign_keys=[order_id])
    items        = relationship("ReturnItem", back_populates="ret", cascade="all, delete-orphan")
    user         = relationship("User", foreign_keys=[user_id])
    approver     = relationship("User", foreign_keys=[approved_by])


class ReturnItem(Base):
    """Qaytarilgan mahsulot elementi"""
    __tablename__ = "return_items"
    id                  = Column(Integer, primary_key=True, index=True)
    return_id           = Column(Integer, ForeignKey("returns.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id          = Column(Integer, ForeignKey("products.id"), nullable=False)
    order_item_id       = Column(Integer, ForeignKey("order_items.id"), nullable=True)
    quantity            = Column(Float, nullable=False)
    # BOSQICH B-returns (pachka/dona): omborga QAYTARILADIGAN dona miqdori.
    # Pachka qaytarilsa base_qty = pack_size × quantity; dona/oddiy = quantity.
    # NULL (eski qaytarish) → tiklashda quantity ishlatiladi (fallback).
    base_qty            = Column(Float, nullable=True)
    unit_price          = Column(Float, nullable=False)
    total               = Column(Float, nullable=False)
    restore_to_inventory = Column(Boolean, default=True)  # omborga qaytarilsinmi
    goes_to_brak         = Column(Boolean, default=False)  # BOSQICH 25: brakka yo'naltirilsinmi

    ret     = relationship("Return", back_populates="items")
    product = relationship("Product")


# ============== BOSQICH 20: MAGAZIN PRO MODELLARI ==============

class ProductBarcode(Base):
    """Bir mahsulotga bir nechta barcode"""
    __tablename__ = "product_barcodes"
    # BOSQICH 39: barcode har TENANT ichida unikal (global emas)
    __table_args__ = (
        UniqueConstraint("tenant_id", "barcode", name="uq_product_barcodes_tenant_barcode"),
    )
    id             = Column(Integer, primary_key=True, index=True)
    tenant_id      = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    product_id     = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    barcode        = Column(String(100), nullable=False)
    barcode_type   = Column(String(20), default="CODE128")  # CODE128|EAN13|weight
    is_primary     = Column(Boolean, default=False)
    weight_variable = Column(Boolean, default=False)  # tarozi (PLU) barcode
    notes          = Column(Text, nullable=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    product = relationship("Product")


class Promotion(Base):
    """Aksiya va murakkab chegirmalar"""
    __tablename__ = "promotions"
    id                  = Column(Integer, primary_key=True, index=True)
    tenant_id           = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    name                = Column(String(150), nullable=False)
    # promo_type: buy_x_get_y | min_amount | flash_price | min_qty_discount
    promo_type          = Column(String(30), nullable=False)
    product_id          = Column(Integer, ForeignKey("products.id"), nullable=True)
    category_id         = Column(Integer, ForeignKey("categories.id"), nullable=True)
    buy_qty             = Column(Integer, default=2)
    get_qty             = Column(Integer, default=1)
    free_product_id     = Column(Integer, ForeignKey("products.id"), nullable=True)  # Faza 3b: bepul Y (NULL → 3a bir xil)
    free_qty_per_set    = Column(Integer, default=1)                                  # har to'plamга nechа Y bepul
    discount_type       = Column(String(20), default="percentage")  # percentage|fixed
    discount_value      = Column(Float, default=0.0)
    min_purchase_amount = Column(Float, default=0.0)
    min_purchase_qty    = Column(Integer, default=0)
    flash_price         = Column(Float, nullable=True)
    start_date          = Column(DateTime, nullable=True)
    end_date            = Column(DateTime, nullable=True)
    days_of_week        = Column(String(20), nullable=True)  # "1,2,3,4,5"
    time_from           = Column(String(5), nullable=True)   # "09:00"
    time_to             = Column(String(5), nullable=True)   # "18:00"
    is_active           = Column(Boolean, default=True)
    usage_limit         = Column(Integer, nullable=True)
    used_count          = Column(Integer, default=0)
    created_at          = Column(DateTime(timezone=True), server_default=func.now())

    product      = relationship("Product", foreign_keys=[product_id])
    free_product = relationship("Product", foreign_keys=[free_product_id])   # Faza 3b: bepul Y
    category     = relationship("Category")


class QuickSellItem(Base):
    """Tez sotuv paneli — eng tez-tez sotiladigan mahsulotlar"""
    __tablename__ = "quick_sell_items"
    id            = Column(Integer, primary_key=True, index=True)
    tenant_id     = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    product_id    = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    display_name  = Column(String(50), nullable=True)
    display_order = Column(Integer, default=0)
    color         = Column(String(20), default="#4CAF50")
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())

    product = relationship("Product")


# BOSQICH 6: PurchaseOrder / PurchaseOrderItem (Tizim A) modellari olib tashlandi.
# Yangi Tizim B: PurchaseReceipt / PurchaseReceiptItem (yuqorida).


class SupplierPayment(Base):
    """Yetkazib beruvchiga to'lov"""
    __tablename__ = "supplier_payments"
    id             = Column(Integer, primary_key=True, index=True)
    tenant_id      = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    supplier_id    = Column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)
    amount         = Column(Float, nullable=False)
    payment_method = Column(String(20), default="cash")
    notes          = Column(Text, nullable=True)
    user_id        = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())
    # BOSQICH 24: B2B yangi maydonlar
    receipt_id   = Column(Integer, ForeignKey("purchase_receipts.id"), nullable=True)
    payment_date = Column(Date, nullable=True)
    created_by   = Column(Integer, ForeignKey("users.id"), nullable=True)

    supplier = relationship("Supplier", foreign_keys=[supplier_id])
    user     = relationship("User", foreign_keys=[user_id])
    receipt  = relationship("PurchaseReceipt", backref="b2b_payments")


class PriceHistory(Base):
    """Mahsulot narxi o'zgarish tarixi (audit)"""
    __tablename__ = "price_history"
    id         = Column(Integer, primary_key=True, index=True)
    tenant_id  = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    old_price  = Column(Float, nullable=False)
    new_price  = Column(Float, nullable=False)
    old_cost   = Column(Float, nullable=True)
    new_cost   = Column(Float, nullable=True)
    reason     = Column(String(200), nullable=True)
    changed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    product    = relationship("Product")
    changer    = relationship("User")


class ReceiptSettings(Base):
    """Chek/kvitansiya sozlamalari (har tenant uchun bitta)"""
    __tablename__ = "receipt_settings"
    id          = Column(Integer, primary_key=True, index=True)
    tenant_id   = Column(Integer, ForeignKey("cafes.id"), nullable=False, unique=True)
    store_name  = Column(String(150), nullable=True)
    address     = Column(Text, nullable=True)
    phone       = Column(String(30), nullable=True)
    tax_id      = Column(String(30), nullable=True)
    header_text = Column(Text, nullable=True)
    footer_text = Column(Text, nullable=True)
    show_logo   = Column(Boolean, default=False)
    qr_enabled  = Column(Boolean, default=False)
    qr_url      = Column(String(300), nullable=True)
    paper_width = Column(Integer, default=80)    # 57 yoki 80 mm
    font_size   = Column(String(10), default="normal")
    # Print turi (B0 poydevor) — markaziy print servis shu yo'lni tanlaydi:
    #   "usb" → SumatraPDF (hozirgi, do'kon); "lan" → IP:port (kelajak); "qr" → ekran QR
    # default "usb" → mavjud do'kon avvalgidek SumatraPDF (regressiya yo'q).
    print_type   = Column(String(10), default="usb")
    printer_ip   = Column(String(45), nullable=True)   # LAN/API uchun (kelajak)
    printer_port = Column(Integer, nullable=True)      # LAN/API porti (mas. 9100)
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())


class TenantSettings(Base):
    """Tenant-scoped konfiguratsiya (printer/fiscal/payment/kitchen/app va h.k.)

    Har tenant + config_name uchun bitta yozuv; `data` o'sha config'ning butun
    dict'ini saqlaydi. Eski global config_loader yonida turadi — ko'chirish
    bosqichma-bosqich (BOSQICH: settings tenant-scoped, 1-qadam poydevor).
    """
    __tablename__ = "tenant_settings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "config_name", name="uq_tenant_settings_tenant_config"),
    )
    id          = Column(Integer, primary_key=True, index=True)
    tenant_id   = Column(Integer, ForeignKey("cafes.id"), nullable=False, index=True)
    config_name = Column(String(50), nullable=False)  # "printer"/"fiscal"/"payment"/"kitchen"/"app"
    data        = Column(JSON, nullable=False, default=dict)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())


# ============== BOSQICH 22: DORIXONA MAXSUS MODELLARI ==============

class ProductBatch(Base):
    """Dori partiyasi / seriya nazorati — BOSQICH 22"""
    __tablename__ = "product_batches"
    id               = Column(Integer, primary_key=True, index=True)
    tenant_id        = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    branch_id        = Column(Integer, ForeignKey("branches.id"), nullable=True, index=True)
    product_id       = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_number     = Column(String(100), nullable=False)        # seriya raqami
    manufacturer     = Column(String(200), nullable=True)         # ishlab chiqaruvchi
    manufacture_date = Column(Date, nullable=True)                # ishlab chiqarilgan sana
    expiry_date      = Column(Date, nullable=False)               # yaroqlilik muddati
    quantity         = Column(Float, default=0.0)                 # qolgan miqdor
    initial_quantity = Column(Float, default=0.0)                 # boshlang'ich miqdor
    cost_price       = Column(Float, default=0.0)                 # kelish narxi
    notes            = Column(Text, nullable=True)
    is_active        = Column(Boolean, default=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    updated_at       = Column(DateTime(timezone=True), onupdate=func.now())

    product = relationship("Product", backref="batches")


class Prescription(Base):
    """Shifokor retsepti arxivi — BOSQICH 22"""
    __tablename__ = "prescriptions"
    id               = Column(Integer, primary_key=True, index=True)
    tenant_id        = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    branch_id        = Column(Integer, ForeignKey("branches.id"), nullable=True, index=True)
    patient_name     = Column(String(200), nullable=False)        # bemor ismi
    patient_phone    = Column(String(30), nullable=True)          # bemor telefoni
    doctor_name      = Column(String(200), nullable=True)         # shifokor ismi
    clinic_name      = Column(String(200), nullable=True)         # klinika nomi
    prescription_date = Column(Date, nullable=False)              # retsept sanasi
    image_url        = Column(String(500), nullable=True)         # retsept rasmi
    notes            = Column(Text, nullable=True)                # qo'shimcha izoh
    medicines        = Column(JSON, default=list)                 # [{name, quantity, dosage, instructions}]
    is_dispensed     = Column(Boolean, default=False)             # dori berilganmi
    dispensed_at     = Column(DateTime(timezone=True), nullable=True)
    order_id         = Column(Integer, ForeignKey("orders.id"), nullable=True)
    created_by       = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    updated_at       = Column(DateTime(timezone=True), onupdate=func.now())

    order      = relationship("Order", backref="prescriptions")
    creator    = relationship("User")


# ============== BOSQICH 25: TOVAR HARAKATI VA HISOBDAN CHIQARISH ==============

class WriteOff(Base):
    """Utilizatsiya / Spisaniye akti — tovarni hisobdan chiqarish"""
    __tablename__ = "write_offs"
    id            = Column(Integer, primary_key=True, index=True)
    tenant_id     = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    branch_id     = Column(Integer, ForeignKey("branches.id"), nullable=True, index=True)
    act_number    = Column(String(30), unique=True, nullable=False)
    # reason: expired=muddati tugagan, damaged=buzilgan, theft=o'g'irlik,
    #         brak=ishlab chiqarish nuqsoni, other=boshqa
    reason        = Column(String(30), default="other", nullable=False, index=True)
    write_off_date = Column(Date, nullable=False)
    total_loss    = Column(Float, default=0.0)
    notes         = Column(Text, nullable=True)
    status        = Column(String(20), default="draft", index=True)  # draft/confirmed
    created_by    = Column(Integer, ForeignKey("users.id"), nullable=True)
    confirmed_by  = Column(Integer, ForeignKey("users.id"), nullable=True)
    confirmed_at  = Column(DateTime(timezone=True), nullable=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())

    items     = relationship("WriteOffItem", back_populates="write_off", cascade="all, delete-orphan")
    creator   = relationship("User", foreign_keys=[created_by])
    confirmer = relationship("User", foreign_keys=[confirmed_by])


class WriteOffItem(Base):
    """Utilizatsiya aktining qatori — har bir tovar"""
    __tablename__ = "write_off_items"
    id           = Column(Integer, primary_key=True, index=True)
    write_off_id = Column(Integer, ForeignKey("write_offs.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id   = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity     = Column(Float, nullable=False)
    cost_price   = Column(Float, default=0.0)
    total_loss   = Column(Float, default=0.0)
    notes        = Column(Text, nullable=True)

    write_off = relationship("WriteOff", back_populates="items")
    product   = relationship("Product")


class GoodsRegrade(Base):
    """Peresort — xato kirimni tuzatish: A tovar → B tovar"""
    __tablename__ = "goods_regrades"
    id            = Column(Integer, primary_key=True, index=True)
    tenant_id     = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    branch_id     = Column(Integer, ForeignKey("branches.id"), nullable=True, index=True)
    regrade_date  = Column(Date, nullable=False)
    notes         = Column(Text, nullable=True)
    status        = Column(String(20), default="draft", index=True)  # draft/confirmed
    created_by    = Column(Integer, ForeignKey("users.id"), nullable=True)
    confirmed_by  = Column(Integer, ForeignKey("users.id"), nullable=True)
    confirmed_at  = Column(DateTime(timezone=True), nullable=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())

    items     = relationship("GoodsRegradeItem", back_populates="regrade", cascade="all, delete-orphan")
    creator   = relationship("User", foreign_keys=[created_by])
    confirmer = relationship("User", foreign_keys=[confirmed_by])


class GoodsRegradeItem(Base):
    """Peresort qatori — qaysi tovardan qaysi tovarga"""
    __tablename__ = "goods_regrade_items"
    id              = Column(Integer, primary_key=True, index=True)
    regrade_id      = Column(Integer, ForeignKey("goods_regrades.id", ondelete="CASCADE"), nullable=False, index=True)
    from_product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    to_product_id   = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity        = Column(Float, nullable=False)
    notes           = Column(Text, nullable=True)

    regrade      = relationship("GoodsRegrade", back_populates="items")
    from_product = relationship("Product", foreign_keys=[from_product_id])
    to_product   = relationship("Product", foreign_keys=[to_product_id])


class InternalTransfer(Base):
    """Ichki ko'chirish — filiallar orasida tovar harakati"""
    __tablename__ = "internal_transfers"
    id             = Column(Integer, primary_key=True, index=True)
    tenant_id      = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    from_branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True, index=True)
    to_branch_id   = Column(Integer, ForeignKey("branches.id"), nullable=True, index=True)
    transfer_date  = Column(Date, nullable=False)
    notes          = Column(Text, nullable=True)
    status         = Column(String(20), default="draft", index=True)  # draft/confirmed
    created_by     = Column(Integer, ForeignKey("users.id"), nullable=True)
    confirmed_by   = Column(Integer, ForeignKey("users.id"), nullable=True)
    confirmed_at   = Column(DateTime(timezone=True), nullable=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    items       = relationship("InternalTransferItem", back_populates="transfer", cascade="all, delete-orphan")
    from_branch = relationship("Branch", foreign_keys=[from_branch_id])
    to_branch   = relationship("Branch", foreign_keys=[to_branch_id])
    creator     = relationship("User", foreign_keys=[created_by])
    confirmer   = relationship("User", foreign_keys=[confirmed_by])


class InternalTransferItem(Base):
    """Ichki ko'chirma qatori"""
    __tablename__ = "internal_transfer_items"
    id          = Column(Integer, primary_key=True, index=True)
    transfer_id = Column(Integer, ForeignKey("internal_transfers.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id  = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity    = Column(Float, nullable=False)
    cost_price  = Column(Float, default=0.0)

    transfer = relationship("InternalTransfer", back_populates="items")
    product  = relationship("Product")


# ============== BOSQICH 26: NARX, AKSIYA VA MARKIROVKA ==============

class MarkupPolicy(Base):
    """Naценka siyosati — tan narxdan sotuv narxini avtomatik hisoblash"""
    __tablename__ = "markup_policies"
    id          = Column(Integer, primary_key=True, index=True)
    tenant_id   = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    name        = Column(String(100), nullable=False)
    # scope: global=hamma, category=bo'lim, product=tovar
    scope       = Column(String(20), default="global", nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True, index=True)
    product_id  = Column(Integer, ForeignKey("products.id"), nullable=True, index=True)
    markup_pct  = Column(Float, nullable=False)         # naценka foizi, masalan 30.0 = 30%
    min_price   = Column(Float, nullable=True)          # minimal sotuv narxi
    is_active   = Column(Boolean, default=True)
    created_by  = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())

    category = relationship("Category")
    product  = relationship("Product")
    creator  = relationship("User", foreign_keys=[created_by])


class BonusCard(Base):
    """Mijoz bonus kartasi — xarid qilganda ball to'plash va sarflash"""
    __tablename__ = "bonus_cards"
    id           = Column(Integer, primary_key=True, index=True)
    tenant_id    = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    card_number  = Column(String(30), unique=True, nullable=False, index=True)
    customer_id  = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    balance      = Column(Float, default=0.0)           # joriy bonus ball (so'm)
    earn_rate    = Column(Float, default=1.0)           # har 100 so'm xariddan % ball
    total_earned = Column(Float, default=0.0)
    total_spent  = Column(Float, default=0.0)
    is_active    = Column(Boolean, default=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    updated_at   = Column(DateTime(timezone=True), onupdate=func.now())

    customer      = relationship("Customer", foreign_keys=[customer_id])
    transactions  = relationship("BonusTransaction", back_populates="card", cascade="all, delete-orphan")


class BonusTransaction(Base):
    """Bonus ball harakati tarixi"""
    __tablename__ = "bonus_transactions"
    id          = Column(Integer, primary_key=True, index=True)
    tenant_id   = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    card_id     = Column(Integer, ForeignKey("bonus_cards.id", ondelete="CASCADE"), nullable=False, index=True)
    order_id    = Column(Integer, ForeignKey("orders.id"), nullable=True)
    # tx_type: earn=to'plash, spend=sarflash, manual=qo'lda kiritish, expire=muddati tugash
    tx_type     = Column(String(20), nullable=False, index=True)
    amount      = Column(Float, nullable=False)         # + yoki - so'm
    description = Column(String(200), nullable=True)
    created_by  = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    card    = relationship("BonusCard", back_populates="transactions")
    order   = relationship("Order")
    creator = relationship("User", foreign_keys=[created_by])


class ProductMark(Base):
    """Markirovka (Asl belgisi) — tovar uchun DataMatrix/QR kod"""
    __tablename__ = "product_marks"
    id          = Column(Integer, primary_key=True, index=True)
    tenant_id   = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    product_id  = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    batch_id    = Column(Integer, ForeignKey("product_batches.id"), nullable=True)
    mark_code   = Column(String(500), unique=True, nullable=False, index=True)
    mark_type   = Column(String(20), default="datamatrix")  # datamatrix|qr|barcode
    # status: active=mavjud, sold=sotilgan, returned=qaytarilgan, invalid=yaroqsiz
    status      = Column(String(20), default="active", index=True)
    order_id    = Column(Integer, ForeignKey("orders.id"), nullable=True)
    scanned_at  = Column(DateTime(timezone=True), nullable=True)
    created_by  = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    product = relationship("Product")
    batch   = relationship("ProductBatch")
    order   = relationship("Order")


# ============== BOSQICH 27: AQLLI HISOBOT VA NAZORAT ==============

class ProductReorderSetting(Base):
    """Minimal qoldiq va avto-zakaz sozlamalari — BOSQICH 27"""
    __tablename__ = "product_reorder_settings"
    id                   = Column(Integer, primary_key=True, index=True)
    tenant_id            = Column(Integer, ForeignKey("cafes.id"), nullable=True, index=True)
    product_id           = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    min_qty              = Column(Float, nullable=False, default=10.0)    # minimal qoldiq chegarasi
    reorder_qty          = Column(Float, nullable=False, default=50.0)    # zakaz berish miqdori
    preferred_supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    notes                = Column(String(300), nullable=True)
    created_at           = Column(DateTime(timezone=True), server_default=func.now())
    updated_at           = Column(DateTime(timezone=True), onupdate=func.now())

    product  = relationship("Product", backref="reorder_setting")
    supplier = relationship("Supplier")