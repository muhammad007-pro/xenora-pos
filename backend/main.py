from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os
import sys
import logging

# Windows konsoli (cp1251) emoji belgilarni chop eta olmasligi sababli,
# chiqishni UTF-8'ga majburan o'tkazamiz (aks holda print() lar xato beradi)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from config import settings
from database import init_db
from core.logger import setup_logger
from core.middleware import RequestIDMiddleware, LoggingMiddleware, ErrorHandlingMiddleware
from core.rate_limit import RateLimitMiddleware
from routers import (
    auth, user, role, category, product, table, order, order_item, payment,
    customer, reservation, report, analytics, inventory, kitchen,
    notification, discount, shift, settings as settings_router, upload,
    recipe, attendance, salary, cafe, employee, public, loyalty, telegram,
    purchase, promo, qr, device,
    appointment, service, membership, vehicle, hotel,
    modifier, combo, happy_hour,
    backup, daily_special, profit, branch, station, cash_register,
)
from routers import super_admin
from routers import waste
from routers import staff_meal
from routers import debt       # BOSQICH 19: nasiya/qarz
from routers import returns    # BOSQICH 19: qaytarish/almashtirish
from routers import barcodes          # BOSQICH 20: ko'p barcode
from routers import promotions        # BOSQICH 20: aksiya/chegirma
from routers import quick_sell        # BOSQICH 20: tez sotuv paneli
from routers import price_history     # BOSQICH 20: narx tarixi
from routers import audit             # Audit: xodimlar faoliyati jurnali
from routers import receipt_settings  # BOSQICH 20: chek sozlamasi
from routers import departments       # BOSQICH 21: bo'limlar tizimi
from routers import prescription      # BOSQICH 22: retsept arxivi (dorixona)
from routers import batches           # BOSQICH 22: partiya nazorati (dorixona)
from routers import staff_schedule    # BOSQICH 23: usta jadvali (salon)
from routers import client_photos     # BOSQICH 23: oldin/keyin foto (salon)
from routers import suppliers as suppliers_b2b    # BOSQICH 24: yetkazib beruvchilar
from routers import purchase_receipts             # BOSQICH 24: priyomka
from routers import supplier_payments             # BOSQICH 24: firmaga to'lov
from routers import supplier_returns              # BOSQICH 24: vozvrat postavshchikka
from routers import write_offs                    # BOSQICH 25: utilizatsiya/spisaniye
from routers import goods_regrade                 # BOSQICH 25: peresort
from routers import customer_returns_ext          # BOSQICH 25: kengaytirilgan vozvrat
from routers import internal_transfers            # BOSQICH 25: ichki ko'chirish
from routers import loss_report                   # BOSQICH 25: zarar hisoboti
from routers import markup_policy                 # BOSQICH 26: naценka siyosati
from routers import bonus_cards                   # BOSQICH 26: bonus karta
from routers import markirovka                    # BOSQICH 26: asl belgisi markirovka
from routers import reorder_settings              # BOSQICH 27: minimal qoldiq va avto-zakaz
from routers import ai_warehouse                  # AI-Ombor: rasmdan mahsulot o'qish (BOSQICH 1)
from websocket.routes import router as ws_router
from tasks.scheduler import start_scheduler, stop_scheduler

