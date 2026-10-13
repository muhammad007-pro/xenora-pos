-- ════════════════════════════════════════════════════════════════════════════
-- BEKOR QILINGAN CHEK + PAID TO'LOV — 6 ta osilgan chek
--
-- ⚠️ BU SKRIPT BAJARILMAGAN. Tayyor SQL; qarorni EGASI beradi.
--
-- HOLAT (prodda 2026-10-14 o'lchandi, READ ONLY):
--   • 6 chek / 211 998 so'm: BARAKA (27) 4 ta = 182 000, XOZMAG (28) 2 ta = 29 998
--   • XOZMAG — kg float nuqsoni (ildiz kodda tuzatildi: fix/payment-rounding,
--     `payment_service.covers` 1 tiyin dopusk + POS `roundMoney`)
--   • BARAKA — Click (stub) PENDING + naqd; chek qayta ochilib to'liq naqd sotilgan
--
-- ⚠️ ILDIZ TUZATISHI DEPLOY QILINMAGUNCHA A blok qayta kerak bo'lib qolishi
--    mumkin (yangi kg sotuvlar osilishi davom etadi). Avval deploy, keyin SQL.
-- ════════════════════════════════════════════════════════════════════════════
-- ════════════════════════════════════════════════════════════════════════════
-- BEKOR QILINGAN CHEK + PAID TO'LOV — tuzatish SQL (2026-10-14). BAJARILMAGAN.
-- Har blok o'z tranzaksiyasida; oxirida ROLLBACK turibdi — natijani ko'rib,
-- qo'lda COMMIT ga almashtiring. Avval zaxira:
--   sudo -u postgres pg_dump -Fc -d xenora_db > /opt/backups/pre_cancelpaid_$(date +%F_%H%M).dump
-- Enum yorliqlari KATTA harf (CASH/PAID/CANCELLED/COMPLETED/FAILED).
-- ════════════════════════════════════════════════════════════════════════════


-- ── A) XOZMAG (28) #3339, #3641 — SOTUV HAQIQIY, YAKUNLANSIN ────────────────
-- Sabab: 0.566 kg × 26 500 = 14998.999999999998 (float) < final 14999 →
-- server buyurtmani yakunlamadi, "kutilayotgan"da qoldi, kassir o'chirdi.
-- Pul KASSADA (Z to'g'ri), tovar KETGAN, ombordan AYRILMAGAN.
-- To'g'ri tuzatish: FAILED/REFUNDED EMAS — buyurtma COMPLETED + ombor chiqimi.
BEGIN;

-- 0) Holat aynan kutilgandekmi (2 qator bo'lishi SHART)
SELECT o.id, o.status, o.ingredients_deducted, p.id AS pay_id, p.method, p.status, p.amount,
       i.id AS inv_id, i.quantity AS qoldiq
FROM orders o
JOIN payments p ON p.order_id = o.id
JOIN order_items oi ON oi.order_id = o.id
JOIN inventory i ON i.product_id = oi.product_id AND i.tenant_id = 28
WHERE o.id IN (3339, 3641) AND o.tenant_id = 28
  AND o.status = 'CANCELLED' AND o.ingredients_deducted = false
  AND p.id IN (2910, 3180) AND p.method = 'CASH' AND p.status = 'PAID'
  AND abs(p.amount - 14999) < 0.01;

-- 1) To'lov summasini chek summasiga tenglash (14998.999999999998 → 14999)
UPDATE payments SET amount = 14999
WHERE id IN (2910, 3180) AND method = 'CASH' AND status = 'PAID' AND abs(amount - 14999) < 0.01;

-- 2) Buyurtmani yakunlash (vaqt = to'lov vaqti; hisobotlar o'sha kunga tushadi)
UPDATE orders o
SET status = 'COMPLETED',
    completed_at = p.created_at,
    ingredients_deducted = true,
    notes = coalesce(o.notes, '') || E'\n[2026-10-14 tuzatish] float (14998.999…) sababli yakunlanmagan; to''lov haqiqiy — yakunlandi, ombor ayrildi'
FROM payments p
WHERE p.order_id = o.id AND p.id IN (2910, 3180)
  AND o.id IN (3339, 3641) AND o.status = 'CANCELLED' AND o.ingredients_deducted = false;

-- 3) Ombor chiqimi izi (deduct_order_ingredients bilan bir xil shakl)
INSERT INTO stock_movements (tenant_id, product_id, inventory_id, movement_type, quantity, unit,
                             unit_cost, total_cost, reason, reference_id, reference_type,
                             notes, user_id, created_at)
