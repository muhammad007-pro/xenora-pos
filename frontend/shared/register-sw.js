/**
 * Service worker'ni ro'yxatdan o'tkazish — YAGONA joy.
 *
 * NEGA ALOHIDA FAYL: ilgari bu kod UCH joyda takrorlangan edi
 * (`shared/login.html`, `app/pos.html`, `js/main.js`) va uchalasi ham
 * `'../pwa/service-worker.js'` ni scope BERMASDAN ro'yxatga olardi. Standart
 * scope = skript turgan papka, ya'ni `/pwa/` — service worker `/app/*`,
 * `/js/*`, `/shared/*` so'rovlarini UMUMAN ko'rmasdi. Offline fallback ham,
 * kesh ham ishlamagan (`pwa/manifest.json` esa `"scope": "/"` deb turardi).
 *
 * Endi fayl ildizda (`/service-worker.js`) — scope `/` AVTOMATIK.
 * Serverdan `Service-Worker-Allowed` header TALAB QILINMAYDI (u ishlab
 * chiqarish nginx'ida yo'q).
 *
 * Classic skript (modul EMAS) — inline `<script src>` bilan yuklanadi va
 * hech qanday global yaratmaydi.
 *
 * ⚠️ Electron (`file://`) da service worker ro'yxatdan o'tmaydi — bu normal,
 * `catch` jim yutadi. Electron offline'ni IndexedDB + sync navbati bilan
 * qiladi (`js/core/db.js`, `js/core/sync.js`), service worker'ga tayanmaydi.
 */
(function () {
    if (!('serviceWorker' in navigator)) return;

    // `/service-worker.js` — ildizdan, ABSOLUT yo'l bilan. Sahifa qaysi
    // papkada bo'lishidan (/, /app/, /shared/) qat'i nazar bir xil ishlaydi.
    navigator.serviceWorker.register('/service-worker.js', { scope: '/' })
        .catch(() => { /* file:// yoki HTTP — e'tiborsiz */ });

    // ── ESKI ro'yxatni tozalash ──────────────────────────────────────────
    // Fayl `/pwa/service-worker.js` dan ildizga ko'chdi. Mijoz brauzerida
    // eski ro'yxat (scope `/pwa/`) qolib ketadi: u hech narsani boshqarmaydi
    // (`/pwa/` ostida sahifa yo'q), lekin ikkita service worker turishi
    // chalkash va u eski keshni ushlab turishi mumkin. Shuning uchun
    // ataylab o'chiramiz.
    //
    // ⚠️ Yangi ro'yxatni O'CHIRIB YUBORMASLIK uchun scope tekshiriladi —
    // faqat `/pwa/` bilan tugaydigani olib tashlanadi.
    if (navigator.serviceWorker.getRegistrations) {
        navigator.serviceWorker.getRegistrations()
            .then(regs => {
                regs.forEach(reg => {
                    if (reg.scope && reg.scope.endsWith('/pwa/')) reg.unregister();
                });
            })
            .catch(() => {});
    }
})();
