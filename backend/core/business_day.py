"""
Hisobot kuni (ish kuni) — kalendar yoki smena bo'yicha. YAGONA MANBA.

═══ MUAMMO (jonli, MANHATTAN 2026-10) ═══
Kechasi 01:00–02:00 gacha ishlaydigan do'konda yarim tundan keyingi savdo
kalendar bo'yicha ERTANGI kunga tushadi. Egasi "kecha 12 mln sotdim" deydi,
dashboard esa 11 mln + ertangi kunda ortiqcha 760 000 ko'rsatadi.

═══ IKKI REJIM (tenant_settings: config_name="report_day", data={"mode": ...}) ═══
  • "calendar" (STANDART) — Toshkent 00:00 … 00:00. Avvalgi xulq, BIT-BA-BIT:
    `window()` aynan `ts >= start AND ts <= end` ni qaytaradi.
  • "shift" — buyurtma SMENA OCHILGAN kunga yoziladi.

═══ SMENA QOIDASI VA HIMOYA ═══
Buyurtma smena ochilgan kunga (D) faqat D 00:00 … D+1 06:00 oralig'ida
yaratilgan bo'lsa yoziladi. Undan keyingisi — kalendar kuniga.
Sabab — jonli ma'lumot: smenalar yopilmay qoladi (MANHATTAN #52 10.04 dan
beri ochiq, 1001 BARAKA #56 4 kun ochiq turgan). Himoyasiz qoida bir
haftalik savdoni bitta kunga yig'ib qo'yardi.
`shift_id IS NULL` (smenasiz sotuv) — doim kalendar kuni, YO'QOLMAYDI.

Natijada farq FAQAT bitta holatda: buyurtma C kuni 00:00–06:00 da, smenasi
esa C−1 kuni ochilgan → ish kuni C−1. Qolgan hamma narsa kalendar.

═══ NEGA SQL'da sana funksiyasi YO'Q ═══
`func.date()` / `AT TIME ZONE` / `date_trunc` server zonasida (UTC) kesadi
va SQLite testlarida yo'q. Shu sabab filtr faqat VAQT SOLISHTIRISHLARI
bilan quriladi (ikkala dialektda bir xil), kunlik guruhlash esa Python'da
`day_of()` orqali — jami va kunlik qatorlar AYNAN bir qoidada bo'ladi.

Oraliq chegarasida ko'chadigan buyurtmalar faqat ikki joyda: boshlanish
kuni ertalabki 6 soat (oldingi kunga KETADI) va tugash kunidan keyingi
ertalabki 6 soat (shu davrga KELADI). Davr ichidagi ko'chishlar davrdan
chiqmaydi. Shuning uchun filtr — kalendar sharti + ikki kichik tuzatish.

═══ KECH OCHILGAN SMENA (data["late_open"] = "HH:MM", standart O'CHIQ) ═══
Jonli (MANHATTAN 2026-10-22): kassir ertangi kunning smenasini 23:57 da
ochdi → smena kuni 22.10 bo'ldi, himoya 23.10 06:00 da tugadi va 24.10
00:02 dagi chek 24.10 ga tushdi (egasi uchun bu 23.10 savdosi).
Yoqilsa: shu soatdan KEYIN ochilgan smenaning kuni = ochilgan kun + 1.
Qolgan qoida o'zgarmaydi (00:00–06:00 himoyasi shu kunga nisbatan).
Faqat yarim tunda smena ALMASHTIRMAYDIGAN do'kon uchun — 24/7 ishlaydigan
BARAKA (27) da tungi smena 23:xx da ochiladi va o'sha kunga tegishli,
u yerda YOQILMAYDI. O'chiq bo'lsa xulq bit-ba-bit avvalgidek.
"""
from datetime import date, datetime, time, timedelta
from typing import Optional

from sqlalchemy import and_, not_, or_

from core.timeutils import day_bounds, tenant_now, to_local

CONFIG_NAME = "report_day"
MODE_CALENDAR = "calendar"
MODE_SHIFT = "shift"
MODES = (MODE_CALENDAR, MODE_SHIFT)

#: Smena ochilgan kunning ertasi shu soatgacha hali o'sha ish kuni.
SHIFT_GRACE_HOURS = 6
_GRACE = timedelta(hours=SHIFT_GRACE_HOURS)
_EPS = timedelta(microseconds=1)


#: data kaliti: "HH:MM" — shu vaqtdan keyin ochilgan smena ertangi kunniki.
LATE_OPEN_KEY = "late_open"


def _config(db, tenant_id) -> dict:
    if tenant_id is None:
        return {}
    from models import TenantSettings
    row = (
        db.query(TenantSettings.data)
        .filter(TenantSettings.tenant_id == tenant_id,
                TenantSettings.config_name == CONFIG_NAME)
        .first()
    )
    data = row[0] if row else None
    return data if isinstance(data, dict) else {}


