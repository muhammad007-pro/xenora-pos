"""cash_movements — smena ichida kassadan pul olish / qo'shish (inkassatsiya)

Revision ID: e7a3c5d91b24
Revises: d4e8b2f61a07
Create Date: 2026-10-13

NEGA: egasi smena davomida yashikdan pul olsa, buni yozadigan joy yo'q edi —
smena yopilganda u KAMOMAD bo'lib ko'rinardi (1001 BARAKA: 30 kunda −20,7 mln).
`expected_cash` endi: ... − olingan + qo'shilgan.

⚠️ MA'LUMOT O'ZGARMAYDI: faqat bo'sh jadval yaratiladi. Yozuv yo'q smenada
Z-hisob bit-bitiga avvalgidek.

IDEMPOTENT: jadval allaqachon bo'lsa — hech narsa qilinmaydi.
"""
from alembic import context, op
import sqlalchemy as sa

revision = "e7a3c5d91b24"
down_revision = "d4e8b2f61a07"
branch_labels = None
depends_on = None


def _bor(bind) -> bool:
    return "cash_movements" in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    if not context.is_offline_mode() and _bor(op.get_bind()):
        return
    op.create_table(
        "cash_movements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("cafes.id"), nullable=True),
        sa.Column("shift_id", sa.Integer(), sa.ForeignKey("shifts.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_cash_movements_id", "cash_movements", ["id"])
    op.create_index("ix_cash_movements_tenant_id", "cash_movements", ["tenant_id"])
    op.create_index("ix_cash_movements_shift_id", "cash_movements", ["shift_id"])


def downgrade() -> None:
    if context.is_offline_mode() or _bor(op.get_bind()):
        op.drop_index("ix_cash_movements_shift_id", table_name="cash_movements")
        op.drop_index("ix_cash_movements_tenant_id", table_name="cash_movements")
        op.drop_index("ix_cash_movements_id", table_name="cash_movements")
        op.drop_table("cash_movements")
