"""order_items.quantity: Integer -> Float (kasrli miqdor — tarozi sotuvi)

Revision ID: b3d7f1c92a48
Revises: a7c3e91f4b60
Create Date: 2026-09-07

NEGA: tarozi mahsulotlari (kg/g/l) kasrli miqdorda sotiladi — 0.740 kg.
`order_items.quantity` INTEGER bo'lgani uchun bunday sotuv API chegarasidayoq
422 bilan rad etilardi ("got a number with a fractional part"), ya'ni
oziq-ovqat do'konida tarozi bilan sotish MUMKIN EMAS edi.

⚠️ ADASHTIRMASIN: `ml` bo'yicha sotuv (atir maydalash) shu paytgacha ishlab
turgan — lekin kasr qo'llab-quvvatlangani uchun emas, balki ml miqdorlari
BUTUN SON (30, 50, 100) bo'lgani uchun. Birinchi `kg` mahsulot qo'shilishi
bilan bu yo'l darrov yiqilardi.

MA'LUMOT YO'QOLMAYDI: INTEGER -> DOUBLE PRECISION KENGAYTIRISH. Mavjud butun
qiymatlar (prodda 2337 qator, hammasi butun) aynan saqlanadi: 3 -> 3.0.
PostgreSQL bu o'zgarishni USING'siz bajaradi.

DOWNGRADE: DOUBLE PRECISION -> INTEGER. ⚠️ Bu YO'QOTUVCHI amal — kasrli
qiymatlar yaxlitlanadi. Shu sabab downgrade oldidan tekshiriladi: kasrli
qator bo'lsa, migratsiya XATO beradi va to'xtaydi (jimgina ma'lumot buzmaydi).

IDEMPOTENT: ustun tipi allaqachon float bo'lsa — hech narsa qilinmaydi.
"""
from alembic import op
import sqlalchemy as sa

revision = "b3d7f1c92a48"
down_revision = "a7c3e91f4b60"
branch_labels = None
depends_on = None

JADVAL = "order_items"
USTUN = "quantity"


def _tur(bind) -> str:
    """Ustunning joriy tipi (kichik harflarda). Jadval yo'q bo'lsa — bo'sh satr."""
    insp = sa.inspect(bind)
    if JADVAL not in insp.get_table_names():
        return ""
    for c in insp.get_columns(JADVAL):
        if c["name"] == USTUN:
            return str(c["type"]).lower()
    return ""


def upgrade() -> None:
    bind = op.get_bind()
    tur = _tur(bind)
    if not tur:
        return                      # jadval yo'q — qiladigan ish yo'q
    if "int" not in tur:
        return                      # allaqachon float/numeric — idempotent

    with op.batch_alter_table(JADVAL) as batch:
        batch.alter_column(USTUN,
                           existing_type=sa.Integer(),
                           type_=sa.Float(),
                           existing_nullable=False)


def downgrade() -> None:
    bind = op.get_bind()
    tur = _tur(bind)
    if not tur or "int" in tur:
        return                      # allaqachon integer — qiladigan ish yo'q

    # ⚠️ HIMOYA: kasrli qiymat bo'lsa, downgrade ma'lumotni BUZADI.
    # Jimgina yaxlitlashdan ko'ra to'xtash xavfsizroq.
    kasrli = bind.execute(sa.text(
        f"SELECT count(*) FROM {JADVAL} WHERE {USTUN} <> floor({USTUN})"
    )).scalar() or 0
    if kasrli:
        raise RuntimeError(
            f"downgrade to'xtatildi: {JADVAL}.{USTUN} da {kasrli} ta KASRLI qiymat bor. "
            "Integer'ga qaytarish ularni yaxlitlab, sotuv summalarini buzadi. "
            "Avval o'sha buyurtmalarni hal qiling."
        )

    with op.batch_alter_table(JADVAL) as batch:
        batch.alter_column(USTUN,
                           existing_type=sa.Float(),
                           type_=sa.Integer(),
                           existing_nullable=False,
                           postgresql_using=f"{USTUN}::integer")