def _parse_late_open(value) -> Optional[time]:
    """"HH:MM" → time. Yo'q / noto'g'ri → None (o'chiq). 00:00 ham o'chiq —
    yarim tunda ochilgan smena allaqachon o'z kunida."""
    if not isinstance(value, str):
        return None
    try:
        t = datetime.strptime(value.strip(), "%H:%M").time()
    except ValueError:
        return None
    return t if t != time(0, 0) else None


def get_mode(db, tenant_id) -> str:
    """Tenant rejimi. Yozuv yo'q / noma'lum qiymat → "calendar" (xavfsiz standart)."""
    mode = _config(db, tenant_id).get("mode")
    return mode if mode in MODES else MODE_CALENDAR


def get_late_open(db, tenant_id) -> Optional[time]:
    """Kech ochilgan smena chegarasi. Standart — None (o'chiq)."""
    return _parse_late_open(_config(db, tenant_id).get(LATE_OPEN_KEY))


def _save(db, tenant_id, **changes) -> dict:
    # Bitta qator ikki kalitni saqlaydi — rejimni o'zgartirish late_open ni
    # o'chirib yubormasin (va aksincha).
    from core.tenant_config import set_tenant_config
    data = dict(_config(db, tenant_id))
    for k, v in changes.items():
        if v is None:
            data.pop(k, None)
        else:
            data[k] = v
    set_tenant_config(db, tenant_id, CONFIG_NAME, data)
    return data


def set_mode(db, tenant_id, mode: str) -> str:
    if mode not in MODES:
        raise ValueError(f"report_day mode noto'g'ri: {mode!r}")
    _save(db, tenant_id, mode=mode)
    return mode


def set_late_open(db, tenant_id, value: Optional[str]) -> Optional[str]:
    """"HH:MM" — yoqish, None — o'chirish."""
    if value is not None and _parse_late_open(value) is None:
        raise ValueError(f"late_open noto'g'ri: {value!r} (HH:MM, 00:00 dan farqli)")
    _save(db, tenant_id, **{LATE_OPEN_KEY: value})
    return value


