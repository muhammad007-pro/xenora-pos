"""Super admin: tenant management — cafes jadvaliga yangi ustunlar + tenant_payments jadval

Revision ID: e1f2a3b4c5d6
Revises: d1e2f3a4b5c6
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa

revision = 'e1f2a3b4c5d6'
down_revision = 'd1e2f3a4b5c6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # cafes jadvaliga tenant boshqaruvi uchun yangi ustunlar
    op.add_column('cafes', sa.Column('owner_name',     sa.String(100), nullable=True))
    op.add_column('cafes', sa.Column('owner_phone',    sa.String(20),  nullable=True))
    op.add_column('cafes', sa.Column('tenant_status',  sa.String(20),  nullable=True, server_default='active'))
    op.add_column('cafes', sa.Column('trial_expires',  sa.DateTime(),  nullable=True))
    op.add_column('cafes', sa.Column('blocked_at',     sa.DateTime(),  nullable=True))
    op.add_column('cafes', sa.Column('blocked_reason', sa.Text(),      nullable=True))

    # tenant_payments — platforma egasining to'lov tarixi
    op.create_table(
        'tenant_payments',
        sa.Column('id',             sa.Integer(),  primary_key=True),
        sa.Column('tenant_id',      sa.Integer(),  sa.ForeignKey('cafes.id'), nullable=False, index=True),
        sa.Column('amount',         sa.Float(),    nullable=False),
        sa.Column('months',         sa.Integer(),  server_default='1'),
        sa.Column('payment_method', sa.String(20), server_default='cash'),
        sa.Column('period_start',   sa.DateTime(), nullable=True),
        sa.Column('period_end',     sa.DateTime(), nullable=True),
        sa.Column('note',           sa.Text(),     nullable=True),
        sa.Column('created_by_id',  sa.Integer(),  sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at',     sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('tenant_payments')
    op.drop_column('cafes', 'blocked_reason')
    op.drop_column('cafes', 'blocked_at')
    op.drop_column('cafes', 'trial_expires')
    op.drop_column('cafes', 'tenant_status')
    op.drop_column('cafes', 'owner_phone')
    op.drop_column('cafes', 'owner_name')
