"""username unikalligini tenant ichiga ko'chirish (global unique → composite)

Xato #7: har do'konda "admin"/"cashier" kabi username takrorlanishi kerak (rol nomi,
tenant ichida). Ilgari `users.username` GLOBAL unique edi → ikkinchi tenant "admin"
qo'ysa "band" xatosi. Endi unikallik (tenant_id, username) bo'yicha — tenant izolyatsiya
buzilmaydi, faqat validatsiya doirasi torayadi.

Revision ID: e5f6a7b9c0d1
Revises: d4e5f6a7b9c0
Create Date: 2026-07-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b9c0d1'
down_revision: Union[str, None] = 'd4e5f6a7b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    # Eski GLOBAL unique cheklovini olib tashlash. Postgres avtomatik nom bergan
    # (odatda users_username_key). Nom o'zgargan bo'lsa ham xato bermasin — IF EXISTS.
    conn.execute(sa.text("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_username_key"))
    # Ehtimoliy unique indeks (ba'zi muhitlarda indeks sifatida yaratilgan) ni ham olib tashlaymiz.
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_users_username"))
    # Oddiy (unikal bo'lmagan) qidiruv indeksini qayta yaratamiz — qidiruv tezligi uchun.
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_users_username ON users (username)"))
    # Yangi TENANT-SCOPED unique cheklov.
    op.create_unique_constraint("uq_users_tenant_username", "users", ["tenant_id", "username"])


def downgrade() -> None:
    conn = op.get_bind()
    op.drop_constraint("uq_users_tenant_username", "users", type_="unique")
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_users_username"))
    conn.execute(sa.text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username)"))
