"""Bo'limlar (Departments) tizimi — magazin/supermarket uchun fizik seksiyalar"""

revision = 'l7m8n9o0p1q2'
down_revision = 'k6l7m8n9o0p1'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    # ── 1. departments jadval ────────────────────────────────────────────────
    op.create_table(
        'departments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('cafes.id'), nullable=True, index=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('color', sa.String(20), default='#6366f1'),   # rang kodi
        sa.Column('icon', sa.String(50), nullable=True),        # emoji yoki icon nomi
        sa.Column('display_order', sa.Integer(), default=0),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # ── 2. products.department_id ────────────────────────────────────────────
    with op.batch_alter_table('products') as batch_op:
        batch_op.add_column(
            sa.Column('department_id', sa.Integer(),
                      sa.ForeignKey('departments.id', ondelete='SET NULL'),
                      nullable=True, index=True)
        )

    # ── 3. categories.department_id ──────────────────────────────────────────
    with op.batch_alter_table('categories') as batch_op:
        batch_op.add_column(
            sa.Column('department_id', sa.Integer(),
                      sa.ForeignKey('departments.id', ondelete='SET NULL'),
                      nullable=True, index=True)
        )
        batch_op.add_column(
            sa.Column('color', sa.String(20), nullable=True)
        )
        batch_op.add_column(
            sa.Column('icon', sa.String(50), nullable=True)
        )


def downgrade():
    with op.batch_alter_table('categories') as batch_op:
        batch_op.drop_column('icon')
        batch_op.drop_column('color')
        batch_op.drop_column('department_id')
    with op.batch_alter_table('products') as batch_op:
        batch_op.drop_column('department_id')
    op.drop_table('departments')
