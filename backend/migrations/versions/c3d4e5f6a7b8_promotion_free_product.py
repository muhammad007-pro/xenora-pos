"""Promotion.free_product_id + free_qty_per_set — buy X get Y (BOSHQA mahsulot bepul, Faza 3b)

buy_x_get_y hozir faqat BIR XIL mahsulot (Faza 3a). 3b uchun BEPUL Y mahsulot kerak:
  free_product_id   — bepul beriladigan Y mahsulot (NULL → 3a, bir xil mahsulot)
  free_qty_per_set  — har (buy_qty+get_qty) to'plamга nechа Y bepul (default 1)

IDEMPOTENT: ADD COLUMN IF NOT EXISTS — jonli DB'da bir marta qo'shiladi, mavjud promotion'lar
buzilmaydi (yangi ustunlar NULLABLE). downgrade: DROP IF EXISTS.

Revision ID: c3d4e5f6a7b8
Revises: d0e1f2a3b4c5
Create Date: 2026-07-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'd0e1f2a3b4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        "ALTER TABLE promotions ADD COLUMN IF NOT EXISTS free_product_id INTEGER REFERENCES products(id)"
    ))
    conn.execute(sa.text(
        "ALTER TABLE promotions ADD COLUMN IF NOT EXISTS free_qty_per_set INTEGER DEFAULT 1"
    ))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE promotions DROP COLUMN IF EXISTS free_qty_per_set"))
    conn.execute(sa.text("ALTER TABLE promotions DROP COLUMN IF EXISTS free_product_id"))
