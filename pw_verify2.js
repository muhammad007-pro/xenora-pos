const { chromium } = require('playwright');
const TOKEN = process.env.PW_TOKEN;
const SHOTS = 'D:/cafe/screenshots';
const fs = require('fs');
if (!fs.existsSync(SHOTS)) fs.mkdirSync(SHOTS, { recursive: true });

(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  await ctx.addInitScript(t => { localStorage.setItem('access_token', t); }, TOKEN);

  const page = await ctx.newPage();
  const errors = [], netReqs = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', e => errors.push(e.message));
  page.on('response', r => { if (r.url().includes('/profit/')) netReqs.push(r.status()+' '+r.url().split('?')[0].split('/').pop()); });

  // ── 1. Sahifani och, .sc.net paydo bo'lguncha kut ────────────────────────
  await page.goto('http://127.0.0.1:5500/app/profit.html');
  try {
    await page.waitForSelector('#sg .sc.net', { timeout: 10000 });
    console.log('INITIAL_LOAD=OK');
  } catch {
    console.log('INITIAL_LOAD=TIMEOUT (10s ichida kartalar chiqmadi)');
  }
  await page.screenshot({ path: SHOTS + '/01_today.png' });

  const sg_count  = await page.locator('#sg .sc').count();
  const biz_type  = await page.evaluate(() => window._bizType || 'ANIQLANMADI');
  const net_text  = await page.locator('.sc.net .sv').innerText().catch(() => '—');
  const net_label = await page.locator('.sc.net .sl').innerText().catch(() => '—');
  const all_labels= await page.locator('#sg .sl').allInnerTexts();
  console.log('TODAY_KARTA_SONI=' + sg_count);
  console.log('BIZ_TYPE=' + biz_type);
  console.log('NET_LABEL=' + net_label);
  console.log('NET_VALUE=' + net_text);
  console.log('KARTA_SARLAVHALAR=' + all_labels.join(' | '));
  console.log('API_REQUESTS=' + netReqs.join(', '));

  // ── 2. Haftalik davr ──────────────────────────────────────────────────────
  await page.locator('.pb[data-p="week"]').click();
  await page.waitForSelector('#sg .sc.net', { timeout: 8000 }).catch(()=>{});
  await page.screenshot({ path: SHOTS + '/02_week.png' });
  const week_count  = await page.locator('#sg .sc').count();
  const week_labels = await page.locator('#sg .sl').allInnerTexts();
  console.log('WEEK_KARTA_SONI=' + week_count);
  console.log('WEEK_SARLAVHALAR=' + week_labels.join(' | '));

  // ── 3. Oylik davr + to'liq sahifa skrinshot ───────────────────────────────
  await page.locator('.pb[data-p="month"]').click();
  await page.waitForSelector('#sg .sc.net', { timeout: 8000 }).catch(()=>{});
  await page.screenshot({ path: SHOTS + '/03_month_top.png' });
  await page.screenshot({ path: SHOTS + '/03_month_full.png', fullPage: true });

  // ── 4. TOP jadval ─────────────────────────────────────────────────────────
  const top_title   = await page.locator('#topBestTitle').innerText();
  const worst_title = await page.locator('#topWorstTitle').innerText();
  const top_rows    = await page.locator('#topBest tbody tr').count();
  const top_headers = await page.locator('#topBest thead th').allInnerTexts();
  console.log('TOP_TITLE=' + top_title);
  console.log('WORST_TITLE=' + worst_title);
  console.log('TOP_ROWS=' + top_rows);
  console.log('TOP_USTUNLAR=' + top_headers.join(' | '));

  // ── 5. Kategoriya jadvali ─────────────────────────────────────────────────
  const cat_title   = await page.locator('#byCatTitle').innerText();
  const cat_rows    = await page.locator('#byCat tbody tr').count();
  const cat_headers = await page.locator('#byCat thead th').allInnerTexts();
  console.log('CAT_TITLE=' + cat_title);
  console.log('CAT_ROWS=' + cat_rows);
  console.log('CAT_USTUNLAR=' + cat_headers.join(' | '));

  // ── 6. Grafik (canvas) ────────────────────────────────────────────────────
  const chart_ok = await page.locator('#chTimeline').isVisible();
  console.log('CHART=' + (chart_ok ? 'OK' : 'YOQ'));

  // ── 7. Xarajatlar bo'limi ─────────────────────────────────────────────────
  await page.evaluate(() => document.querySelector('.exp-form').scrollIntoView());
  await page.screenshot({ path: SHOTS + '/04_expenses.png' });
  const exp_visible = await page.locator('.exp-form').isVisible();
  console.log('EXP_FORM=' + exp_visible);

  // ── PROBE 1: Xarajat formasiga noto'g'ri ma'lumot (summa=0) ─────────────
  await page.fill('#exName', 'Test');
  await page.fill('#exAmount', '0');
  await page.locator('#exBtn').click();
  await page.waitForTimeout(500);
  const alertProbe = await page.evaluate(() => {
    // alert chaqirilganini tekshirish
    return document.body.innerText.includes('Nomi va summa') ? 'ALERT_CHIQDI' : 'ALERT_CHIQMADI';
  });
  console.log('PROBE_EMPTY_EXPENSE=' + alertProbe);

  // ── PROBE 2: Davr tugmalarini tez bosish (race condition) ─────────────────
  await page.locator('.pb[data-p="today"]').click();
  await page.locator('.pb[data-p="week"]').click();
  await page.locator('.pb[data-p="month"]').click();
  await page.waitForSelector('#sg .sc.net', { timeout: 8000 }).catch(()=>{});
  const after_race = await page.locator('#sg .sc').count();
  console.log('PROBE_RAPID_CLICK_KARTALAR=' + after_race);
  await page.screenshot({ path: SHOTS + '/05_after_race.png' });

  // ── 8. JS xatolari ────────────────────────────────────────────────────────
  console.log('JS_ERRORS=' + (errors.length ? errors.slice(0,5).join(' || ') : 'YOQ'));
  await browser.close();
  console.log('DONE');
})().catch(e => { console.error('FATAL: ' + e.message); process.exit(1); });
