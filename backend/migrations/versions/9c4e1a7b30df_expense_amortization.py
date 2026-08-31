"""expenses.amortize_from / amortize_to — xarajatni kunlarga taqsimlash

Revision ID: 9c4e1a7b30df
Revises: 3f7a2c9e1b04
Create Date: 2026-08-31

NEGA: Fazza Parfum 22-avgustda ARENDA 1.8M + ISHCHI 2.5M + UJN 1.5M kiritdi.
Uchalasining `expense_date` i ham 22-avgust bo'lgani uchun 5 800 000 BITTA
KUNGA tushdi va o'sha kun sof foydasi −5 268 070 bo'lib ko'rindi. Aslida bu
oylik xarajat: 1–31 avgust davrini qoplaydi.

Endi xarajat qaysi davrni qoplashi aniq ko'rsatiladi va foyda hisobotlarida
kunlarga proporsional taqsimlanadi (services/expense_allocation.py).

⚠️ `is_recurring` ATAYIN ISHLATILMADI — u boshqa savolga javob beradi
("keyingi oy takrorlansinmi?"), amortizatsiya esa "qancha davrni qoplaydi?"
degan savolga. Bitta bayroqni ikki ma'noda ishlatish shu loyihada qayta-qayta
tuzatilgan xato sinfi.

XAVFSIZLIK: ikkala ustun ham NULLABLE, default YO'Q. Mavjud barcha qatorlarda
NULL qoladi -> `is_amortized()` False -> hisob AYNAN AVVALGIDEK. Ma'lumot
o'zgartirilmaydi, faqat ikkita bo'sh ustun qo'shiladi.
"""
from alembic import op
import sqlalchemy as sa

revision = "9c4e1a7b30df"
down_revision = "3f7a2c9e1b04"
branch_labels = None
depends_on = None

_COLS = ("amortize_from", "amortize_to")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for c in _COLS:
            op.execute(f"ALTER TABLE expenses ADD COLUMN IF NOT EXISTS {c} DATE")
    else:
        existing = {c["name"] for c in sa.inspect(bind).get_columns("expenses")}
        for c in _COLS:
            if c not in existing:
                op.add_column("expenses", sa.Column(c, sa.Date(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for c in _COLS:
            op.execute(f"ALTER TABLE expenses DROP COLUMN IF EXISTS {c}")
    else:
        for c in _COLS:
            op.drop_column("expenses", c)
