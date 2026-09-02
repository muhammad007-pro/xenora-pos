"""cafes.telegram_chat_id + subscription_alerts — obuna Telegram ogohlantirishlari

Revision ID: d9e4f1a2b3c5
Revises: c8b3e5d90a17
Create Date: 2026-09-02

NEGA: mijoz ekranga qaramasa muddat tugayotganini bilmasdi. Bannerni faqat
ilovaga kirgan odam ko'radi; egasi bir hafta kirmasa, muddat jimgina tugardi.

IKKI OBYEKT:

1) `cafes.telegram_chat_id` — do'kon egasining chat id'si (nullable).
   Bo'sh bo'lsa egasiga xabar yuborilmaydi (super-admin kanali mustaqil).
   Qiymatni super-admin qo'lda kiritadi.

2) `subscription_alerts` — YUBORILGAN xabar yozuvi, takrorni to'sadi.
   UNIQUE(tenant_id, stage, expiry_date, audience).
   Kalitga MUDDAT SANASI ataylab kiritilgan: obuna uzaytirilsa sana o'zgaradi
   va yangi ogohlantirish tsikli o'z-o'zidan ochiladi — hech qanday "flagni
   nollash" qadami yo'q. `cafes` ga "oxirgi bosqich" ustuni qo'yilganda aynan
   shu nollashni unutish tuzog'i paydo bo'lardi (`renew_subscription` da
   xuddi shunday xato bo'lgan edi, v1.10.2 da tuzatildi).

IDEMPOTENT: `IF NOT EXISTS` / inspector tekshiruvi bilan — qayta yugurtirilsa
xato bermaydi. `downgrade()` ikkalasini ham qaytarib olib tashlaydi.

⚠️ MA'LUMOT YO'QOLMAYDI: faqat qo'shiladi, mavjud ustunlarga tegilmaydi.
"""
from alembic import op
import sqlalchemy as sa

revision = "d9e4f1a2b3c5"
down_revision = "c8b3e5d90a17"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # ── 1) cafes.telegram_chat_id ────────────────────────────────────────────
    cols = {c["name"] for c in insp.get_columns("cafes")}
    if "telegram_chat_id" not in cols:
        op.add_column("cafes", sa.Column("telegram_chat_id", sa.String(32), nullable=True))

    # ── 2) subscription_alerts ───────────────────────────────────────────────
    if "subscription_alerts" not in insp.get_table_names():
        op.create_table(
            "subscription_alerts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(),
                      sa.ForeignKey("cafes.id"), nullable=False),
            sa.Column("stage", sa.String(16), nullable=False),
            sa.Column("audience", sa.String(16), nullable=False),
            sa.Column("expiry_date", sa.Date(), nullable=False),
            sa.Column("sent_at", sa.DateTime(), nullable=False,
                      server_default=sa.func.now()),
            sa.UniqueConstraint("tenant_id", "stage", "expiry_date", "audience",
                                name="uq_subscription_alert_once"),
        )
        op.create_index("ix_subscription_alerts_tenant",
                        "subscription_alerts", ["tenant_id"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "subscription_alerts" in insp.get_table_names():
        # Indeks jadval bilan birga ketadi, lekin aniq bo'lsin.
        try:
            op.drop_index("ix_subscription_alerts_tenant",
                          table_name="subscription_alerts")
        except Exception:
            pass
        op.drop_table("subscription_alerts")

    cols = {c["name"] for c in insp.get_columns("cafes")}
    if "telegram_chat_id" in cols:
        op.drop_column("cafes", "telegram_chat_id")
