# Kategoriya nomi yagonaligi — baza darajasidagi kafolat (roadmap)

Kontekst: `create_category` dagi takrorlanish tekshiruvi 2026-09-09 da tuzatildi —
endi u tenant bilan cheklangan va registrga sezgir emas
(`backend/routers/category.py`, test: `backend/tests/test_category_tenant_scope.py`).

Bu **ilova darajasidagi** kafolat. Baza darajasida hali hech narsa yo'q.

## Tugagan

- ✅ `create_category` — `apply_tenant_filter` bilan cheklangan. Ilgari filtrsiz edi:
  bitta do'kon nomni band qilsa, boshqasi o'sha nomni ishlata olmasdi (prodda
  FAZZA "UMUMIY" olgan → 1001 BARAKA "UMUMIY mahsulotlar" deb nomlashga majbur bo'lgan).
- ✅ Registr: `func.lower(...)` — bitta do'konda "Umumiy" va "UMUMIY" endi dublikat.
- ✅ `create_product` — kategoriya qidiruvi ham tenant bilan cheklandi (begona
  kategoriyaga biriktirish yo'li yopildi).

## Qolgan

### 1. UNIQUE constraint: `(tenant_id, lower(name))`

Hozir `categories` jadvalida **faqat** `categories_pkey (id)` bor — nom bo'yicha
hech qanday UNIQUE yo'q. Ya'ni yagonalikni faqat ilova kodi ushlab turadi.
Bu yetarli emas: to'g'ridan-to'g'ri SQL, kelajakdagi import/seed skripti yoki
poyga holati (bir vaqtda ikkita bir xil so'rov) dublikat yaratib qo'yishi mumkin.

Kerakli migratsiya (taxminiy):

```sql
CREATE UNIQUE INDEX uq_categories_tenant_lower_name
    ON categories (tenant_id, lower(name));
```

**NEGA HOZIR QO'SHILMADI** — mavjud ma'lumotda konflikt chiqishi mumkin.
Migratsiyadan OLDIN quyidagi tekshiruv 0 qator qaytarishi shart:

```sql
SELECT tenant_id, lower(name), count(*)
FROM categories
GROUP BY tenant_id, lower(name)
HAVING count(*) > 1;
```

2026-09-09 holatiga ko'ra prodda 38 kategoriya bor va bu so'rov **0 qator**
qaytaradi (dublikat yo'q), ya'ni migratsiya bugun xavfsiz o'tardi. Lekin:

- `update_category` da nom tekshiruvi **umuman yo'q** (`category.py:~102-109`) —
  ya'ni mavjud kategoriyani dublikat nomga qayta nomlash hozir ochiq. Migratsiyadan
  oldin (yoki u bilan birga) shu teshik ham yopilishi kerak, aks holda constraint
  foydalanuvchiga xom `IntegrityError` (500) sifatida chiqadi.
- `tenant_id IS NULL` bo'lgan kategoriyalar (platforma egasi yaratganlari) —
  Postgres'da NULL'lar bir-biriga teng emas, ya'ni ular constraintdan chetda qoladi.
  Kerak bo'lsa partial index yoki `COALESCE(tenant_id, 0)` ko'rib chiqilsin.

### 2. Bir xil naqsh boshqa joyda — TEKSHIRILDI, boshqa nuqson yo'q

2026-09-09 da qidirildi:

```
grep -rn "filter(.*\.name ==" backend/routers/
```

Yagona qolgan mos joy — `role.py:37` (`Role.name == role_data.name`). Bu **nuqson
emas**: `Role` modelida `tenant_id` umuman yo'q va `name` ustuni `unique=True`
(global). Rollar ataylab platforma darajasida umumiy (qarang: v1.0.3 auditi).
Ya'ni kategoriya nuqsoni yolg'iz holat edi.
