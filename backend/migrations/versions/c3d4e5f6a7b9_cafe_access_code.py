"""cafes jadvaliga access_code (do'kon kirish kodi 100.200.N) qo'shish + mavjudlarni to'ldirish

Revision ID: c3d4e5f6a7b9
Revises: b2c3d4e5f6a8
Create Date: 2026-07-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b9'
down_revision: Union[str, None] = 'b2c3d4e5f6a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('cafes', sa.Column('access_code', sa.String(length=20), nullable=True))
    op.create_index('ix_cafes_access_code', 'cafes', ['access_code'], unique=True)

    # Mavjud do'konlarga 100.200.N kodini id tartibida beramiz (faol/nofaol farqsiz — noyob).
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id FROM cafes ORDER BY id")).fetchall()
    for i, row in enumerate(rows, start=1):
        conn.execute(
            sa.text("UPDATE cafes SET access_code = :ac WHERE id = :id"),
            {"ac": f"100.200.{i}", "id": row[0]},
        )


def downgrade() -> None:
    op.drop_index('ix_cafes_access_code', table_name='cafes')
    op.drop_column('cafes', 'access_code')
