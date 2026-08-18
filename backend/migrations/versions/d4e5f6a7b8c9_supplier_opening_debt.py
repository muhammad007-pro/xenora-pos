"""suppliers.opening_debt — boshlang'ich qarz (FAZA 3)

Revision ID: d4e5f6a7b8c9
Revises: b9c8d7e6f5a4
Create Date: 2026-08-18

NEGA: do'kon XENORA'ni yangi o'rnatganda firmaga ALLAQACHON qarzi bo'ladi, lekin
unga mos priyomka hujjati yo'q. Ilgari o'sha eski qarzni kiritish joyi umuman
yo'q edi — do'konchi soxta priyomka yaratishga majbur bo'lardi (ombor qoldig'ini
buzadi).

NEGA `balance` EMAS: mavjud `suppliers.balance` ustunining tarixi iflos — Ombor
"Kirim qilish" o'sha yerga yozardi (B2, f812ecb da to'xtatildi). Uni qayta
ta'riflash semantikani chalkashtiradi, shuning uchun YANGI ustun.

XAVFSIZLIK:
  - `ADD COLUMN IF NOT EXISTS` / `DROP COLUMN IF EXISTS` — idempotent
  - `DEFAULT 0` + NOT NULL — mavjud qatorlar 0 oladi, ma'lumot yo'qolmaydi
  - jadval qulflanishi minimal (PostgreSQL 11+ da default bilan ADD COLUMN
    jadvalni qayta yozmaydi)
  - downgrade ustunni o'chiradi (unda saqlangan qiymatlar yo'qoladi — pastda
    ogohlantirish yoziladi)

⚠️ DEPLOY: backup-first (`pg_dump`) — kod deployidan ALOHIDA qadam.
"""
from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "b9c8d7e6f5a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE suppliers "
            "ADD COLUMN IF NOT EXISTS opening_debt NUMERIC(14,2) NOT NULL DEFAULT 0"
        )
    else:
        # sqlite (testlar) — IF NOT EXISTS yo'q, ustun bor-yo'qligini o'zimiz tekshiramiz
        cols = {c["name"] for c in sa.inspect(bind).get_columns("suppliers")}
        if "opening_debt" not in cols:
            op.add_column(
                "suppliers",
                sa.Column("opening_debt", sa.Numeric(14, 2),
                          nullable=False, server_default="0"),
            )


def downgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT count(*) FROM suppliers WHERE opening_debt <> 0"
    )).scalar() if bind.dialect.name == "postgresql" else 0
    if rows:
        print(f"[downgrade] DIQQAT: {rows} ta firmada boshlang'ich qarz kiritilgan — "
              f"ustun o'chirilishi bilan bu qiymatlar YO'QOLADI.")

    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE suppliers DROP COLUMN IF EXISTS opening_debt")
    else:
        op.drop_column("suppliers", "opening_debt")
