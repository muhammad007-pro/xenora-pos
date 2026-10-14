-- ═══════════════════════════════════════════════════════════════════════════
-- ASTRONOMIK OMBOR HARAKATLARI — tuzatish (XOZMAG 7 juft, BARAKA 1 juft)
-- Tayyorlandi: 2026-10-14. ⛔ HALI BAJARILMAGAN. Oxiri ROLLBACK — COMMIT
-- qilish uchun eng oxirgi qatorni almashtiring (pastdagi ko'rsatma).
-- ═══════════════════════════════════════════════════════════════════════════
--
-- NIMA BO'LGAN (prod, faqat o'qish bilan tekshirildi 2026-10-14):
--   Mahsulot yaratilganda "Boshlang'ich qoldiq" maydoniga MIQDOR o'rniga
--   SHTRIX-KOD kiritilgan (in, reason=manual, notes="Boshlang'ich qoldiq").
--   Do'konchi xatoni ko'rib, deyarli shuncha HISOBDAN CHIQARGAN (writeoff,
--   unit_cost=0, total_cost=0). Qoldiq (inventory) TO'G'RI: farq = haqiqiy
--   boshlang'ich qoldiq. Lekin harakatlar tarixida miqdorlar ~10^12–10^14,
--   kirim summasi esa ~10^19 — XOZMAG ombor hisobotida
--   21 672 088 339 478 920 000 shu 7 ta kirimning total_cost yig'indisi.
--
--   Faqat `stock_movements` ga ta'sir qilgan: priyomka, firma qarzi,
--   write_offs hujjatlari, partiyalar, inventarizatsiya — tekshirildi, toza.
--
-- TANLANGAN YO'L — O'CHIRISH EMAS, JUFTNI NEYTRALLASH (qatorlar qoladi):
--   kirim:   quantity := kirim − chiqarish  (haqiqiy boshlang'ich qoldiq)
--            total_cost := yangi quantity × unit_cost
--   chiqarish: quantity := 0  (total_cost allaqachon 0)
--   ikkalasining notes iga asl miqdor va juft id yoziladi (audit izi).
--
--   NEGA SHU:
--   • Har juftning SOF ta'siri (kirim − chiqarish) AYNAN saqlanadi →
--     inventory.quantity va har mahsulotning harakatlar balansi o'zgarmaydi.
--   • Faqat kirimni o'chirish/tuzatish xavfli: keyingi "hisobdan chiqarish"
--     yetim qolib, balans −10^12 ga tushardi (siz aytgan xavf).
--   • Juftni o'chirish tarixni yo'qotadi (kim, qachon xato qildi — iz yo'q),
--     id lar boshqa joyda (audit) havola bo'lishi mumkin.
--   • movement_type ni almashtirish (masalan 'void') hisobot filtrlarini
--     o'zgartiradi va kodda bunday tur yo'q — yangi xatti-harakat.
--   • Natija: hisobotlarda kirim = haqiqiy (6 dona × narx), zarar (writeoff)
--     soni 0, summa avvalgidek 0. Qoldiq va sotuvlar tegilmaydi.
--
-- QO'RIQCHI: id lar VA hozirgi miqdorlar AYNAN kutilgandek bo'lmasa (kimdir
-- o'zgartirgan, boshqa baza) — DO-blok xato tashlaydi, hech narsa yozilmaydi.
--
-- BAJARISH (serverda, root):
--   1) Zaxira:  sudo -u postgres pg_dump -Fc -d xenora_db > /root/backups/pre_astro_$(date +%Y%m%d_%H%M%S).dump
--   2) Sinov (ROLLBACK bilan):  sudo -u postgres psql -d xenora_db -X -v ON_ERROR_STOP=1 < /root/astro_fix.sql
--      ⚠️ `-f /root/...` ishlamaydi (postgres /root ni o'qiy olmaydi) — stdin bilan.
--   3) Natija to'g'ri bo'lsa: oxirgi `ROLLBACK;` ni `COMMIT;` ga almashtirib qayta.
-- ═══════════════════════════════════════════════════════════════════════════

\set ON_ERROR_STOP on
\pset pager off
BEGIN;

-- Juftlar: (kirim id, chiqarish id, tenant, mahsulot, kirim qty, chiqarish qty, kutilgan sof)
CREATE TEMP TABLE _astro (in_id int, wo_id int, tenant int, product int,
                          in_qty float8, wo_qty float8, net float8) ON COMMIT DROP;
INSERT INTO _astro VALUES
  ( 6923,  7782, 27, 2158,   4780069000147,   4780069000147,  0),  -- CHEERS 45gr
  (10966, 10994, 28, 2432, 508681002822184, 508681002822184,  0),  -- JIDKIY GVOZ SOMAFIX S 176
  (11070, 11113, 28, 2505,  14780127363252,  14780127363251,  1),  -- AVTOMAT UZO 16A DUSEL
  (11131, 11132, 28, 2548,   4780026660216,   4780026660210,  6),  -- KRASKA WEBER MOKRIY 2.7 KG
  (12329, 12330, 28, 3129,   6948271941056,   6948271941054,  2),  -- AFIXS KRASKA BLACK QORA
  (12613, 12614, 28, 3271, 104607036690029, 104607036690019, 10),  -- KOLLER PALIZH 02.1
  (12653, 12656, 28, 3294,  84607036690999,  84607036690991,  8),  -- KOLLER PALIZH 24
  (13112, 13160, 28, 3451,  16900556077690,  16900556077689,  1);  -- PW112-24-1 PERFARATOR

-- Har mahsulot bo'yicha harakatlar balansi — OLDIN (keyin solishtiriladi)
CREATE TEMP TABLE _bal_before ON COMMIT DROP AS
SELECT product_id,
       sum(CASE WHEN movement_type IN ('in','return','adjustment') THEN quantity::numeric ELSE -quantity::numeric END) AS bal
FROM stock_movements WHERE product_id IN (SELECT product FROM _astro) GROUP BY product_id;
CREATE TEMP TABLE _inv_before ON COMMIT DROP AS
SELECT id, quantity FROM inventory WHERE product_id IN (SELECT product FROM _astro);

-- ── QO'RIQCHI ────────────────────────────────────────────────────────────────
DO $$
DECLARE n int; bad int; extra int;
BEGIN
  -- 1) 16 qator aynan shu holatda bor (id, tur, tenant, mahsulot, miqdor, sabab)
  SELECT count(*) INTO n FROM _astro a
    JOIN stock_movements i ON i.id = a.in_id AND i.movement_type = 'in' AND i.tenant_id = a.tenant
         AND i.product_id = a.product AND i.quantity = a.in_qty AND i.reason = 'manual'
    JOIN stock_movements w ON w.id = a.wo_id AND w.movement_type = 'writeoff' AND w.tenant_id = a.tenant
         AND w.product_id = a.product AND w.quantity = a.wo_qty AND coalesce(w.total_cost,0) = 0;
  IF n <> 8 THEN RAISE EXCEPTION 'QO''RIQCHI: kutilgan 8 juftdan % tasi mos — hech narsa o''zgarmadi', n; END IF;
  -- 2) sof = kirim − chiqarish (qo'lda yozilgan qiymatlar to'g'rimi)
  SELECT count(*) INTO bad FROM _astro WHERE in_qty - wo_qty <> net;
  IF bad <> 0 THEN RAISE EXCEPTION 'QO''RIQCHI: % juftda sof qiymat mos emas', bad; END IF;
  -- 3) boshqa astronomik harakat yo'q (ro'yxatdan tashqari)
  SELECT count(*) INTO extra FROM stock_movements
   WHERE quantity > 1000000 AND id NOT IN (SELECT in_id FROM _astro UNION SELECT wo_id FROM _astro);
  IF extra <> 0 THEN RAISE EXCEPTION 'QO''RIQCHI: ro''yxatdan tashqari % ta astronomik harakat bor — avval tekshiring', extra; END IF;
  RAISE NOTICE 'Qo''riqchi: 8 juft mos, tashqarida astronomik harakat yo''q';
