"""product expiry_date va batch_number qoshish (BOSQICH 4.5)

Revision ID: a3b4c5d6e7f8
Revises: 7d1f3eff3087
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa

revision = 'a3b4c5d6e7f8'
down_revision = '7d1f3eff3087'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('products', sa.Column('expiry_date',   sa.Date(),        nullable=True))
    op.add_column('products', sa.Column('batch_number',  sa.String(50),    nullable=True))


def downgrade() -> None:
    op.drop_column('products', 'batch_number')
    op.drop_column('products', 'expiry_date')
