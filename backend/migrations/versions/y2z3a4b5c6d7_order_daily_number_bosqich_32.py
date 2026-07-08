"""order_daily_number_bosqich_32

orders jadvaliga daily_number (nullable Integer) qo'shish.
Ko'rinadigan kunlik chek raqami — har tenant + har kun bo'yicha 1 dan ketma-ket.
order_number (ichki unikal id) o'zgarmaydi. Eski buyurtmalarda NULL qoladi.

Revision ID: y2z3a4b5c6d7
Revises: x1y2z3a4b5c6
Create Date: 2026-06-22 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'y2z3a4b5c6d7'
down_revision: Union[str, None] = 'x1y2z3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('orders', sa.Column('daily_number', sa.Integer(), nullable=True))
    op.create_index('ix_orders_daily_number', 'orders', ['daily_number'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_orders_daily_number', table_name='orders')
    op.drop_column('orders', 'daily_number')
