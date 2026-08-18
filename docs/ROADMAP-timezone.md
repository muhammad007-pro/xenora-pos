# Timezone tozalash — qolgan ishlar (roadmap)

Kontekst: server **UTC**, do'kon **Toshkent (UTC+5)**. `core/timeutils.py` shu farqni
hal qilish uchun yozilgan (`tenant_now()`, `day_bounds()`, `to_local()`), lekin eski
kodning bir qismi hali **naive `datetime.now()`** yoki **`.replace(tzinfo=None)`**
ishlatadi. Ular jimgina noto'g'ri natija beradi — qulamaydi, shuning uchun sezilmaydi.

## Tugagan

- ✅ `analytics.py` `/summary` kunlik grafigi — aware/naive solishtirish `TypeError`
  berib, butun endpointni 500 qilardi → dashboard KPI kartalari va grafik BO'SH edi.
  Tuzatildi: `to_local()` bilan Toshkent sanasi bo'yicha guruhlash.
  Test: `backend/tests/test_dashboard_timezone.py`
- ✅ `analytics.py` oylik maqsad `days_left` — `+ 1` bugungi kunni ham sanardi
  (15-avgustda 17 chiqardi). Tuzatildi: `last_day - now.day`.

## Qolgan (alohida bandlarda qilinadi)

Qasddan kechiktirildi: ular boshqa sahifalarga tegadi, dashboard commiti toza qolsin.

### 1. `/analytics/peak-hours` — soatlar UTC bo'yicha
`backend/routers/analytics.py:~1261`
```python
dt = o.created_at.replace(tzinfo=None) if o.created_at.tzinfo else o.created_at
hour_stats[dt.hour] ...
```
Qulamaydi (solishtirish yo'q), lekin **soat va hafta kunini UTC'da** hisoblaydi.
Toshkentdagi 14:00 gavjum soati hisobotda **09:00** bo'lib ko'rinadi — "Peak soatlar"
sahifasi jimgina yolg'on gapiradi. Hafta kuni ham yarim tundan keyin siljiydi.
**Yechim:** `to_local(o.created_at)` ishlatish (`.hour` / `.weekday()` undan olinadi).

### 2. Davomat — naive "bugun"
`backend/routers/attendance.py:82, 127, 159`
```python
today = datetime.now().date()
```
Server UTC → 00:00–05:00 (Toshkent) oralig'idagi kelish/ketish **oldingi kunga**
yoziladi. Erta kelgan xodim kechagi kunda ko'rinadi.
**Yechim:** `tenant_now().date()` yoki `day_bounds()`.

### 3. Oshxona kunlik filtri
`backend/routers/kitchen.py:367`, `backend/services/kitchen_service.py:160`
Bir xil naqsh (`datetime.now().date()`). Kechqurun/tunda ishlaydigan oshxona uchun
kunlik ro'yxat noto'g'ri kunga tushadi.

### 4. Ombor — 30 kunlik oyna
`backend/services/inventory_service.py:194`
```python
thirty_days_ago = datetime.now().replace(hour=0, ...) - timedelta(days=30)
```
Ta'siri kichik (oyna chegarasi 5 soatga suriladi), lekin izchillik uchun
`day_bounds()` ga o'tkazilsin.

## Tekshirish qoidasi (yangi kod uchun)

- "Bugun/kecha/oy" chegarasi kerak bo'lsa → `day_bounds()` / `month_bounds()`
- DB timestampidan sana/soat olish kerak bo'lsa → `to_local(dt).date()` / `.hour`
- **Hech qachon** `.replace(tzinfo=None)` bilan "tuzatmaslik" — u aware/naive
  aralashuviga va `TypeError` ga olib keladi (aynan shu xato dashboardni buzgan edi)
- **Hech qachon** hisobot mantig'ida yalang'och `datetime.now()` — u UTC beradi
