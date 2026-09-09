/**
 * KIRISH EKRANI — yopiq do'kon xabari EKRANDA to'g'ri ko'rinsinmi.
 *
 * NUQSON (2026-09-09, jonli chiqdi): backend 403 javobini ICHMA-ICH qaytarardi —
 *
 *     {"detail": {"code": "STORE_INACTIVE", "detail": "Do'kon vaqtincha..."}}
 *
 * chunki `HTTPException(detail=<obyekt>)` ni FastAPI yana `{"detail": ...}`
 * ichiga o'raydi. `login.html:636` esa `data.detail` ni MATN deb kutadi:
 *
 *     throw new Error(data.detail || 'Do\'kon topilmadi');
 *
 * Natijada kassir ekranida "[object Object]" chiqardi. Backend testlari 403 va
 * `code` ni tekshirardi-yu, EKRANGA nima chiqishini hech kim sinamagan edi —
 * shuning uchun nuqson deploygacha yetib bordi. Bu fayl aynan o'sha bo'shliqni
 * yopadi: HTTP javobdan EKRANDAGI MATNgacha.
 *
 * Ishga tushirish:  node frontend/tests/test_blocked_store_login_message.mjs
 */
import { chromium } from 'playwright';
import { createServer } from 'http';
import { readFile } from 'fs/promises';
import { resolve, extname, join } from 'path';

const ROOT = resolve('frontend');
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript',
               '.css': 'text/css', '.json': 'application/json' };
const server = createServer(async (req, res) => {
  try {
    const p = join(ROOT, decodeURIComponent(req.url.split('?')[0]));
    const body = await readFile(p);
    res.writeHead(200, { 'Content-Type': MIME[extname(p)] || 'application/octet-stream' });
    res.end(body);
  } catch { res.writeHead(404); res.end('not found'); }
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const PAGE = `http://127.0.0.1:${server.address().port}/shared/login.html`;

let pass = 0, fail = 0;
const check = (name, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  ok ? pass++ : fail++;
  console.log(`[${ok ? 'OK  ' : 'FAIL'}] ${name}: ${JSON.stringify(got)} (kutilgan ${JSON.stringify(want)})`);
};

const XABAR = "Do'kon vaqtincha faol emas. Bog'laning: +998 94 997 47 70";

// Serverning HAQIQIY javoblari (prodda o'lchangan, 2026-09-09)
const JAVOBLAR = {
  '100.200.4': { status: 403, body: { detail: XABAR, code: 'STORE_INACTIVE' } },
  '100.200.5': { status: 200, body: { id: 26, name: 'FAZZA PERFUM', business_type: 'store' } },
  '100.200.99': { status: 404, body: { detail: "Do'kon topilmadi" } },
};

const browser = await chromium.launch({ headless: true });

/** Sahifani ochadi, resolve-code javobini stublaydi. */
async function ochish(javoblar = JAVOBLAR) {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.route('**/api/v1/**', async (route) => {
    const u = new URL(route.request().url());
    if (u.pathname.endsWith('/auth/resolve-code')) {
      const kod = u.searchParams.get('code');
      const j = javoblar[kod] || { status: 404, body: { detail: "Do'kon topilmadi" } };
      return route.fulfill({ status: j.status, contentType: 'application/json',
                             body: JSON.stringify(j.body) });
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  });
  await page.goto(PAGE, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof window.fetch === 'function');
  await page.waitForTimeout(300);
  return { page, ctx };
}

/** Kodni kiritib "davom etish" ni bosadi, ekrandagi xato matnini qaytaradi. */
async function kodKirit(page, kod) {
  await page.fill('#storeCodeInput', kod);
  await page.click('#resolveBtn');
  await page.waitForTimeout(600);
  return {
    xato: await page.$eval('#codeError', el => (el.style.display === 'none' ? '' : el.textContent)),
    kodEkrani: await page.$eval('#stepCode', el => el.style.display !== 'none'),
    parolEkrani: await page.$eval('#stepAuth', el => el.style.display !== 'none'),
    dokonNomi: await page.$eval('#storeName', el => el.textContent),
  };
}

// ══════════════════════════════════════════════════════════════════════════════
// 1) YOPIQ DO'KON — ekranda TO'G'RI MATN, "[object Object]" EMAS
// ══════════════════════════════════════════════════════════════════════════════
{
  const { page, ctx } = await ochish();
  const r = await kodKirit(page, '100.200.4');

  check('1_ekranda_TOGRI_matn', r.xato, XABAR);
  check('1_object_Object_YOQ', r.xato.includes('[object Object]'), false);
  check('1_telefon_korinadi', r.xato.includes('+998 94 997 47 70'), true);
  check('1_kod_ekranida_qoladi', r.kodEkrani, true);
  check('1_parol_ekraniga_otmaydi', r.parolEkrani, false);
  await ctx.close();
}

// ══════════════════════════════════════════════════════════════════════════════
// 2) REGRESSIYA QO'RIQCHISI — eski ICHMA-ICH shakl qaytsa, test YIQILSIN
// ══════════════════════════════════════════════════════════════════════════════
{
  // Backend yana `{"detail": {...}}` qaytara boshlasa ekranda "[object Object]"
  // chiqadi. Shu holatni ataylab modellashtiramiz va uni RAD ETAMIZ.
  const eski = {
    '100.200.4': {
      status: 403,
      body: { detail: { code: 'STORE_INACTIVE', detail: XABAR } },   // ← eski buzuq shakl
    },
  };
  const { page, ctx } = await ochish(eski);
  const r = await kodKirit(page, '100.200.4');

  // Bu — nuqsonning ISBOTI: ichma-ich shakl aynan shunga olib keladi.
  check('2_ichma_ich_shakl_object_Object_beradi', r.xato, '[object Object]');
  check('2_shuning_uchun_backend_TEKIS_qaytaradi', r.xato !== XABAR, true);
  await ctx.close();
}

// ══════════════════════════════════════════════════════════════════════════════
// 3) BOSHQA YO'LLAR buzilmagan
// ══════════════════════════════════════════════════════════════════════════════
{
  const { page, ctx } = await ochish();

  // Faol do'kon → parol ekraniga o'tadi, nomi ko'rinadi
  const faol = await kodKirit(page, '100.200.5');
  check('3_faol_dokon_xatosiz', faol.xato, '');
  check('3_faol_dokon_parol_ekrani', faol.parolEkrani, true);
  check('3_faol_dokon_nomi', faol.dokonNomi, 'FAZZA PERFUM');
  await ctx.close();
}
{
  const { page, ctx } = await ochish();
  // Mavjud bo'lmagan kod → eski matn
  const yoq = await kodKirit(page, '100.200.99');
  check('3_yoq_kod_matni', yoq.xato, "Do'kon topilmadi");
  check('3_yoq_kod_ekranda_qoladi', yoq.kodEkrani, true);
  await ctx.close();
}

await browser.close();
server.close();
console.log(`\n${pass} o'tdi, ${fail} yiqildi`);
process.exit(fail ? 1 : 0);
