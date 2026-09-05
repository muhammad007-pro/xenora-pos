"""off_products — Open Food Facts kesimi (tashqi manba, offline nusxa)

Revision ID: a7c3e91f4b60
Revises: f5b2d8e3a147
Create Date: 2026-09-05

NEGA: yangi do'kon mahsulotni skaner qilganda nomi o'zi to'lsin. Bizning
`catalog_candidates` faqat do'konlarimiz kiritgan nomlardan to'planadi va u
sekin o'sadi (haftasiga ~20-25 nomzod). Open Food Facts — 4.7 mln mahsulotli
ochiq baza; undan kerakli mamlakatlar kesimini bir marta olib qo'ysak, katalog
darrov ishlaydigan hajmga chiqadi.

NEGA ALOHIDA JADVAL (`catalog_candidates` ga qo'shilmaydi):
  • `catalog_candidates` — ICHKI manba: qaysi do'kon qanday nom yozganini
    saqlaydi (`tenant_id`, bir barkodga ko'p qator, ovoz berish uchun).
  • `off_products`      — TASHQI manba: hech kimning ma'lumoti emas, tenant
    yo'q, bir barkodga bitta qator, to'liq qayta yuklanadi.
  Aralashtirilsa "bu nom bizning do'kondanmi yoki internetdanmi" degan farq
  yo'qoladi — nom tanlash bosqichida esa aynan shu farq hal qiluvchi.

NEGA ONLINE API EMAS: do'konlarda internet uziladi va OFF API rate limit
qo'yadi. Mahalliy jadval bo'lsa qidiruv internetsiz ham, ~1 ms da ishlaydi.

⚠️ NARX USTUNI YO'Q va qo'shilmasin — `catalog_candidates` dagi bilan bir xil
qoida (sxema darajasidagi kafolat).

TO'LDIRISH: `scripts/off_import.py` (migratsiya ma'lumot yozmaydi). Manba
faylni `scripts/off_filter.py` DEV mashinada tayyorlaydi — prod serverda
(1 vCPU / 1 GB) 9 GB CSV qayta ishlanmaydi.

IDEMPOTENT: inspector tekshiruvi bilan, qayta yugurtirilsa xato bermaydi.
`downgrade()` jadvalni indekslari bilan olib tashlaydi.

⚠️ MA'LUMOT YO'QOLMAYDI: faqat yangi jadval qo'shiladi, mavjudlariga
tegilmaydi.
"""
from alembic import op
import sqlalchemy as sa

revision = "a7c3e91f4b60"
down_revision = "f5b2d8e3a147"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "off_products" in insp.get_table_names():
        return

    op.create_table(
        "off_products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("barcode", sa.String(20), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("brand", sa.String(120), nullable=True),
        sa.Column("quantity", sa.String(50), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("source", sa.String(20), nullable=False,
                  server_default=sa.text("'off'")),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        # Upsert (ON CONFLICT) shu cheklovga tayanadi — nomi qulflangan.
        sa.UniqueConstraint("barcode", name="uq_off_products_barcode"),
    )
    op.create_index("ix_off_products_barcode", "off_products", ["barcode"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "off_products" not in insp.get_table_names():
        return

    try:
        op.drop_index("ix_off_products_barcode", table_name="off_products")
    except Exception:
        pass    # indeks jadval bilan ketadi — ba'zi backend'larda alohida yo'q
    op.drop_table("off_products")
