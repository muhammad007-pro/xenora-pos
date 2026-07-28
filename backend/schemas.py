from pydantic import BaseModel, EmailStr, Field, validator, computed_field
from typing import Optional, List, Any, Dict
from datetime import datetime, date
from enum import Enum

# ============== User Schemas ==============
class UserBase(BaseModel):
    # BOSQICH 38: telefon asosiy login kaliti (majburiy); username/email ixtiyoriy (display/legacy)
    phone: str
    full_name: Optional[str] = None
    username: Optional[str] = None
    email: Optional[EmailStr] = None

class UserCreate(UserBase):
    # Xodim (kassir/ofitsiant) faqat ISM + PIN bilan qo'shilishi mumkin:
    # phone/username/password IXTIYORIY. Berilmasa server sintetik qiymat yaratadi
    # (xodim access_code + PIN bilan kiradi). phone/password bo'lsa — mavjud oqim saqlanadi.
    phone: Optional[str] = None
    password: Optional[str] = None
    pin: Optional[str] = None
    role_id: Optional[int] = None
    branch_id: Optional[int] = None
    tenant_id: Optional[int] = None  # BOSQICH 2.1: qaysi tenant'ga tegishli

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None
    role_id: Optional[int] = None
    branch_id: Optional[int] = None
    pin: Optional[str] = None

class PinLoginRequest(BaseModel):
    pin: str
    branch_id: Optional[int] = None
    access_code: Optional[str] = None   # do'kon kirish kodi (100.200.N) — branch_id o'rniga

class UserInDB(UserBase):
    id: int
    # Chiqish himoyasi: bazadagi yaroqsiz/bo'sh email /auth/me'da 500 bermasin → Optional[str]
    # (EmailStr emas). Kirish validatsiyasi UserCreate/UserBase'da qoladi.
    email: Optional[str] = None
    is_active: bool
    is_superuser: bool
    role_id: Optional[int]
    branch_id: Optional[int] = None
    role: Optional['RoleInDB'] = None
    hashed_pin: Optional[str] = Field(default=None, exclude=True)
    created_at: datetime
    last_login: Optional[datetime]

    @computed_field
    @property
    def has_pin(self) -> bool:
        return bool(self.hashed_pin)

    class Config:
        from_attributes = True

