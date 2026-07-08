"""b2b_suppliers_bosqich_24

B2B oldi-berdi tizimi: priyomka, vozvrat, firma qarz hisob-kitob.

Revision ID: o1p2q3r4s5t6
Revises: n9o0p1q2r3s4
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa

revision = 'o1p2q3r4s5t6'
down_revision = 'n9o0p1q2r3s4'
branch_labels = None
depends_on = None


def upgrade():
    # 1. suppliers jadvaliga yangi ustunlar
    op.add_column('suppliers', sa.Column('contract_number', sa.String(50), nullable=True))
    op.add_column('suppliers', sa.Column('payment_delay_days', sa.Integer(), nullable=True, server_default='0'))

    # 2. purchase_receipts (yangi jadval — supplier_payments FK dan oldin yaratilishi kerak)
    op.create_table(
        'purchase_receipts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('cafes.id'), nullable=True),
        sa.Column('supplier_id', sa.Integer(), sa.ForeignKey('suppliers.id'), nullable=False),
        sa.Column('invoice_number', sa.String(50), nullable=True),
        sa.Column('receipt_date', sa.Date(), nullable=False),
        sa.Column('total_amount', sa.Float(), nullable=True, server_default='0'),
        sa.Column('discount_amount', sa.Float(), nullable=True, server_default='0'),
        sa.Column('net_amount', sa.Float(), nullable=True, server_default='0'),
        sa.Column('status', sa.String(20), nullable=True, server_default='draft'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('confirmed_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_purchase_receipts_id', 'purchase_receipts', ['id'])
    op.create_index('ix_purchase_receipts_tenant_id', 'purchase_receipts', ['tenant_id'])

    # 3. purchase_receipt_items
    op.create_table(
        'purchase_receipt_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('receipt_id', sa.Integer(), sa.ForeignKey('purchase_receipts.id'), nullable=False),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('unit_price', sa.Float(), nullable=False),
        sa.Column('total_price', sa.Float(), nullable=False),
        sa.Column('brak_qty', sa.Float(), nullable=True, server_default='0'),
        sa.Column('accepted_qty', sa.Float(), nullable=True),
        sa.Column('notes', sa.String(200), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_purchase_receipt_items_id', 'purchase_receipt_items', ['id'])

    # 4. supplier_payments jadvaliga yangi ustunlar (purchase_receipts dan keyin)
    op.add_column('supplier_payments', sa.Column('receipt_id', sa.Integer(), sa.ForeignKey('purchase_receipts.id'), nullable=True))
    op.add_column('supplier_payments', sa.Column('payment_date', sa.Date(), nullable=True))
    op.add_column('supplier_payments', sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True))

    # 5. supplier_returns (yangi jadval)
    op.create_table(
        'supplier_returns',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('cafes.id'), nullable=True),
        sa.Column('supplier_id', sa.Integer(), sa.ForeignKey('suppliers.id'), nullable=False),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('unit_price', sa.Float(), nullable=False),
        sa.Column('total_amount', sa.Float(), nullable=False),
        sa.Column('return_date', sa.Date(), nullable=False),
        sa.Column('reason', sa.String(200), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_supplier_returns_id', 'supplier_returns', ['id'])
    op.create_index('ix_supplier_returns_tenant_id', 'supplier_returns', ['tenant_id'])


def downgrade():
    op.drop_table('supplier_returns')
    op.drop_column('supplier_payments', 'created_by')
    op.drop_column('supplier_payments', 'payment_date')
    op.drop_column('supplier_payments', 'receipt_id')
    op.drop_table('purchase_receipt_items')
    op.drop_table('purchase_receipts')
    op.drop_column('suppliers', 'payment_delay_days')
    op.drop_column('suppliers', 'contract_number')
