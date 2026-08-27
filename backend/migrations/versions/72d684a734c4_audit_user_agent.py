"""audit_logs.user_agent — audit izidagi ikkinchi identifikator

Revision ID: 72d684a734c4
Revises: a9b8c7d6e5f4
Create Date: 2026-08-27

NEGA: 2026-08-27 xavfsizlik tekshiruvida (/auth/register teshigi) `ip_address`
ustuni BOR-u, hamma qatorda NULL ekani aniqlandi — `client_ip()` yozilgan edi,
lekin 18 ta `log_audit()` chaqiruvining birortasi uni uzatmasdi. Kelajakda
buzilish bo'lsa "kim qildi" degan savolga javob yo'q edi.

Endi IP middleware orqali AVTOMATIK yoziladi. User-Agent — ikkinchi qatlam:
IP o'zgaruvchan (mobil internet, NAT), lekin UA qaysi ILOVA ekanini aytadi:
    "... xenora/1.9.5 ... Electron/27.3.11 ..."  -> do'kondagi .exe
    "... Mobile ... Capacitor ..."               -> APK
    "curl/8.x", "python-requests/..."            -> SKRIPT (shubhali!)
Aynan shu farq hujumni oddiy ishdan ajratishga yordam beradi.

⚠️ REVIZSIYA ID: birinchi urinishda `b1c2d3e4f5a6` tanlangan edi — u
`b1c2d3e4f5a6_order_type_source_bosqich_5_1.py` da ALLAQACHON band edi
(alembic "present more than once" berdi). Yangi ID tasodifiy hex, 56 ta
migratsiya faylida tekshirildi.

XAVFSIZLIK: `ADD COLUMN IF NOT EXISTS` (idempotent), NULLABLE — mavjud
qatorlar tegilmaydi, hech qanday ma'lumot o'zgarmaydi. Faqat qo'shimcha ustun.
255 belgi: UA satrlari uzun bo'lishi mumkin, kod ham [:255] ga qirqadi.
"""
from alembic import op
import sqlalchemy as sa

revision = "72d684a734c4"
down_revision = "a9b8c7d6e5f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE audit_logs "
            "ADD COLUMN IF NOT EXISTS user_agent VARCHAR(255)"
        )
    else:
        cols = {c["name"] for c in sa.inspect(bind).get_columns("audit_logs")}
        if "user_agent" not in cols:
            op.add_column(
                "audit_logs",
                sa.Column("user_agent", sa.String(255), nullable=True),
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE audit_logs DROP COLUMN IF EXISTS user_agent")
    else:
        op.drop_column("audit_logs", "user_agent")
