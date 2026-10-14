/* ═══════════════════════════════════════════════════════════════════════════
   PRINTER SOZLAMASI — JIMGINA "USB" GA TUSHMASLIK (POS + admin)
   ───────────────────────────────────────────────────────────────────────────
   MUAMMO (2026-10): POS sozlamani faqat sahifa ochilganda bir marta o'qirdi.
   So'rov yiqilsa (internet, server qayta ishga tushishi) yoki `{success:false}`
   qaytsa — xato JIMGINA yutilib, standart `print_type: 'usb'` va bo'sh printer
   nomi qolardi. Electron esa bo'sh nom bilan WINDOWS STANDART printeriga
   yuborardi — u etiketka printeri bo'lishi mumkin (chek etiketka rulonida).

   QOIDA:
     • Sozlama FAQAT muvaffaqiyatli javobdan olinadi (server sozlamasi bo'lmasa
       ham o'zining standartini qaytaradi — demak javob har doim ANIQ tanlov).
     • Oxirgi muvaffaqiyatli sozlama do'kon bo'yicha keshlanadi (localStorage)
       — internet yo'q holatda ochilgan POS ham to'g'ri printerga chiqaradi.
     • Na serverdan, na keshdan sozlama yo'q → chop etish TO'XTAYDI, kassirga
       ogohlantirish + "Qayta urinish". Jimgina USB'ga O'TILMAYDI.
     • Har chop etishdan oldin sozlama eskirgan bo'lsa (5 daqiqa) — qisqa
       kutish bilan yangilanadi (admin printer o'zgartirsa POS'ni qayta
       ochish shart emas); yangilash yiqilsa mavjud ANIQ sozlama qoladi.
   ═══════════════════════════════════════════════════════════════════════════ */

const CACHE_PREFIX = 'xenora_print_cfg_v1:';
export const PRINT_CFG_MAX_AGE_MS = 5 * 60 * 1000;

function tenantKey() {
  try {
    const u = JSON.parse(localStorage.getItem('user') || '{}');
    if (u && u.tenant_id != null) return String(u.tenant_id);
  } catch { /* buzuq user */ }
  try {
    const t = localStorage.getItem('access_token') || '';
    const p = JSON.parse(atob(t.split('.')[1] || ''));
    if (p && p.tenant_id != null) return String(p.tenant_id);
  } catch { /* token yo'q */ }
  return 'default';
}

/** Javob muvaffaqiyatlimi va undan ma'lumot. api.js o'rami ({success,data})
 *  ham, xom obyekt ham qabul qilinadi; `success:false` — XATO (ilgari o'ram
 *  obyektning o'zi sozlama deb olinardi). */
function unwrap(res) {
  if (!res || typeof res !== 'object') return null;
  if ('success' in res) return res.success && res.data && typeof res.data === 'object' ? res.data : null;
  if ('detail' in res && Object.keys(res).length <= 2) return null;   // xom FastAPI xatosi
  return res;
}

/**
 * fetchStatus()  → /settings/printer/status javobi (o'ralgan yoki xom)
 * fetchReceipt() → /receipt-settings/ javobi
 */
