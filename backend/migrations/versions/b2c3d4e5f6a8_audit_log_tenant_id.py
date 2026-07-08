"""audit_logs jadvaliga tenant_id ustuni qo'shish (audit yozish — multi-tenant)

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
Create Date: 2026-06-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a8'
down_revision: Union[str, None] = 'a1b2c3d4e5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('audit_logs', sa.Column('tenant_id', sa.Integer(), nullable=True))
    op.create_index('ix_audit_logs_tenant_id', 'audit_logs', ['tenant_id'])
    op.create_foreign_key(
        'fk_audit_logs_tenant_id_cafes', 'audit_logs', 'cafes', ['tenant_id'], ['id']
    )


def downgrade() -> None:
    op.drop_constraint('fk_audit_logs_tenant_id_cafes', 'audit_logs', type_='foreignkey')
    op.drop_index('ix_audit_logs_tenant_id', table_name='audit_logs')
    op.drop_column('audit_logs', 'tenant_id')
