"""user_pin_bosqich_16

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-06-13 14:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('hashed_pin', sa.String(64), nullable=True))
    op.create_index('ix_users_hashed_pin', 'users', ['hashed_pin'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_users_hashed_pin', table_name='users')
    op.drop_column('users', 'hashed_pin')
