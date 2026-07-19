"""sodiqlik S0: customers.discount_percent ustuni

Doimiy mijozga avtomatik % chegirma uchun (0-100). NULLABLE, default 0 → mavjud
mijozlar chegirmasiz (regressiya yo'q). S0'da faqat poydevor — POS/forma/chek
HALI ishlatmaydi (S1/S2 da). IF NOT EXISTS / IF EXISTS bilan idempotent
(B0/B-returns uslubi).

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-07-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        "ALTER TABLE customers ADD COLUMN IF NOT EXISTS discount_percent DOUBLE PRECISION DEFAULT 0"
    ))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE customers DROP COLUMN IF EXISTS discount_percent"))
