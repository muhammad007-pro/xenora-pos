"""tenant_payments jadvali — IDEMPOTENT (obuna to'lov/invoice tarixi)

TenantPayment modeli allaqachon bor edi va jonli DB'da `tenant_payments` jadvali
`create_all`'dan YARATILGAN (database.py:48 — create_all endi o'chirilgan). Bu migratsiya
uni RASMIYLASHTIRADI: toza (migrate-only) deploy'da jadval yaratiladi; jonli DB'da jadval
ALLAQACHON bor → `CREATE TABLE IF NOT EXISTS` HECH NARSA qilmaydi (no-op, data buzilmaydi).

MUHIM: faqat IF NOT EXISTS — mavjud jadvalni O'ZGARTIRMAYDI, ma'lumot yo'qotmaydi.

Revision ID: f2a3b4c5d6e7
Revises: d0e1f2a3b4c5
Create Date: 2026-07-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, None] = 'd0e1f2a3b4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    # Jadval — modeldagi ustunlar bilan bir xil (Integer/Float/String(20)/DateTime/Text).
    # IF NOT EXISTS: jonli DB'da jadval bor → no-op; toza DB'da → yaratadi.
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS tenant_payments (
            id             SERIAL PRIMARY KEY,
            tenant_id      INTEGER NOT NULL REFERENCES cafes(id),
            amount         DOUBLE PRECISION NOT NULL,
            months         INTEGER DEFAULT 1,
            payment_method VARCHAR(20) DEFAULT 'cash',
            period_start   TIMESTAMP WITHOUT TIME ZONE,
            period_end     TIMESTAMP WITHOUT TIME ZONE,
            note           TEXT,
            created_by_id  INTEGER REFERENCES users(id),
            created_at     TIMESTAMP WITH TIME ZONE DEFAULT now()
        )
    """))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_tenant_payments_tenant_id ON tenant_payments (tenant_id)"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_tenant_payments_id ON tenant_payments (id)"
    ))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_tenant_payments_id"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_tenant_payments_tenant_id"))
    conn.execute(sa.text("DROP TABLE IF EXISTS tenant_payments"))
