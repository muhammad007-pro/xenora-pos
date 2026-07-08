"""order_daily_unique_bosqich_33

(tenant_id, created_at kun, daily_number) bo'yicha UNIQUE indeks.
Maqsad: bir tenant + bir kun ichida daily_number takrorlanmasin (konkurensiya kafolati).
create_order retry mantig'i shu bilan ishlaydi (IntegrityError → qayta urinadi).

daily_number NULL bo'lgan eski buyurtmalar to'qnashmaydi (PG unique NULL'larni hisobga olmaydi).

Revision ID: z3a4b5c6d7e8
Revises: y2z3a4b5c6d7
Create Date: 2026-06-22 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op


revision: str = 'z3a4b5c6d7e8'
down_revision: Union[str, None] = 'y2z3a4b5c6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # timezone('Asia/Tashkent', created_at)::date — IMMUTABLE (indeks ifodasi uchun shart).
    # Oddiy created_at::date (timestamptz) STABLE bo'lib, PG indeksga ruxsat bermaydi.
    op.execute(
        "CREATE UNIQUE INDEX uq_orders_tenant_day_daily "
        "ON orders (tenant_id, (timezone('Asia/Tashkent', created_at)::date), daily_number)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_orders_tenant_day_daily")
