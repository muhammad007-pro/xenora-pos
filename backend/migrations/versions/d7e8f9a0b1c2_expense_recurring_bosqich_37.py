"""expense_recurring_bosqich_37

expenses jadvaliga takroriylik maydonlari (ijara/kommunal har oy avtomatik):
  is_recurring         — True bo'lsa shablon (har oy/hafta takrorlanadi)
  recurrence_period    — 'monthly' | 'weekly' (default 'monthly')
  recurrence_day       — oyning kuni (monthly uchun, masalan ijara 1-sanada)
  recurrence_parent_id — generatsiya qilingan nusxa qaysi shablondan (FK -> expenses.id)

Mantiq (profit.py: ensure_recurring_expenses): summary/timeline/expenses
so'rovida shu oygacha yetishmagan takroriy nusxalar avtomatik yaratiladi.
IKKI MARTA YARATILMASIN: nusxa shu (parent, oy) uchun mavjudligi tekshiriladi.

Hammasi nullable yoki server_default bilan — eski xarajatlar buzilmaydi.

Revision ID: d7e8f9a0b1c2
Revises: c6d7e8f9a0b1
Create Date: 2026-06-25 00:00:01.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'd7e8f9a0b1c2'
down_revision: Union[str, None] = 'c6d7e8f9a0b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('expenses', sa.Column('is_recurring', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('expenses', sa.Column('recurrence_period', sa.String(length=10), nullable=False, server_default='monthly'))
    op.add_column('expenses', sa.Column('recurrence_day', sa.Integer(), nullable=True))
    op.add_column('expenses', sa.Column('recurrence_parent_id', sa.Integer(), nullable=True))
    op.create_index('ix_expenses_recurrence_parent_id', 'expenses', ['recurrence_parent_id'])
    op.create_foreign_key(
        'fk_expenses_recurrence_parent_id', 'expenses', 'expenses',
        ['recurrence_parent_id'], ['id'], ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint('fk_expenses_recurrence_parent_id', 'expenses', type_='foreignkey')
    op.drop_index('ix_expenses_recurrence_parent_id', table_name='expenses')
    op.drop_column('expenses', 'recurrence_parent_id')
    op.drop_column('expenses', 'recurrence_day')
    op.drop_column('expenses', 'recurrence_period')
    op.drop_column('expenses', 'is_recurring')