export function createPrintConfig({ fetchStatus, fetchReceipt, timeoutMs = 4000 }) {
  let cfg = null;          // { printerName, printType, printerIp, printerPort, fontSize, paperWidth, receipt, status }
  let loadedAt = 0;
  let source = 'none';     // 'server' | 'cache' | 'none'
  let inflight = null;

  const withTimeout = (p) => Promise.race([
    Promise.resolve().then(p),
    new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), timeoutMs)),
  ]);

  function readCache() {
    try {
      const c = JSON.parse(localStorage.getItem(CACHE_PREFIX + tenantKey()) || 'null');
      return c && c.cfg ? c : null;
    } catch { return null; }
  }
  function writeCache() {
    try { localStorage.setItem(CACHE_PREFIX + tenantKey(), JSON.stringify({ cfg, at: loadedAt })); } catch { /* to'la */ }
  }

  function build(status, rec) {
    return {
      printerName: typeof status.printer_name === 'string' ? status.printer_name : '',
      printType:   rec.print_type || 'usb',     // server javobidagi ANIQ qiymat (u o'z standartini beradi)
      printerIp:   rec.printer_ip || null,
      printerPort: rec.printer_port || null,
      fontSize:    rec.font_size || 'normal',
      paperWidth:  rec.paper_width || null,
      receipt:     rec,
      status,
    };
  }

  async function load() {
    if (inflight) return inflight;
    inflight = (async () => {
      try {
        const [s, r] = await Promise.all([withTimeout(fetchStatus), withTimeout(fetchReceipt)]);
        const status = unwrap(s), rec = unwrap(r);
        if (!status || !rec) throw new Error('printer sozlamasi javobi xato');
        cfg = build(status, rec);
        loadedAt = Date.now();
        source = 'server';
        writeCache();
        return true;
      } catch (e) {
        if (!cfg) {
          const c = readCache();
          if (c) { cfg = c.cfg; loadedAt = c.at || 0; source = 'cache'; }
        }
        return false;
      } finally {
        inflight = null;
      }
    })();
    return inflight;
  }

  /** Chop etishdan oldin: sozlama yo'q → yuklash; eskirgan → yangilashga urinish.
   *  Qaytaradi: true (ANIQ sozlama bor) | false (yo'q — chop etilmasin). */
  async function ensure(maxAgeMs = PRINT_CFG_MAX_AGE_MS) {
    if (!cfg || source !== 'server' || Date.now() - loadedAt > maxAgeMs) await load();
    return !!cfg;
  }

  return {
    load, ensure,
    get: () => cfg,
    source: () => source,
    /** printReceiptHTML opsiyalari — sozlama yo'q bo'lsa null (chop etilmasin). */
    printOpts(extra) {
      if (!cfg) return null;
      return Object.assign({
        deviceName:  cfg.printerName,
        fontSize:    cfg.fontSize,
        printType:   cfg.printType,
        printerIp:   cfg.printerIp,
        printerPort: cfg.printerPort,
        paperWidth:  cfg.paperWidth,
      }, extra || {});
    },
  };
}

/** Kassirga ogohlantirish: chek chiqmadi, sabab va "Qayta urinish".
 *  Toast emas — yo'qolib ketmasin, kassir aniq ko'rsin (bir vaqtda bitta). */
export function showPrintConfigAlert(onRetry) {
  document.getElementById('xnPrintCfgAlert')?.remove();
  const el = document.createElement('div');
  el.id = 'xnPrintCfgAlert';
  el.setAttribute('role', 'alert');
  el.style.cssText = 'position:fixed;left:50%;top:16px;transform:translateX(-50%);z-index:100001;'
    + 'max-width:min(560px,94vw);display:flex;gap:.75rem;align-items:center;flex-wrap:wrap;'
    + 'padding:.8rem 1rem;border-radius:12px;background:#7f1d1d;color:#fff;'
    + 'box-shadow:0 12px 40px rgba(0,0,0,.45);font:600 .875rem/1.4 Inter,system-ui,sans-serif';
  el.innerHTML = '<span style="flex:1 1 260px">🖨 Chek chiqarilmadi: printer sozlamasi serverdan olinmadi '
    + '(internetni tekshiring). Chek boshqa printerga yuborilmadi.</span>'
    + '<button type="button" data-a="retry" style="padding:.45rem .9rem;border-radius:8px;border:none;'
    + 'background:#fff;color:#7f1d1d;font-weight:700;cursor:pointer">Qayta urinish</button>'
    + '<button type="button" data-a="close" aria-label="Yopish" style="padding:.45rem .6rem;border-radius:8px;'
    + 'border:1px solid rgba(255,255,255,.4);background:transparent;color:#fff;cursor:pointer">✕</button>';
  el.addEventListener('click', (e) => {
    const a = e.target.closest('button')?.dataset.a;
    if (!a) return;
    el.remove();
    if (a === 'retry' && onRetry) onRetry();
  });
  document.body.appendChild(el);
  return el;
}
