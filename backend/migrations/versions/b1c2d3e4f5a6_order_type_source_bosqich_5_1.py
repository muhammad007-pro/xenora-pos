"""order jadvaliga order_type va source qoshish (BOSQICH 5.1)

Revision ID: b1c2d3e4f5a6
Revises: a3b4c5d6e7f8
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa

revision = 'b1c2d3e4f5a6'
down_revision = 'a3b4c5d6e7f8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('orders', sa.Column('order_type', sa.String(20), nullable=True, server_default='dine-in'))
    op.add_column('orders', sa.Column('source',     sa.String(20), nullable=True, server_default='pos'))


def downgrade() -> None:
    op.drop_column('orders', 'source')
    op.drop_column('orders', 'order_type')
