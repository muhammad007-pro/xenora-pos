"""OFD Fiskal integratsiya — BOSQICH 28

Revision ID: s5t6u7v8w9x0
Revises: r4s5t6u7v8w9
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa

revision      = 's5t6u7v8w9x0'
down_revision = 'r4s5t6u7v8w9'
branch_labels = None
depends_on    = None


def upgrade():
    op.add_column('orders', sa.Column('fiscal_number',  sa.Integer(),     nullable=True))
    op.add_column('orders', sa.Column('fiscal_qr_url',  sa.String(500),   nullable=True))
    op.add_column('orders', sa.Column('fiscal_sent_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_orders_fiscal_number', 'orders', ['fiscal_number'])


def downgrade():
    op.drop_index('ix_orders_fiscal_number', table_name='orders')
    op.drop_column('orders', 'fiscal_sent_at')
    op.drop_column('orders', 'fiscal_qr_url')
    op.drop_column('orders', 'fiscal_number')
