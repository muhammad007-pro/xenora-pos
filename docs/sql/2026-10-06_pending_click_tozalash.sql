-- ════════════════════════════════════════════════════════════════════════════
-- ESKI PENDING CLICK TO'LOVLARI — TOZALASH
--
-- ⚠️ BU SKRIPT BAJARILMAGAN. Tavsiya va tayyor SQL; qarorni EGASI beradi.
--
-- HOLAT (prodda 2026-10-06 o'lchandi):
--   • 24 ta `status=PENDING, method=CLICK` to'lov yozuvi
--   • HAMMASI (24/24) BEKOR QILINGAN (`CANCELLED`) buyurtmada
--   • tenant bo'yicha: 26 FAZZA 4 ta, 27 BARAKA 16 ta, 28 XOZMAG 3 ta,
--     30 MANHATTAN 1 ta; jami 953 998 so'm
--   • PAYME'da bitta ham yo'q
--
-- PULGA TA'SIRI — YO'Q (tekshirildi):
--   `routers/shift.py` Z-hisobotida `card_sales` `_paid(p)` talab qiladi,
--   ya'ni pending CLICK `cash_sales`/`card_sales`/`total_sales`/`sales_count`
--   ga 0 qo'shadi. `credit_total` faqat `method='credit'` ni oladi.
--   Foyda hisoboti (`utils/revenue.py`) buyurtma/`ReturnItem` bo'yicha yuradi.
--   Ya'ni bu yozuvlar INERT — faqat "kutilmoqda" ro'yxatlarida shovqin.
--
-- NEGA QAYTA PAYDO BO'LMAYDI: POS'da Click/Payme standart O'CHIQ
-- (`/settings/payment-methods`, `_payment_methods()` → ["cash","card"]).
--
-- ── TAVSIYA: O'CHIRMASLIK, `failed` DEB BELGILASH ──────────────────────────
-- Sabab:
--   1. `PaymentStatus.FAILED` aynan shu holat uchun bor ("to'lov o'tmadi").
--   2. Yozuv DALIL: kassir Click'ni bosgan va shu sabab sotuv bekor bo'lgan.
--      O'chirsak, buyurtma nega bekor qilingani tarixdan yo'qoladi.
--   3. Pul yo'lida DELETE qaytarilmaydi; status o'zgarishi qaytariladi.
--   4. `failed` bo'lgach ular `status IN ('paid','pending')` filtriga
--      TUSHMAYDI → "kutilmoqda" ro'yxatlaridan chiqadi, hisobot o'zgarmaydi
--      (chunki allaqachon 0 qo'shardi).
--
-- ⚠️ NASIYA (CREDIT) PENDING YOZUVLARIGA TEGILMAYDI — 35 ta bor va ular
-- TO'G'RI holatda: pul kelmagan, qarz `customer_debts` orqali yuritiladi,
-- Z-hisobotda "nasiya" qatori aynan shulardan hisoblanadi.
-- ════════════════════════════════════════════════════════════════════════════

BEGIN;

-- 1) OLDIN KO'RISH — nima o'zgaradi (0 qatorga tegmasdan)
SELECT p.id, p.tenant_id, c.name AS dokon, p.amount, p.created_at,
       o.order_number, o.status AS buyurtma_holati
FROM payments p
JOIN orders o ON o.id = p.order_id
LEFT JOIN cafes c ON c.id = p.tenant_id
WHERE lower(p.status::text) = 'pending'
  AND lower(p.method::text) = 'click'
  AND lower(o.status::text) = 'cancelled'
ORDER BY p.tenant_id, p.created_at;

-- 2) SANOQ — 24 bo'lishi kerak. Boshqa son chiqsa TO'XTANG va qayta o'lchang.
SELECT count(*) AS belgilanadigan
FROM payments p JOIN orders o ON o.id = p.order_id
WHERE lower(p.status::text) = 'pending'
  AND lower(p.method::text) = 'click'
  AND lower(o.status::text) = 'cancelled';

-- 3) BELGILASH
--    ⚠️ `AND lower(o.status::text)='cancelled'` SHARTI MAJBURIY:
--    busiz kelajakda (shlyuz ulangach) HAQIQIY kutilayotgan Click to'lovi
--    ham "failed" bo'lib ketardi.
UPDATE payments p
SET status = 'FAILED'
FROM orders o
WHERE o.id = p.order_id
  AND lower(p.status::text) = 'pending'
  AND lower(p.method::text) = 'click'
  AND lower(o.status::text) = 'cancelled';

-- 4) TEKSHIRISH — pending CLICK 0 bo'lsin, CREDIT 35 da QOLSIN
SELECT p.method, p.status, count(*) AS n
FROM payments p
WHERE lower(p.status::text) IN ('pending', 'failed')
GROUP BY p.method, p.status
ORDER BY 1, 2;

-- Hammasi to'g'ri bo'lsa: COMMIT;  aks holda: ROLLBACK;
ROLLBACK;   -- ⚠️ ATAYLAB: qo'lda COMMIT ga o'zgartirilmaguncha hech narsa o'zgarmaydi

-- ── ALTERNATIVA (TAVSIYA ETILMAYDI): butunlay o'chirish ────────────────────
-- DELETE FROM payments p USING orders o
--  WHERE o.id = p.order_id AND lower(p.status::text)='pending'
--    AND lower(p.method::text)='click' AND lower(o.status::text)='cancelled';
-- Audit izi yo'qoladi; yuqoridagi 2-3 sabablarga qara.
