"""purchase_receipts.is_manual_debt — priyomkasiz ("qo'lda") firma qarzi

Revision ID: 3f7a2c9e1b04
Revises: 72d684a734c4
Create Date: 2026-08-29

NEGA: Fazza Parfum tovar hisobini yuritmaydi — ular firmadan nasiyaga tovar
oladi va faqat PUL OLDI-BERDIni yozib borishni xohlaydi. Ilgari qarzni oshirish
uchun yagona yo'l tovarli nakladnoy kiritish edi (ya'ni ombor hisobini yuritish
majburiy bo'lardi). `suppliers.opening_debt` esa BITTA son — sanasi, izohi va
tarixi yo'q, xato kiritilganini alohida bekor qilib ham bo'lmaydi.

Yechim: summasi bor, tovar qatorlari yo'q priyomka. Iqtisodiy ma'noda bu aynan
nasiyaga xarid, shuning uchun FIFO, oborot varag'i, /debt-summary va
/store-dashboard O'ZGARISHSIZ ishlaydi (services/supplier_debt.py dagi
`compute_supplier_debt()` ga bitta qator ham qo'shilmadi).

⚠️ NEGA "QATORI YO'Q" DEB TAXMIN QILINMAYDI: birinchi urinishda marker
`len(items) == 0` edi. U mavjud testni buzdi — test fixture'i qatorsiz
nakladnoy yaratardi va u JIMGINA "qo'lda qarz" bo'lib ko'rindi. Bu shu
loyihada qayta-qayta uchragan xato sinfi: semantik xossani tasodifiy xossaga
bog'lash. Aniq ustun bilan bunday chalkashlik mumkin emas.

XAVFSIZLIK: `ADD COLUMN IF NOT EXISTS`, NOT NULL + server_default 'false'.
Mavjud qatorlar avtomatik `false` oladi, ya'ni ularning hammasi ODDIY
nakladnoy bo'lib qoladi — birorta qarz raqami o'zgarmaydi. Ma'lumot
o'zgartirilmaydi, faqat ustun qo'shiladi.
"""
from alembic import op
import sqlalchemy as sa

revision = "3f7a2c9e1b04"
down_revision = "72d684a734c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE purchase_receipts "
            "ADD COLUMN IF NOT EXISTS is_manual_debt BOOLEAN NOT NULL DEFAULT FALSE"
        )
    else:
        cols = {c["name"] for c in sa.inspect(bind).get_columns("purchase_receipts")}
        if "is_manual_debt" not in cols:
            op.add_column(
                "purchase_receipts",
                sa.Column("is_manual_debt", sa.Boolean(), nullable=False,
                          server_default=sa.text("0")),
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE purchase_receipts DROP COLUMN IF EXISTS is_manual_debt")
    else:
        op.drop_column("purchase_receipts", "is_manual_debt")
