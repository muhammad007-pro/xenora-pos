"""merge tenant_payments + free_product heads (2 parallel migratsiyani birlashtirish)

subscription-invoice (`f2a3b4c5d6e7` — tenant_payments) va pricing-resolver (`c3d4e5f6a7b8` —
promotions.free_product_id) ikkalasi ham `d0e1f2a3b4c5`ning PARALLEL bolasi edi → 2 alembic head.
Bu MERGE revision ularni BITTA head'ga birlashtiradi. HECH QANDAY jadval/ustun/data o'zgarmaydi
(upgrade/downgrade BO'SH) — faqat migratsiya zanjirini yagona head qiladi.

Revision ID: b9c8d7e6f5a4
Revises: c3d4e5f6a7b8, f2a3b4c5d6e7
Create Date: 2026-07-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b9c8d7e6f5a4'
down_revision: Union[str, Sequence[str], None] = ('c3d4e5f6a7b8', 'f2a3b4c5d6e7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
