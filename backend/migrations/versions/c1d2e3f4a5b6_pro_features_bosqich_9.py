"""Pro funksiyalar uchun yangi jadvallar va ustunlar (BOSQICH 9)

Revision ID: c1d2e3f4a5b6
Revises: b1c2d3e4f5a6
Create Date: 2026-06-09

Qo'shiladi:
- orders: delivery_address, delivery_phone, delivery_note, service_charge,
          courses_enabled, merged_table_ids
- order_items: course_number
- payments: tip_amount
- modifier_groups jadval (yangi)
- modifiers jadval (yangi)
- order_item_modifiers jadval (yangi)
- combo_sets jadval (yangi)
- combo_set_items jadval (yangi)
- happy_hours jadval (yangi)
"""
from alembic import op
import sqlalchemy as sa

revision = 'c1d2e3f4a5b6'
down_revision = 'b91cab296885'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── orders jadvaliga yangi ustunlar ──────────────────────────────────────
    op.add_column('orders', sa.Column('delivery_address',  sa.Text(),        nullable=True))
    op.add_column('orders', sa.Column('delivery_phone',    sa.String(20),    nullable=True))
    op.add_column('orders', sa.Column('delivery_note',     sa.Text(),        nullable=True))
    op.add_column('orders', sa.Column('service_charge',    sa.Float(),       nullable=True, server_default='0'))
    op.add_column('orders', sa.Column('courses_enabled',   sa.Boolean(),     nullable=True, server_default='false'))
    op.add_column('orders', sa.Column('merged_table_ids',  sa.JSON(),        nullable=True))

    # ── order_items jadvaliga yangi ustun ────────────────────────────────────
    op.add_column('order_items', sa.Column('course_number', sa.Integer(), nullable=True, server_default='1'))

    # ── payments jadvaliga yangi ustun ───────────────────────────────────────
    op.add_column('payments', sa.Column('tip_amount', sa.Float(), nullable=True, server_default='0'))

    # ── modifier_groups jadval ───────────────────────────────────────────────
    op.create_table(
        'modifier_groups',
        sa.Column('id',           sa.Integer(), primary_key=True),
        sa.Column('tenant_id',    sa.Integer(), sa.ForeignKey('cafes.id'), nullable=True, index=True),
        sa.Column('product_id',   sa.Integer(), sa.ForeignKey('products.id'), nullable=True),
        sa.Column('name',         sa.String(100), nullable=False),
        sa.Column('type',         sa.String(20), server_default='single'),
        sa.Column('is_required',  sa.Boolean(), server_default='false'),
        sa.Column('min_select',   sa.Integer(), server_default='0'),
        sa.Column('max_select',   sa.Integer(), server_default='1'),
        sa.Column('is_active',    sa.Boolean(), server_default='true'),
        sa.Column('display_order',sa.Integer(), server_default='0'),
        sa.Column('created_at',   sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── modifiers jadval ─────────────────────────────────────────────────────
    op.create_table(
        'modifiers',
        sa.Column('id',           sa.Integer(), primary_key=True),
        sa.Column('tenant_id',    sa.Integer(), sa.ForeignKey('cafes.id'), nullable=True, index=True),
        sa.Column('group_id',     sa.Integer(), sa.ForeignKey('modifier_groups.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name',         sa.String(100), nullable=False),
        sa.Column('price_delta',  sa.Float(), server_default='0'),
        sa.Column('is_default',   sa.Boolean(), server_default='false'),
        sa.Column('is_active',    sa.Boolean(), server_default='true'),
        sa.Column('display_order',sa.Integer(), server_default='0'),
    )

    # ── order_item_modifiers jadval ──────────────────────────────────────────
    op.create_table(
        'order_item_modifiers',
        sa.Column('id',            sa.Integer(), primary_key=True),
        sa.Column('order_item_id', sa.Integer(), sa.ForeignKey('order_items.id', ondelete='CASCADE'), nullable=False),
        sa.Column('modifier_id',   sa.Integer(), sa.ForeignKey('modifiers.id'),  nullable=False),
        sa.Column('name',          sa.String(100)),
        sa.Column('price_delta',   sa.Float(), server_default='0'),
    )

    # ── combo_sets jadval ────────────────────────────────────────────────────
    op.create_table(
        'combo_sets',
        sa.Column('id',         sa.Integer(), primary_key=True),
        sa.Column('tenant_id',  sa.Integer(), sa.ForeignKey('cafes.id'), nullable=True, index=True),
        sa.Column('name',       sa.String(100), nullable=False),
        sa.Column('description',sa.Text()),
        sa.Column('price',      sa.Float(), nullable=False),
        sa.Column('image_url',  sa.String(500)),
        sa.Column('is_active',  sa.Boolean(), server_default='true'),
        sa.Column('valid_from', sa.DateTime(), nullable=True),
        sa.Column('valid_to',   sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # ── combo_set_items jadval ───────────────────────────────────────────────
    op.create_table(
        'combo_set_items',
        sa.Column('id',              sa.Integer(), primary_key=True),
        sa.Column('combo_id',        sa.Integer(), sa.ForeignKey('combo_sets.id', ondelete='CASCADE'), nullable=False),
        sa.Column('product_id',      sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
        sa.Column('quantity',        sa.Integer(), server_default='1'),
        sa.Column('is_replaceable',  sa.Boolean(), server_default='false'),
    )

    # ── happy_hours jadval ───────────────────────────────────────────────────
    op.create_table(
        'happy_hours',
        sa.Column('id',              sa.Integer(), primary_key=True),
        sa.Column('tenant_id',       sa.Integer(), sa.ForeignKey('cafes.id'), nullable=True, index=True),
        sa.Column('name',            sa.String(100), nullable=False),
        sa.Column('discount_type',   sa.String(20), server_default='percentage'),
        sa.Column('discount_value',  sa.Float(), nullable=False),
        sa.Column('weekdays',        sa.JSON()),
        sa.Column('time_from',       sa.String(5), nullable=False),
        sa.Column('time_to',         sa.String(5), nullable=False),
        sa.Column('applies_to',      sa.String(20), server_default='all'),
        sa.Column('category_id',     sa.Integer(), sa.ForeignKey('categories.id'), nullable=True),
        sa.Column('product_id',      sa.Integer(), sa.ForeignKey('products.id'), nullable=True),
        sa.Column('is_active',       sa.Boolean(), server_default='true'),
        sa.Column('created_at',      sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at',      sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('happy_hours')
    op.drop_table('combo_set_items')
    op.drop_table('combo_sets')
    op.drop_table('order_item_modifiers')
    op.drop_table('modifiers')
    op.drop_table('modifier_groups')
    op.drop_column('payments', 'tip_amount')
    op.drop_column('order_items', 'course_number')
    op.drop_column('orders', 'merged_table_ids')
    op.drop_column('orders', 'courses_enabled')
    op.drop_column('orders', 'service_charge')
    op.drop_column('orders', 'delivery_note')
    op.drop_column('orders', 'delivery_phone')
    op.drop_column('orders', 'delivery_address')
