"""pachka/dona B0: pack_size/pack_price + base_qty/unit_sold ustunlari

B0 (poydevor) — 1 mahsulot ham PACHKA, ham DONA sotilishi uchun 4 nullable ustun.
Hech qaysi kod (POS, ombor, chek, forma) bu maydonlarni HALI ishlatmaydi — shu
sabab sotuv/ombor xulqi 0 o'zgaradi. Keyingi bosqichlar (B1..B7) ularni bosqichma-
bosqich ishlatadi.

  products.pack_size   INTEGER          — 1 pachka = nechta dona (NULL/<2 = pachkasiz)
  products.pack_price  DOUBLE PRECISION — 1 pachka narxi (price = dona narxi)
  order_items.base_qty  DOUBLE PRECISION — ombordan ayiriladigan DONA miqdori
  order_items.unit_sold VARCHAR(20)      — "pachka" | "dona" | NULL

Barcha ustun NULLABLE, default YO'Q → mavjud qatorlar NULL bo'lib qoladi (data
o'zgarmaydi). IF NOT EXISTS / IF EXISTS bilan — qayta/qisman qo'llangan muhitda
xato bermaydi. OrderItem.quantity Integer QOLADI (pachka soni butun son).

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    # Product — pachka narxi + o'lchami (dona = base birlik, price = dona narxi)
    conn.execute(sa.text(
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS pack_size INTEGER"
    ))
    conn.execute(sa.text(
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS pack_price DOUBLE PRECISION"
    ))
    # OrderItem — ombor chiqimi uchun dona miqdori + sotilgan birlik yorlig'i
    conn.execute(sa.text(
        "ALTER TABLE order_items ADD COLUMN IF NOT EXISTS base_qty DOUBLE PRECISION"
    ))
    conn.execute(sa.text(
        "ALTER TABLE order_items ADD COLUMN IF NOT EXISTS unit_sold VARCHAR(20)"
    ))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE order_items DROP COLUMN IF EXISTS unit_sold"))
    conn.execute(sa.text("ALTER TABLE order_items DROP COLUMN IF EXISTS base_qty"))
    conn.execute(sa.text("ALTER TABLE products DROP COLUMN IF EXISTS pack_price"))
    conn.execute(sa.text("ALTER TABLE products DROP COLUMN IF EXISTS pack_size"))
