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
