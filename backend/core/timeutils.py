"""
Timezone-aware kun/hafta/oy chegaralari (Tier 2 — timezone yakuni).

MUAMMO: Server UTC. Naive `datetime.now()` UTC vaqtini beradi, shuning uchun
`datetime.now().replace(hour=0)` UTC YARIM TUNINI (= Toshkent 05:00) beradi.
Natijada "bugungi savdo" oralig'i mahalliy kundan 5 soat siljiydi va yarim tundan
keyin (00:00–05:00) ishlaydigan biznes uchun XATO bo'ladi. Bundan tashqari buyurtma
raqami (daily_number, order_service) Toshkent kunini ishlatadi → ichki nomuvofiqlik.

YECHIM: Kun chegarasini TENANT MAHALLIY zonasida hisoblaymiz (aware datetime).
DB ustunlari `timestamp with time zone` (tz-aware, UTC saqlangan) — solishtirish to'g'ri
bo'ladi. Jonli ma'lumotga TEGILMAYDI — faqat hisob tuzatiladi (migratsiya YO'Q).

Hozircha zona `settings.TIMEZONE` (Asia/Tashkent). Funksiyalar `tz_name` parametrini
qabul qiladi — kelajakda tenant o'z timezone'ini bersa, shu yerdan uzatiladi (kod
o'zgarmaydi). daily_number bilan AYNAN bir xil kun ta'rifi (Toshkent kuni).
"""
from datetime import datetime, timedelta, timezone
from config import settings

# O'zbekiston 1991'dan beri DST'siz, doimiy UTC+5. ZoneInfo topilmasa (masalan Windows
# dev'da tzdata paketi yo'q) — shu qat'iy offset ishlatiladi. Linux serverda esa OS
# tzdata mavjud → ZoneInfo ishlaydi (istalgan zona + DST to'g'ri). Ikkalasi Toshkent
# uchun bir xil natija beradi.
_UZ_FALLBACK = timezone(timedelta(hours=5))


def _local_tz(tz_name: str = None):
    """Tenant mahalliy timezone ob'ekti. ZoneInfo bo'lsa u (server), aks holda UTC+5 fallback."""
    name = tz_name or settings.TIMEZONE
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        return _UZ_FALLBACK


def tenant_now(tz_name: str = None) -> datetime:
    """Tenant mahalliy JORIY vaqti (aware). naive datetime.now() O'RNIGA ishlatiladi —
    shunda .replace(hour=0) mahalliy yarim tunni beradi (UTC yarim tuni emas)."""
    return datetime.now(_local_tz(tz_name))


