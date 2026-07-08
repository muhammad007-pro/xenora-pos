"""drop_tizim_a_bosqich_35

Tizim A (eski supplier hisob-kitob) jadvallarini olib tashlash:
  - supplier_payments.po_id ustuni (FK → purchase_orders)
  - purchase_order_items jadvali
  - purchase_orders jadvali

Tizim B (PurchaseReceipt / SupplierPayment.receipt_id) standart bo'lib qoladi.
supplier_payments MODELI saqlanadi — faqat po_id ustuni olib tashlanadi.
Baza: purchase_orders/items 0 qator, supplier_payments.po_id NULL — ma'lumot yo'qolmaydi.

FK tartibi (drop): po_id ustun → purchase_order_items → purchase_orders.

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-06-23 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'b5c6d7e8f9a0'
down_revision: Union[str, None] = 'a4b5c6d7e8f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. supplier_payments.po_id (FK → purchase_orders) — avval olib tashlanadi
    op.drop_column('supplier_payments', 'po_id')
    # 2. purchase_order_items (FK po_id CASCADE → purchase_orders)
    op.drop_table('purchase_order_items')
    # 3. purchase_orders
    op.drop_table('purchase_orders')


def downgrade() -> None:
    # purchase_orders qayta yaratish
    op.create_table(
        'purchase_orders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('cafes.id'), nullable=True),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id'), nullable=True),
        sa.Column('supplier_id', sa.Integer(), sa.ForeignKey('suppliers.id'), nullable=True),
        sa.Column('po_number', sa.String(30), nullable=False, unique=True),
        sa.Column('status', sa.String(20), server_default='draft'),
        sa.Column('invoice_number', sa.String(50), nullable=True),
        sa.Column('ordered_at', sa.DateTime(), nullable=True),
        sa.Column('received_at', sa.DateTime(), nullable=True),
        sa.Column('total_amount', sa.Float(), server_default='0'),
        sa.Column('paid_amount', sa.Float(), server_default='0'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_purchase_orders_id', 'purchase_orders', ['id'])
    op.create_index('ix_purchase_orders_tenant_id', 'purchase_orders', ['tenant_id'])
    op.create_index('ix_purchase_orders_status', 'purchase_orders', ['status'])

    # purchase_order_items qayta yaratish
    op.create_table(
        'purchase_order_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('po_id', sa.Integer(), sa.ForeignKey('purchase_orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('received_qty', sa.Float(), server_default='0'),
        sa.Column('unit_cost', sa.Float(), nullable=False),
        sa.Column('total', sa.Float(), nullable=False),
        sa.Column('expiry_date', sa.Date(), nullable=True),
        sa.Column('batch_number', sa.String(50), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_purchase_order_items_id', 'purchase_order_items', ['id'])
    op.create_index('ix_purchase_order_items_po_id', 'purchase_order_items', ['po_id'])

    # supplier_payments.po_id qayta qo'shish
    op.add_column('supplier_payments', sa.Column('po_id', sa.Integer(), sa.ForeignKey('purchase_orders.id'), nullable=True))
