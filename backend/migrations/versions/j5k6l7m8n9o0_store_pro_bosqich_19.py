"""Store Pro: nasiya/qarz, ko'tara narx, qaytarish — bosqich 19

Revision ID: j5k6l7m8n9o0
Revises: i4j5k6l7m8n9
Create Date: 2026-06-15
"""
from typing import Union
import sqlalchemy as sa
from alembic import op

revision: str = 'j5k6l7m8n9o0'
down_revision: Union[str, None] = 'i4j5k6l7m8n9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Product: ko'tara narx ustunlari ──────────────────────────────────
    op.add_column('products', sa.Column('wholesale_price', sa.Float(), nullable=True))
    op.add_column('products', sa.Column('wholesale_min_qty', sa.Integer(), nullable=True, server_default='10'))

    # ── 2. Customer: qarz limit va mijoz turi ───────────────────────────────
    op.add_column('customers', sa.Column('credit_limit', sa.Float(), nullable=True))
    op.add_column('customers', sa.Column('customer_type', sa.String(20), nullable=True, server_default='retail'))
    op.add_column('customers', sa.Column('total_debt', sa.Float(), nullable=True, server_default='0'))

    # ── 3. customer_debts jadvali ────────────────────────────────────────────
    op.create_table(
        'customer_debts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('cafes.id'), nullable=True, index=True),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id'), nullable=True, index=True),
        sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id'), nullable=False, index=True),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('orders.id'), nullable=True),
        sa.Column('amount', sa.Float(), nullable=False),           # dastlabki qarz
        sa.Column('paid_amount', sa.Float(), nullable=False, server_default='0'),
        sa.Column('remaining', sa.Float(), nullable=False),        # qolgan qarz
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='open'),  # open|partial|paid
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # ── 4. debt_payments jadvali (qarzni to'lash tarixi) ────────────────────
    op.create_table(
        'debt_payments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('debt_id', sa.Integer(), sa.ForeignKey('customer_debts.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('payment_method', sa.String(20), nullable=False, server_default='cash'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── 5. returns jadvali (qaytarish sarlavhasi) ───────────────────────────
    op.create_table(
        'returns',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('cafes.id'), nullable=True, index=True),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id'), nullable=True, index=True),
        sa.Column('return_number', sa.String(30), nullable=False, unique=True),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('orders.id'), nullable=True),
        sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id'), nullable=True),
        # Sabab: broken=buzuq, dislike=yoqmadi, expired=muddati o'tgan,
        #        wrong_item=noto'g'ri tovar, other=boshqa
        sa.Column('reason', sa.String(50), nullable=False, server_default='other'),
        sa.Column('total_amount', sa.Float(), nullable=False, server_default='0'),
        # refund_method: cash=naqd, card=karta, credit=balansdaga, exchange=almashtirish
        sa.Column('refund_method', sa.String(20), nullable=False, server_default='cash'),
        # status: pending=kutilmoqda, approved=tasdiqlandi, rejected=rad etildi
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('exchange_order_id', sa.Integer(), sa.ForeignKey('orders.id'), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('approved_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── 6. return_items jadvali (qaytarilgan mahsulotlar) ───────────────────
    op.create_table(
        'return_items',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('return_id', sa.Integer(), sa.ForeignKey('returns.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
        sa.Column('order_item_id', sa.Integer(), sa.ForeignKey('order_items.id'), nullable=True),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('unit_price', sa.Float(), nullable=False),
        sa.Column('total', sa.Float(), nullable=False),
        sa.Column('restore_to_inventory', sa.Boolean(), nullable=False, server_default='true'),
    )


def downgrade() -> None:
    op.drop_table('return_items')
    op.drop_table('returns')
    op.drop_table('debt_payments')
    op.drop_table('customer_debts')
    op.drop_column('customers', 'total_debt')
    op.drop_column('customers', 'customer_type')
    op.drop_column('customers', 'credit_limit')
    op.drop_column('products', 'wholesale_min_qty')
    op.drop_column('products', 'wholesale_price')
