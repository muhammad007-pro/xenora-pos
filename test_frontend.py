"""Frontend panel Playwright testi"""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

FRONTEND = "http://localhost:5500"
SHOTS    = Path("D:/cafe/backend/logs/screenshots")
SHOTS.mkdir(exist_ok=True)

errors  = []
passed  = []
warns   = []

async def ss(page, name):
    await page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=False)

async def login(page):
    """shared/login.html orqali login qilish"""
    await page.goto(f"{FRONTEND}/shared/login.html", wait_until="domcontentloaded", timeout=12000)
    await page.wait_for_timeout(800)
    await page.fill("#username", "admin")
    await page.fill("#password", "admin123")
    await ss(page, "01_login_filled")
    await page.click("#loginBtn")
    # Redirect kutish — login.html dan chiqishi kerak
    await page.wait_for_function("window.location.href.indexOf('login.html') === -1", timeout=8000)
    await page.wait_for_timeout(1000)
    await ss(page, "02_after_login")
    return page.url

async def test_page(page, name, url, checks=None):
    """Sahifani yuklash va ixtiyoriy DOM tekshiruvi"""
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=12000)
        await page.wait_for_timeout(1200)
        cur = page.url
        if "login.html" in cur:
            errors.append(f"[ERR] {name}: auth redirect - login sahifasiga o'tdi")
            await ss(page, f"err_{name}")
            return False
        await ss(page, name)
        msg = f"[OK]  {name} yuklandi"
        if checks:
            for sel, desc in checks:
                cnt = await page.locator(sel).count()
                msg += f" | {desc}={cnt}"
        passed.append(msg)
        return True
    except Exception as e:
        errors.append(f"[ERR] {name}: {str(e)[:120]}")
        return False

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()

        # Console xatolarini yig'ish
        console_errs = []
        page.on("console", lambda m: console_errs.append(m.text[:200]) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errs.append(f"pageerror: {str(e)[:160]}"))
        page.on("requestfailed", lambda req: console_errs.append(f"reqfail [{req.failure}]: {req.url[:200]}"))

        def on_response(resp):
            if resp.status in (404, 422, 500):
                console_errs.append(f"HTTP {resp.status}: {resp.url[:200]}")
        page.on("response", on_response)

        # --- LOGIN ---
        print("1. Login...")
        try:
            url_after = await login(page)
            passed.append(f"[OK]  Login muvaffaqiyatli -> {url_after}")
        except Exception as e:
            errors.append(f"[ERR] Login: {e}")
            await ss(page, "err_login")
            await browser.close()
            _report(console_errs)
            return

        # --- APP SAHIFALARI ---
        print("2. Admin dashboard...")
        await test_page(page, "03_admin",    f"{FRONTEND}/app/admin.html",
            [(".stat-card, .kpi-card, [class*='stat']", "stat-cards")])

        print("3. POS...")
        await test_page(page, "04_pos",       f"{FRONTEND}/app/pos.html",
            [(".category-btn, .category-item, [class*='categ']", "kategoriya"),
             (".product-card, [class*='product-card']", "mahsulot")])

        print("4. Waiter/Orders...")
        await test_page(page, "05_waiter",    f"{FRONTEND}/app/waiter.html",
            [(".order-card, .table-card, [class*='order'], [class*='table-item']", "stol/order")])

        print("5. Kitchen KDS...")
        await test_page(page, "06_kitchen",   f"{FRONTEND}/app/kitchen.html",
            [(".kitchen-card, .order-ticket, [class*='kitchen']", "kitchen-card")])

        print("6. Customers...")
        await test_page(page, "07_customers", f"{FRONTEND}/app/customers.html",
            [("table, .data-table, [class*='table']", "jadval")])

        print("7. Inventory...")
        await test_page(page, "08_inventory", f"{FRONTEND}/app/inventory.html",
            [("table, [class*='table']", "jadval")])

        print("8. Analytics...")
        await test_page(page, "09_analytics", f"{FRONTEND}/app/analytics.html",
            [("canvas, [class*='chart'], .chart-container", "chart")])

        print("9. Reports...")
        await test_page(page, "10_report",    f"{FRONTEND}/app/report.html")

        print("10. Employees...")
        await test_page(page, "11_employees", f"{FRONTEND}/app/employees.html")

        print("11. Tables...")
        await test_page(page, "12_tables",    f"{FRONTEND}/app/tables.html",
            [(".table-card, [class*='table-card'], [class*='floor']", "stol")])

        print("12. Settings...")
        await test_page(page, "13_settings",  f"{FRONTEND}/app/settings.html")

        print("13. Appointments (salon/spa)...")
        await test_page(page, "14_appointments", f"{FRONTEND}/app/appointments.html")

        print("14. Vehicles (avtoservis)...")
        await test_page(page, "15_vehicles",  f"{FRONTEND}/app/vehicles.html")

        print("15. Reservations (mehmonxona)...")
        await test_page(page, "16_reservations", f"{FRONTEND}/app/reservations.html")

        # --- FINAL: admin da console xatolar ---
        print("16. Admin final (console xatolar)...")
        await page.goto(f"{FRONTEND}/app/admin.html", wait_until="domcontentloaded", timeout=12000)
        await page.wait_for_timeout(2000)
        await ss(page, "17_admin_final")

        await browser.close()
        _report(console_errs)

def _report(console_errs):
    print("\n" + "=" * 65)
    print(f"NATIJA: {len(passed)} muvaffaqiyatli, {len(errors)} xato")
    print("=" * 65)
    for m in passed:  print(m)
    print("-" * 65)
    for m in errors:  print(m)
    if console_errs:
        print("-- Console xatolar --")
        for c in console_errs[:20]:
            print(f"  [CONSOLE] {c}")
    print(f"\nScreenshotlar: D:/cafe/backend/logs/screenshots/")

asyncio.run(run())
