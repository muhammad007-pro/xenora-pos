"""shifts.start_time / end_time: timestamp WITHOUT tz -> timestamptz

Revision ID: c9f2a71d3e84
Revises: b3d7f1c92a48
Create Date: 2026-09-30

NEGA: `shifts` — butun bazada YOLG'IZ jadval edi, vaqtni zona belgisiSIZ
saqlaydigan. orders/payments/audit_logs/stock_movements/returns — hammasi
`timestamp with time zone`. Natijasi:

  • `routers/shift.py:116` naive `datetime.now()` yozardi. Server UTC bo'lgani
    uchun bazaga UTC DEVOR VAQTI tushardi, lekin zona belgisi qolmasdi.
  • Pydantic uni `"2026-09-29T17:37:03.442941"` deb OFFSETSIZ berardi.
  • JS `new Date()` offsetsiz ISO satrni spetsifikatsiya bo'yicha MAHALLIY deb
    o'qiydi -> ekranda 17:37, kompyuter soatida esa 22:37. Toshkentda AYNAN
    5 SOAT orqada. Ochiq smena taymeri esa teskari — 5 soat OSHIQ ko'rsatardi.

O'lchangan isbot (prod, 1001 BARAKA smena #11):
    shifts.start_time (naive)       = 2026-09-08 16:57:24
    o'sha smenadagi 1-buyurtma
    orders.created_at (timestamptz) = 2026-09-08 16:57:43+00 = Toshkent 21:57:43
Smena buyurtmadan 19 soniya oldin ochilgan, ya'ni haqiqiy vaqt 21:57:24
Toshkent. Bazadagi 16:57:24 — UTC devor vaqti.

⚠️ MA'LUMOT O'ZGARMAYDI. `USING <ustun> AT TIME ZONE 'UTC'` mavjud naive
qiymatni UTC deb TALQIN qiladi va aynan shu instantni timestamptz sifatida
yozadi. Raqamlar bit-bitiga o'sha:
    2026-09-29 17:37:03.442941  ->  2026-09-29 17:37:03.442941+00
Faqat zona BELGISI qo'shiladi. Prodda SELECT bilan oldindan tekshirilgan
(46 smena, 5 tasi OCHIQ — ochiqlarda `end_time` NULL bo'lib qoladi).

⚠️ USING'siz qilish XATO bo'lardi: PostgreSQL naive qiymatni SESSIYA zonasida
talqin qiladi. Sessiya `Asia/Tashkent` bo'lsa 17:37 -> 12:37 UTC ga aylanib,
har bir smena YANA 5 soat surilardi. Shu sabab 'UTC' ATAYLAB qat'iy yozilgan.

DOWNGRADE: timestamptz -> naive, `USING <ustun> AT TIME ZONE 'UTC'` bilan
(teskari yo'nalishda bu UTC devor vaqtini qaytaradi) — ya'ni migratsiyadan
oldingi holat AYNAN tiklanadi, ma'lumot yo'qolmaydi.

IDEMPOTENT: ustun allaqachon timestamptz bo'lsa — hech narsa qilinmaydi.
SQLite'da (testlar) tegilmaydi: u zonani umuman saqlamaydi, `DateTime` va
`DateTime(timezone=True)` bir xil ustun.
"""
from alembic import context, op
import sqlalchemy as sa

revision = "c9f2a71d3e84"
down_revision = "b3d7f1c92a48"
branch_labels = None
depends_on = None

JADVAL = "shifts"
USTUNLAR = ("start_time", "end_time")


def _ozgartir(ustun: str, tz_ga: bool) -> None:
    """Bitta ustunni o'giradi. `USING` ikkala yo'nalishda ham 'UTC' — qat'iy."""
    op.alter_column(
        JADVAL, ustun,
        existing_type=sa.DateTime(timezone=not tz_ga),
        type_=sa.DateTime(timezone=tz_ga),
        existing_nullable=(ustun == "end_time"),
        postgresql_using=f"{ustun} AT TIME ZONE 'UTC'",
    )


def _tz_holati(bind) -> dict:
    """{ustun: timezone_bormi} — jadval/ustun yo'q bo'lsa kalit ham bo'lmaydi."""
    insp = sa.inspect(bind)
    if JADVAL not in insp.get_table_names():
        return {}
    natija = {}
    for c in insp.get_columns(JADVAL):
        if c["name"] in USTUNLAR:
            natija[c["name"]] = bool(getattr(c["type"], "timezone", False))
    return natija


def upgrade() -> None:
    # OFFLINE (`alembic upgrade --sql`): ulanish MockConnection, introspeksiya
    # mumkin emas -> DDL shartsiz chiqariladi. Bu operatorga migratsiyani
    # ishlatishdan OLDIN aniq SQL ni ko'rish imkonini beradi.
    if context.is_offline_mode():
        for ustun in USTUNLAR:
            _ozgartir(ustun, tz_ga=True)
        return

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return                      # SQLite zonani saqlamaydi — qiladigan ish yo'q

    holat = _tz_holati(bind)
    for ustun in USTUNLAR:
        if ustun not in holat or holat[ustun]:
            continue                # ustun yo'q yoki allaqachon timestamptz
        _ozgartir(ustun, tz_ga=True)


def downgrade() -> None:
    if context.is_offline_mode():
        for ustun in USTUNLAR:
            _ozgartir(ustun, tz_ga=False)
        return

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    holat = _tz_holati(bind)
    for ustun in USTUNLAR:
        if ustun not in holat or not holat[ustun]:
            continue                # ustun yo'q yoki allaqachon naive
        # Teskari yo'nalish: instantni UTC devor vaqtiga qaytaradi —
        # migratsiyadan OLDINGI qiymat aynan tiklanadi.
        _ozgartir(ustun, tz_ga=False)