def to_utc(dt, tz_name: str = None):
    """Qiymatni aware UTC ga keltiradi. SOLISHTIRISH/ARIFMETIKA uchun.

    NEGA KERAK: bazadan kelgan qiymat naive ham (SQLite, yoki PostgreSQL'da
    migratsiya HALI QO'LLANMAGAN bo'lsa) aware ham (timestamptz) bo'lishi
    mumkin. Ularni to'g'ridan `utc_now()` bilan ayirish/solishtirish
    `TypeError: can't subtract offset-naive and offset-aware datetimes`
    beradi — ochiq smena hisoboti aynan shu sabab 500 qaytarardi.

    Naive qiymat UTC deb qaraladi (ustunlar UTC saqlaydi — `to_local` bilan
    bir xil shartnoma). Shu bilan kod migratsiyadan OLDIN ham, KEYIN ham,
    ikkala bazada ham bir xil ishlaydi (deploy tartibi muhim emas).
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def utc_now() -> datetime:
    """SAQLASH uchun joriy vaqt — aware UTC.

    ═══ NEGA `tenant_now()` EMAS ═══
    `tenant_now()` HISOBLASH uchun (kun chegarasi, solishtirish). Bazaga YOZISH
    uchun esa UTC-aware kerak, chunki SQLAlchemy'ning SQLite dialekti zonani
    SAQLAMAYDI — aware qiymatning DEVOR VAQTINI yozib, `tzinfo` ni tashlaydi:
        tenant_now() = 01:55+05:00  ->  SQLite'da "01:55" (naive)
    `to_local()` esa naive qiymatni UTC deb oladi (ustunlar UTC saqlaydi) ->
    01:55 + 5 = 06:55. Ya'ni testlarda vaqt 5 soat OSHIQ chiqardi, prodda esa
    to'g'ri — xulq baza turiga qarab AJRALARDI.
        utc_now()    = 20:55+00:00  ->  SQLite'da "20:55" (naive UTC) -> to_local
                                        -> 01:55 Toshkent ✔
    PostgreSQL'da (timestamptz) ikkisi ham to'g'ri instantni saqlaydi. UTC-aware
    esa IKKALA bazada bir xil ishlaydi — shuning uchun yozishda faqat shu.

    Naive `datetime.now()` HAM ishlatilmaydi: u server zonasiga bog'liq
    (hozir UTC bo'lgani uchun tasodifan to'g'ri) va zona belgisi qolmaydi.
    """
    return datetime.now(timezone.utc)


def to_local(dt, tz_name: str = None):
    """DB dan o'qilgan timestampni TENANT MAHALLIY zonasiga o'giradi (aware).

    NEGA KERAK: `tenant_now()` aware qiymat qaytaradi. DB dan kelgan `created_at`
    bilan uni to'g'ridan solishtirish yoki `.hour`/`.date()` olish XATO beradi:
      - PostgreSQL (prod): created_at aware UTC → `.date()` UTC kunini beradi,
        Toshkent kunini emas (00:00–05:00 oralig'i oldingi kunga tushadi).
      - `.replace(tzinfo=None)` bilan "tuzatish" esa aware↔naive aralashuviga olib
        keladi → `TypeError: can't compare offset-naive and offset-aware datetimes`
        (aynan shu xato dashboard kartalarini bo'sh qoldirgan edi).

    Naive qiymat UTC deb qaraladi — DB ustunlari UTC saqlaydi (SQLite dev'da
    `func.now()` ham UTC naive beradi).
    """
    if dt is None:
        return None
    z = _local_tz(tz_name)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(z)


def _as_local(dt, z):
    """Berilgan qiymatni mahalliy aware datetime'ga keltiradi (date/datetime/None)."""
    if dt is None:
        return datetime.now(z)
    if isinstance(dt, datetime):
        return dt.astimezone(z) if dt.tzinfo else dt.replace(tzinfo=z)
    # date
    return datetime(dt.year, dt.month, dt.day, tzinfo=z)


def day_bounds(target=None, tz_name: str = None):
    """Mahalliy KUN chegarasi → (start, end) aware datetime, [00:00, ertaga 00:00).

    target: date | datetime | None(bugun). daily_number (Toshkent kuni) bilan izchil.
    Qaytgan qiymatlar aware — tz-aware ustunlar bilan to'g'ri solishtiriladi."""
    z = _local_tz(tz_name)
    d = _as_local(target, z)
    start = d.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def week_bounds(target=None, tz_name: str = None):
    """Oxirgi 7 mahalliy kun: (6 kun oldingi 00:00, ertaga 00:00). Kalendar-tekislangan."""
    start_today, end_today = day_bounds(target, tz_name)
    return start_today - timedelta(days=6), end_today


def month_bounds(target=None, tz_name: str = None):
    """Joriy kalendar oy: (oy 1-kuni 00:00, ertaga 00:00), mahalliy zonada."""
    start_today, end_today = day_bounds(target, tz_name)
    return start_today.replace(day=1), end_today


# ═══ DAVR TA'RIFI — YAGONA MANBA (2026-09) ════════════════════════════════════
#
# MUAMMO (jonli, FAZZA): ikki foyda ekrani bir xil "7 kun" uchun 984 000 so'm
# farq ko'rsatardi.
#   • profit.py:_period_range  → KALENDAR kun: bugun−6 00:00 … bugun oxiri
#   • analytics.py (11 joyda)  → SURILUVCHI OYNA: `tenant_now() - timedelta(days=7)`
#     ya'ni 168 soat orqaga. Bugun 14:00 bo'lsa oyna 7 kun oldingi 14:00 dan
#     boshlanadi → o'sha kunning ERTALABKI savdosi TUSHIB QOLADI, lekin 8-kun
#     qismi hisobga KIRADI. Kun bo'yi raqam "suzib" turardi.
#
# QAROR: hamma joyda KALENDAR KUN (tenant mahalliy zonasi, Toshkent).
#   "7 kun" = bugun−6 00:00:00 … bugun 23:59:59.999999
#   168 soatlik suriluvchi oyna BUTUNLAY olib tashlandi.
#
# Kun soni `days - 1` offset bilan olinadi (bugun ham davr ichida):
#   today=1, week=7, month=30, quarter=90, year=365, all=2000-01-01 dan.

from datetime import date as _date

ALL_TIME_START = _date(2000, 1, 1)

#: period nomi → davr QAMRAGAN kalendar kunlar soni (bugun bilan birga).
PERIOD_DAYS = {
    "today":   1,
    "day":     1,
    "week":    7,
    "month":   30,
    "quarter": 90,
    "year":    365,
}


def parse_date(raw, field: str = "sana"):
    """'YYYY-MM-DD' → `date`. None/'' → None. Buzuq qiymat → HTTP 400.

    Ilgari `datetime.strptime()` to'g'ridan chaqirilardi → buzuq sana
    ushlanmagan `ValueError` berib endpointni 500 qilardi (mijozga "server
    xatosi" ko'rinardi, aslida so'rov xato edi).
    """
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, _date):
        return raw
    from fastapi import HTTPException
    try:
        return datetime.strptime(str(raw).strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=400,
            detail=f"{field} formati noto'g'ri — YYYY-MM-DD kutiladi",
        )


def period_start_date(period: str, today: _date) -> _date:
    """period nomi → davr BOSHLANISH kalendar sanasi (`today` ham davr ichida)."""
    p = (period or "today").strip().lower()
    if p in ("all", "barchasi", "lifetime"):
        return ALL_TIME_START
    return today - timedelta(days=PERIOD_DAYS.get(p, 1) - 1)


def period_dates(period: str = "today", date_from=None, date_to=None, *, tz_name: str = None):
    """(start_date, end_date) — INKLYUZIV kalendar sanalar, tenant zonasida.

    • `date_from`/`date_to` berilsa — USTUN (period e'tiborsiz qoldiriladi).
      Faqat bittasi berilsa, ikkinchisi period/bugundan to'ldiriladi (additiv).
    • KELAJAK KESILADI: `end` hech qachon bugundan katta bo'lmaydi. Soati
      noto'g'ri qurilmadan kelgan kelajak sanali yozuv hisobga kirmasin.
    • So'ralgan davr BUTUNLAY kelajakda bo'lsa (`start > end`) — oraliq bo'sh
      qoladi va so'rov 0 qator beradi (bu ATAYIN: "ertangi hisobot" ≠ "bugun").
    """
    today   = tenant_now(tz_name).date()
    d_from  = parse_date(date_from, "date_from")
    d_to    = parse_date(date_to,   "date_to")

    if d_from is None and d_to is None:
        start, end = period_start_date(period, today), today
    else:
        start = d_from if d_from is not None else period_start_date(period, today)
        end   = d_to   if d_to   is not None else today

    if end > today:
        end = today
    return start, end


def period_bounds(period: str = "today", date_from=None, date_to=None, *, tz_name: str = None):
    """(start, end) aware TIMESTAMP oralig'i — `created_at >= start AND <= end` uchun.

    `start` = boshlanish kuni 00:00 (mahalliy), `end` = tugash kuni
    23:59:59.999999 — ammo BUGUN uchun `tenant_now()` da kesiladi (kelajak
    soatli yozuv "bugun" ga qo'shilmasin; `/analytics/store-margin` allaqachon
    shu qoida bilan ishlardi).

    Chegarasi `<` emas, `<=` — mavjud analytics/profit filtrlari shunday.
    """
    s_date, e_date = period_dates(period, date_from, date_to, tz_name=tz_name)
    start, _       = day_bounds(s_date, tz_name)
    _, next_day    = day_bounds(e_date, tz_name)
    end            = next_day - timedelta(microseconds=1)
    now            = tenant_now(tz_name)
    return start, min(end, now)


def report_bounds(date_from=None, date_to=None, *, default_days: int = 30, tz_name: str = None):
    """Hisobot oralig'i → (boshlanish 00:00.000, tugash 23:59:59.999999) mahalliy zonada.

    `routers/report.py:_dates()` dan KO'CHIRILDI — xulqi AYNAN saqlangan
    (standart 30 kun orqaga, kelajak KESILMAYDI: hisobot ekranida do'konchi
    o'zi oraliq tanlaydi). Yagona o'zgarish: buzuq sana 500 emas, 400 beradi.

    ═══ TUZATILGAN XATO (P0-3) ═══
    Avval ikkala chegara ham `strptime(...)` = o'sha kun 00:00:00 edi. Chaqiruvchi
    servislar `created_at <= date_to` filtri bilan ishlaydi, ya'ni TUGASH KUNINING
    O'ZI QAMRALMASDI. `report.html` standart holatda `date_from = date_to = bugun`
    yuboradi → "Bugun" foyda/savdo hisoboti HAR DOIM BO'SH (0 so'm) chiqardi.

    Ikkinchi xato: naive `datetime` — server UTC, shuning uchun kun chegarasi
    Toshkent kunidan 5 soat siljirdi. Endi `day_bounds()` (tenant mahalliy,
    aware) ishlatiladi.
    """
    today_local = tenant_now(tz_name).date()
    d_from = parse_date(date_from, "date_from") or today_local - timedelta(days=default_days)
    d_to   = parse_date(date_to,   "date_to")   or today_local

    start, _    = day_bounds(d_from, tz_name)   # d_from 00:00 (mahalliy)
    _, next_day = day_bounds(d_to, tz_name)     # d_to + 1 kun 00:00 (mahalliy)
    # Servislar `<=` ishlatadi → ertangi yarim tunni QAMRAMASLIK uchun 1 mks orqaga.
    return start, next_day - timedelta(microseconds=1)
