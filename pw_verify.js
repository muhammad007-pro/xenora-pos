const { chromium } = require('playwright');
const TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiIsInVzZXJfaWQiOjEsImV4cCI6MTc4MTMzMDUyOCwidHlwZSI6ImFjY2VzcyJ9.U2Msej2XOKQZgVBubV9s5VKsFjB3iTUhDzjO5XsJ72M';
const SHOTS = 'D:/cafe/screenshots';
const fs = require('fs');
if (!fs.existsSync(SHOTS)) fs.mkdirSync(SHOTS, { recursive: true });

(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  await ctx.addInitScript(t => { localStorage.setItem('access_token', t); }, TOKEN);

  const page = await ctx.newPage();
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', e => errors.push(e.message));

  await page.goto('http://127.0.0.1:5500/app/profit.html');
  await page.waitForTimeout(3000);
  await page.screenshot({ path: SHOTS + '/01_initial.png' });

  const sg = await page.locator('#sg .sc').count();
  const sgText = await page.locator('#sg').innerText();
  console.log('KARTA_SONI=' + sg);
  console.log('SG_TEXT=' + sgText.replace(/\n/g,'|').substring(0,300));

  const bizType = await page.evaluate(() => window.bizType || 'UNDEFINED');
  console.log('BIZ_TYPE=' + bizType);

  const netCard = await page.locator('.sc.net').innerText().catch(() => 'TOPILMADI');
  console.log('NET_CARD=' + netCard.replace(/\n/g,' ').trim());

  await page.locator('.pb[data-p="week"]').click();
  await page.waitForTimeout(1500);
  await page.screenshot({ path: SHOTS + '/02_week.png' });
  const week_sg = await page.locator('#sg .sc').count();
  console.log('WEEK_KARTA=' + week_sg);

  await page.locator('.pb[data-p="month"]').click();
  await page.waitForTimeout(1500);
  await page.screenshot({ path: SHOTS + '/03_month_full.png', fullPage: true });

  const topBest = await page.locator('#topBest table').count();
  const topTitle = await page.locator('#topBestTitle').innerText();
  console.log('TOP_TABLE=' + (topBest>0?'OK':'YOQ'));
  console.log('TOP_TITLE=' + topTitle);

  const catTable = await page.locator('#byCat table').count();
  const catTitle = await page.locator('#byCatTitle').innerText();
  console.log('CAT_TABLE=' + (catTable>0?'OK':'YOQ'));
  console.log('CAT_TITLE=' + catTitle);

  const expVisible = await page.locator('.exp-form').isVisible();
  console.log('EXP_FORM=' + expVisible);

  // Probe: xarajat formasi to'ldirish
  await page.fill('#exName', 'Test ijara xarajati');
  await page.fill('#exAmount', '500000');
  await page.screenshot({ path: SHOTS + '/04_exp_filled.png' });

  // Probe: noto'g'ri davr parametri yo'q — bugun tugmasi
  await page.locator('.pb[data-p="today"]').click();
  await page.waitForTimeout(1000);
  await page.screenshot({ path: SHOTS + '/05_today.png' });

  console.log('JS_ERRORS=' + (errors.length ? errors.slice(0,5).join(' || ') : 'YOQ'));
  await browser.close();
  console.log('DONE');
})().catch(e => { console.error('FATAL:'+e.message); process.exit(1); });
