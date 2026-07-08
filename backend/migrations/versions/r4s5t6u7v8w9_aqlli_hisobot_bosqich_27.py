"""Aqlli hisobot va nazorat — BOSQICH 27

Revision ID: r4s5t6u7v8w9
Revises: q3r4s5t6u7v8
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa

revision      = 'r4s5t6u7v8w9'
down_revision = 'q3r4s5t6u7v8'
branch_labels = None
depends_on    = None


def upgrade():
    op.create_table(
        'product_reorder_settings',
        sa.Column('id',                    sa.Integer(),  primary_key=True),
        sa.Column('tenant_id',             sa.Integer(),  sa.ForeignKey('cafes.id'),     nullable=True),
        sa.Column('product_id',            sa.Integer(),  sa.ForeignKey('products.id', ondelete='CASCADE'), nullable=False),
        sa.Column('min_qty',               sa.Float(),    nullable=False, server_default='10'),
        sa.Column('reorder_qty',           sa.Float(),    nullable=False, server_default='50'),
        sa.Column('preferred_supplier_id', sa.Integer(),  sa.ForeignKey('suppliers.id'), nullable=True),
        sa.Column('notes',                 sa.String(300), nullable=True),
        sa.Column('created_at',            sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at',            sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_reorder_settings_tenant_id',   'product_reorder_settings', ['tenant_id'])
    op.create_index('ix_reorder_settings_product_id',  'product_reorder_settings', ['product_id'])


def downgrade():
    op.drop_table('product_reorder_settings')