SELECT 28, oi.product_id, i.id, 'sale', oi.quantity, coalesce(i.unit, 'kg'),
       coalesce(pr.cost_price, 0), round((coalesce(pr.cost_price, 0) * oi.quantity)::numeric, 2),
       'sale', oi.order_id, 'order',
       'Kechiktirilgan chiqim: 2026-10-14 tuzatish (float yakunlanmagan sotuv)', 26, p.created_at
FROM order_items oi
JOIN inventory i ON i.product_id = oi.product_id AND i.tenant_id = 28
JOIN products pr ON pr.id = oi.product_id
JOIN payments p ON p.order_id = oi.order_id AND p.id IN (2910, 3180)
WHERE oi.order_id IN (3339, 3641);

-- 4) Qoldiqni kamaytirish (3 xona — kasrli sotuv konvensiyasi)
UPDATE inventory i
SET quantity = round((i.quantity - oi.quantity)::numeric, 3)
FROM order_items oi
WHERE oi.order_id IN (3339, 3641) AND i.product_id = oi.product_id AND i.tenant_id = 28;

-- 5) Natija: 2 buyurtma COMPLETED, 2 harakat, qoldiq −0.566 dan
SELECT id, status, completed_at, ingredients_deducted FROM orders WHERE id IN (3339, 3641);
SELECT reference_id, product_id, quantity FROM stock_movements
WHERE reference_type = 'order' AND reference_id IN (3339, 3641);

ROLLBACK;   -- ← tekshirib bo'lgach COMMIT;


-- ── B) BARAKA (27) #3612, #3686 — "QAYTA SOTILDI": ESKI NAQD SOXTA ─────────
-- Click (stub) PENDING qolgan, chek qayta ochilib #3613 / #3692 da TO'LIQ naqd
-- sotilgan (o'sha soniyada, aynan o'sha mahsulotlar). Eski chekdagi 43 000 va
-- 45 000 naqd Z'da IKKINCHI marta turibdi.
-- FAILED (REFUNDED EMAS): REFUNDED = "pul olingan, keyin qaytarilgan" —
-- yangi Z qoidasida u sotuv sifatida qoladi. FAILED = "to'lov bo'lmagan".
-- ⚠️ Smena #51 YOPIQ: saqlangan Z raqamlari o'zgarmaydi, faqat print-z qayta
-- qurilganda naqd −88 000 bo'ladi. Pending Click'lar (alohida qaror) TEGILMAYDI.
BEGIN;

SELECT p.id, p.order_id, p.method, p.status, p.amount, o.status
FROM payments p JOIN orders o ON o.id = p.order_id
WHERE p.order_id IN (3612, 3686) AND o.tenant_id = 27 AND o.status = 'CANCELLED'
  AND p.method = 'CASH' AND p.status = 'PAID';                 -- 2 qator: 43000, 45000

UPDATE payments p
SET status = 'FAILED',
    reference = left(coalesce(p.reference, '') || ' [2026-10-14: chek qayta sotildi (#3613/#3692) — soxta naqd]', 200)
FROM orders o
WHERE o.id = p.order_id AND p.order_id IN (3612, 3686) AND o.tenant_id = 27
  AND o.status = 'CANCELLED' AND p.method = 'CASH' AND p.status = 'PAID';

ROLLBACK;   -- ← tekshirib bo'lgach COMMIT;


-- ── C) BARAKA (27) #2723, #3171 — "KUTILAYOTGAN O'CHIRILDI": NOANIQ ─────────
-- Qayta sotish TOPILMADI (±10 daqiqa, bir xil mahsulot). Naqd 41 000 / 53 000
-- mijozdan olinganmi — faqat do'kon biladi. Kassirlar smenani yaxlit summa
-- bilan yopgan (2 000 000), kamomad raqamidan dalil chiqmaydi.
-- Do'kon "pul olinmagan" desa — B bilan bir xil (FAILED). "Olingan, tovar
-- ketgan" desa — A bilan bir xil (COMPLETED + ombor), lekin chek jamisi
-- (121 986 / 83 000) to'lovdan katta: qolgan qism Click edi — avval aniqlash.
-- UPDATE payments SET status = 'FAILED' WHERE order_id IN (2723, 3171)
--   AND method = 'CASH' AND status = 'PAID';
