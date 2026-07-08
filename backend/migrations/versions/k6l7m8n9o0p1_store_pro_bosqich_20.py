"""Store Pro Bosqich 20: kassa smena to'liq, aksiya, ko'p barcode,
   tez sotuv, yetkazib beruvchi hisob-kitob, narx tarixi, chek sozlamasi"""

revision = 'k6l7m8n9o0p1'
down_revision = 'j5k6l7m8n9o0'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade():
    # ── 1. product_barcodes ─────────────────────────────────────────────────
    op.create_table(
        'product_barcodes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('cafes.id'), nullable=True, index=True),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('barcode', sa.String(100), nullable=False, unique=True),
        sa.Column('barcode_type', sa.String(20), default='CODE128'),  # CODE128|EAN13|weight
        sa.Column('is_primary', sa.Boolean(), default=False),
        sa.Column('weight_variable', sa.Boolean(), default=False),  # tarozi barcode (PLU)
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── 2. promotions (aksiya/chegirma murakkab turlari) ────────────────────
    op.create_table(
        'promotions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('cafes.id'), nullable=True, index=True),
        sa.Column('name', sa.String(150), nullable=False),
        # promo_type: buy_x_get_y | min_amount | flash_price | min_qty_discount
        sa.Column('promo_type', sa.String(30), nullable=False),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=True),
        sa.Column('category_id', sa.Integer(), sa.ForeignKey('categories.id'), nullable=True),
        # buy_x_get_y
        sa.Column('buy_qty', sa.Integer(), default=2),
        sa.Column('get_qty', sa.Integer(), default=1),
        # discount
        sa.Column('discount_type', sa.String(20), default='percentage'),  # percentage|fixed
        sa.Column('discount_value', sa.Float(), default=0.0),
        # min_amount trigger
        sa.Column('min_purchase_amount', sa.Float(), default=0.0),
        sa.Column('min_purchase_qty', sa.Integer(), default=0),
        # flash price
        sa.Column('flash_price', sa.Float(), nullable=True),
        # validity
        sa.Column('start_date', sa.DateTime(), nullable=True),
        sa.Column('end_date', sa.DateTime(), nullable=True),
        sa.Column('days_of_week', sa.String(20), nullable=True),  # "1,2,3,4,5" (1=dushanba)
        sa.Column('time_from', sa.String(5), nullable=True),      # "09:00"
        sa.Column('time_to', sa.String(5), nullable=True),        # "18:00"
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('usage_limit', sa.Integer(), nullable=True),
        sa.Column('used_count', sa.Integer(), default=0),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── 3. quick_sell_items ─────────────────────────────────────────────────
    op.create_table(
        'quick_sell_items',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('cafes.id'), nullable=True, index=True),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id', ondelete='CASCADE'), nullable=False),
        sa.Column('display_name', sa.String(50), nullable=True),  # qisqa nom
        sa.Column('display_order', sa.Integer(), default=0),
        sa.Column('color', sa.String(20), default='#4CAF50'),     # rang kodi
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── 4. purchase_orders (priyomka) ────────────────────────────────────────
    op.create_table(
        'purchase_orders',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('cafes.id'), nullable=True, index=True),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id'), nullable=True),
        sa.Column('supplier_id', sa.Integer(), sa.ForeignKey('suppliers.id'), nullable=True),
        sa.Column('po_number', sa.String(30), unique=True, nullable=False),
        # status: draft|received|partial|cancelled
        sa.Column('status', sa.String(20), default='draft'),
        sa.Column('invoice_number', sa.String(50), nullable=True),
        sa.Column('ordered_at', sa.DateTime(), nullable=True),
        sa.Column('received_at', sa.DateTime(), nullable=True),
        sa.Column('total_amount', sa.Float(), default=0.0),
        sa.Column('paid_amount', sa.Float(), default=0.0),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # ── 5. purchase_order_items ──────────────────────────────────────────────
    op.create_table(
        'purchase_order_items',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('po_id', sa.Integer(), sa.ForeignKey('purchase_orders.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('received_qty', sa.Float(), default=0.0),
        sa.Column('unit_cost', sa.Float(), nullable=False),
        sa.Column('total', sa.Float(), nullable=False),
        sa.Column('expiry_date', sa.Date(), nullable=True),
        sa.Column('batch_number', sa.String(50), nullable=True),
    )

    # ── 6. supplier_payments ─────────────────────────────────────────────────
    op.create_table(
        'supplier_payments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('cafes.id'), nullable=True, index=True),
        sa.Column('supplier_id', sa.Integer(), sa.ForeignKey('suppliers.id'), nullable=False, index=True),
        sa.Column('po_id', sa.Integer(), sa.ForeignKey('purchase_orders.id'), nullable=True),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('payment_method', sa.String(20), default='cash'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── 7. price_history ─────────────────────────────────────────────────────
    op.create_table(
        'price_history',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('cafes.id'), nullable=True, index=True),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('old_price', sa.Float(), nullable=False),
        sa.Column('new_price', sa.Float(), nullable=False),
        sa.Column('old_cost', sa.Float(), nullable=True),
        sa.Column('new_cost', sa.Float(), nullable=True),
        sa.Column('reason', sa.String(200), nullable=True),
        sa.Column('changed_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )

    # ── 8. receipt_settings ──────────────────────────────────────────────────
    op.create_table(
        'receipt_settings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('cafes.id'), nullable=False, unique=True),
        sa.Column('store_name', sa.String(150), nullable=True),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('phone', sa.String(30), nullable=True),
        sa.Column('tax_id', sa.String(30), nullable=True),
        sa.Column('header_text', sa.Text(), nullable=True),
        sa.Column('footer_text', sa.Text(), nullable=True),
        sa.Column('show_logo', sa.Boolean(), default=False),
        sa.Column('qr_enabled', sa.Boolean(), default=False),
        sa.Column('qr_url', sa.String(300), nullable=True),
        sa.Column('paper_width', sa.Integer(), default=80),   # mm: 57|80
        sa.Column('font_size', sa.String(10), default='normal'),  # small|normal|large
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # ── 9. shifts jadvaliga yangi ustunlar ───────────────────────────────────
    with op.batch_alter_table('shifts') as batch_op:
        batch_op.add_column(sa.Column('credit_total', sa.Float(), server_default='0'))
        batch_op.add_column(sa.Column('counted_cash', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('shortage', sa.Float(), server_default='0'))  # kamomad (-)

    # ── 10. inventory_counts jadvaliga category_id ───────────────────────────
    with op.batch_alter_table('inventory_counts') as batch_op:
        batch_op.add_column(sa.Column('category_id', sa.Integer(), sa.ForeignKey('categories.id'), nullable=True))
        batch_op.add_column(sa.Column('count_type', sa.String(20), server_default='full'))  # full|partial


def downgrade():
    op.drop_table('receipt_settings')
    op.drop_table('price_history')
    op.drop_table('supplier_payments')
    op.drop_table('purchase_order_items')
    op.drop_table('purchase_orders')
    op.drop_table('quick_sell_items')
    op.drop_table('promotions')
    op.drop_table('product_barcodes')
    with op.batch_alter_table('shifts') as batch_op:
        batch_op.drop_column('credit_total')
        batch_op.drop_column('counted_cash')
        batch_op.drop_column('shortage')
    with op.batch_alter_table('inventory_counts') as batch_op:
        batch_op.drop_column('category_id')
        batch_op.drop_column('count_type')
