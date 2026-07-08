import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

const BASE = 'http://localhost:8000';
const API  = BASE + '/api/v1';
const DIR  = 'C:\\Users\\user\\AppData\\Local\\Temp\\branch_verify';

const log = (...a) => console.log('[verify]', ...a);

// 1. Login — token olish
const loginRes = await fetch(`${API}/auth/login`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  body: 'username=admin&password=admin123'
});
const { access_token: token } = await loginRes.json();
log('Token:', token.slice(0,30) + '...');

// 2. Branches ro'yxati
const brRes = await fetch(`${API}/branches/`, {
  headers: { Authorization: 'Bearer ' + token }
});
const branches = await brRes.json();
log('Branches:', JSON.stringify(branches));
writeFileSync(`${DIR}/branches.json`, JSON.stringify(branches, null, 2));

// 3. /auth/me dan user obyektini olish
const meRes = await fetch(`${API}/auth/me`, {
  headers: { Authorization: 'Bearer ' + token }
});
const userObj = await meRes.json();
log('User:', userObj.username, '| is_superuser:', userObj.is_superuser);

// 4. Browser — admin.html yuklab, switch qilish
const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();

// localhost da avval sahifa ochamiz (localStorage uchun same-origin kerak)
await page.goto(BASE + '/frontend/shared/login.html', { waitUntil: 'domcontentloaded' });
await page.evaluate(({ t, u }) => {
  localStorage.setItem('access_token', t);
  localStorage.setItem('user', JSON.stringify(u));
}, { t: token, u: userObj });

// Redirectni ushlaymiz
page.on('response', resp => {
  if (resp.status() >= 300 && resp.status() < 400) {
    log('REDIRECT:', resp.status(), resp.url(), '→', resp.headers()['location']);
  }
});

// admin.html ga o'tamiz
await page.goto(BASE + '/frontend/app/admin.html', { waitUntil: 'networkidle' });
log('Navigated to:', page.url());

// --- Skrinshot 1: Dashboard (login holat) ---
await page.waitForTimeout(1500);
log('Current URL after reload:', page.url());
await page.screenshot({ path: `${DIR}/01_dashboard.png`, fullPage: false });
log('SS1: dashboard');

// Branch switcher ko'rinadimi?
const switcherVisible = await page.locator('#branchSwitcher').isVisible();
log('Branch switcher visible:', switcherVisible);

// 4. Sidebar "Filiallar" bosamiz
const branchNav = page.locator('[data-page="branches"]');
const navVisible = await branchNav.isVisible();
log('Branches nav item visible:', navVisible);

if (navVisible) {
  await branchNav.click();
  await page.waitForTimeout(1200);
  await page.screenshot({ path: `${DIR}/02_branches_page.png` });
  log('SS2: branches page');

  // KPI kartalar yuklandimi?
  const total = await page.locator('#brTotalCount').textContent();
  const active = await page.locator('#brActiveCount').textContent();
  const defName = await page.locator('#brDefaultName').textContent();
  log('KPI — total:', total, 'active:', active, 'default:', defName);

  // Jadval satrlari
  const rows = await page.locator('#branchTbody tr').count();
  log('Table rows:', rows);
}

// 5. Branch switcher — click qilish (2 ta filial bo'lsa ko'rinadi)
if (switcherVisible) {
  await page.locator('#branchBtn').click();
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${DIR}/03_switcher_open.png` });
  log('SS3: switcher dropdown open');

  // Yunusobod filialini tanlash
  const ddItems = page.locator('#branchDDList .branch-dd-item');
  const itemCount = await ddItems.count();
  log('Dropdown items:', itemCount);

  if (itemCount > 0) {
    await ddItems.first().click();
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `${DIR}/04_switched.png` });
    log('SS4: after branch switch');

    // Token yangilandimi?
    const newToken = await page.evaluate(() => localStorage.getItem('access_token'));
    const parts = newToken.split('.');
    const pad = s => s + '='.repeat((4 - s.length % 4) % 4);
    const payload = JSON.parse(atob(pad(parts[1])));
    log('New JWT branch_id:', payload.branch_id);
    writeFileSync(`${DIR}/new_jwt_payload.json`, JSON.stringify(payload, null, 2));
  }
} else {
  log('Switcher not visible — 1 ta filial yoki yuklanmadi');
}

// 6. "Yangi filial" modali — ochish
const branchNavAfter = page.locator('[data-page="branches"]');
if (await branchNavAfter.isVisible()) {
  await branchNavAfter.click();
  await page.waitForTimeout(800);
  const addBtn = page.locator('button', { hasText: 'Yangi filial' });
  if (await addBtn.isVisible()) {
    await addBtn.click();
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${DIR}/05_modal_open.png` });
    log('SS5: new branch modal');

    // Modal ichida input bor?
    const nameInput = page.locator('#branchNameInput');
    const inputVisible = await nameInput.isVisible();
    log('Branch name input visible:', inputVisible);

    // Bekor tugmasi (branch modal specific)
    await page.locator('#branchModalOverlay').getByRole('button', { name: 'Bekor' }).click();
    await page.waitForTimeout(300);
  }
}

// 7. Sidebar da "Filiallar" badge
const badge = page.locator('#branchCountBadge');
const badgeText = await badge.textContent().catch(() => 'n/a');
const badgeVis = await badge.isVisible().catch(() => false);
log('Branch badge:', badgeText, 'visible:', badgeVis);

await page.screenshot({ path: `${DIR}/06_final.png` });
log('SS6: final state');

await browser.close();
log('Done. Screenshots:', DIR);
