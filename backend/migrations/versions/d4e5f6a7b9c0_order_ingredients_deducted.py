"""orders jadvaliga ingredients_deducted (retsept chiqimi bir marta) qo'shish

Oshxona 2-bosqich: zakaz "ready" bo'lganda retsept inventar chiqimi bir marta bo'lishi
kerak. reopen (tayyor→faol qaytarish) + qayta-ready ikki marta chiqim qilmasin.

Revision ID: d4e5f6a7b9c0
Revises: c3d4e5f6a7b9
Create Date: 2026-07-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b9c0'
down_revision: Union[str, None] = 'c3d4e5f6a7b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('orders', sa.Column('ingredients_deducted', sa.Boolean(), nullable=True, server_default=sa.false()))
    # Mavjud yakunlangan zakazlar (completed) allaqachon chiqim qilingan deb belgilaymiz,
    # aks holda ular reopen bo'lса (imkonsiz — himoyalangan) yoki hisobда chalkashmasin.
    conn = op.get_bind()
    # status — native enum; text'ga cast qilib registrga bog'liq bo'lmagan solishtirish
    conn.execute(sa.text(
        "UPDATE orders SET ingredients_deducted = true "
        "WHERE lower(status::text) IN ('ready','completed','served')"
    ))
    conn.execute(sa.text("UPDATE orders SET ingredients_deducted = false WHERE ingredients_deducted IS NULL"))


def downgrade() -> None:
    op.drop_column('orders', 'ingredients_deducted')
