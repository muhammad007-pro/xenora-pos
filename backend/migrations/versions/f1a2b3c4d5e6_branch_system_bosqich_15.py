"""branch_system_bosqich_15

Revision ID: f1a2b3c4d5e6
Revises: 56c6f688ae01
Create Date: 2026-06-13 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = '56c6f688ae01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. branches jadvali yaratish
    op.create_table(
        'branches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('phone', sa.String(20), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['cafes.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_branches_id', 'branches', ['id'])
    op.create_index('ix_branches_tenant_id', 'branches', ['tenant_id'])

    # 2. branch_id ustunlarini qo'shish (nullable — eski ma'lumot buzilmaydi)
    tables_to_update = [
        'users', 'orders', 'payments', 'inventory',
        'employees', 'tables', 'shifts', 'reservations',
        'service_orders', 'rooms', 'room_bookings',
        'appointments', 'memberships',
    ]
    for tbl in tables_to_update:
        op.add_column(tbl, sa.Column(
            'branch_id', sa.Integer(),
            sa.ForeignKey('branches.id'),
            nullable=True,
            index=True
        ))

    # 3. inventory jadvalidagi product_id unique cheklovini olib tashlash
    #    (har filialda bitta mahsulotga alohida inventar bo'lishi mumkin)
    try:
        op.drop_constraint('inventory_product_id_key', 'inventory', type_='unique')
    except Exception:
        pass  # Constraint nomi boshqacha bo'lishi mumkin — xatolikni o'tkazib yuboramiz

    # 4. tables jadvalidagi number unique cheklovini olib tashlash
    #    (2 ta filialda ham "Stol 1" bo'lishi mumkin)
    try:
        op.drop_constraint('tables_number_key', 'tables', type_='unique')
    except Exception:
        pass

    # 5. Har tenant uchun "Asosiy filial" yaratish va eski yozuvlarni bog'lash
    conn = op.get_bind()

    # Hamma aktiv tenantlarni olish
    cafes = conn.execute(sa.text("SELECT id, name FROM cafes")).fetchall()

    for cafe in cafes:
        tenant_id = cafe[0]
        cafe_name = cafe[1]

        # Default filial qo'shish
        result = conn.execute(
            sa.text(
                "INSERT INTO branches (tenant_id, name, is_active, is_default) "
                "VALUES (:tid, :name, true, true) RETURNING id"
            ),
            {"tid": tenant_id, "name": f"Asosiy filial"}
        )
        branch_id = result.fetchone()[0]

        # Eski yozuvlarni default filialga bog'lash
        for tbl in tables_to_update:
            try:
                # Faqat bu tenantga tegishli yozuvlarni yangilash
                if tbl == 'users':
                    conn.execute(
                        sa.text(f"UPDATE {tbl} SET branch_id = :bid WHERE tenant_id = :tid AND branch_id IS NULL"),
                        {"bid": branch_id, "tid": tenant_id}
                    )
                elif tbl in ('tables', 'reservations'):
                    # tables va reservations tenant_id ga ega
                    conn.execute(
                        sa.text(f"UPDATE {tbl} SET branch_id = :bid WHERE tenant_id = :tid AND branch_id IS NULL"),
                        {"bid": branch_id, "tid": tenant_id}
                    )
                else:
                    conn.execute(
                        sa.text(f"UPDATE {tbl} SET branch_id = :bid WHERE tenant_id = :tid AND branch_id IS NULL"),
                        {"bid": branch_id, "tid": tenant_id}
                    )
            except Exception:
                pass  # Jadvalda tenant_id yo'q bo'lsa — o'tkazib yuboramiz


def downgrade() -> None:
    tables_to_update = [
        'users', 'orders', 'payments', 'inventory',
        'employees', 'tables', 'shifts', 'reservations',
        'service_orders', 'rooms', 'room_bookings',
        'appointments', 'memberships',
    ]
    for tbl in tables_to_update:
        try:
            op.drop_column(tbl, 'branch_id')
        except Exception:
            pass

    op.drop_index('ix_branches_tenant_id', 'branches')
    op.drop_index('ix_branches_id', 'branches')
    op.drop_table('branches')
