"""baseline - mavjud sxema (create_all orqali yaratilgan)

Revision ID: ca406934e5dd
Revises: 
Create Date: 2026-06-09 00:10:37.760315

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ca406934e5dd'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Bo'sh baseline: bu sxema avval Base.metadata.create_all() orqali
    # yaratilgan edi (BOSQICH 1.1). Shu nuqtadan boshlab barcha o'zgarishlar
    # faqat Alembic migratsiyalari orqali amalga oshiriladi.
    pass


def downgrade() -> None:
    pass