# Logger sozlash
setup_logger()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 Tizim ishga tushmoqda...")
    
    # Database ni yaratish
    init_db()
    
    # Schedulerni ishga tushirish
    start_scheduler()
    
    # Papkalarni yaratish
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs("static/receipts", exist_ok=True)
    os.makedirs("backup/auto", exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    
    logger.info("✅ Tizim tayyor!")
    
    yield
    
    # Shutdown
    logger.info("👋 Tizim to'xtatilmoqda...")
    stop_scheduler()

# FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# Middleware (oxirgisi birinchi bajariladi — LIFO tartib)
app.add_middleware(LoggingMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(ErrorHandlingMiddleware)
# Rate limit — CORS'dan OLDIN qo'shiladi → CORS eng tashqarida qoladi, 429 javobga
# ham CORS header qo'shiladi (brauzer XHR xatoni o'qiy oladi) va OPTIONS preflight ishlaydi.
app.add_middleware(RateLimitMiddleware)

# CORS (eng tashqi qatlam)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

# Frontend fayllari — absolut path bilan
_backend_dir  = os.path.dirname(os.path.abspath(__file__))
_frontend_dir = os.path.normpath(os.path.join(_backend_dir, "..", "frontend"))
if os.path.isdir(_frontend_dir):
    app.mount("/frontend", StaticFiles(directory=_frontend_dir), name="frontend")

# API Routerlar
api_prefix = settings.API_V1_STR

app.include_router(auth.router, prefix=f"{api_prefix}/auth", tags=["Authentication"])
app.include_router(user.router, prefix=f"{api_prefix}/users", tags=["Users"])
app.include_router(role.router, prefix=f"{api_prefix}/roles", tags=["Roles"])
app.include_router(category.router, prefix=f"{api_prefix}/categories", tags=["Categories"])
app.include_router(product.router, prefix=f"{api_prefix}/products", tags=["Products"])
app.include_router(table.router, prefix=f"{api_prefix}/tables", tags=["Tables"])
app.include_router(order.router,      prefix=f"{api_prefix}/orders",      tags=["Orders"])
app.include_router(order_item.router, prefix=f"{api_prefix}/order-items",  tags=["Order Items"])
app.include_router(payment.router,    prefix=f"{api_prefix}/payments",     tags=["Payments"])
app.include_router(customer.router, prefix=f"{api_prefix}/customers", tags=["Customers"])
app.include_router(reservation.router, prefix=f"{api_prefix}/reservations", tags=["Reservations"])
app.include_router(report.router, prefix=f"{api_prefix}/reports", tags=["Reports"])
app.include_router(analytics.router, prefix=f"{api_prefix}/analytics", tags=["Analytics"])
app.include_router(inventory.router, prefix=f"{api_prefix}/inventory", tags=["Inventory"])
app.include_router(kitchen.router, prefix=f"{api_prefix}/kitchen", tags=["Kitchen"])
app.include_router(station.router, prefix=f"{api_prefix}/stations", tags=["Stations"])
app.include_router(notification.router, prefix=f"{api_prefix}/notifications", tags=["Notifications"])
app.include_router(discount.router, prefix=f"{api_prefix}/discounts", tags=["Discounts"])
app.include_router(shift.router, prefix=f"{api_prefix}/shifts", tags=["Shifts"])
app.include_router(settings_router.router, prefix=f"{api_prefix}/settings", tags=["Settings"])
app.include_router(upload.router, prefix=f"{api_prefix}/upload", tags=["Upload"])

# Yangi routerlar
app.include_router(recipe.router, prefix=f"{api_prefix}/recipes", tags=["Recipes"])
app.include_router(attendance.router, prefix=f"{api_prefix}/attendance", tags=["Attendance"])
app.include_router(salary.router, prefix=f"{api_prefix}/salaries", tags=["Salaries"])
app.include_router(cafe.router, prefix=f"{api_prefix}/cafes", tags=["Cafes"])
app.include_router(employee.router, prefix=f"{api_prefix}/employees", tags=["Employees"])
app.include_router(public.router,  prefix="/public",                   tags=["Public QR Menu"])   # BOSQICH 5.1
app.include_router(loyalty.router,   prefix=f"{api_prefix}/loyalty",   tags=["Loyalty"])          # BOSQICH 5.2
app.include_router(telegram.router, prefix="/telegram",                 tags=["Telegram Bot"])     # BOSQICH 5.3

# Universal biznes routerlari (BOSQICH 4)
app.include_router(purchase.router,    prefix=f"{api_prefix}/purchases",    tags=["Purchases"])
app.include_router(promo.router,       prefix=f"{api_prefix}/promos",       tags=["Promos"])
app.include_router(qr.router,          prefix=f"{api_prefix}/qr",           tags=["QR"])
app.include_router(device.router,      prefix=f"{api_prefix}/devices",      tags=["Devices"])
app.include_router(appointment.router, prefix=f"{api_prefix}/appointments", tags=["Appointments"])
app.include_router(service.router,     prefix=f"{api_prefix}/services",     tags=["Services"])
app.include_router(membership.router,  prefix=f"{api_prefix}/memberships",  tags=["Memberships"])
app.include_router(vehicle.router,     prefix=f"{api_prefix}/vehicles",     tags=["Vehicles"])
app.include_router(hotel.router,       prefix=f"{api_prefix}/rooms",         tags=["Hotel"])

# Pro funksiyalar (BOSQICH 9)
app.include_router(modifier.router,    prefix=f"{api_prefix}/modifiers",    tags=["Modifiers"])
app.include_router(combo.router,       prefix=f"{api_prefix}/combos",       tags=["Combos"])
app.include_router(happy_hour.router,  prefix=f"{api_prefix}/happy-hours",  tags=["Happy Hours"])

# Admin utility routerlar (BOSQICH 13)
app.include_router(backup.router,       prefix=f"{api_prefix}/backups",       tags=["Backups"])

# Restoran/Kafe maxsus (BOSQICH 14)
app.include_router(daily_special.router, prefix=f"{api_prefix}/daily-specials", tags=["Daily Specials"])

# Foyda tahlili — tan narx va sof foyda
app.include_router(profit.router, prefix=f"{api_prefix}/profit", tags=["Profit Analysis"])

# Filial tizimi (BOSQICH 15)
app.include_router(branch.router, prefix=f"{api_prefix}/branches", tags=["Branches"])
app.include_router(cash_register.router, prefix=f"{api_prefix}/cash-registers", tags=["Cash Registers"])

# Super Admin — faqat is_superuser=True
app.include_router(super_admin.router,  prefix=f"{api_prefix}/super-admin",  tags=["Super Admin"])
app.include_router(waste.router,        prefix=f"{api_prefix}/waste",        tags=["Waste / Poteriya"])   # BOSQICH 17
app.include_router(staff_meal.router,   prefix=f"{api_prefix}/staff-meals",  tags=["Staff Meals"])        # BOSQICH 18
app.include_router(debt.router,             prefix=f"{api_prefix}/debts",            tags=["Debts / Nasiya"])
app.include_router(returns.router,          prefix=f"{api_prefix}/returns",          tags=["Returns / Qaytarish"])
app.include_router(barcodes.router,         prefix=f"{api_prefix}/barcodes",         tags=["Barcodes / Ko'p barcode"])
app.include_router(promotions.router,       prefix=f"{api_prefix}/promotions",       tags=["Promotions / Aksiya"])
app.include_router(quick_sell.router,       prefix=f"{api_prefix}/quick-sell",       tags=["QuickSell / Tez sotuv"])
app.include_router(price_history.router,    prefix=f"{api_prefix}/price-history",    tags=["PriceHistory / Narx tarixi"])
app.include_router(audit.router,            prefix=f"{api_prefix}/audit-logs",       tags=["Audit / Xodimlar faoliyati"])
app.include_router(receipt_settings.router, prefix=f"{api_prefix}/receipt-settings", tags=["ReceiptSettings / Chek"])
app.include_router(departments.router,      prefix=f"{api_prefix}/departments",      tags=["Departments / Bo'limlar"])  # BOSQICH 21
app.include_router(prescription.router,     prefix=f"{api_prefix}/prescriptions",     tags=["Prescriptions / Retsept"])  # BOSQICH 22
app.include_router(batches.router,          prefix=f"{api_prefix}/batches",           tags=["Batches / Partiya"])        # BOSQICH 22
app.include_router(staff_schedule.router,   prefix=f"{api_prefix}/staff-schedules",   tags=["Staff Schedule / Usta Jadvali"])  # BOSQICH 23
app.include_router(client_photos.router,    prefix=f"{api_prefix}/client-photos",     tags=["Client Photos / Foto"])     # BOSQICH 23
app.include_router(suppliers_b2b.router,    prefix=f"{api_prefix}/suppliers-b2b",     tags=["Suppliers B2B / Yetkazib beruvchilar"])  # BOSQICH 24
app.include_router(purchase_receipts.router,prefix=f"{api_prefix}/purchase-receipts", tags=["Purchase Receipts / Priyomka"])  # BOSQICH 24
app.include_router(supplier_payments.router,prefix=f"{api_prefix}/supplier-payments", tags=["Supplier Payments / To'lov"])    # BOSQICH 24
app.include_router(supplier_returns.router, prefix=f"{api_prefix}/supplier-returns",  tags=["Supplier Returns / Vozvrat"])    # BOSQICH 24
app.include_router(write_offs.router,           prefix=f"{api_prefix}/write-offs",          tags=["Write Offs / Utilizatsiya"])        # BOSQICH 25
app.include_router(goods_regrade.router,        prefix=f"{api_prefix}/goods-regrades",      tags=["Goods Regrade / Peresort"])         # BOSQICH 25
app.include_router(customer_returns_ext.router, prefix=f"{api_prefix}/returns-ext",         tags=["Customer Returns Ext / Vozvrat+"])  # BOSQICH 25
app.include_router(internal_transfers.router,   prefix=f"{api_prefix}/internal-transfers",  tags=["Internal Transfers / Ko'chirish"])  # BOSQICH 25
app.include_router(loss_report.router,          prefix=f"{api_prefix}/loss-report",         tags=["Loss Report / Zarar Hisoboti"])     # BOSQICH 25
app.include_router(markup_policy.router,        prefix=f"{api_prefix}/markup-policies",     tags=["Markup Policy / Naценka Siyosati"])  # BOSQICH 26
app.include_router(bonus_cards.router,          prefix=f"{api_prefix}/bonus-cards",         tags=["Bonus Cards / Bonus Karta"])         # BOSQICH 26
app.include_router(markirovka.router,           prefix=f"{api_prefix}/markirovka",          tags=["Markirovka / Asl Belgisi"])          # BOSQICH 26
app.include_router(reorder_settings.router,     prefix=f"{api_prefix}/reorder-settings",    tags=["Reorder Settings / Avto-Zakaz"])     # BOSQICH 27
app.include_router(ai_warehouse.router,         prefix=f"{api_prefix}/ai-warehouse",        tags=["AI-Ombor / Rasmdan mahsulot"])       # AI-Ombor BOSQICH 1

# WebSocket
app.include_router(ws_router, prefix="/ws", tags=["WebSocket"])

@app.get("/")
async def root():
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "running",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    from sqlalchemy import text
    from database import engine
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        db_status = "disconnected"
    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "database": db_status,
        "version": settings.VERSION,
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )