"""pachka/dona B-returns: return_items.base_qty ustuni

Pachka QAYTARILGANДА ombor to'g'ri (dona) tiklanishi uchun. base_qty — omborga
qaytariladigan DONA miqdori (pachka: pack_size×qty; dona/oddiy: quantity).
NULLABLE, default YO'Q → mavjud qaytarishlar NULL (tiklashda quantity fallback,
xulq o'zgarmaydi). IF NOT EXISTS / IF EXISTS bilan idempotent (B0 uslubi).

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-07-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        "ALTER TABLE return_items ADD COLUMN IF NOT EXISTS base_qty DOUBLE PRECISION"
    ))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE return_items DROP COLUMN IF EXISTS base_qty"))
