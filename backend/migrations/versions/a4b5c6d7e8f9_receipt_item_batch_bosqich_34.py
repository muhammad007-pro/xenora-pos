"""receipt_item_batch_bosqich_34

purchase_receipt_items jadvaliga partiya maydonlari (nullable):
  batch_number     — seriya / partiya raqami
  expiry_date      — yaroqlilik muddati
  manufacture_date — ishlab chiqarilgan sana

Maqsad: priyomka confirm'da ProductBatch (partiya) yaratish uchun item darajasida
seriya + muddat saqlanadi. Hammasi nullable — eski priyomkalarda NULL qoladi (buzilmaydi).

Revision ID: a4b5c6d7e8f9
Revises: z3a4b5c6d7e8
Create Date: 2026-06-23 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'a4b5c6d7e8f9'
down_revision: Union[str, None] = 'z3a4b5c6d7e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('purchase_receipt_items', sa.Column('batch_number', sa.String(100), nullable=True))
    op.add_column('purchase_receipt_items', sa.Column('expiry_date', sa.Date(), nullable=True))
    op.add_column('purchase_receipt_items', sa.Column('manufacture_date', sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column('purchase_receipt_items', 'manufacture_date')
    op.drop_column('purchase_receipt_items', 'expiry_date')
    op.drop_column('purchase_receipt_items', 'batch_number')
