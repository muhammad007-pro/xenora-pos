"""cash_register_bosqich_30

Multi-register: `cash_registers` jadvali (bir filialda bir nechta kassa).
`cash_register` feature flagi bilan boshqariladi (FREE tier).

Revision ID: v8w9x0y1z2a3
Revises: u7v8w9x0y1z2
Create Date: 2026-06-19 00:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'v8w9x0y1z2a3'
down_revision: Union[str, None] = 'u7v8w9x0y1z2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'cash_registers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('branch_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['cafes.id']),
        sa.ForeignKeyConstraint(['branch_id'], ['branches.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_cash_registers_id', 'cash_registers', ['id'], unique=False)
    op.create_index('ix_cash_registers_tenant_id', 'cash_registers', ['tenant_id'], unique=False)
    op.create_index('ix_cash_registers_branch_id', 'cash_registers', ['branch_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_cash_registers_branch_id', table_name='cash_registers')
    op.drop_index('ix_cash_registers_tenant_id', table_name='cash_registers')
    op.drop_index('ix_cash_registers_id', table_name='cash_registers')
    op.drop_table('cash_registers')
