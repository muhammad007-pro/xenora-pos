"""employee_pin_hash_bosqich_29

Employees.pin_code (ochiq matn) → employees.hashed_pin (HMAC-SHA256).
Ochiq matnli PIN bazada qolmaydi. Mavjud PINlar hash qilib ko'chiriladi.

Revision ID: t6u7v8w9x0y1
Revises: s5t6u7v8w9x0
Create Date: 2026-06-19 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 't6u7v8w9x0y1'
down_revision: Union[str, None] = 's5t6u7v8w9x0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Yangi hash ustuni
    op.add_column('employees', sa.Column('hashed_pin', sa.String(64), nullable=True))
    op.create_index('ix_employees_hashed_pin', 'employees', ['hashed_pin'], unique=False)

    # 2) Mavjud ochiq-matn PINlarni hash qilib ko'chirish (loyiha hash_pin bilan bir xil)
    from core.security import hash_pin
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, pin_code FROM employees WHERE pin_code IS NOT NULL AND pin_code <> ''"
    )).fetchall()
    for row in rows:
        conn.execute(
            sa.text("UPDATE employees SET hashed_pin = :h WHERE id = :id"),
            {"h": hash_pin(str(row[1])), "id": row[0]},
        )

    # 3) Ochiq-matn ustunni butunlay olib tashlash (unique constraint ham tushadi)
    op.drop_column('employees', 'pin_code')


def downgrade() -> None:
    # Ochiq matnni tiklab bo'lmaydi — ustun bo'sh holatda qaytariladi
    op.add_column('employees', sa.Column('pin_code', sa.String(10), nullable=True))
    op.drop_index('ix_employees_hashed_pin', table_name='employees')
    op.drop_column('employees', 'hashed_pin')