END $$;

-- ── TUZATISH ─────────────────────────────────────────────────────────────────
UPDATE stock_movements m
   SET quantity   = a.net,
       total_cost = a.net * coalesce(m.unit_cost, 0),
       notes      = concat_ws(' | ', nullif(m.notes, ''),
                    format('[2026-10-14 tuzatildi] asl miqdor %s (shtrix-kod kiritilgan); juft hisobdan chiqarish #%s bilan neytrallandi, sof %s',
                           to_char(a.in_qty, 'FM999999999999999'), a.wo_id, a.net))
  FROM _astro a WHERE m.id = a.in_id;

UPDATE stock_movements m
   SET quantity = 0,
       notes    = concat_ws(' | ', nullif(m.notes, ''),
                  format('[2026-10-14 tuzatildi] asl miqdor %s - kirim #%s dagi shtrix-kod xatosini to''g''rilagan; endi kirim haqiqiy miqdorda',
                         to_char(a.wo_qty, 'FM999999999999999'), a.in_id))
  FROM _astro a WHERE m.id = a.wo_id;

-- ── TEKSHIRUV ────────────────────────────────────────────────────────────────
DO $$
DECLARE d int; inv_d int; left_ int;
BEGIN
  -- balans har mahsulotda AYNAN o'zgarmagan
  SELECT count(*) INTO d FROM _bal_before b
    JOIN (SELECT product_id,
                 sum(CASE WHEN movement_type IN ('in','return','adjustment') THEN quantity::numeric ELSE -quantity::numeric END) AS bal
            FROM stock_movements WHERE product_id IN (SELECT product FROM _astro) GROUP BY product_id) a
      ON a.product_id = b.product_id
   WHERE a.bal <> b.bal;
  IF d <> 0 THEN RAISE EXCEPTION 'TEKSHIRUV: % mahsulotda harakat balansi o''zgardi', d; END IF;
  -- inventory'ga tegilmagan
  SELECT count(*) INTO inv_d FROM _inv_before b JOIN inventory i ON i.id = b.id WHERE i.quantity <> b.quantity;
  IF inv_d <> 0 THEN RAISE EXCEPTION 'TEKSHIRUV: inventory o''zgardi'; END IF;
  -- astronomik qolmadi
  SELECT count(*) INTO left_ FROM stock_movements WHERE quantity > 1000000;
  IF left_ <> 0 THEN RAISE EXCEPTION 'TEKSHIRUV: hali % ta astronomik harakat', left_; END IF;
  RAISE NOTICE 'Tekshiruv: balans va qoldiq aynan, astronomik harakat 0';
END $$;

\echo '== Natija (16 qator)'
SELECT m.id, m.tenant_id t, m.product_id pid, m.movement_type typ, m.quantity, m.unit_cost, m.total_cost,
       left(m.notes, 90) notes
  FROM stock_movements m
 WHERE m.id IN (SELECT in_id FROM _astro UNION SELECT wo_id FROM _astro)
 ORDER BY m.product_id, m.id;

\echo '== XOZMAG / BARAKA kirim summasi (barcha davr): endi'
SELECT tenant_id t, round(sum(total_cost)::numeric, 0) kirim_summa, count(*) n
  FROM stock_movements WHERE movement_type = 'in' AND tenant_id IN (27, 28) GROUP BY tenant_id ORDER BY 1;

-- ⛔ SUKUT — ROLLBACK. Natija to'g'ri bo'lsa: shu qatorni `COMMIT;` qiling.
ROLLBACK;
