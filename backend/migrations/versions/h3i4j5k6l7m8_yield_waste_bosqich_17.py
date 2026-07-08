"""yield_waste_bosqich_17

Revision ID: h3i4j5k6l7m8
Revises: g2h3i4j5k6l7
Create Date: 2026-06-14 10:00:00.000000

O'zgarishlar:
  - products.yield_pct ustuni (models.py da bor edi, DB ga qo'shilmagan edi)
  - waste_logs yangi jadvali (poteriya/chiqindi hisobi)
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'h3i4j5k6l7m8'
down_revision: Union[str, None] = 'g2h3i4j5k6l7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. products jadvaliga yield_pct ustuni qo'shish
    op.add_column(
        'products',
        sa.Column('yield_pct', sa.Float(), nullable=True)
    )

    # 2. waste_logs jadvali — poteriya (chiqindi) hisobi
    op.create_table(
        'waste_logs',
        sa.Column('id',         sa.Integer(), primary_key=True, index=True),
        sa.Column('tenant_id',  sa.Integer(), sa.ForeignKey('cafes.id'),    nullable=True,  index=True),
        sa.Column('branch_id',  sa.Integer(), sa.ForeignKey('branches.id'), nullable=True,  index=True),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False, index=True),
        # Yo'qolgan miqdor va qiymati
        sa.Column('quantity',   sa.Float(),   nullable=False),
        sa.Column('unit',       sa.String(20), nullable=False, server_default='kg'),
        sa.Column('unit_cost',  sa.Float(),   nullable=False, server_default='0'),
        sa.Column('total_cost', sa.Float(),   nullable=False, server_default='0'),
        # Tur: recipe=avtomatik (retseptdan), manual=qo'lda, expired=muddati o'tgan
        sa.Column('waste_type', sa.String(20), nullable=False, index=True),
        # Bog'lanishlar
        sa.Column('order_id',   sa.Integer(), sa.ForeignKey('orders.id'),   nullable=True),
        sa.Column('user_id',    sa.Integer(), sa.ForeignKey('users.id'),    nullable=True),
        sa.Column('notes',      sa.Text(),    nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), index=True),
    )


def downgrade() -> None:
    op.drop_table('waste_logs')
    op.drop_column('products', 'yield_pct')
