"""inventory_full_bosqich_16

Revision ID: g2h3i4j5k6l7
Revises: f1a2b3c4d5e6
Create Date: 2026-06-13 15:00:00.000000

Yangi jadvallar:
  - stock_movements  — kelim/chiqim/writeoff/adjustment tarixi
  - inventory_counts — inventarizatsiya seanslari
  - inventory_count_items — inventarizatsiya elementlari

O'zgarishlar:
  - suppliers.balance ustuni qo'shildi
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'g2h3i4j5k6l7'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. stock_movements jadvali
    op.create_table(
        'stock_movements',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('cafes.id'), nullable=True, index=True),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id'), nullable=True, index=True),
        sa.Column('inventory_id', sa.Integer(), sa.ForeignKey('inventory.id'), nullable=True),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=True),
        sa.Column('movement_type', sa.String(20), nullable=False, index=True),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('unit', sa.String(20), default='dona'),
        sa.Column('unit_cost', sa.Float(), default=0.0),
        sa.Column('total_cost', sa.Float(), default=0.0),
        sa.Column('supplier_id', sa.Integer(), sa.ForeignKey('suppliers.id'), nullable=True),
        sa.Column('batch_number', sa.String(50), nullable=True),
        sa.Column('expiry_date', sa.Date(), nullable=True),
        sa.Column('reason', sa.String(200), nullable=True),
        sa.Column('reference_id', sa.Integer(), nullable=True),
        sa.Column('reference_type', sa.String(50), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), index=True),
    )

    # 2. inventory_counts jadvali
    op.create_table(
        'inventory_counts',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('cafes.id'), nullable=True, index=True),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id'), nullable=True, index=True),
        sa.Column('status', sa.String(20), default='draft'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('confirmed_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )

    # 3. inventory_count_items jadvali
    op.create_table(
        'inventory_count_items',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('count_id', sa.Integer(), sa.ForeignKey('inventory_counts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('inventory_id', sa.Integer(), sa.ForeignKey('inventory.id'), nullable=True),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=True),
        sa.Column('product_name', sa.String(200), nullable=True),
        sa.Column('unit', sa.String(20), default='dona'),
        sa.Column('system_qty', sa.Float(), default=0.0),
        sa.Column('actual_qty', sa.Float(), nullable=True),
        sa.Column('difference', sa.Float(), nullable=True),
        sa.Column('notes', sa.String(300), nullable=True),
    )

    # 4. suppliers jadvaliga balance ustuni qo'shish
    op.add_column('suppliers', sa.Column('balance', sa.Float(), nullable=True, server_default='0'))


def downgrade() -> None:
    op.drop_column('suppliers', 'balance')
    op.drop_table('inventory_count_items')
    op.drop_table('inventory_counts')
    op.drop_table('stock_movements')
