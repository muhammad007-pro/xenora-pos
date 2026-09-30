/**
 * Sahifalar orasidagi yo'llar — YAGONA MANBA.
 *
 * ⚠️ NEGA KERAK: Electron sahifalarni `loadFile()` bilan, ya'ni `file://`
 * protokolida ochadi (`electron/main.js`). U yerda MUTLAQ yo'l
 * (`/app/pos.html`) DISK ILDIZIGA ishora qiladi — fayl topilmaydi va oyna
 * QORAYIB qoladi.
 *
 * JONLI HODISA (1001 BARAKA, 2026-09-10): kassir "Kirish taqiqlangan"
 * ekranidagi "POS ga" tugmasini bosdi → qora ekran. Brauzerda (`app.xenora.uz`)
 * o'sha yo'l ishlayveradi, shuning uchun nuqson faqat `.exe` da ko'rinardi.
 *
 * QOIDA: sahifalar orasida MUTLAQ yo'l yozilmaydi. Shu moduldan foydalaning:
 *
 *     import { PATHS } from './paths.js';
 *     location.href = PATHS.login();      // ../shared/login.html
 *
 * Fayl tuzilishi (frontend ildizidan):
 *     app/…      shared/…      owner/…      index.html
 * Ya'ni `app/`, `shared/`, `owner/` — bir xil chuqurlikda. Shuning uchun
 * ulardan istalganidan boshqasiga borish `../<papka>/<fayl>` ko'rinishida.
 */

/** Joriy sahifa papkasidan frontend ILDIZIGA qaytish prefiksi ('' yoki '../'). */
export function rootPrefix(pathname) {
    const p = pathname !== undefined
        ? pathname
        : (typeof location !== 'undefined' ? location.pathname : '');
    // `/app/`, `/shared/`, `/owner/` ichidamizmi? Bo'lsa — bir pog'ona yuqoriga.
    return /\/(app|shared|owner)\//.test(p) ? '../' : '';
}

/** Frontend ildiziga NISBATAN berilgan yo'lni joriy sahifaga moslaydi.
 *  `pathTo('app/pos.html')` → `../app/pos.html` (app/ ichida bo'lsak ham —
 *  `../app/pos.html` to'g'ri ishlaydi va qoida bitta bo'lib qoladi). */
export function pathTo(rel, pathname) {
    return rootPrefix(pathname) + rel;
}

export const PATHS = {
    pos:                 (p) => pathTo('app/pos.html', p),
    admin:               (p) => pathTo('app/admin.html', p),
    login:               (p) => pathTo('shared/login.html', p),
    subscriptionBlocked: (p) => pathTo('shared/subscription-blocked.html', p),
};
