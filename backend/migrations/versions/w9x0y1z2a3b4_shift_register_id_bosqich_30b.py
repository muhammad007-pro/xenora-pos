"""shift_register_id_bosqich_30b

shifts jadvaliga register_id (nullable FK -> cash_registers) qo'shish.
Nullable — orqaga moslik: cash_register flagi o'chiq bo'lsa NULL qoladi.

Revision ID: w9x0y1z2a3b4
Revises: v8w9x0y1z2a3
Create Date: 2026-06-19 00:35:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'w9x0y1z2a3b4'
down_revision: Union[str, None] = 'v8w9x0y1z2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('shifts', sa.Column('register_id', sa.Integer(), nullable=True))
    op.create_index('ix_shifts_register_id', 'shifts', ['register_id'], unique=False)
    op.create_foreign_key(
        'fk_shifts_register_id', 'shifts', 'cash_registers', ['register_id'], ['id']
    )


def downgrade() -> None:
    op.drop_constraint('fk_shifts_register_id', 'shifts', type_='foreignkey')
    op.drop_index('ix_shifts_register_id', table_name='shifts')
    op.drop_column('shifts', 'register_id')
