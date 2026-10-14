-- ═══════════════════════════════════════════════════════════════════════════
-- ASTRONOMIK NARX / TANNARX (mahsulot kartasi) — topish + tuzatish. ⛔ BAJARILMAGAN.
-- Tayyorlandi: 2026-10-14 (fix/inventory-precision). Oxiri ROLLBACK.
-- ═══════════════════════════════════════════════════════════════════════════
--
-- SHIKOYAT: BARAKA "Ombor qiymati (tannarx)" 95 600 990 267 183 UZS,
-- "Potensial foyda" −95 600 879 550 451.
--
-- SABAB (prod, faqat o'qish bilan aniqlandi):
--   /inventory/value = Σ (inventory.quantity × products.cost_price), faol mahsulotlar.
--   RIZQ 200 GR (#2221) cost_price = 4 780 045 170 147 (SHTRIX-KOD), qoldiq 20:
--     4 780 045 170 147 × 20 = 95 600 903 402 940  +  qolganlar ~86,9 mln
--     = 95 600 990 267 183  ← skrinshotdagi son AYNAN.
--   Naqsh: kassir narx/tannarx maydoniga son yozadi, keyin skaner shtrix-kodni
--   o'sha maydonga QO'SHIB yuboradi: "12000" + "4780019480..." = 1.2000478...e17.
--   audit_logs da 11 ta shunday tahrir (3 do'kon, 10.09–14.10).
--
-- HOLAT 2026-10-14 ~13:00: do'kon O'ZI tuzatgan (AZIZBEK, 12:31–12:34):
--   RIZQ 200 GR      4 780 045 170 147 → 9 000
--   HOLVA QIMMAT     1.2000478001948e17 → 12 000
--   MEGA CHIPS ACHCHIQ 6.000481027900483e16 → 6 000
--   /inventory/value hozir BARAKA: 87 242 415 (normal). inventory.quantity da
--   astronomik qiymat YO'Q (avvalgi SQL faqat stock_movements ni tuzatgani to'g'ri).
--
-- QOLGANI: faqat #2009 MEGA CHIPS ACHACHIQ — O'CHIRILGAN (is_active=false),
--   qoldiq 0, price = 7.000481027900483e16 ("7000" + shtrix-kod). Ombor qiymatiga
--   ta'sir qilmaydi, lekin o'chirilganlar ro'yxati/eksportda astronomik ko'rinadi.
--   To'g'ri qiymat: 7 000 (faol egizagi #2008 "MEGA CHIPS ACHCHIQ" narxi 7 000,
--   ikkalasining tannarxi 6 000; ikkinchi qism shtrix-kod 4810279004830 ga mos).
--
-- BAJARISH: zaxira → ROLLBACK bilan ko'rish → COMMIT (pastdagi ko'rsatma).
-- ═══════════════════════════════════════════════════════════════════════════

\set ON_ERROR_STOP on
\pset pager off
BEGIN;
SET LOCAL extra_float_digits = 3;

\echo '== 1) HOZIR: narx yoki tannarx > 100 mln, yoki tannarx > 20 x narx (barcha do''konlar)'
SELECT p.id, p.tenant_id t, p.name, p.barcode, p.cost_price, p.price, p.pack_price, p.wholesale_price,
       p.is_active, coalesce(i.quantity, 0) qoldiq,
       round((coalesce(i.quantity,0) * coalesce(p.cost_price,0))::numeric) ombor_qiymati
  FROM products p LEFT JOIN inventory i ON i.product_id = p.id
 WHERE p.cost_price > 1e8 OR p.price > 1e8 OR p.pack_price > 1e8 OR p.wholesale_price > 1e8
    OR (p.price > 0 AND p.cost_price > 20 * p.price)
 ORDER BY ombor_qiymati DESC NULLS LAST, p.id;

\echo '== 2) Do''kon bo''yicha ombor qiymati (faol, /inventory/value bilan bir xil formula)'
SELECT i.tenant_id t, round(sum(i.quantity * p.cost_price)::numeric) tannarx, round(sum(i.quantity * p.price)::numeric) sotuv
  FROM inventory i JOIN products p ON p.id = i.product_id
 WHERE p.is_active GROUP BY 1 ORDER BY 1;

\echo '== 3) Tarix: audit da astronomik narx/tannarx tahrirlari'
SELECT a.id, a.tenant_id t, a.resource_id pid, a.detail->>'name' nom,
       a.detail->>'cost_old' cost_old, a.detail->>'cost_new' cost_new,
       a.detail->>'price_old' price_old, a.detail->>'price_new' price_new,
       a.created_at AT TIME ZONE 'Asia/Tashkent' cr
  FROM audit_logs a
 WHERE a.resource = 'products'
   AND greatest(coalesce((a.detail->>'cost_old')::float8,0), coalesce((a.detail->>'price_old')::float8,0),
                coalesce((a.detail->>'cost_new')::float8,0), coalesce((a.detail->>'price_new')::float8,0)) > 1e8
 ORDER BY a.id;

-- ── QO'RIQCHI + TUZATISH: #2009 ─────────────────────────────────────────────
DO $$
DECLARE n int; extra int;
BEGIN
  SELECT count(*) INTO n FROM products
   WHERE id = 2009 AND tenant_id = 27 AND name = 'MEGA CHIPS ACHACHIQ' AND is_active = false
     AND price = 7.000481027900483e16 AND cost_price = 6000;
  IF n <> 1 THEN RAISE EXCEPTION 'QO''RIQCHI: #2009 kutilgan holatda emas (o''zgargan?) — hech narsa o''zgarmadi'; END IF;
  SELECT count(*) INTO extra FROM products
   WHERE id <> 2009 AND (cost_price > 1e8 OR price > 1e8 OR pack_price > 1e8 OR wholesale_price > 1e8);
  IF extra <> 0 THEN RAISE EXCEPTION 'QO''RIQCHI: yana % ta astronomik mahsulot bor — avval 1-blokni ko''ring', extra; END IF;
END $$;

UPDATE products SET price = 7000 WHERE id = 2009;

DO $$
DECLARE left_ int;
BEGIN
  SELECT count(*) INTO left_ FROM products WHERE cost_price > 1e8 OR price > 1e8 OR pack_price > 1e8 OR wholesale_price > 1e8;
  IF left_ <> 0 THEN RAISE EXCEPTION 'TEKSHIRUV: hali % ta astronomik', left_; END IF;
  RAISE NOTICE 'Tekshiruv: astronomik narx/tannarx 0';
END $$;

SELECT id, name, price, cost_price, is_active FROM products WHERE id IN (2008, 2009) ORDER BY id;

-- ⛔ SUKUT — ROLLBACK. Natija to'g'ri bo'lsa: shu qatorni `COMMIT;` qiling.
ROLLBACK;
