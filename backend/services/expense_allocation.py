"""XARAJATNI KUNLARGA TAQSIMLASH (amortizatsiya) — YAGONA HISOB MANBAI.

═══ MUAMMO (Fazza Parfum, 2026-08) ═══
Do'kon 22-avgustda ARENDA 1 800 000 + ISHCHI 2 500 000 + UJN 1 500 000
kiritdi. Uchalasi ham `expense_date = 22-avgust` bo'lgani uchun 5 800 000
BITTA KUNGA tushdi:
    22-avgust yalpi foyda  +531 930
    22-avgust xarajat    −5 800 000
    22-avgust SOF FOYDA  −5 268 070   ← sun'iy minus
Aslida bu OYLIK xarajat: 1-31 avgust davrini qoplaydi, bir kunni emas.

═══ NEGA `is_recurring` ISHLATILMAYDI ═══
U BOSHQA savolga javob beradi:
    is_recurring  -> "keyingi oy TAKRORLANSINMI?"
    amortizatsiya -> "bu pul QANCHA DAVRNI qoplaydi?"
Ular ustma-ust tushmaydi: yillik litsenziya oylik takrorlanmaydi, lekin
12 oyga taqsimlanishi kerak; bugungi transport puli takrorlanadi, lekin
BIR KUNLIK. Bitta bayroqni ikki ma'noda ishlatish — shu loyihada qayta-qayta
tuzatilgan xato sinfi (`pack_size`, vozvrat markeri). Shuning uchun ALOHIDA
maydonlar: `Expense.amortize_from` / `amortize_to` (ikkalasi NULL bo'lsa —
taqsimlanmaydi, ya'ni ESKI XATTI-HARAKAT).

═══ IKKI XIL KO'RSATKICH (ARALASHTIRILMAYDI) ═══
`utils/cashflow.py` dagi qoidaning aynan o'zi:
  1) FOYDA (accrual) — xarajat QAYSI DAVRGA tegishli bo'lsa o'shanga.
     Iste'molchilar: `/profit/summary`, `/profit/timeline`.
  2) KASSA (cash) — pul QACHON CHIQQAN bo'lsa o'sha kunga.
     Iste'molchi: `/profit/expenses` (to'lovlar reyestri) — SHU FAYLNI
     CHAQIRMAYDI, `expense_date` ni o'zgarishsiz ko'rsatadi.
Bir o'lchovni ikkinchisiga qo'shish = ikki marta hisoblash.

═══ YAXLITLASH — KÜMÜLATIV TAQSIMLASH ═══
"Oxirgi kunga qoldiqni qo'shish" usuli BUZILADI: hisobot oralig'i davr
o'rtasida tugasa qoldiq yo umuman ko'rinmaydi, yo ikki oraliqda ikki marta
chiqadi. Shuning uchun har kun uchun TO'PLANGAN farq olinadi:

    cum(i) = round(amount × i / N, 2)      (cum(0)=0, cum(N)=amount AYNAN)
    ulush([a..b]) = cum(i_b) − cum(i_{a−1})

KAFOLATLAR (test bilan qotirilgan):
  • butun davr yig'indisi = amount AYNAN (1 tiyin ham farq yo'q)
  • qo'shni oraliqlar (1–15 + 16–30) = to'liq davr — bo'shliq ham,
    ustma-ustlik ham YO'Q
  • har qanday qism-oraliq ≤ amount
"""
from __future__ import annotations

from datetime import date as Date, timedelta
from typing import Dict, Iterable, Optional, Sequence

from sqlalchemy.orm import Session

from models import Expense


def is_amortized(exp) -> bool:
    """Bu xarajat kunlarga taqsimlanadimi?"""
    return bool(getattr(exp, "amortize_from", None) and getattr(exp, "amortize_to", None))


def period_of(exp):
    """(from, to) — taqsimlash davri. Taqsimlanmasa None.

    `to < from` bo'lsa (buzuq yozuv) — taqsimlanmagan deb qaraladi, chunki
    manfiy uzunlikdagi davr ma'nosiz va u nolga bo'lishga olib borardi.
    """
    if not is_amortized(exp):
        return None
    a, b = exp.amortize_from, exp.amortize_to
    return (a, b) if b >= a else None


def _cum(amount: float, i: int, n: int) -> float:
    """Davr boshidan `i`-kungacha to'plangan ulush.

    `i >= n` da AYNAN `amount` qaytadi — float ko'paytma/bo'linma qoldig'i
    (999999.9999999999 kabi) jami summani buzmasin.
    """
    if i <= 0:
        return 0.0
    if i >= n:
        return round(amount, 2)
    return round(amount * i / n, 2)


def share_in_range(exp, start: Date, end: Date) -> float:
    """Shu xarajatning [start, end] oralig'iga tegishli qismi.

    Taqsimlanmagan xarajat — ESKI mantiq: `expense_date` oraliqda bo'lsa
    to'liq summa, bo'lmasa 0.
    """
    amount = float(exp.amount or 0)
    per = period_of(exp)
    if per is None:
        return amount if start <= exp.expense_date <= end else 0.0

    p_from, p_to = per
    n = (p_to - p_from).days + 1

    # Oraliqni davr ichiga qisamiz
    a = max(start, p_from)
    b = min(end, p_to)
    if a > b:
        return 0.0

    i_b = (b - p_from).days + 1     # 1..n
    i_a = (a - p_from).days         # a dan OLDINGI kun indeksi (0..n-1)
    return round(_cum(amount, i_b, n) - _cum(amount, i_a, n), 2)


