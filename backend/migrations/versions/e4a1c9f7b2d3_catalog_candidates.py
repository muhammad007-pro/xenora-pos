"""catalog_candidates + cafes.catalog_share_enabled — umumiy katalog, yig'ish qatlami

Revision ID: e4a1c9f7b2d3
Revises: d9e4f1a2b3c5
Create Date: 2026-09-04

NEGA: yangi do'kon mahsulotni skaner qilganda nomi/kategoriyasi o'zi to'lsin.
Buning uchun avval ma'lumot to'planishi kerak. Bu migratsiya faqat YIG'ISH
qatlamini ochadi — o'qish API'si YO'Q, hech kim hech narsa ko'rmaydi.

IKKI OBYEKT:

1) `cafes.catalog_share_enabled` — do'kon o'z mahsulot NOMLARINI ulashishga
   rozimi. `server_default="false"` — MAVJUD do'konlar ham, YANGI do'konlar ham
   o'chiq holatda boshlaydi. Hech kimning ma'lumoti so'ramasdan yig'ilmaydi.
   (Fazza va Eco Aroma'dan ruxsat alohida so'raladi — kod tayyor tursin.)

2) `catalog_candidates` — nomzod nomlar. Bir do'kon bir barkod bo'yicha BITTA
   qator: UNIQUE(tenant_id, barcode). Mahsulot tahrirlansa yangi qator emas,
   mavjudi yangilanadi — ya'ni bitta do'kon "ovoz" ko'paytira olmaydi.

⚠️ NARX USTUNI ATAYLAB YO'Q. Bu jadvalda faqat barcode, nom (normalizatsiyalangan
va asl), kategoriya, birlik bor. Narx, tan narx, ta'minotchi, ombor qoldig'i —
do'konning tijorat siri va bu jadvalga HECH QACHON qo'shilmasin. Kafolat sxema
darajasida: bo'lmagan ustunga yozib bo'lmaydi.

`tenant_id` faqat ovoz sanash va super-admin paneli uchun — API javobida
qaytmaydi.

IDEMPOTENT: inspector tekshiruvi bilan, qayta yugurtirilsa xato bermaydi.
`downgrade()` ikkalasini ham qaytarib olib tashlaydi.

⚠️ MA'LUMOT YO'QOLMAYDI: faqat qo'shiladi, mavjud ustunlarga tegilmaydi.
"""
from alembic import op
import sqlalchemy as sa

revision = "e4a1c9f7b2d3"
down_revision = "d9e4f1a2b3c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # ── 1) cafes.catalog_share_enabled ───────────────────────────────────────
    cols = {c["name"] for c in insp.get_columns("cafes")}
    if "catalog_share_enabled" not in cols:
        op.add_column(
            "cafes",
            sa.Column("catalog_share_enabled", sa.Boolean(),
                      nullable=False, server_default=sa.text("false")),
        )

    # ── 2) catalog_candidates ────────────────────────────────────────────────
    if "catalog_candidates" not in insp.get_table_names():
        op.create_table(
            "catalog_candidates",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("barcode", sa.String(20), nullable=False),
            sa.Column("name_normalized", sa.String(200), nullable=False),
            sa.Column("name_original", sa.String(200), nullable=False),
            sa.Column("tenant_id", sa.Integer(),
                      sa.ForeignKey("cafes.id"), nullable=False),
            sa.Column("category_hint", sa.String(100), nullable=True),
            sa.Column("unit", sa.String(20), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("tenant_id", "barcode",
                                name="uq_catalog_candidate_tenant_barcode"),
        )
        op.create_index("ix_catalog_candidates_barcode",
                        "catalog_candidates", ["barcode"])
        op.create_index("ix_catalog_candidates_tenant_id",
                        "catalog_candidates", ["tenant_id"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "catalog_candidates" in insp.get_table_names():
        # Indekslar jadval bilan ketadi, lekin aniq bo'lsin.
        for ix in ("ix_catalog_candidates_barcode", "ix_catalog_candidates_tenant_id"):
            try:
                op.drop_index(ix, table_name="catalog_candidates")
            except Exception:
                pass
        op.drop_table("catalog_candidates")

    cols = {c["name"] for c in insp.get_columns("cafes")}
    if "catalog_share_enabled" in cols:
        op.drop_column("cafes", "catalog_share_enabled")
