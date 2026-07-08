"""audit_log jadval — BOSQICH 13

Revision ID: d1e2f3a4b5c6
Revises: c1d2e3f4a5b6
Create Date: 2025-06-10
"""
from alembic import op
import sqlalchemy as sa

revision = 'd1e2f3a4b5c6'
down_revision = 'c1d2e3f4a5b6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'audit_logs',
        sa.Column('id',          sa.Integer(),     nullable=False),
        sa.Column('user_id',     sa.Integer(),     nullable=True),
        sa.Column('resource',    sa.String(50),    nullable=False),
        sa.Column('action',      sa.String(20),    nullable=False),
        sa.Column('resource_id', sa.String(50),    nullable=True),
        sa.Column('detail',      sa.JSON(),        nullable=True),
        sa.Column('ip_address',  sa.String(45),    nullable=True),
        sa.Column('created_at',  sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_audit_logs_id',         'audit_logs', ['id'])
    op.create_index('ix_audit_logs_resource',   'audit_logs', ['resource'])
    op.create_index('ix_audit_logs_user_id',    'audit_logs', ['user_id'])
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'])


def downgrade():
    op.drop_index('ix_audit_logs_created_at', table_name='audit_logs')
    op.drop_index('ix_audit_logs_user_id',    table_name='audit_logs')
    op.drop_index('ix_audit_logs_resource',   table_name='audit_logs')
    op.drop_index('ix_audit_logs_id',         table_name='audit_logs')
    op.drop_table('audit_logs')
