"""tenant_settings_bosqich_40

Settings tenant-scoped — 1-qadam: poydevor.
Yangi `tenant_settings` jadvali (tenant_id + config_name unikal, data JSON).
Eski global config_loader yonida turadi — hali hech narsa ko'chirilmaydi.

Revision ID: a1b2c3d4e5f7
Revises: f9a0b1c2d3e4
Create Date: 2026-06-26 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f7'
down_revision: Union[str, None] = 'f9a0b1c2d3e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tenant_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('config_name', sa.String(length=50), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['cafes.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'config_name', name='uq_tenant_settings_tenant_config'),
    )
    op.create_index(op.f('ix_tenant_settings_id'), 'tenant_settings', ['id'], unique=False)
    op.create_index(op.f('ix_tenant_settings_tenant_id'), 'tenant_settings', ['tenant_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_tenant_settings_tenant_id'), table_name='tenant_settings')
    op.drop_index(op.f('ix_tenant_settings_id'), table_name='tenant_settings')
    op.drop_table('tenant_settings')
