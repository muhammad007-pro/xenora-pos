"""expense_salary_link_bosqich_36

expenses jadvaliga salary_id (nullable, FK -> salaries.id):
  Maosh "to'landi" deb belgilanganda avtomatik Expense(category="salary") yaratiladi
  va shu maoshga bog'lanadi. Bog'lanish IKKI MARTA HISOBLASHNI to'sadi:
  bitta maoshga ko'pi bilan bitta xarajat (salary_id orqali tekshiriladi).

Hammasi nullable — eski xarajatlarda NULL qoladi (buzilmaydi).

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-06-25 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'c6d7e8f9a0b1'
down_revision: Union[str, None] = 'b5c6d7e8f9a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('expenses', sa.Column('salary_id', sa.Integer(), nullable=True))
    op.create_index('ix_expenses_salary_id', 'expenses', ['salary_id'])
    op.create_foreign_key(
        'fk_expenses_salary_id', 'expenses', 'salaries',
        ['salary_id'], ['id'], ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint('fk_expenses_salary_id', 'expenses', type_='foreignkey')
    op.drop_index('ix_expenses_salary_id', table_name='expenses')
    op.drop_column('expenses', 'salary_id')
