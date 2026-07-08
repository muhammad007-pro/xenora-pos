"""order_shift_id_bosqich_31

orders jadvaliga shift_id (nullable FK -> shifts) qo'shish.
Z-hisobot uchun har buyurtma yaratilgan smenaga aniq bog'lanadi. Nullable —
smena ochiq bo'lmaganda yoki eski buyurtmalarda NULL qoladi (orqaga moslik).

Revision ID: x1y2z3a4b5c6
Revises: w9x0y1z2a3b4
Create Date: 2026-06-21 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'x1y2z3a4b5c6'
down_revision: Union[str, None] = 'w9x0y1z2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('orders', sa.Column('shift_id', sa.Integer(), nullable=True))
    op.create_index('ix_orders_shift_id', 'orders', ['shift_id'], unique=False)
    op.create_foreign_key(
        'fk_orders_shift_id', 'orders', 'shifts', ['shift_id'], ['id']
    )


def downgrade() -> None:
    op.drop_constraint('fk_orders_shift_id', 'orders', type_='foreignkey')
    op.drop_index('ix_orders_shift_id', table_name='orders')
    op.drop_column('orders', 'shift_id')
