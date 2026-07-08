"""Dorixona maxsus funksiyalar — BOSQICH 22

Prescription archive, product batches, pharmacy product fields.

Revision ID: m8n9o0p1q2r3
Revises: l7m8n9o0p1q2
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa

revision = 'm8n9o0p1q2r3'
down_revision = 'l7m8n9o0p1q2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. products jadvaliga dorixona maydonlari ───────────────────────────
    op.add_column('products', sa.Column('active_ingredient',     sa.String(300), nullable=True))
    op.add_column('products', sa.Column('dosage',                sa.String(100), nullable=True))
    op.add_column('products', sa.Column('drug_form',             sa.String(50),  nullable=True))
    op.add_column('products', sa.Column('dosing_schedule',       sa.String(300), nullable=True))
    op.add_column('products', sa.Column('requires_prescription', sa.Boolean(),   nullable=False, server_default='false'))

    # ── 2. product_batches jadval ───────────────────────────────────────────
    op.create_table(
        'product_batches',
        sa.Column('id',               sa.Integer(),    primary_key=True),
        sa.Column('tenant_id',        sa.Integer(),    sa.ForeignKey('cafes.id'), nullable=True, index=True),
        sa.Column('branch_id',        sa.Integer(),    sa.ForeignKey('branches.id'), nullable=True, index=True),
        sa.Column('product_id',       sa.Integer(),    sa.ForeignKey('products.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('batch_number',     sa.String(100),  nullable=False),
        sa.Column('manufacturer',     sa.String(200),  nullable=True),
        sa.Column('manufacture_date', sa.Date(),       nullable=True),
        sa.Column('expiry_date',      sa.Date(),       nullable=False),
        sa.Column('quantity',         sa.Float(),      default=0.0),
        sa.Column('initial_quantity', sa.Float(),      default=0.0),
        sa.Column('cost_price',       sa.Float(),      default=0.0),
        sa.Column('notes',            sa.Text(),       nullable=True),
        sa.Column('is_active',        sa.Boolean(),    default=True),
        sa.Column('created_at',       sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at',       sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # ── 3. prescriptions jadval ─────────────────────────────────────────────
    op.create_table(
        'prescriptions',
        sa.Column('id',                sa.Integer(),    primary_key=True),
        sa.Column('tenant_id',         sa.Integer(),    sa.ForeignKey('cafes.id'), nullable=True, index=True),
        sa.Column('branch_id',         sa.Integer(),    sa.ForeignKey('branches.id'), nullable=True, index=True),
        sa.Column('patient_name',      sa.String(200),  nullable=False),
        sa.Column('patient_phone',     sa.String(30),   nullable=True),
        sa.Column('doctor_name',       sa.String(200),  nullable=True),
        sa.Column('clinic_name',       sa.String(200),  nullable=True),
        sa.Column('prescription_date', sa.Date(),       nullable=False),
        sa.Column('image_url',         sa.String(500),  nullable=True),
        sa.Column('notes',             sa.Text(),       nullable=True),
        sa.Column('medicines',         sa.JSON(),       nullable=True),
        sa.Column('is_dispensed',      sa.Boolean(),    default=False),
        sa.Column('dispensed_at',      sa.DateTime(timezone=True), nullable=True),
        sa.Column('order_id',          sa.Integer(),    sa.ForeignKey('orders.id'), nullable=True),
        sa.Column('created_by',        sa.Integer(),    sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at',        sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at',        sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('prescriptions')
    op.drop_table('product_batches')
    op.drop_column('products', 'requires_prescription')
    op.drop_column('products', 'dosing_schedule')
    op.drop_column('products', 'drug_form')
    op.drop_column('products', 'dosage')
    op.drop_column('products', 'active_ingredient')
