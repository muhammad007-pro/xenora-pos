/**
 * `js/core/toast.js` — YETISHMAYOTGAN modul (mijozda topildi, 2026-08).
 *
 * MUAMMO: to'rtta sahifa shu yo'ldan import qilardi —
 *   app/markup_policy.html, app/promotions.html,
 *   app/bonus_cards.html,   app/markirovka.html
 * lekin fayl HECH QACHON mavjud bo'lmagan. ES modulda YO'Q importni yuklab
 * bo'lmasa BUTUN modul skripti bajarilmaydi — ya'ni bu sahifalarda hech narsa
 * ishlamasdi: ma'lumot yuklanmasdi, tugmalar javob bermasdi, konsolda esa
 * bitta MIME/404 xatosi. Nginx bu yo'lga HTML fallback (200) qaytargani uchun
 * xato "topilmadi" emas, "modul emas" bo'lib ko'rinardi.
 *
 * Yechim: shu yo'lni HAQIQIY modulga aylantiramiz va mavjud `js/ui/toast.js`
 * ni qayta eksport qilamiz. Shu tarzda 4 ta sahifa ham tuzatiladi va ularning
 * import qatorlariga TEGILMAYDI (kelajakda shu yo'ldan import qilgan sahifa
 * ham ishlayveradi).
 */
export { showToast, showToast as toast, ToastService } from '../ui/toast.js';
