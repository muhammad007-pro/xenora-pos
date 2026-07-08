"""Narx, Aksiya va Markirovka — BOSQICH 26

Revision ID: q3r4s5t6u7v8
Revises: p2q3r4s5t6u7
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa

revision      = 'q3r4s5t6u7v8'
down_revision = 'p2q3r4s5t6u7'
branch_labels = None
depends_on    = None


def upgrade():
    # 1. CREATE markup_policies
    op.create_table(
        'markup_policies',
        sa.Column('id',          sa.Integer(),  primary_key=True),
        sa.Column('tenant_id',   sa.Integer(),  sa.ForeignKey('cafes.id'),      nullable=True),
        sa.Column('name',        sa.String(100), nullable=False),
        sa.Column('scope',       sa.String(20),  server_default='global'),
        sa.Column('category_id', sa.Integer(),  sa.ForeignKey('categories.id'), nullable=True),
        sa.Column('product_id',  sa.Integer(),  sa.ForeignKey('products.id'),   nullable=True),
        sa.Column('markup_pct',  sa.Float(),    nullable=False),
        sa.Column('min_price',   sa.Float(),    nullable=True),
        sa.Column('is_active',   sa.Boolean(),  server_default='true'),
        sa.Column('created_by',  sa.Integer(),  sa.ForeignKey('users.id'),      nullable=True),
        sa.Column('created_at',  sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at',  sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_markup_policies_tenant_id',   'markup_policies', ['tenant_id'])
    op.create_index('ix_markup_policies_category_id', 'markup_policies', ['category_id'])
    op.create_index('ix_markup_policies_product_id',  'markup_policies', ['product_id'])

    # 2. CREATE bonus_cards
    op.create_table(
        'bonus_cards',
        sa.Column('id',           sa.Integer(),  primary_key=True),
        sa.Column('tenant_id',    sa.Integer(),  sa.ForeignKey('cafes.id'),     nullable=True),
        sa.Column('card_number',  sa.String(30), nullable=False, unique=True),
        sa.Column('customer_id',  sa.Integer(),  sa.ForeignKey('customers.id'), nullable=True),
        sa.Column('balance',      sa.Float(),    server_default='0'),
        sa.Column('earn_rate',    sa.Float(),    server_default='1.0'),
        sa.Column('total_earned', sa.Float(),    server_default='0'),
        sa.Column('total_spent',  sa.Float(),    server_default='0'),
        sa.Column('is_active',    sa.Boolean(),  server_default='true'),
        sa.Column('created_at',   sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at',   sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_bonus_cards_tenant_id',   'bonus_cards', ['tenant_id'])
    op.create_index('ix_bonus_cards_card_number', 'bonus_cards', ['card_number'])
    op.create_index('ix_bonus_cards_customer_id', 'bonus_cards', ['customer_id'])

    # 3. CREATE bonus_transactions
    op.create_table(
        'bonus_transactions',
        sa.Column('id',          sa.Integer(),   primary_key=True),
        sa.Column('tenant_id',   sa.Integer(),   sa.ForeignKey('cafes.id'),  nullable=True),
        sa.Column('card_id',     sa.Integer(),   sa.ForeignKey('bonus_cards.id', ondelete='CASCADE'), nullable=False),
        sa.Column('order_id',    sa.Integer(),   sa.ForeignKey('orders.id'),  nullable=True),
        sa.Column('tx_type',     sa.String(20),  nullable=False),
        sa.Column('amount',      sa.Float(),     nullable=False),
        sa.Column('description', sa.String(200), nullable=True),
        sa.Column('created_by',  sa.Integer(),   sa.ForeignKey('users.id'),   nullable=True),
        sa.Column('created_at',  sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_bonus_transactions_card_id',  'bonus_transactions', ['card_id'])
    op.create_index('ix_bonus_transactions_tx_type',  'bonus_transactions', ['tx_type'])
    op.create_index('ix_bonus_transactions_tenant_id','bonus_transactions', ['tenant_id'])

    # 4. CREATE product_marks
    op.create_table(
        'product_marks',
        sa.Column('id',         sa.Integer(),   primary_key=True),
        sa.Column('tenant_id',  sa.Integer(),   sa.ForeignKey('cafes.id'),       nullable=True),
        sa.Column('product_id', sa.Integer(),   sa.ForeignKey('products.id'),    nullable=False),
        sa.Column('batch_id',   sa.Integer(),   sa.ForeignKey('product_batches.id'), nullable=True),
        sa.Column('mark_code',  sa.String(500), nullable=False, unique=True),
        sa.Column('mark_type',  sa.String(20),  server_default='datamatrix'),
        sa.Column('status',     sa.String(20),  server_default='active'),
        sa.Column('order_id',   sa.Integer(),   sa.ForeignKey('orders.id'),      nullable=True),
        sa.Column('scanned_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.Integer(),   sa.ForeignKey('users.id'),       nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_product_marks_tenant_id',  'product_marks', ['tenant_id'])
    op.create_index('ix_product_marks_product_id', 'product_marks', ['product_id'])
    op.create_index('ix_product_marks_mark_code',  'product_marks', ['mark_code'])
    op.create_index('ix_product_marks_status',     'product_marks', ['status'])


def downgrade():
    op.drop_table('product_marks')
    op.drop_table('bonus_transactions')
    op.drop_table('bonus_cards')
    op.drop_table('markup_policies')
