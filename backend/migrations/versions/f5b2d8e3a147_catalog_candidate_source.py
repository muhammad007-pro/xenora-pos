"""catalog_candidates.source — nomzod qayerdan kelgani ('live' | 'backfill')

Revision ID: f5b2d8e3a147
Revises: e4a1c9f7b2d3
Create Date: 2026-09-04

NEGA: retrospektiv yig'ishdan oldin qo'shiladi. Mavjud 1427 mahsulotning nomlari
bir martalik yozuv bilan nomzodlar jadvaliga ko'chiriladi — va keyinchalik
"bu nomni do'kon SKANERLAB kiritdimi, yoki eski bazadan ko'chirildimi" degan
savol muqarrar chiqadi. Tozalash panelida bu farq muhim: `live` yozuv — do'kon
aynan o'sha kunda ishlatgan nom; `backfill` — tarixiy, ehtimol eskirgan.

Ustunni KEYIN qo'shish qimmat bo'lardi (manba ma'lumoti yo'qolgan bo'lardi),
shuning uchun retrospektiv yozuvdan OLDIN qo'shiladi.

Qiymatlar:
  'live'     — `core/catalog.py: record_candidate()` orqali, do'kon mahsulot
               yaratgan/tahrirlagan paytda (STANDART).
  'backfill' — `scripts/backfill_catalog_candidates.py` orqali, bir martalik.

Mavjud yozuvlar `server_default='live'` oladi — bu to'g'ri, chunki migratsiya
paytidagi yagona qator (Fazza'ning LCHEAR eyeliner'i) haqiqatan ham jonli
yozilgan.

IDEMPOTENT: inspector tekshiruvi bilan. `downgrade()` ustunni olib tashlaydi.

⚠️ MA'LUMOT YO'QOLMAYDI: faqat ustun qo'shiladi.
"""
from alembic import op
import sqlalchemy as sa

revision = "f5b2d8e3a147"
down_revision = "e4a1c9f7b2d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "catalog_candidates" not in insp.get_table_names():
        return   # jadval yo'q (e4a1c9f7b2d3 qo'llanmagan) — qo'shadigan narsa yo'q

    cols = {c["name"] for c in insp.get_columns("catalog_candidates")}
    if "source" not in cols:
        op.add_column(
            "catalog_candidates",
            sa.Column("source", sa.String(20), nullable=False,
                      server_default=sa.text("'live'")),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "catalog_candidates" not in insp.get_table_names():
        return

    cols = {c["name"] for c in insp.get_columns("catalog_candidates")}
    if "source" in cols:
        op.drop_column("catalog_candidates", "source")
