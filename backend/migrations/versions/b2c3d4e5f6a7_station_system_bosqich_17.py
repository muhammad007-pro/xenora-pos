"""station_system_bosqich_17

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-13 15:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. stations jadvali
    op.create_table(
        'stations',
        sa.Column('id',            sa.Integer(),     nullable=False),
        sa.Column('tenant_id',     sa.Integer(),     nullable=True),
        sa.Column('branch_id',     sa.Integer(),     nullable=True),
        sa.Column('name',          sa.String(100),   nullable=False),
        sa.Column('color',         sa.String(20),    nullable=False, server_default='#d4af37'),
        sa.Column('has_display',   sa.Boolean(),     nullable=False, server_default='true'),
        sa.Column('display_order', sa.Integer(),     nullable=False, server_default='0'),
        sa.Column('is_active',     sa.Boolean(),     nullable=False, server_default='true'),
        sa.Column('created_at',    sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['cafes.id']),
        sa.ForeignKeyConstraint(['branch_id'], ['branches.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_stations_tenant_id', 'stations', ['tenant_id'])
    op.create_index('ix_stations_branch_id', 'stations', ['branch_id'])

    # 2. products.station_id ustuni
    op.add_column('products', sa.Column('station_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_products_station_id', 'products', 'stations', ['station_id'], ['id'])
    op.create_index('ix_products_station_id', 'products', ['station_id'])


def downgrade() -> None:
    op.drop_index('ix_products_station_id', table_name='products')
    op.drop_constraint('fk_products_station_id', 'products', type_='foreignkey')
    op.drop_column('products', 'station_id')
    op.drop_index('ix_stations_branch_id', table_name='stations')
    op.drop_index('ix_stations_tenant_id', table_name='stations')
    op.drop_table('stations')
