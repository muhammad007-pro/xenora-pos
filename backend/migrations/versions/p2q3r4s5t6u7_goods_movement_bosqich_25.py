"""Tovar harakati va hisobdan chiqarish — BOSQICH 25

Revision ID: p2q3r4s5t6u7
Revises: o1p2q3r4s5t6
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa

revision     = 'p2q3r4s5t6u7'
down_revision = 'o1p2q3r4s5t6'
branch_labels = None
depends_on    = None


def upgrade():
    # 1. ALTER return_items — goes_to_brak qo'shish
    op.add_column('return_items',
        sa.Column('goes_to_brak', sa.Boolean(), nullable=True, server_default='false')
    )

    # 2. CREATE write_offs
    op.create_table(
        'write_offs',
        sa.Column('id',             sa.Integer(),     primary_key=True),
        sa.Column('tenant_id',      sa.Integer(),     sa.ForeignKey('cafes.id'),    nullable=True),
        sa.Column('branch_id',      sa.Integer(),     sa.ForeignKey('branches.id'), nullable=True),
        sa.Column('act_number',     sa.String(30),    nullable=False, unique=True),
        sa.Column('reason',         sa.String(30),    nullable=False, server_default='other'),
        sa.Column('write_off_date', sa.Date(),        nullable=False),
        sa.Column('total_loss',     sa.Float(),       server_default='0'),
        sa.Column('notes',          sa.Text(),        nullable=True),
        sa.Column('status',         sa.String(20),    server_default='draft'),
        sa.Column('created_by',     sa.Integer(),     sa.ForeignKey('users.id'),   nullable=True),
        sa.Column('confirmed_by',   sa.Integer(),     sa.ForeignKey('users.id'),   nullable=True),
        sa.Column('confirmed_at',   sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at',     sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_write_offs_tenant_id',      'write_offs', ['tenant_id'])
    op.create_index('ix_write_offs_reason',         'write_offs', ['reason'])
    op.create_index('ix_write_offs_status',         'write_offs', ['status'])

    # 3. CREATE write_off_items
    op.create_table(
        'write_off_items',
        sa.Column('id',          sa.Integer(),  primary_key=True),
        sa.Column('write_off_id',sa.Integer(),  sa.ForeignKey('write_offs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('product_id',  sa.Integer(),  sa.ForeignKey('products.id'),  nullable=False),
        sa.Column('quantity',    sa.Float(),    nullable=False),
        sa.Column('cost_price',  sa.Float(),    server_default='0'),
        sa.Column('total_loss',  sa.Float(),    server_default='0'),
        sa.Column('notes',       sa.Text(),     nullable=True),
    )
    op.create_index('ix_write_off_items_write_off_id', 'write_off_items', ['write_off_id'])

    # 4. CREATE goods_regrades
    op.create_table(
        'goods_regrades',
        sa.Column('id',           sa.Integer(),  primary_key=True),
        sa.Column('tenant_id',    sa.Integer(),  sa.ForeignKey('cafes.id'),    nullable=True),
        sa.Column('branch_id',    sa.Integer(),  sa.ForeignKey('branches.id'), nullable=True),
        sa.Column('regrade_date', sa.Date(),     nullable=False),
        sa.Column('notes',        sa.Text(),     nullable=True),
        sa.Column('status',       sa.String(20), server_default='draft'),
        sa.Column('created_by',   sa.Integer(),  sa.ForeignKey('users.id'),   nullable=True),
        sa.Column('confirmed_by', sa.Integer(),  sa.ForeignKey('users.id'),   nullable=True),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at',   sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_goods_regrades_tenant_id', 'goods_regrades', ['tenant_id'])
    op.create_index('ix_goods_regrades_status',    'goods_regrades', ['status'])

    # 5. CREATE goods_regrade_items
    op.create_table(
        'goods_regrade_items',
        sa.Column('id',              sa.Integer(), primary_key=True),
        sa.Column('regrade_id',      sa.Integer(), sa.ForeignKey('goods_regrades.id', ondelete='CASCADE'), nullable=False),
        sa.Column('from_product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
        sa.Column('to_product_id',   sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
        sa.Column('quantity',        sa.Float(),   nullable=False),
        sa.Column('notes',           sa.Text(),    nullable=True),
    )
    op.create_index('ix_goods_regrade_items_regrade_id', 'goods_regrade_items', ['regrade_id'])

    # 6. CREATE internal_transfers
    op.create_table(
        'internal_transfers',
        sa.Column('id',             sa.Integer(),  primary_key=True),
        sa.Column('tenant_id',      sa.Integer(),  sa.ForeignKey('cafes.id'),    nullable=True),
        sa.Column('from_branch_id', sa.Integer(),  sa.ForeignKey('branches.id'), nullable=True),
        sa.Column('to_branch_id',   sa.Integer(),  sa.ForeignKey('branches.id'), nullable=True),
        sa.Column('transfer_date',  sa.Date(),     nullable=False),
        sa.Column('notes',          sa.Text(),     nullable=True),
        sa.Column('status',         sa.String(20), server_default='draft'),
        sa.Column('created_by',     sa.Integer(),  sa.ForeignKey('users.id'),   nullable=True),
        sa.Column('confirmed_by',   sa.Integer(),  sa.ForeignKey('users.id'),   nullable=True),
        sa.Column('confirmed_at',   sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at',     sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_internal_transfers_tenant_id',      'internal_transfers', ['tenant_id'])
    op.create_index('ix_internal_transfers_from_branch_id', 'internal_transfers', ['from_branch_id'])
    op.create_index('ix_internal_transfers_to_branch_id',   'internal_transfers', ['to_branch_id'])
    op.create_index('ix_internal_transfers_status',         'internal_transfers', ['status'])

    # 7. CREATE internal_transfer_items
    op.create_table(
        'internal_transfer_items',
        sa.Column('id',          sa.Integer(), primary_key=True),
        sa.Column('transfer_id', sa.Integer(), sa.ForeignKey('internal_transfers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('product_id',  sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
        sa.Column('quantity',    sa.Float(),   nullable=False),
        sa.Column('cost_price',  sa.Float(),   server_default='0'),
    )
    op.create_index('ix_internal_transfer_items_transfer_id', 'internal_transfer_items', ['transfer_id'])


def downgrade():
    op.drop_table('internal_transfer_items')
    op.drop_table('internal_transfers')
    op.drop_table('goods_regrade_items')
    op.drop_table('goods_regrades')
    op.drop_table('write_off_items')
    op.drop_table('write_offs')
    op.drop_column('return_items', 'goes_to_brak')
