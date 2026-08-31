"""cafes.block_oversell — qoldiq yetmasa sotuvni bloklash

Revision ID: c8b3e5d90a17
Revises: 9c4e1a7b30df
Create Date: 2026-09-01

NEGA: POS ombor qoldig'ini UMUMAN tekshirmasdi. Sotuv o'tardi, ombor esa
0 da to'xtatilib (`recipe_inventory_service._deduct_product_directly`)
kamomad JIMGINA yo'qolardi — manfiy qoldiq ham qolmasdi, ya'ni ekranda
hech qanday signal yo'q edi. Fazza Parfum'da 15–31 avgust oralig'ida
24 ta shunday sotuv (22 buyurtma, 14 mahsulot, 297 dona) topildi.

Ziddiyat ham bor edi: xuddi shu ombordan QO'LDA chiqim va hisobdan o'chirish
BLOKLANADI (`routers/inventory.py`: "Yetarli miqdor yo'q"), sotish esa yo'q.

⚠️ DEFAULT — IKKI XIL, ATAYIN:
  • MAVJUD do'konlar -> FALSE. Fazza'da 92, Eco Aroma'da 7 mahsulot hozir
    qoldiq 0. TRUE qilinsa ular ERTAGA o'sha tovarlarni sotolmasdi —
    tuzatish do'konni ishdan chiqargan bo'lardi. Egasi inventarizatsiya
    qilib, haqiqiy qoldiqni kiritgach Sozlamalardan O'ZI yoqadi.
  • YANGI do'konlar -> TRUE (to'g'ri standart). Buning uchun ustun avval
    DEFAULT FALSE bilan qo'shiladi (mavjud qatorlar false oladi), keyin
    DEFAULT TRUE ga o'zgartiriladi. Ikki qadam ataylab.

Batafsil qoida va istisnolar: services/stock_guard.py
"""
from alembic import op
import sqlalchemy as sa

revision = "c8b3e5d90a17"
down_revision = "9c4e1a7b30df"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # 1-qadam: mavjud qatorlar FALSE oladi
        op.execute(
            "ALTER TABLE cafes "
            "ADD COLUMN IF NOT EXISTS block_oversell BOOLEAN NOT NULL DEFAULT FALSE"
        )
        # 2-qadam: BUNDAN KEYINGI yangi do'konlar TRUE bo'ladi
        op.execute("ALTER TABLE cafes ALTER COLUMN block_oversell SET DEFAULT TRUE")
    else:
        cols = {c["name"] for c in sa.inspect(bind).get_columns("cafes")}
        if "block_oversell" not in cols:
            # SQLite `ALTER COLUMN` ni qo'llab-quvvatlamaydi. Testlarda jadval
            # `Base.metadata.create_all()` bilan MODELDAN quriladi (server_default
            # "true"), shuning uchun bu shox faqat mavjud sqlite bazani yangilash
            # uchun — u yerda ham mavjud qatorlar FALSE bo'lishi kerak.
            op.add_column(
                "cafes",
                sa.Column("block_oversell", sa.Boolean(), nullable=False,
                          server_default=sa.text("0")),
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE cafes DROP COLUMN IF EXISTS block_oversell")
    else:
        op.drop_column("cafes", "block_oversell")