# ─── Bucket (kun / hafta / oy) yordamchilari ─────────────────────────────────
# PostgreSQL `date_trunc('week', ...)` DUSHANBAdan boshlaydi — `weekday()` ham
# dushanbada 0 beradi, ya'ni timeline kalitlari mos tushadi.

def bucket_start(d: Date, trunc: str) -> Date:
    if trunc == "month":
        return d.replace(day=1)
    if trunc == "week":
        return d - timedelta(days=d.weekday())
    return d


def bucket_next(b: Date, trunc: str) -> Date:
    if trunc == "month":
        return (b.replace(day=28) + timedelta(days=4)).replace(day=1)
    if trunc == "week":
        return b + timedelta(days=7)
    return b + timedelta(days=1)


def _buckets(start: Date, end: Date, trunc: str) -> Iterable[tuple]:
    b = bucket_start(start, trunc)
    while b <= end:
        nxt = bucket_next(b, trunc)
        yield b, nxt - timedelta(days=1)
        b = nxt


# ─── DB bilan ishlaydigan yuza ────────────────────────────────────────────────

def _fetch(db: Session, current_user, start: Date, end: Date) -> Sequence[Expense]:
    """Oraliqqa TEGISHLI BO'LISHI MUMKIN bo'lgan xarajatlar.

    Taqsimlangan xarajat `expense_date` oraliqdan TASHQARIDA bo'lsa ham
    oraliqqa ulush berishi mumkin (22-avgustda kiritilgan, 1-avgustdan
    taqsimlangan). Shuning uchun filtr ikki shartning BIRI bilan.
    """
    from deps import apply_tenant_filter

    q = db.query(Expense).filter(
        (Expense.expense_date.between(start, end))
        | (
            Expense.amortize_from.isnot(None)
            & Expense.amortize_to.isnot(None)
            & (Expense.amortize_from <= end)
            & (Expense.amortize_to >= start)
        )
    )
    return apply_tenant_filter(q, Expense, current_user).all()


def total_in_range(db: Session, current_user, start: Date, end: Date) -> float:
    """Davrga TEGISHLI xarajat (accrual). `/profit/summary` shuni ishlatadi."""
    return round(sum(share_in_range(e, start, end) for e in _fetch(db, current_user, start, end)), 2)


def breakdown_in_range(db: Session, current_user, start: Date, end: Date) -> dict:
    """UI uchun: "Bu davrga tegishli X so'm (jami Y so'm dan)".

    `raw` — taqsimlangan xarajatlarning TO'LIQ summasi (davr qanchaligidan
    qat'i nazar), ya'ni do'konchi "5 800 000 kiritgandim, nega 1 850 000?"
    deb hayron bo'lmasligi uchun ko'rsatiladigan son.
    """
    rows = _fetch(db, current_user, start, end)
    allocated = 0.0
    raw = 0.0
    n_amort = 0
    for e in rows:
        sh = share_in_range(e, start, end)
        if sh == 0:
            continue
        allocated += sh
        raw += float(e.amount or 0)
        if is_amortized(e):
            n_amort += 1
    return {
        "allocated":       round(allocated, 2),
        "raw":             round(raw, 2),
        "amortized_count": n_amort,
        "is_split":        n_amort > 0 and abs(allocated - raw) > 0.005,
    }


def by_bucket(db: Session, current_user, start: Date, end: Date, trunc: str) -> Dict[str, float]:
    """{ "YYYY-MM-DD": xarajat } — `/profit/timeline` grafigi uchun.

    Kalit `date_trunc` natijasi bilan bir xil (bucket boshlanish sanasi).
    """
    rows = _fetch(db, current_user, start, end)
    out: Dict[str, float] = {}
    for b_start, b_end in _buckets(start, end, trunc):
        a = max(b_start, start)
        b = min(b_end, end)
        if a > b:
            continue
        amt = sum(share_in_range(e, a, b) for e in rows)
        if amt:
            out[b_start.isoformat()] = round(amt, 2)
    return out


# ─── Kiritish/tahrirlashda davrni aniqlash ───────────────────────────────────

def month_bounds(d: Date):
    """`d` tushgan KALENDAR OY chegarasi.

    NEGA kalendar oyi, "kiritilgan kundan 30 kun" emas: takrorlanuvchi
    xarajatlar ustma-ust tushmasligi kerak. 22-avg + 30 kun = 20-sen, keyingi
    oy 22-sen dan boshlanadi -> 21-sen BO'SHLIQ; sana biroz surilsa esa
    USTMA-UST tushadi va oy jami buziladi. Kalendar oylari mukammal yopishadi.
    """
    first = d.replace(day=1)
    return first, bucket_next(first, "month") - timedelta(days=1)


def clamp_from(p_from: Date, tenant_start: Optional[Date]) -> Date:
    """`amortize_from` do'kon tizimga kirgan sanadan OLDINGA o'tmasin.

    Aks holda xarajat do'kon hali ishlamagan kunlarga tarqalib, o'sha kunlarni
    sun'iy zarar qilib ko'rsatardi.
    """
    if tenant_start and p_from < tenant_start:
        return tenant_start
    return p_from
