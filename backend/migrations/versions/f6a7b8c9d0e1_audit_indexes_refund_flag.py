"""audit tozalash: refund flag + tezlik indekslari (B4)

Ikki maqsad:
  1) A2 (refund ombor tiklash) uchun orders.ingredients_restored bayrog'i —
     to'liq qaytarish omborni bir marta tiklashini kafolatlaydi (idempotent).
  2) B4 (tezlik) composite indekslar:
       - orders(tenant_id, created_at)  → hisobot sana oralig'i + tartiblash
       - orders(tenant_id, status)      → status filtri
       - products(tenant_id, category_id) → kategoriya bo'yicha katalog filtri
     Ilgari faqat tenant_id yakka indeksda edi; sana/status/kategoriya filtri
     to'liq skanga tushardi.

Barcha amal IF NOT EXISTS bilan — qayta ishga tushirish yoki qisman qo'llangan
muhitda xato bermaydi (xavfsiz migratsiya).

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b9c0d1
Create Date: 2026-07-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b9c0d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1) orders.ingredients_restored — refund idempotentligi uchun.
    #    server_default='false' → mavjud qatorlar False bilan to'ldiriladi.
    conn.execute(sa.text(
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS ingredients_restored "
        "BOOLEAN NOT NULL DEFAULT false"
    ))

    # 2) Tezlik indekslari (composite — tenant birinchi ustun).
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_orders_tenant_created "
        "ON orders (tenant_id, created_at)"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_orders_tenant_status "
        "ON orders (tenant_id, status)"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_products_tenant_category "
        "ON products (tenant_id, category_id)"
    ))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_products_tenant_category"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_orders_tenant_status"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_orders_tenant_created"))
    conn.execute(sa.text("ALTER TABLE orders DROP COLUMN IF EXISTS ingredients_restored"))