class BusinessDay:
    """Bitta so'rov uchun ish kuni qoidasi (tenant + rejim keshlanadi).

    Ishlatish:
        bd = BusinessDay(db, current_user)
        start, end = bd.period_bounds(period, date_from, date_to)
        q = q.filter(bd.window(Order.created_at, Order.shift_id, start, end))
        kun = bd.day_of(order.created_at, order.shift_id)
    """

    def __init__(self, db, current_user=None, *, tenant_id=None, mode: Optional[str] = None,
                 late_open: Optional[str] = None):
        self.db = db
        if tenant_id is None and current_user is not None:
            from deps import resolve_tenant_id
            tenant_id = resolve_tenant_id(db, current_user)
        self.tenant_id = tenant_id
        if mode is None:
            cfg = _config(db, tenant_id)
            mode = cfg.get("mode")
            late_open = cfg.get(LATE_OPEN_KEY)
        self.mode = mode if mode in MODES else MODE_CALENDAR
        late = _parse_late_open(late_open)
        #: Kech ochilish chegarasi yarim tundan keyingi siljish sifatida; None — o'chiq.
        self._late = timedelta(hours=late.hour, minutes=late.minute) if late else None
        self._shift_day: dict = {}

    @property
    def is_shift(self) -> bool:
        return self.mode == MODE_SHIFT and self.tenant_id is not None

    # ── "bugun" ────────────────────────────────────────────────────────────
    def today(self) -> date:
        """Joriy ish kuni. Smena rejimida 00:00–06:00 da KECHA ochilgan smena
        hali ochiq bo'lsa — kechagi sana (kassir hali o'sha kunni sotyapti)."""
        now = tenant_now()
        cal = now.date()
        if not self.is_shift or now.hour >= SHIFT_GRACE_HOURS:
            return cal
        from models import Shift
        midnight, _ = day_bounds(cal)
        open_from_yesterday = (
            self._shifts_of_day_before(midnight)
            .filter(Shift.end_time.is_(None))
            .first()
        )
        return cal - timedelta(days=1) if open_from_yesterday else cal

    def period_dates(self, period="today", date_from=None, date_to=None):
        from core.timeutils import period_dates
        return period_dates(period, date_from, date_to, today=self.today())

    def period_bounds(self, period="today", date_from=None, date_to=None):
        from core.timeutils import period_bounds
        return period_bounds(period, date_from, date_to, today=self.today())

    # ── SQL filtr ──────────────────────────────────────────────────────────
    def _shifts_of_day_before(self, midnight):
        """`midnight` dan oldingi ISH kuniga tegishli smenalar (so'rov).

        O'chiq: o'sha kalendar kunida ochilganlar [m−1k, m).
        Kech ochilish yoqilgan: [m−2k+chegara, m−1k+chegara) — oldingi kuni
        chegaradan keyin ochilgan smena shu kunniki, o'sha kuni chegaradan
        keyin ochilgani esa ertangi kunniki."""
        from models import Shift
        lo = midnight - timedelta(days=1)
        if self._late is not None:
            lo = lo - timedelta(days=1) + self._late
        return (
            self.db.query(Shift.id)
            .filter(Shift.tenant_id == self.tenant_id,
                    Shift.start_time >= lo,
                    Shift.start_time < lo + timedelta(days=1))
        )

    def _shift_ids_opened_before(self, midnight) -> list:
        return [r[0] for r in self._shifts_of_day_before(midnight).all()]

    @staticmethod
    def _midnight_in(lo, hi):
        """lo < m <= hi bo'lgan mahalliy yarim tun (oraliq < 24 soat → ko'pi bilan bitta)."""
        m, _ = day_bounds(hi)
        return m if m > lo else None

    def window(self, ts_col, shift_col, start, end):
        """`ts_col >= start AND ts_col <= end` ning ish kuni varianti (drop-in).

        Kalendar rejimida AYNAN o'sha shartni qaytaradi (GOLDEN).
        """
        cal = and_(ts_col >= start, ts_col <= end)
        if not self.is_shift:
            return cal

        cond = cal
        # 1) Boshlanish: start kunining 00:00–06:00 dagi, KECHA ochilgan smena
        #    buyurtmalari oldingi kunga tegishli → CHIQARILADI.
        a_out = self._midnight_in(start - _GRACE, start)
        if a_out is not None:
            ids = self._shift_ids_opened_before(a_out)
            if ids:
                # `isnot(None)` SHART: NULL IN (...) → NULL, NOT NULL → NULL va
                # smenasiz buyurtma jimgina yo'qolardi.
                cond = and_(cal, not_(and_(shift_col.isnot(None),
                                           shift_col.in_(ids),
                                           ts_col < a_out + _GRACE)))
        # 1b) Kech ochilish: tugash kunida ochilgan ERTANGI smena buyurtmalari
        #     (23:57 dan keyingi) ertangi kunniki → CHIQARILADI.
        if self._late is not None:
            m_end, _ = day_bounds(end)
            ids = self._shift_ids_opened_before(m_end + timedelta(days=2))
            if ids:
                cond = and_(cond, not_(and_(shift_col.isnot(None),
                                            shift_col.in_(ids),
                                            ts_col >= m_end)))
        # 2) Tugash: keyingi kunning 00:00–06:00 dagi, OXIRGI kunda ochilgan
        #    smena buyurtmalari shu davrga tegishli → QO'SHILADI.
        a_in = self._midnight_in(max(start, end - _GRACE), end + _EPS)
        if a_in is not None:
            ids = self._shift_ids_opened_before(a_in)
            if ids:
                cond = or_(cond, and_(shift_col.isnot(None),
                                      shift_col.in_(ids),
                                      ts_col > end,
                                      ts_col < a_in + _GRACE))
        # 2b) Kech ochilish: boshlanish kunining smenasi KECHA kechqurun ochilgan
        #     bo'lsa, uning yarim tungacha bo'lgan buyurtmalari → QO'SHILADI.
        if self._late is not None:
            m_start, _ = day_bounds(start)
            if start == m_start:
                ids = self._shift_ids_opened_before(m_start + timedelta(days=1))
                if ids:
                    cond = or_(cond, and_(shift_col.isnot(None),
                                          shift_col.in_(ids),
                                          ts_col >= m_start - timedelta(days=1),
                                          ts_col < start))
        return cond

    # ── Python guruhlash ───────────────────────────────────────────────────
    def _opened_on(self, shift_id) -> Optional[date]:
        if shift_id not in self._shift_day:
            from models import Shift
            row = self.db.query(Shift.start_time).filter(Shift.id == shift_id).first()
            day = None
            if row and row[0]:
                local = to_local(row[0])
                day = local.date()
                if self._late is not None and local - day_bounds(local)[0] >= self._late:
                    day += timedelta(days=1)
            self._shift_day[shift_id] = day
        return self._shift_day[shift_id]

    def day_of(self, ts, shift_id=None) -> Optional[date]:
        """Yozuvning ish kuni. `window()` bilan AYNAN bir qoida."""
        if ts is None:
            return None
        local = to_local(ts)
        cal = local.date()
        if not self.is_shift or shift_id is None:
            return cal
        if self._late is None and local.hour >= SHIFT_GRACE_HOURS:
            return cal
        sd = self._opened_on(shift_id)
        prev = cal - timedelta(days=1)
        if local.hour < SHIFT_GRACE_HOURS and sd == prev:
            return prev
        if self._late is not None and sd == cal + timedelta(days=1):
            return sd
        return cal


def shift_of_payment():
    """Payment uchun smena ustuni (Payment'da shift_id yo'q — buyurtmadan).

    Korrelyatsiyalangan subquery: JOIN qo'shilmaydi, shuning uchun buyurtmasiz
    to'lov ham (order_id NULL) yo'qolmaydi va qator soni o'zgarmaydi.
    """
    from sqlalchemy import select
    from models import Order, Payment
    return (
        select(Order.shift_id)
        .where(Order.id == Payment.order_id)
        .correlate(Payment)
        .scalar_subquery()
    )