class UserLogin(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    username: Optional[str] = None
    user_id: Optional[int] = None

# ============== Role va Permission Schemas ==============
class PermissionBase(BaseModel):
    code: str
    description: Optional[str] = None

class PermissionCreate(PermissionBase):
    pass

class PermissionInDB(PermissionBase):
    id: int
    created_at: Optional[datetime] = None   # eski/edge yozuvlarda NULL bo'lsa /me 500 bermasin

    class Config:
        from_attributes = True

class RoleBase(BaseModel):
    name: str
    description: Optional[str] = None

class RoleCreate(RoleBase):
    permission_ids: Optional[List[int]] = []

class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class RoleInDB(RoleBase):
    id: int
    permissions: List[PermissionInDB] = []
    created_at: Optional[datetime] = None   # eski/edge yozuvlarda NULL bo'lsa /me 500 bermasin

    class Config:
        from_attributes = True

# ============== Station Schemas ==============
class StationBase(BaseModel):
    name: str
    color: str = "#d4af37"
    has_display: bool = True
    display_order: int = 0

class StationCreate(StationBase):
    branch_id: Optional[int] = None

class StationUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    has_display: Optional[bool] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = None
    branch_id: Optional[int] = None

class StationInDB(StationBase):
    id: int
    tenant_id: Optional[int] = None
    branch_id: Optional[int] = None
    is_active: bool

    class Config:
        from_attributes = True

# ============== Branch Schemas ==============
class BranchBase(BaseModel):
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None

class BranchCreate(BranchBase):
    pass

class BranchUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None

class BranchInDB(BranchBase):
    id: int
    tenant_id: int
    is_active: bool
    is_default: bool
    created_at: datetime

    class Config:
        from_attributes = True

# ── Kassa nuqtalari (multi-register, BOSQICH 30) ──────────────────────────────
class CashRegisterBase(BaseModel):
    name: str
    branch_id: Optional[int] = None

class CashRegisterCreate(CashRegisterBase):
    pass

class CashRegisterUpdate(BaseModel):
    name: Optional[str] = None
    branch_id: Optional[int] = None
    is_active: Optional[bool] = None

class CashRegisterInDB(CashRegisterBase):
    id: int
    tenant_id: Optional[int] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

# ============== Category Schemas ==============
class CategoryBase(BaseModel):
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = None
    display_order: int = 0

class CategoryCreate(CategoryBase):
    pass

class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[int] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = None

class CategoryInDB(CategoryBase):
    id: int
    image_url: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    children: List['CategoryInDB'] = []

    class Config:
        from_attributes = True

# ============== Product Schemas ==============
class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: float = Field(gt=0)
    cost_price: float = 0.0
    barcode: Optional[str] = None
    sku: Optional[str] = None
    category_id: int
    station_id: Optional[int] = None
    preparation_time: int = 10
    sale_unit: str = "pcs"
    is_available: bool = True
    yield_pct: Optional[float] = None
    # BOSQICH 19: ko'tara narx
    wholesale_price: Optional[float] = None
    wholesale_min_qty: Optional[int] = 10
    # BOSQICH B2 (pachka/dona): price = DONA narxi; pack_price = 1 PACHKA narxi;
    # pack_size = 1 pachkadagi dona soni. NULL/pack_size<2 → oddiy (pachkasiz).
    pack_size: Optional[int] = None
    pack_price: Optional[float] = None
    # BOSQICH 22: dorixona maydonlari
    active_ingredient: Optional[str] = None
    dosage: Optional[str] = None
    drug_form: Optional[str] = None
    dosing_schedule: Optional[str] = None
    requires_prescription: bool = False

class ProductCreate(ProductBase):
    pass

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = Field(None, gt=0)
    cost_price: Optional[float] = None
    barcode: Optional[str] = None
    sku: Optional[str] = None
    category_id: Optional[int] = None
    station_id: Optional[int] = None
    preparation_time: Optional[int] = None
    is_active: Optional[bool] = None
    is_available: Optional[bool] = None
    sale_unit: Optional[str] = None
    yield_pct: Optional[float] = None
    wholesale_price: Optional[float] = None
    wholesale_min_qty: Optional[int] = None
    # BOSQICH B2 (pachka/dona)
    pack_size: Optional[int] = None
    pack_price: Optional[float] = None
    # BOSQICH 22
    active_ingredient: Optional[str] = None
    dosage: Optional[str] = None
    drug_form: Optional[str] = None
    dosing_schedule: Optional[str] = None
    requires_prescription: Optional[bool] = None

class ProductInDB(ProductBase):
    id: int
    image_url: Optional[str] = None
    is_active: bool
    is_available: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    category: Optional[CategoryInDB] = None
    station: Optional['StationInDB'] = None

    class Config:
        from_attributes = True

# ============== Table Schemas ==============
class TableBase(BaseModel):
    number: str
    name: Optional[str] = None
    capacity: int = 4
    section: Optional[str] = None
    position_x: Optional[int] = None
    position_y: Optional[int] = None

class TableCreate(TableBase):
    pass

class TableUpdate(BaseModel):
    name: Optional[str] = None
    capacity: Optional[int] = None
    section: Optional[str] = None
    status: Optional[str] = None
    position_x: Optional[int] = None
    position_y: Optional[int] = None

class TableInDB(TableBase):
    id: int
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    current_order: Optional['OrderInDB'] = None

    class Config:
        from_attributes = True

# ============== Order Schemas ==============
class OrderItemCreate(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)
    notes: Optional[str] = None
    # BOSQICH B3 (pachka/dona): client FAQAT sotilgan birlikni yuboradi ("pachka"|"dona"|None).
    # unit_price/base_qty SERVERDA product'dan hisoblanadi (client narxiga ishonilmaydi).
    unit_sold: Optional[str] = None

class OrderItemUpdate(BaseModel):
    quantity: Optional[int] = Field(None, gt=0)
    notes: Optional[str] = None
    status: Optional[str] = None

class OrderItemInDB(BaseModel):
    id: int
    product_id: int
    product_name: str
    quantity: int
    unit_price: float
    total_price: float
    notes: Optional[str] = None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

class OrderCreate(BaseModel):
    table_id: Optional[int] = None
    customer_id: Optional[int] = None
    items: List[OrderItemCreate] = []
    notes: Optional[str] = None
    order_type: str = "dine-in"
    # FAZA 3b: kassir tasdiqlagan "boshqa mahsulot bepul" aksiyalar (server qayta tekshiradi). Bo'sh → gated.
    accepted_gift_promotions: List[int] = []
    source: Optional[str] = "pos"
    # Yetkazib berish
    delivery_address: Optional[str] = None
    delivery_phone: Optional[str] = None
    delivery_note: Optional[str] = None
    # Narx
    total_amount: Optional[float] = None
    discount_type: Optional[str] = None
    discount_value: Optional[float] = None
    discount_amount: Optional[float] = 0.0
    tax_amount: Optional[float] = 0.0
    service_amount: Optional[float] = 0.0
    final_amount: Optional[float] = None
    # Pro
    courses_enabled: Optional[bool] = False
    # Dorixona — retsept
    rx_patient_name: Optional[str] = None
    rx_patient_phone: Optional[str] = None
    rx_number: Optional[str] = None
    # Auto servis — avtomobil
    car_plate: Optional[str] = None
    car_make: Optional[str] = None
    car_model: Optional[str] = None
    car_year: Optional[int] = None
    # Maktab — o'quvchi
    student_name: Optional[str] = None
    student_phone: Optional[str] = None
    student_group: Optional[str] = None
    # Kimyoviy tozalash
    cleaning_items: Optional[str] = None
    cleaning_notes: Optional[str] = None
    # Savatcha snapshot (C1): held buyurtma qayta ochilganda modifikator/og'irlik
    # to'liq tiklanishi uchun POS savatcha satrlari xom holda saqlanadi (biz_meta['cart']).
    # Serverdagi summa hisobiga TA'SIR QILMAYDI — faqat qayta ochishda ko'rsatish uchun.
    cart_snapshot: Optional[list] = None

class OrderUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    discount_amount: Optional[float] = None

class OrderInDB(BaseModel):
    id: int
    order_number: str
    daily_number: Optional[int] = None   # ko'rinadigan kunlik chek raqami
    table_id: Optional[int] = None
    table_number: Optional[str] = None
    waiter_id: Optional[int] = None
    waiter_name: Optional[str] = None
    register_name: Optional[str] = None   # kassa nomi (Shift.register orqali)
    payment_method: Optional[str] = None  # to'lov usuli (Payment orqali)
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    status: str
    total_amount: float
    discount_amount: float
    tax_amount: float
    final_amount: float
    notes: Optional[str] = None
    order_type: Optional[str] = "dine-in"
    source: Optional[str] = "pos"
    delivery_address: Optional[str] = None
    delivery_phone: Optional[str] = None
    delivery_note: Optional[str] = None
    service_amount: Optional[float] = 0.0
    biz_meta: Optional[dict] = None
    items: List[OrderItemInDB] = []
    items_count: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True

    @classmethod
    def model_validate(cls, obj, **kwargs):
        inst = super().model_validate(obj, **kwargs)
        if hasattr(obj, 'items'):
            inst.items_count = len(obj.items)
        return inst

# ============== Payment Schemas ==============
class PaymentCreate(BaseModel):
    order_id: int
    amount: float = Field(gt=0)
    method: str
    reference: Optional[str] = None
    cash_received: Optional[float] = None
    # Sodiqlik: shu to'lovда ishlatiladigan ball (ixtiyoriy). SERVER qayta tekshiradi.
    redeem_points: Optional[int] = 0

class PaymentInDB(BaseModel):
    id: int
    order_id: int
    cashier_id: Optional[int] = None
    amount: float
    method: str
    status: str
    transaction_id: Optional[str] = None
    reference: Optional[str] = None
    created_at: datetime
    # Sodiqlik natijasi (chek uchun) — transient, faqat javobда to'ldiriladi
    earned_points: Optional[int] = None
    redeemed_points: Optional[int] = None
    customer_points: Optional[int] = None

    class Config:
        from_attributes = True

# ============== Customer Schemas ==============
class CustomerBase(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    birthday: Optional[datetime] = None
    # BOSQICH 19: nasiya tizimi
    credit_limit: Optional[float] = None
    customer_type: str = "retail"  # retail|wholesale
    # BOSQICH S0 (sodiqlik): doimiy mijoz avtomatik % chegirmasi (0-100)
    discount_percent: Optional[float] = Field(0, ge=0, le=100)

class CustomerCreate(CustomerBase):
    pass

class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    birthday: Optional[datetime] = None
    credit_limit: Optional[float] = None
    customer_type: Optional[str] = None
    # BOSQICH S0 (sodiqlik)
    discount_percent: Optional[float] = Field(None, ge=0, le=100)

class CustomerInDB(CustomerBase):
    id: int
    total_visits: int
    total_spent: float
    points: int
    total_debt: float = 0.0
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# ============== Shift Schemas ==============
class ShiftBase(BaseModel):
    user_id: int
    starting_cash: float = 0.0

class ShiftCreate(ShiftBase):
    register_id: Optional[int] = None   # qaysi kassada (cash_register flagi yoqilgan bo'lsa)

class ShiftUpdate(BaseModel):
    ending_cash: Optional[float] = None
    notes: Optional[str] = None

class ShiftInDB(ShiftBase):
    id: int
    register_id: Optional[int] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    ending_cash: Optional[float] = None
    counted_cash: Optional[float] = None
    total_sales: float
    cash_sales: float
    card_sales: float
    credit_total: float = 0.0
    shortage: float = 0.0
    notes: Optional[str] = None
    user: Optional[UserInDB] = None

    class Config:
        from_attributes = True

# ============== Reservation Schemas ==============
class ReservationBase(BaseModel):
    customer_id: int
    table_id: int
    reservation_time: datetime
    duration_minutes: int = 120
    guests_count: int = 2
    notes: Optional[str] = None

class ReservationCreate(ReservationBase):
    pass

class ReservationUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None

class ReservationInDB(ReservationBase):
    id: int
    status: str
    created_at: datetime
    customer: Optional[CustomerInDB] = None
    table: Optional[TableInDB] = None

    class Config:
        from_attributes = True

# ============== Inventory Schemas ==============
class InventoryBase(BaseModel):
    product_id: int
    quantity: float = 0.0
    unit: str = "dona"
    min_threshold: float = 5.0
    max_threshold: float = 100.0

class InventoryCreate(InventoryBase):
    pass

class InventoryUpdate(BaseModel):
    quantity: Optional[float] = None
    min_threshold: Optional[float] = None
    max_threshold: Optional[float] = None

class InventoryInDB(InventoryBase):
    id: int
    last_restock: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    product: Optional[ProductInDB] = None

    class Config:
        from_attributes = True


# ============== StockMovement Schemas (BOSQICH 16) ==============
class StockMovementCreate(BaseModel):
    inventory_id: Optional[int] = None
    product_id: Optional[int] = None
    movement_type: str                    # in | out | writeoff | adjustment | return
    quantity: float
    unit: str = "dona"
    unit_cost: float = 0.0
    supplier_id: Optional[int] = None
    batch_number: Optional[str] = None
    expiry_date: Optional[date] = None
    reason: Optional[str] = None
    reference_id: Optional[int] = None
    reference_type: Optional[str] = None
    notes: Optional[str] = None

class StockMovementInDB(BaseModel):
    id: int
    tenant_id: Optional[int] = None
    branch_id: Optional[int] = None
    inventory_id: Optional[int] = None
    product_id: Optional[int] = None
    movement_type: str
    quantity: float
    unit: str
    unit_cost: float
    total_cost: float
    supplier_id: Optional[int] = None
    batch_number: Optional[str] = None
    expiry_date: Optional[date] = None
    reason: Optional[str] = None
    reference_id: Optional[int] = None
    reference_type: Optional[str] = None
    notes: Optional[str] = None
    user_id: Optional[int] = None
    created_at: datetime
    product_name: Optional[str] = None    # computed

    class Config:
        from_attributes = True

class WriteoffCreate(BaseModel):
    inventory_id: int
    quantity: float
    reason: str                           # spoiled | lost | internal_use | expired | other
    batch_number: Optional[str] = None
    notes: Optional[str] = None

class StockInCreate(BaseModel):
    """Kirim qilish uchun kengaytirilgan forma"""
    quantity: float
    unit_cost: float = 0.0
    supplier_id: Optional[int] = None
    batch_number: Optional[str] = None
    expiry_date: Optional[date] = None
    notes: Optional[str] = None


# ============== InventoryCount Schemas (BOSQICH 16) ==============
class InventoryCountCreate(BaseModel):
    notes: Optional[str] = None

class InventoryCountItemUpdate(BaseModel):
    actual_qty: float
    notes: Optional[str] = None

class InventoryCountItemInDB(BaseModel):
    id: int
    count_id: int
    inventory_id: Optional[int] = None
    product_id: Optional[int] = None
    product_name: Optional[str] = None
    unit: str
    system_qty: float
    actual_qty: Optional[float] = None
    difference: Optional[float] = None
    notes: Optional[str] = None

    class Config:
        from_attributes = True

class InventoryCountInDB(BaseModel):
    id: int
    tenant_id: Optional[int] = None
    branch_id: Optional[int] = None
    status: str
    notes: Optional[str] = None
    user_id: Optional[int] = None
    confirmed_by: Optional[int] = None
    confirmed_at: Optional[datetime] = None
    created_at: datetime
    items: List["InventoryCountItemInDB"] = []

    class Config:
        from_attributes = True

class InventoryValueResponse(BaseModel):
    total_cost: float
    total_retail: float
    potential_profit: float
    item_count: int


# ============== Discount Schemas ==============
class DiscountBase(BaseModel):
    name: str
    type: str
    value: float
    product_id: Optional[int] = None
    category_id: Optional[int] = None
    min_order_amount: float = 0.0
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    usage_limit: Optional[int] = None

class DiscountCreate(DiscountBase):
    pass

class DiscountInDB(DiscountBase):
    id: int
    is_active: bool
    used_count: int
    created_at: datetime

    class Config:
        from_attributes = True

# ============== Notification Schemas ==============
class NotificationBase(BaseModel):
    title: str
    message: str
    type: str = "system"
    data: Optional[Dict[str, Any]] = None

class NotificationCreate(NotificationBase):
    user_id: int

class NotificationInDB(NotificationBase):
    id: int
    user_id: int
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True

# ============== Report Schemas ==============
class DailyReportData(BaseModel):
    date: str
    total_sales: float
    cash_sales: float
    card_sales: float
    orders_count: int
    completed_orders: int
    cancelled_orders: int
    avg_check: float

class SalesReportData(BaseModel):
    date_from: str
    date_to: str
    total_sales: float
    daily_sales: List[Dict[str, Any]]
    payment_methods: List[Dict[str, Any]]

# ============== API Response Schemas ==============
class PaginationParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)

class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    page_size: int
    total_pages: int

class MessageResponse(BaseModel):
    message: str
    success: bool = True

class ErrorResponse(BaseModel):
    detail: str
    error_code: Optional[str] = None

# ============== Analytics Schemas ==============
class DashboardData(BaseModel):
    total_revenue: float
    total_orders: int
    total_customers: int
    average_check: float
    revenue_trend: float
    orders_trend: float
    customers_trend: float
    avg_check_trend: float
    revenue_data: Dict[str, List]
    popular_products: List[Dict[str, Any]]
    categories_data: List[Dict[str, Any]]
    payment_methods: List[Dict[str, Any]]
    recent_orders: List[Dict[str, Any]]

# ============== Kitchen Schemas ==============
class KitchenOrderItem(BaseModel):
    id: int
    product_id: int
    product_name: str
    quantity: int
    notes: Optional[str] = None
    status: str

class KitchenOrder(BaseModel):
    id: int
    order_number: str
    table_number: Optional[str] = None
    order_type: str
    waiter_name: Optional[str] = None
    customer_name: Optional[str] = None
    created_at: datetime
    status: str
    notes: Optional[str] = None
    urgent: bool = False
    items: List[KitchenOrderItem]

class KitchenOrdersResponse(BaseModel):
    pending: List[KitchenOrder]
    preparing: List[KitchenOrder]
    ready: List[KitchenOrder]
    completed: List[KitchenOrder]

# ============== Service Schemas ==============
class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: float = 0.0
    duration_minutes: int = 30
    category: Optional[str] = None
    color: str = "#c9a84c"
    cost_price: float = 0.0
    commission_pct: float = 0.0

class ServiceCreate(ServiceBase):
    pass

class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    duration_minutes: Optional[int] = None
    category: Optional[str] = None
    color: Optional[str] = None
    is_active: Optional[bool] = None
    cost_price: Optional[float] = None
    commission_pct: Optional[float] = None

class ServiceInDB(ServiceBase):
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

# ============== Appointment Schemas ==============
class AppointmentBase(BaseModel):
    customer_name: str
    customer_phone: Optional[str] = None
    customer_id: Optional[int] = None
    service_id: Optional[int] = None
    employee_id: Optional[int] = None
    date: str
    start_time: str
    duration_minutes: int = 30
    notes: Optional[str] = None
    price: float = 0.0

class AppointmentCreate(AppointmentBase):
    pass

class AppointmentUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    employee_id: Optional[int] = None
    start_time: Optional[str] = None
    date: Optional[str] = None

class AppointmentInDB(AppointmentBase):
    id: int
    status: str
    service_name: Optional[str] = None
    employee_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

# ============== Membership Schemas ==============
class MembershipBase(BaseModel):
    customer_id: int
    plan_name: str
    price: float
    start_date: str
    end_date: str
    visits_total: int = 0
    notes: Optional[str] = None

class MembershipCreate(MembershipBase):
    pass

class MembershipUpdate(BaseModel):
    status: Optional[str] = None
    visits_used: Optional[int] = None
    notes: Optional[str] = None
    end_date: Optional[str] = None

class MembershipInDB(MembershipBase):
    id: int
    visits_used: int
    status: str
    customer: Optional[CustomerInDB] = None
    created_at: datetime

    class Config:
        from_attributes = True

# ============== Vehicle Schemas ==============
class VehicleBase(BaseModel):
    plate_number: str
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    color: Optional[str] = None
    vin: Optional[str] = None
    mileage: int = 0
    customer_id: Optional[int] = None
    notes: Optional[str] = None

class VehicleCreate(VehicleBase):
    pass

class VehicleUpdate(BaseModel):
    plate_number: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    color: Optional[str] = None
    mileage: Optional[int] = None
    notes: Optional[str] = None

# ============== Staff Meal Schemas (BOSQICH 18) ==============
class StaffMealCreate(BaseModel):
    employee_id: int
    product_id: int
    quantity: float = Field(1.0, gt=0, description="Porsiya soni (0 dan katta bo'lishi shart)")
    notes: Optional[str] = None

class StaffMealInDB(BaseModel):
    id: int
    tenant_id: Optional[int] = None
    branch_id: Optional[int] = None
    employee_id: int
    product_id: int
    quantity: float
    cost_price: float
    total_cost: float
    notes: Optional[str] = None
    created_by: Optional[int] = None
    created_at: datetime
    employee_name: Optional[str] = None
    employee_position: Optional[str] = None
    product_name: Optional[str] = None

    class Config:
        from_attributes = True

class VehicleInDB(VehicleBase):
    id: int
    customer: Optional[CustomerInDB] = None
    created_at: datetime

    class Config:
        from_attributes = True

class ServiceOrderBase(BaseModel):
    vehicle_id: Optional[int] = None
    customer_id: Optional[int] = None
    description: str
    total_amount: float = 0.0
    intake_date: datetime
    notes: Optional[str] = None

class ServiceOrderCreate(ServiceOrderBase):
    pass

class ServiceOrderUpdate(BaseModel):
    status: Optional[str] = None
    total_amount: Optional[float] = None
    paid_amount: Optional[float] = None
    completion_date: Optional[datetime] = None
    notes: Optional[str] = None

class ServiceOrderInDB(ServiceOrderBase):
    id: int
    order_number: Optional[str] = None
    status: str
    paid_amount: float
    completion_date: Optional[datetime] = None
    created_at: datetime
    vehicle: Optional[VehicleInDB] = None

    class Config:
        from_attributes = True

# ============== Room Schemas ==============
class RoomBase(BaseModel):
    number: str
    name: Optional[str] = None
    floor: int = 1
    room_type: str = "standard"
    capacity: int = 2
    price_per_night: float = 0.0
    amenities: List[str] = []

class RoomCreate(RoomBase):
    pass

class RoomUpdate(BaseModel):
    name: Optional[str] = None
    floor: Optional[int] = None
    room_type: Optional[str] = None
    capacity: Optional[int] = None
    price_per_night: Optional[float] = None
    amenities: Optional[List[str]] = None
    status: Optional[str] = None
    is_active: Optional[bool] = None

class RoomInDB(RoomBase):
    id: int
    status: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class RoomBookingBase(BaseModel):
    room_id: int
    guest_name: str
    guest_phone: Optional[str] = None
    guest_count: int = 1
    check_in: str
    check_out: str
    nights: int = 1
    total_amount: float = 0.0
    customer_id: Optional[int] = None
    notes: Optional[str] = None

class RoomBookingCreate(RoomBookingBase):
    pass

class RoomBookingUpdate(BaseModel):
    status: Optional[str] = None
    paid_amount: Optional[float] = None
    notes: Optional[str] = None

class RoomBookingInDB(RoomBookingBase):
    id: int
    status: str
    paid_amount: float
    room: Optional[RoomInDB] = None
    created_at: datetime

    class Config:
        from_attributes = True

# ============== Loyalty Schemas ==============
class LoyaltyTransactionCreate(BaseModel):
    customer_id: int
    type: str
    points: int
    order_id: Optional[int] = None
    description: Optional[str] = None

class LoyaltyTransactionInDB(BaseModel):
    id: int
    customer_id: int
    order_id: Optional[int] = None
    type: str
    points: int
    description: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

# ============== Supplier Schemas ==============
class SupplierBase(BaseModel):
    name:               str
    contact_person:     Optional[str] = None
    phone:              Optional[str] = None
    email:              Optional[str] = None
    address:            Optional[str] = None
    tax_id:             Optional[str] = None    # INN
    notes:              Optional[str] = None
    # BOSQICH 24: B2B
    contract_number:    Optional[str] = None
    payment_delay_days: int = 0

class SupplierCreate(SupplierBase):
    pass

class SupplierUpdate(BaseModel):
    name:               Optional[str] = None
    contact_person:     Optional[str] = None
    phone:              Optional[str] = None
    email:              Optional[str] = None
    address:            Optional[str] = None
    tax_id:             Optional[str] = None
    is_active:          Optional[bool] = None
    notes:              Optional[str] = None
    contract_number:    Optional[str] = None
    payment_delay_days: Optional[int] = None

class SupplierInDB(SupplierBase):
    id:         int
    is_active:  bool
    tenant_id:  Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ============== BOSQICH 19: NASIYA / QARZ SCHEMALAR ==============

class DebtCreate(BaseModel):
    customer_id: int
    order_id: Optional[int] = None
    amount: float = Field(gt=0)
    due_date: Optional[date] = None
    notes: Optional[str] = None

class DebtPaymentCreate(BaseModel):
    amount: float = Field(gt=0)
    payment_method: str = "cash"
    notes: Optional[str] = None

class DebtPaymentInDB(BaseModel):
    id: int
    debt_id: int
    amount: float
    payment_method: str
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class DebtInDB(BaseModel):
    id: int
    customer_id: int
    order_id: Optional[int] = None
    amount: float
    paid_amount: float
    remaining: float
    due_date: Optional[date] = None
    status: str
    notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    customer: Optional[CustomerInDB] = None
    payments: List[DebtPaymentInDB] = []

    class Config:
        from_attributes = True

class DebtSummary(BaseModel):
    total_debtors: int
    total_debt: float
    total_overdue: float
    open_count: int
    partial_count: int


# ============== BOSQICH 19: QAYTARISH / ALMASHTIRISH SCHEMALAR ==============

class ReturnItemCreate(BaseModel):
    product_id: int
    order_item_id: Optional[int] = None
    quantity: float = Field(gt=0)
    unit_price: float = Field(gt=0)
    restore_to_inventory: bool = True

class ReturnCreate(BaseModel):
    order_id: Optional[int] = None
    customer_id: Optional[int] = None
    reason: str = "other"       # broken|dislike|expired|wrong_item|other
    refund_method: str = "cash" # cash|card|credit|exchange
    notes: Optional[str] = None
    items: List[ReturnItemCreate]

class ReturnItemInDB(BaseModel):
    id: int
    product_id: int
    order_item_id: Optional[int] = None
    quantity: float
    unit_price: float
    total: float
    restore_to_inventory: bool

    class Config:
        from_attributes = True

class ReturnInDB(BaseModel):
    id: int
    return_number: str
    order_id: Optional[int] = None
    customer_id: Optional[int] = None
    reason: str
    total_amount: float
    refund_method: str
    status: str
    exchange_order_id: Optional[int] = None
    notes: Optional[str] = None
    approved_at: Optional[datetime] = None
    created_at: datetime
    items: List[ReturnItemInDB] = []
    customer: Optional[CustomerInDB] = None

    class Config:
        from_attributes = True

class ReturnReport(BaseModel):
    total_returns: int
    total_amount: float
    by_reason: Dict[str, Any]


# ============== BOSQICH 22: Dorixona Schemas ==============

class ProductBatchBase(BaseModel):
    batch_number: str
    manufacturer: Optional[str] = None
    manufacture_date: Optional[date] = None
    expiry_date: date
    quantity: float = 0.0
    initial_quantity: float = 0.0
    cost_price: float = 0.0
    notes: Optional[str] = None

class ProductBatchCreate(ProductBatchBase):
    product_id: int
    branch_id: Optional[int] = None

class ProductBatchUpdate(BaseModel):
    batch_number: Optional[str] = None
    manufacturer: Optional[str] = None
    manufacture_date: Optional[date] = None
    expiry_date: Optional[date] = None
    quantity: Optional[float] = None
    cost_price: Optional[float] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None

class ProductBatchInDB(ProductBatchBase):
    id: int
    product_id: int
    tenant_id: Optional[int] = None
    branch_id: Optional[int] = None
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PrescriptionMedicine(BaseModel):
    name: str
    quantity: Optional[str] = None
    dosage: Optional[str] = None
    instructions: Optional[str] = None

class PrescriptionBase(BaseModel):
    patient_name: str
    patient_phone: Optional[str] = None
    doctor_name: Optional[str] = None
    clinic_name: Optional[str] = None
    prescription_date: date
    notes: Optional[str] = None
    medicines: List[PrescriptionMedicine] = []

class PrescriptionCreate(PrescriptionBase):
    branch_id: Optional[int] = None

class PrescriptionUpdate(BaseModel):
    patient_name: Optional[str] = None
    patient_phone: Optional[str] = None
    doctor_name: Optional[str] = None
    clinic_name: Optional[str] = None
    prescription_date: Optional[date] = None
    notes: Optional[str] = None
    medicines: Optional[List[PrescriptionMedicine]] = None
    is_dispensed: Optional[bool] = None
    image_url: Optional[str] = None

class PrescriptionInDB(PrescriptionBase):
    id: int
    tenant_id: Optional[int] = None
    branch_id: Optional[int] = None
    image_url: Optional[str] = None
    is_dispensed: bool
    dispensed_at: Optional[datetime] = None
    order_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class ExpiryReportItem(BaseModel):
    product_id: int
    product_name: str
    batch_number: Optional[str] = None
    expiry_date: date
    days_left: int
    quantity: float
    status: str  # expired | critical (<=7d) | warning (<=30d) | ok

    class Config:
        from_attributes = True


# ============== BOSQICH 23: Salon Schemas ==============

class StaffScheduleBase(BaseModel):
    weekday:    int = Field(ge=0, le=6)   # 0=Du ... 6=Ya
    work_start: str = "09:00"
    work_end:   str = "18:00"
    is_working: bool = True

class StaffScheduleCreate(StaffScheduleBase):
    employee_id: int

class StaffScheduleUpdate(BaseModel):
    work_start: Optional[str] = None
    work_end:   Optional[str] = None
    is_working: Optional[bool] = None

class StaffScheduleInDB(StaffScheduleBase):
    id: int
    employee_id: int
    tenant_id: Optional[int] = None

    class Config:
        from_attributes = True


class ClientPhotoCreate(BaseModel):
    customer_id:    Optional[int] = None
    appointment_id: Optional[int] = None
    photo_type:     str   # before | after
    service_name:   Optional[str] = None
    notes:          Optional[str] = None

class ClientPhotoInDB(ClientPhotoCreate):
    id: int
    tenant_id:  Optional[int] = None
    image_url:  str
    created_by: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AvailableSlot(BaseModel):
    time: str          # "09:00"
    available: bool


class SalonServiceSummary(BaseModel):
    service_name: str
    count: int
    total: float

class SalonClientHistory(BaseModel):
    customer_id:   int
    customer_name: str
    phone:         Optional[str] = None
    total_visits:  int
    total_spent:   float
    last_visit:    Optional[str] = None
    is_vip:        bool
    services:      List[SalonServiceSummary] = []
    favorite_employee: Optional[str] = None


class EmployeeCommission(BaseModel):
    employee_id:   int
    employee_name: str
    total_services: int
    total_revenue:  float
    commission_amount: float
    services: List[SalonServiceSummary] = []

class CommissionReport(BaseModel):
    period_start: str
    period_end:   str
    employees:    List[EmployeeCommission] = []
    grand_total:  float
    total_commission: float


# ============== BOSQICH 24: B2B Schemas ==============

class SupplierDebtSummary(BaseModel):
    supplier_id:     int
    supplier_name:   str
    phone:           Optional[str] = None
    total_purchases: float
    total_paid:      float
    total_returned:  float
    debt:            float
    overdue_amount:  float
    last_purchase:   Optional[str] = None


class PurchaseReceiptItemCreate(BaseModel):
    product_id: int
    quantity:   float = Field(gt=0)
    unit_price: float = Field(ge=0)
    brak_qty:   float = 0.0
    notes:      Optional[str] = None
    # BOSQICH 34: partiya (nullable)
    batch_number:     Optional[str]  = None
    expiry_date:      Optional[date] = None
    manufacture_date: Optional[date] = None

class PurchaseReceiptItemInDB(BaseModel):
    id:           int
    receipt_id:   int
    product_id:   int
    product_name: Optional[str] = None
    quantity:     float
    unit_price:   float
    total_price:  float
    brak_qty:     float
    accepted_qty: Optional[float] = None
    notes:        Optional[str] = None
    class Config:
        from_attributes = True

class PurchaseReceiptCreate(BaseModel):
    supplier_id:     int
    invoice_number:  Optional[str] = None
    receipt_date:    str
    discount_amount: float = 0.0
    notes:           Optional[str] = None
    items:           List[PurchaseReceiptItemCreate]

class PurchaseReceiptUpdate(BaseModel):
    invoice_number:  Optional[str] = None
    receipt_date:    Optional[str] = None
    discount_amount: Optional[float] = None
    notes:           Optional[str] = None

class PurchaseReceiptInDB(BaseModel):
    id:              int
    tenant_id:       Optional[int] = None
    supplier_id:     int
    supplier_name:   Optional[str] = None
    invoice_number:  Optional[str] = None
    receipt_date:    str
    total_amount:    float
    discount_amount: float
    net_amount:      float
    status:          str
    notes:           Optional[str] = None
    created_at:      datetime
    items:           List[PurchaseReceiptItemInDB] = []
    class Config:
        from_attributes = True


class SupplierPaymentCreate(BaseModel):
    supplier_id:    int
    receipt_id:     Optional[int] = None
    amount:         float = Field(gt=0)
    payment_date:   str   # YYYY-MM-DD
    payment_method: str = "cash"
    notes:          Optional[str] = None

class SupplierPaymentInDB(BaseModel):
    id:             int
    tenant_id:      Optional[int] = None
    supplier_id:    int
    receipt_id:     Optional[int] = None
    amount:         float
    payment_date:   Optional[date] = None
    payment_method: str = "cash"
    notes:          Optional[str] = None
    created_at:     datetime
    class Config:
        from_attributes = True


class SupplierReturnCreate(BaseModel):
    supplier_id: int
    product_id:  int
    quantity:    float = Field(gt=0)
    unit_price:  float = Field(ge=0)
    return_date: str
    reason:      Optional[str] = None
    notes:       Optional[str] = None

class SupplierReturnInDB(SupplierReturnCreate):
    id:           int
    tenant_id:    Optional[int] = None
    total_amount: float
    product_name: Optional[str] = None
    created_at:   datetime
    class Config:
        from_attributes = True


# ============== BOSQICH 25: Tovar Harakati Schemas ==============

# ── WriteOff (Utilizatsiya) ───────────────────────────────────────────────────

class WriteOffItemCreate(BaseModel):
    product_id: int
    quantity:   float = Field(gt=0)
    cost_price: float = Field(ge=0, default=0.0)
    notes:      Optional[str] = None

class WriteOffItemInDB(WriteOffItemCreate):
    id:          int
    write_off_id: int
    total_loss:  float
    product_name: Optional[str] = None
    class Config:
        from_attributes = True

class WriteOffCreate(BaseModel):
    reason:         str = "other"  # expired/damaged/theft/brak/other
    write_off_date: str
    notes:          Optional[str] = None
    items:          List[WriteOffItemCreate]

class WriteOffInDB(BaseModel):
    id:             int
    tenant_id:      Optional[int] = None
    act_number:     str
    reason:         str
    write_off_date: date
    total_loss:     float
    notes:          Optional[str] = None
    status:         str
    created_by:     Optional[int] = None
    confirmed_by:   Optional[int] = None
    confirmed_at:   Optional[datetime] = None
    created_at:     datetime
    items:          List[WriteOffItemInDB] = []
    class Config:
        from_attributes = True


# ── GoodsRegrade (Peresort) ───────────────────────────────────────────────────

class GoodsRegradeItemCreate(BaseModel):
    from_product_id: int
    to_product_id:   int
    quantity:        float = Field(gt=0)
    notes:           Optional[str] = None

class GoodsRegradeItemInDB(GoodsRegradeItemCreate):
    id:               int
    regrade_id:       int
    from_product_name: Optional[str] = None
    to_product_name:   Optional[str] = None
    class Config:
        from_attributes = True

class GoodsRegradeCreate(BaseModel):
    regrade_date: str
    notes:        Optional[str] = None
    items:        List[GoodsRegradeItemCreate]

class GoodsRegradeInDB(BaseModel):
    id:           int
    tenant_id:    Optional[int] = None
    regrade_date: date
    notes:        Optional[str] = None
    status:       str
    created_by:   Optional[int] = None
    confirmed_by: Optional[int] = None
    confirmed_at: Optional[datetime] = None
    created_at:   datetime
    items:        List[GoodsRegradeItemInDB] = []
    class Config:
        from_attributes = True


# ── InternalTransfer (Ichki ko'chirish) ──────────────────────────────────────

class InternalTransferItemCreate(BaseModel):
    product_id: int
    quantity:   float = Field(gt=0)
    cost_price: float = Field(ge=0, default=0.0)

class InternalTransferItemInDB(InternalTransferItemCreate):
    id:           int
    transfer_id:  int
    product_name: Optional[str] = None
    class Config:
        from_attributes = True

class InternalTransferCreate(BaseModel):
    from_branch_id: Optional[int] = None
    to_branch_id:   Optional[int] = None
    transfer_date:  str
    notes:          Optional[str] = None
    items:          List[InternalTransferItemCreate]

class InternalTransferInDB(BaseModel):
    id:               int
    tenant_id:        Optional[int] = None
    from_branch_id:   Optional[int] = None
    to_branch_id:     Optional[int] = None
    from_branch_name: Optional[str] = None
    to_branch_name:   Optional[str] = None
    transfer_date:    date
    notes:            Optional[str] = None
    status:           str
    created_by:       Optional[int] = None
    confirmed_by:     Optional[int] = None
    confirmed_at:     Optional[datetime] = None
    created_at:       datetime
    items:            List[InternalTransferItemInDB] = []
    class Config:
        from_attributes = True


# ── LossReport ───────────────────────────────────────────────────────────────

class LossReportItem(BaseModel):
    product_id:   int
    product_name: str
    reason:       str
    quantity:     float
    total_loss:   float
    date:         date

class LossReportSummary(BaseModel):
    period_from:   date
    period_to:     date
    total_loss:    float
    by_reason:     Dict[str, float]    # reason → summa
    items:         List[LossReportItem]


# ============== BOSQICH 26: Narx, Aksiya va Markirovka Schemas ==============

# ── MarkupPolicy ──────────────────────────────────────────────────────────────

class MarkupPolicyCreate(BaseModel):
    name:        str
    scope:       str = "global"    # global / category / product
    category_id: Optional[int] = None
    product_id:  Optional[int] = None
    markup_pct:  float = Field(ge=0, le=10000)
    min_price:   Optional[float] = None
    is_active:   bool = True

class MarkupPolicyUpdate(BaseModel):
    name:        Optional[str] = None
    markup_pct:  Optional[float] = None
    min_price:   Optional[float] = None
    is_active:   Optional[bool] = None

class MarkupPolicyInDB(MarkupPolicyCreate):
    id:            int
    tenant_id:     Optional[int] = None
    created_at:    datetime
    category_name: Optional[str] = None
    product_name:  Optional[str] = None
    class Config:
        from_attributes = True

class MarkupApplyRequest(BaseModel):
    policy_id:   int
    product_ids: Optional[List[int]] = None   # None = siyosat scopega mos hammasi


# ── BonusCard ─────────────────────────────────────────────────────────────────

class BonusCardCreate(BaseModel):
    customer_id: Optional[int] = None
    card_number: Optional[str] = None   # None = avtomatik
    earn_rate:   float = Field(ge=0, le=100, default=1.0)

class BonusCardUpdate(BaseModel):
    customer_id: Optional[int] = None
    earn_rate:   Optional[float] = None
    is_active:   Optional[bool] = None

class BonusCardInDB(BaseModel):
    id:            int
    tenant_id:     Optional[int] = None
    card_number:   str
    customer_id:   Optional[int] = None
    customer_name: Optional[str] = None
    balance:       float
    earn_rate:     float
    total_earned:  float
    total_spent:   float
    is_active:     bool
    created_at:    datetime
    class Config:
        from_attributes = True

class BonusEarnRequest(BaseModel):
    order_id:    Optional[int] = None
    amount:      float = Field(gt=0)     # xarid summasi (so'm), balл avtomatik hisoblanadi
    description: Optional[str] = None

class BonusSpendRequest(BaseModel):
    order_id:    Optional[int] = None
    amount:      float = Field(gt=0)     # sarflanadigan ball (so'm)
    description: Optional[str] = None

class BonusTransactionInDB(BaseModel):
    id:          int
    card_id:     int
    tx_type:     str
    amount:      float
    description: Optional[str] = None
    created_at:  datetime
    class Config:
        from_attributes = True


# ── ProductMark (Markirovka) ──────────────────────────────────────────────────

class ProductMarkCreate(BaseModel):
    product_id: int
    mark_code:  str
    mark_type:  str = "datamatrix"
    batch_id:   Optional[int] = None

class ProductMarkInDB(ProductMarkCreate):
    id:           int
    tenant_id:    Optional[int] = None
    status:       str
    product_name: Optional[str] = None
    order_id:     Optional[int] = None
    scanned_at:   Optional[datetime] = None
    created_at:   datetime
    class Config:
        from_attributes = True

class MarkScanRequest(BaseModel):
    mark_code: str
    order_id:  Optional[int] = None