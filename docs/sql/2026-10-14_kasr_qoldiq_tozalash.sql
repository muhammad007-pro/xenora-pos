-- ═══════════════════════════════════════════════════════════════════════════
-- KASR (FLOAT) CHIQINDISI — topish + ixtiyoriy tozalash. ⛔ BAJARILMAGAN.
-- Tayyorlandi: 2026-10-14 (fix/inventory-precision). Oxiri ROLLBACK.
-- ═══════════════════════════════════════════════════════════════════════════
--
-- NIMA: 0.265 + 8.4 = 8.665000000000001. Kod endi har yozishda yaxlitlaydi
-- (models.round_qty: inventory 3 xona, stock_movements 6 xona), lekin
-- tuzatishdan OLDIN yozilgan qatorlar shunday qoladi.
--
-- ⚠️ TOPISH TUZOG'I: `quantity::numeric` PostgreSQL'da float8 ni 15 raqamga
-- yaxlitlaydi va 8.665000000000001 ni "8.665" qilib YASHIRADI (2026-10-14 da
-- shu sabab birinchi tekshiruv 0 ko'rsatgan). Shuning uchun solishtirish FLOAT
-- darajasida: `quantity <> round(quantity::numeric, N)::float8`, chiqish esa
-- extra_float_digits = 3 bilan (to'liq qiymat ko'rinsin).
--
-- PROD HOLATI (faqat o'qish, 2026-10-14): inventory 0, order_items 0,
-- return_items 0; stock_movements 12 (hammasi BARAKA, bugun, "qoldiqni
-- tenglash" farqlari: 0.665000000000001, 5.86000000000001, 9e-15, 2e-16 ...).
--
-- TOZALASH QOIDASI (kod bilan bir xil):
--   inventory.quantity        → round(.., 3)
--   stock_movements.quantity  → round(.., 6)   (retseptning gramm ulushlari saqlanadi)
--   QOLDIQ (inventory) O'ZGARMAYDI — u allaqachon toza; faqat tarix qatorlari.
--   Harakat farqi ~1e-14 — balans/hisobotga ta'siri yo'q, faqat ko'rinish.
--
-- BAJARISH (serverda, root):
--   1) sudo -u postgres pg_dump -Fc -d xenora_db > /root/backups/pre_kasr_$(date +%Y%m%d_%H%M%S).dump
--   2) sudo -u postgres psql -d xenora_db -X -v ON_ERROR_STOP=1 < /root/kasr.sql      (ROLLBACK bilan)
--   3) to'g'ri bo'lsa oxirgi qatorni COMMIT; qilib qayta
-- ═══════════════════════════════════════════════════════════════════════════

\set ON_ERROR_STOP on
\pset pager off
BEGIN;
SET LOCAL extra_float_digits = 3;

\echo '== 1) qaysi do''konda nechta (float darajasida)'
SELECT 'inventory (3 xona)' jadval, tenant_id, count(*) n
  FROM inventory WHERE quantity <> round(quantity::numeric, 3)::float8 GROUP BY tenant_id
UNION ALL
SELECT 'stock_movements (6 xona)', tenant_id, count(*)
  FROM stock_movements WHERE quantity <> round(quantity::numeric, 6)::float8 GROUP BY tenant_id
UNION ALL
SELECT 'order_items (3 xona)', tenant_id, count(*)
  FROM order_items WHERE quantity <> round(quantity::numeric, 3)::float8 GROUP BY tenant_id
ORDER BY 1, 2;

\echo '== 2) misollar (eng ko''pi 30)'
SELECT 'mv' k, id, tenant_id t, product_id pid, movement_type typ, quantity, round(quantity::numeric, 6) toza,
       created_at AT TIME ZONE 'Asia/Tashkent' cr
  FROM stock_movements WHERE quantity <> round(quantity::numeric, 6)::float8
 ORDER BY id LIMIT 30;

-- Har mahsulot harakat balansi — OLDIN (tozalashdan keyin solishtiriladi; farq < 1e-9 bo'lishi shart)
CREATE TEMP TABLE _bal ON COMMIT DROP AS
SELECT product_id, sum(CASE WHEN movement_type IN ('in','return','adjustment') THEN quantity::numeric ELSE -quantity::numeric END) b
  FROM stock_movements
 WHERE product_id IN (SELECT product_id FROM stock_movements WHERE quantity <> round(quantity::numeric, 6)::float8)
 GROUP BY product_id;
CREATE TEMP TABLE _inv ON COMMIT DROP AS SELECT id, quantity FROM inventory;

-- ── TOZALASH ─────────────────────────────────────────────────────────────────
UPDATE inventory       SET quantity = round(quantity::numeric, 3)::float8
 WHERE quantity <> round(quantity::numeric, 3)::float8;
UPDATE stock_movements SET quantity = round(quantity::numeric, 6)::float8
 WHERE quantity <> round(quantity::numeric, 6)::float8;

-- ── TEKSHIRUV ────────────────────────────────────────────────────────────────
DO $$
DECLARE d int; i int; left_ int;
BEGIN
  SELECT count(*) INTO d FROM _bal b JOIN (
      SELECT product_id, sum(CASE WHEN movement_type IN ('in','return','adjustment') THEN quantity::numeric ELSE -quantity::numeric END) b
        FROM stock_movements WHERE product_id IN (SELECT product_id FROM _bal) GROUP BY product_id) a
    ON a.product_id = b.product_id WHERE abs(a.b - b.b) > 0.000001;
  IF d <> 0 THEN RAISE EXCEPTION 'TEKSHIRUV: % mahsulotda balans 1e-6 dan ko''p o''zgardi', d; END IF;
  SELECT count(*) INTO i FROM _inv o JOIN inventory n ON n.id = o.id WHERE abs(n.quantity - o.quantity) > 0.0005;
  IF i <> 0 THEN RAISE EXCEPTION 'TEKSHIRUV: % ta qoldiq 0.0005 dan ko''p o''zgardi', i; END IF;
  SELECT count(*) INTO left_ FROM stock_movements WHERE quantity <> round(quantity::numeric, 6)::float8;
  IF left_ <> 0 THEN RAISE EXCEPTION 'TEKSHIRUV: hali % ta iflos harakat', left_; END IF;
  RAISE NOTICE 'Tekshiruv: balans va qoldiq saqlandi, iflos harakat 0';
END $$;

-- ⛔ SUKUT — ROLLBACK. Natija to'g'ri bo'lsa: shu qatorni `COMMIT;` qiling.
ROLLBACK;
