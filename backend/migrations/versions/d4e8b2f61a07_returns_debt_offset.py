"""returns.debt_offset — aralash (naqd+nasiya) chek vozvratida qarzdan yopilgan qism

Revision ID: d4e8b2f61a07
Revises: c9f2a71d3e84
Create Date: 2026-10-13

NEGA: Z-hisobot naqd vozvratni `Return.total_amount` dan olardi. Aralash
chekda (170 000 naqd + 130 000 nasiya) to'liq vozvrat qilinsa, kassadan
170 000 chiqadi, 130 000 esa qarzdan yopiladi — lekin `expected_cash`
300 000 ga kamayardi. Endi tasdiqlashda qarz qismi shu ustunga yoziladi va
naqd = total_amount − debt_offset.

⚠️ MA'LUMOT O'ZGARMAYDI: ustun NULL bilan qo'shiladi. NULL → 0 deb o'qiladi,
ya'ni eski vozvratlarning Z-hisobi bit-bitiga avvalgidek.

IDEMPOTENT: ustun allaqachon bo'lsa — hech narsa qilinmaydi.
"""
from alembic import context, op
import sqlalchemy as sa

revision = "d4e8b2f61a07"
down_revision = "c9f2a71d3e84"
branch_labels = None
depends_on = None


def _bor(bind) -> bool:
    insp = sa.inspect(bind)
    if "returns" not in insp.get_table_names():
        return True                 # jadval yo'q — qo'shadigan joy ham yo'q
    return any(c["name"] == "debt_offset" for c in insp.get_columns("returns"))


def upgrade() -> None:
    if context.is_offline_mode() or not _bor(op.get_bind()):
        op.add_column("returns", sa.Column("debt_offset", sa.Float(), nullable=True))


def downgrade() -> None:
    if context.is_offline_mode() or _bor(op.get_bind()):
        op.drop_column("returns", "debt_offset")
