"""drop_pin_codes_bosqich_29b

Eski `pin_codes` jadvalini tashlash — u faqat ishlatilmaydigan B-tizim
PIN-auth yo'liga tegishli edi (PinCode modeli olib tashlangan). Tezkor kirish
endi `User.hashed_pin` orqali amalga oshiriladi.

Revision ID: u7v8w9x0y1z2
Revises: t6u7v8w9x0y1
Create Date: 2026-06-19 00:10:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'u7v8w9x0y1z2'
down_revision: Union[str, None] = 't6u7v8w9x0y1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Jadvalni tashlash (indekslar va constraintlar Postgresda birga tushadi)
    op.drop_table('pin_codes')


def downgrade() -> None:
    # Jadvalni qayta yaratish (asl sxema bo'yicha)
    op.create_table(
        'pin_codes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('pin', sa.String(length=10), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('last_used', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['cafes.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', name='pin_codes_user_id_key'),
    )
    op.create_index('ix_pin_codes_id', 'pin_codes', ['id'], unique=False)
    op.create_index('ix_pin_codes_tenant_id', 'pin_codes', ['tenant_id'], unique=False)
