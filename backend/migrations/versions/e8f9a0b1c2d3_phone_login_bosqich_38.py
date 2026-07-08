"""phone_login_bosqich_38

Login telefon raqamga o'tkazildi:
  users.phone    -> NOT NULL + UNIQUE (login kaliti, global unikal)
  users.username -> nullable (endi ixtiyoriy, display/legacy uchun qoladi)
  users.email    -> nullable (endi ixtiyoriy)

DIQQAT: phone NOT NULL + UNIQUE qo'shilishidan oldin jadvalda NULL yoki takror
telefon BO'LMASLIGI kerak (aks holda ALTER xato beradi). Toza/bo'sh jadvalga
yoki tozalangan ma'lumotga qo'llanadi.

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-06-25 00:00:02.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'e8f9a0b1c2d3'
down_revision: Union[str, None] = 'd7e8f9a0b1c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Telefon — login kaliti: majburiy + unikal
    op.alter_column('users', 'phone',
                    existing_type=sa.String(length=20), nullable=False)
    op.create_unique_constraint('uq_users_phone', 'users', ['phone'])
    # username/email — endi ixtiyoriy (login telefonga o'tdi)
    op.alter_column('users', 'username',
                    existing_type=sa.String(length=50), nullable=True)
    op.alter_column('users', 'email',
                    existing_type=sa.String(length=100), nullable=True)


def downgrade() -> None:
    op.alter_column('users', 'email',
                    existing_type=sa.String(length=100), nullable=False)
    op.alter_column('users', 'username',
                    existing_type=sa.String(length=50), nullable=False)
    op.drop_constraint('uq_users_phone', 'users', type_='unique')
    op.alter_column('users', 'phone',
                    existing_type=sa.String(length=20), nullable=True)
