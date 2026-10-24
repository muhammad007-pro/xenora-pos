# Testlarda vaqt: seed zonasi endpoint asosiga mos bo'lsin

Testlar SQLite'da yuradi, prod esa PostgreSQL `timestamptz`. SQLite aware
qiymatning **devor vaqtini yozadi va zonani tashlaydi**. Shuning uchun bir xil
kod prodda to'g'ri, testda esa kunning ma'lum soatlarida "yiqiladi". Bunday
test kunduzi o'tadi, kechqurun yoki ertalab yiqiladi va hech kim sababini
topolmaydi.

## Qoida

**Seed vaqtini SINALAYOTGAN endpoint nima asosida hisoblasa, o'sha asosda yoz.**

Avval endpointni o'qib chiq: vaqtni qaysi funksiya bilan solishtiradi yoki ajratadi?

| Endpoint asosi | Misol | Seed |
|---|---|---|
| O'tgan vaqt / UTC lahza (`utc_now()`, `to_utc()`) | `/shifts/open-alerts`, `close_shift` oynasi | `utc_now() - timedelta(...)` |
| Mahalliy kun chegarasi (`day_bounds`, `report_bounds`) bilan **filtr** | `/profit/summary`, `/profit/by-receipt` | `tenant_now()` |
| Filtr devor vaqti bilan, **kun** esa `to_local()` / `bd.day_of` bilan — ARALASH | `/profit/staff-sales` (kunlar), business day | mahalliy zonani UTC ga qotir + `utc_now()` |

Aralash holatda SQLite'da +5 zonada ikkala asosga birdan mos seed **yo'q**:
`tenant_now()` bilan 19:00 dan keyin sotuv ertangi kunga o'tadi (`to_local()`
naive'ni UTC deb +5 qiladi), `utc_now()` bilan 00:00–05:00 da "bugun"
filtridan chiqadi. Zona UTC bo'lsa ikki asos bir xil:

```python
import core.timeutils as tu

NOW = tu.utc_now()

@pytest.fixture(autouse=True)
def _utc_local(monkeypatch):
    monkeypatch.setattr(tu, "_local_tz", lambda tz_name=None: timezone.utc)
```

## Misol: `test_uzoq_ochiq_smena_ogohlantirishi`

Endpoint `days = (utc_now() - start) // 24h` — o'tgan SOAT. Seed esa kalendar edi:

```python
# XATO: "8 kun oldin 10:00" — UTC 10:00 gacha (Toshkent 05:00–15:00) atigi 7 kun
start_time=_at(D - timedelta(days=5), 10)
assert days_open >= 8

# TO'G'RI: endpoint asosida, natija har soatda aniq
start_time=tu.utc_now() - timedelta(days=8, hours=1)
assert days_open == 8
```

## Qo'shimcha

- Seed "bugun" bo'lsa `<= now` VA bugun ichida bo'lsin (kelajak emas):
  `min(day_start + 1h, now)`.
- Naive `datetime.now()` ni seedda ishlatma: dev mashinada Toshkent, serverda UTC.
- Modul darajasidagi `NOW = ...` import paytida hisoblanadi; zona monkeypatch'i
  undan keyin keladi — shuning uchun aralash holatda `NOW` `utc_now()` dan olinadi.

## Istalgan soatda sinash

`tests/conftest.py` soat mock'i (`pip install freezegun`):

```powershell
cd backend
foreach ($t in "00:00","06:00","12:00","19:00","23:30") {
  $env:FAKE_NOW = "2026-10-21T${t}:00+05:00"
  py -m pytest tests/test_staff_sales.py -q -p no:randomly
}
Remove-Item Env:FAKE_NOW
```

- Naive `datetime.now()` / `date.today()` = mashina zonasi (Toshkentda +5).
  Server (UTC) kabi: `$env:FAKE_TZ_OFFSET = "0"`.
- Yangi vaqtga bog'liq test yozsang — shu 5 soatda yurgiz.
- Mock bazaga yetmaydi: `server_default=func.now()` (SQLite CURRENT_TIMESTAMP)
  haqiqiy soatni yozardi — conftest ORM orqali yangi qatordagi bo'sh "now"
  ustunlarini soxta UTC bilan to'ldiradi. Xom SQL `INSERT` bunga kirmaydi.
- Pydantic modellari va `/openapi.json` freezer'dan OLDIN quriladi (aks holda
  FakeDatetime bilan qurish yiqiladi → 500). Mock rejimida 500 chiqsa avval shuni o'ylab ko'r.
- `tz_offset=` ishlatma: freezegun uni aware `now(tz)` ga ham qo'shadi.
