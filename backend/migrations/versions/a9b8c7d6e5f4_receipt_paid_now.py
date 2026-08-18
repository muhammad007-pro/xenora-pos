"""purchase_receipts.paid_now — "Hozir to'landi" (FAZA 4)

Revision ID: a9b8c7d6e5f4
Revises: d4e5f6a7b8c9
Create Date: 2026-08-18

NEGA: nakladnoy kelganda do'konchi ko'pincha DARHOL bir qism pul beradi. Ilgari
buni yozish uchun 3 ekran kerak edi: Priyomka yarat -> Tasdiqla -> Qarzlar tabida
to'lov. Endi summa nakladnoy oynasida kiritiladi.

NEGA USTUN KERAK: to'lov yozuvi (SupplierPayment) priyomka TASDIQLANGANDA
yaratiladi — draft hali qarz emas, unga to'lov bog'lash "avans" bo'lib
ko'rinardi. Yaratish va tasdiqlash orasida summa shu ustunda saqlanadi.

XAVFSIZLIK: `ADD COLUMN IF NOT EXISTS` (idempotent), `DEFAULT 0` + NOT NULL
(mavjud qatorlar 0 oladi), downgrade `DROP COLUMN IF EXISTS`.
⚠️ DEPLOY: backup-first, kod deployidan ALOHIDA qadam.
"""
from alembic import op
import sqlalchemy as sa

revision = "a9b8c7d6e5f4"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE purchase_receipts "
            "ADD COLUMN IF NOT EXISTS paid_now NUMERIC(14,2) NOT NULL DEFAULT 0"
        )
    else:
        cols = {c["name"] for c in sa.inspect(bind).get_columns("purchase_receipts")}
        if "paid_now" not in cols:
            op.add_column(
                "purchase_receipts",
                sa.Column("paid_now", sa.Numeric(14, 2),
                          nullable=False, server_default="0"),
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Ma'lumot yo'qolishi: bu ustun faqat "yaratish -> tasdiqlash" oralig'i
        # uchun. Tasdiqlangan priyomkalarda pul allaqachon supplier_payments da,
        # ya'ni qarz hisobi buzilmaydi.
        op.execute("ALTER TABLE purchase_receipts DROP COLUMN IF EXISTS paid_now")
    else:
        op.drop_column("purchase_receipts", "paid_now")
