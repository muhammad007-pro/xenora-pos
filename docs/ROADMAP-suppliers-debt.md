# Firmalar / Nasiya (B2B qarz) — audit va yo'l xaritasi

Mijoz: **Fazza Parfum** — 5-6 firma bilan nasiya ishlaydi.
Branch: `feature/supplier-debt-fix` (main'dan).
Audit sanasi: 2026-08-16.

## Mijozning ikki ish oqimi

**SSENARIY 1 — tovar + qisman to'lov.** Firmadan eski qarz 1 500 000. Yangi nakladnoy
1 000 000 keldi. Do'konchi 500 000 berdi. Qolgan 500 000 eski qarzga qo'shilib
**2 000 000** bo'lishi kerak.

**SSENARIY 2 — tovarsiz to'lov.** Agent keladi, nakladnoysiz 600 000 olib ketadi.
**1 400 000** qolishi kerak.

Ikkalasi ham `backend/tests/test_supplier_debt.py` da GOLDEN test sifatida qotirilgan.

---

## Audit natijasi

### Ishlaydi — tegilmaydi
- Qarz formulasining o'zi: `xarid − to'lov − vozvrat` (yugurib boruvchi qoldiq)
- Priyomka → tasdiqlash → ombor + partiya (ProductBatch) + StockMovement + `cost_price`
- Draft nakladnoy qarzga kirmasligi — **to'g'ri qoida** (tovar hali omborga kirmagan)
- Vozvratda ombordan ayirish va yetarlilik tekshiruvi
- Otsrochka (`payment_delay_days`) mantiqi
- **INN majburiy EMAS** — na modelda (`models.py:1006`), na schemada (`schemas.py:1076`),
  na UIda (`suppliers.html:673`). Mijoz talabi allaqachon bajarilgan, o'zgartirilmaydi.

### Buzuq
| # | Muammo | Joy | Faza |
|---|---|---|---|
| B1 | Umumiy (nakladnoysiz) to'lov qarzni kamaytirmaydi | `routers/suppliers.py:80` | ✅ 1 |
| B2 | Ombor kirimi boshqa daftarga yozadi (`supplier.balance`) | `routers/inventory.py:428` | ✅ 2* |
| B3 | Avans ko'rinmaydi (`max(0, ...)`) | `routers/suppliers.py:84` | ✅ 1 |
| B4 | Direktor panelida butunlay boshqa formula | `routers/analytics.py:1351` | ✅ 1 |
| B5 | To'lov o'chirilsa nakladnoy `paid` bo'lib qoladi | `routers/supplier_payments.py:93` | 5 |
| B6 | Vozvrat StockMovement yozmaydi; o'chirilsa ombor tiklanmaydi | `routers/supplier_returns.py:94,129` | 5 |
| B7 | Arxivlangan firma qarzi jimgina yo'qoladi (`is_active=False`) | `routers/suppliers.py:140` | 5 |

**B1 — eng jiddiy.** UI aynan shu oqimni taklif qiladi (to'lov oynasidagi birinchi
variant "Umumiy to'lov", `suppliers.html:940`), pul saqlanadi va tarixda ko'rinadi,
lekin qarz kamaymaydi → do'konchi ikki marta to'lash xavfi ostida.

**B2 — ikki parallel daftar.** Ombor sahifasidagi "Kirim qilish" firma tanlansa
`supplier.balance += summa` qiladi. Bu ustunni hech bir ekran ko'rsatmaydi va hech
narsa kamaytirmaydi. Ya'ni Ombor orqali kirim qilingan tovar qarz sifatida umuman
paydo bo'lmaydi.

### Yo'q — quriladi
1. To'lov turini ko'rsatish: "Nakladnoy #12 uchun" vs "Umumiy to'lov" + **kim kiritgani**
   (`user_id`/`created_by` bazada BOR, schema va UIda yo'q)
2. Qarzlar tabida JAMI banner (hozir faqat Buxgalteriya tabida)
3. Boshlang'ich qarz — tizimga o'tishdan oldingi qarzni kiritish joyi
4. Firma kartochkasi — oborot varag'i (xronologik: nakladnoy / to'lov / vozvrat + qoldiq)
5. Priyomka oynasida "hozir to'landi" maydoni (1-ssenariy 3 ekrandan 1 ekranga)
6. To'lov va vozvrat uchun audit yozuvi
7. ~~Golden testlar~~ ✅ Faza 1 da yozildi

### Qo'shimcha: ikkita bir xil UI
`frontend/app/supplier_debt.html` (sidebar'dagi alohida sahifa) va
`frontend/app/suppliers.html` "Qarzlar" tabi — deyarli bir xil kod nusxasi.
Faza 2 da bittasi qoldiriladi, aks holda ekranlar bir-biridan uzoqlashadi.

---

## Fazalar

### ✅ FAZA 1 — pul to'g'ri hisoblansin (TUGADI)
Yangi `backend/services/supplier_debt.py` — **yagona hisob manbai**:
- BARCHA to'lovlar sanaladi (bog'langan + umumiy) → B1
- Bog'lanmagan pul **FIFO** bilan eng eski nakladnoydan boshlab taqsimlanadi
  (taqsimot **bazaga yozilmaydi**, har o'qishda qayta hisoblanadi → migratsiya kerak emas,
  to'lov o'chirilsa natija o'z-o'zidan tiklanadi)
- Avans `advance` / ishorali `balance` bo'lib qaytadi → B3
- `/analytics/store-dashboard` ham shu servisni chaqiradi → B4

Test: `tests/test_supplier_debt.py` — 13 ta, ikkala golden ssenariy ichida.
Migratsiya: **YO'Q** (faqat `SupplierDebtSummary` ga `advance`/`balance` qo'shildi,
ikkalasi ham default qiymatli — eski UI buzilmaydi).

### ✅ FAZA 2 — do'konchi ko'rsin (TUGADI)
- ✅ To'lov tarixida: tur (nakladnoy / umumiy) + nakladnoy raqami + kim kiritgani
  (`payment_type` / `receipt_label` / `created_by_name`)
- ✅ Avans belgisi (yashil "↩ Avans"), progress bar 100% da cheklangan
- ✅ Qarzlar tabida JAMI banner: jami qarz (qizil) / avans (yashil) / muddati o'tgan (sariq)
- ✅ `supplier_debt.html` → yo'naltiruvchi; yagona ekran `suppliers.html?tab=qarzlar`
- Migratsiya: **YO'Q** (maydonlar allaqachon bazada edi, faqat schemaga chiqarildi)

### ✅ FAZA 2* — B2 (Faza 3 dan olдinга olindi, KRITIK edi)
Ombor "Kirim qilish" firma tanlanganda **qarz YARATMAYDI** (qaror (a)).
`supplier.balance` yozuvi olib tashlandi; javobda `notice`, modalda esa firma
tanlanishi bilan sariq ogohlantirish chiqadi:
*"Firma bilan qarz yuritish uchun Priyomka bo'limidan foydalaning"*.
`supplier_id` StockMovement'da saqlanadi (kim keltirgani ko'rinadi), lekin qarz
hisobiga ta'sir qilmaydi. Qarzning yagona manbai — hujjatlar.

⚠️ Jonli baza tekshirildi (2026-08-17): **`suppliers` jadvali BO'SH** (0 firma,
`balance <> 0` bo'lgan bitta ham yozuv yo'q) — ya'ni yo'qoladigan ma'lumot yo'q edi,
backfill kerak emas.

### ✅ FAZA 3 — boshlang'ich qarz (TUGADI, migratsiya bor)
**Qaror (b) bajarildi:** yangi `suppliers.opening_debt` ustuni (Numeric 14,2,
default 0) + migratsiya `d4e5f6a7b8c9`. `balance` tegilmadi (tarixi iflos —
Ombor kirimlari o'sha yerga yozilgan edi).

Hisob: `jami_qarz = opening_debt + priyomkalar − to'lovlar − vozvratlar`.
Boshlang'ich qarz FIFO'da **eng eski** qarz — umumiy to'lov avval shuni yopadi.
"Muddati o'tgan" belgisi **qo'yilmaydi**: asl shartnoma sanasi bizda yo'q,
o'ylab topilgan muddat do'konchiga yolg'on ogohlantirish berardi.
`total_purchases` faqat priyomkalar bo'lib qoladi (opening alohida maydon).

UI: firma formasida "Boshlang'ich qarz (so'm)" — ixtiyoriy, default 0.

⚠️ Deploy: **backup-first**, migratsiya kod deployidan **alohida** qadam.

⚠️ **Migratsiya qoidalari (majburiy):**
- backup-first (migratsiyadan oldin baza nusxasi)
- idempotent (`IF NOT EXISTS`)
- `downgrade()` yozilgan bo'lsin
- alohida deploy (kod deployi bilan aralashtirilmaydi)

⚠️ **MIGRATSIYADAN OLDIN — jonli bazani tekshirish (BLOKLOVCHI):**
Fazza Parfum va Eco Aroma bazasida `suppliers.balance` da qanday qiymatlar borligi
tekshirilsin. Agar Ombor orqali kirim qilingan bo'lsa, u summalar **yo'qolib
ketmasligi** kerak — kerak bo'lsa `opening_debt` ga backfill qilinadi.
```sql
SELECT id, name, balance FROM suppliers WHERE balance <> 0 ORDER BY balance DESC;
```

### FAZA 4 — oborot varag'i + priyomkada to'lov
- Firma kartochkasi: xronologik harakat va yugurib boruvchi qoldiq
  (agent bilan hisob-kitob qilish ekrani)
- Nakladnoy oynasida "hozir to'landi" maydoni
- Migratsiya: **YO'Q**

### FAZA 5 — butunlik va himoya
- B5: to'lov o'chirilsa nakladnoy holati tiklansin
- B6: vozvrat StockMovement yozsin; o'chirilganda ombor tiklansin
- B7: qarzi bor firmani arxivlashda ogohlantirish
- To'lov va vozvrat uchun audit yozuvi
- Migratsiya: **YO'Q**

---

## Qoidalar (yangi kod uchun)

- Firma qarzi kerak bo'lsa → **faqat** `services/supplier_debt.py`. Router ichida
  qayta formula yozilmaydi (B4 aynan shundan kelib chiqqan edi).
- To'lov `receipt_id` siz ham to'liq huquqli to'lov — hech qayerda filtrlab
  tashlanmasin.
- Qarzni ustunga (`balance`) yozib qo'yish EMAS, hujjatlardan hisoblash. Ustun
  desinxronlashadi, hujjat esa audit izini qoldiradi.
