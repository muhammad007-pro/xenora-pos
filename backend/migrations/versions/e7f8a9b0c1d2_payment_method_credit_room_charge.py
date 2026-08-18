"""paymentmethod enum: CREDIT va ROOM_CHARGE qo'shish

Revision ID: e7f8a9b0c1d2
Revises: b9c8d7e6f5a4
Create Date: 2026-08-18

MUAMMO (jonli, Fazza Parfum v1.9.0): POS'da "Nasiya" tugmasi bosilganda sotuv
UMUMAN saqlanmasdi:
    psycopg2.errors.InvalidTextRepresentation:
    invalid input value for enum paymentmethod: "credit"
    POST /api/v1/payments/ -> 500  ("Sotuvni saqlashda xatolik ...")

SABAB: `pos.html` da tugma dastlabki deploydan beri bor edi, `PaymentMethod`
enumida esa faqat cash/card/click/payme/qr. Bazada bironta ham `credit` to'lov
yo'q edi — ya'ni POS nasiyasi hech qachon ishlamagan.

Bu migratsiya faqat ENUM QIYMATLARINI qo'shadi. Ma'lumot o'zgarmaydi, jadval
qulflanmaydi, to'ldirish (backfill) YO'Q.

⚠️ Yorliqlar KATTA HARF bilan: `Column(Enum(PaymentMethod))` SQLAlchemy'da enum
NOMINI saqlaydi (CASH, CARD...), qiymatini emas. Mavjud yorliqlar ham shunday.

⚠️ `ALTER TYPE ... ADD VALUE` PostgreSQL'da tranzaksiya ichida ishlamaydi
(eski versiyalarda), shuning uchun AUTOCOMMIT ulanishda bajariladi.
`IF NOT EXISTS` — idempotent: qayta ishga tushirilsa xato bermaydi.

DOWNGRADE: PostgreSQL enum qiymatini O'CHIRA OLMAYDI. Shuning uchun downgrade
xavfsiz yo'ldan boradi — enum tegilmaydi, faqat o'sha qiymatdagi yozuvlar
qolmaganini tekshiradi va ogohlantiradi (ma'lumot yo'qotmaslik uchun).
"""
from alembic import op
import sqlalchemy as sa

revision = "e7f8a9b0c1d2"
down_revision = "b9c8d7e6f5a4"
branch_labels = None
depends_on = None

_NEW_VALUES = ("CREDIT", "ROOM_CHARGE")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # sqlite (testlar) — enum matn sifatida saqlanadi, ish talab qilinmaydi

    # `ALTER TYPE ... ADD VALUE` tranzaksiya ichida bajarilmaydi.
    # Alembic'ning `autocommit_block()` — aynan shu holat uchun mo'ljallangan API.
    with op.get_context().autocommit_block():
        for val in _NEW_VALUES:
            op.execute(f"ALTER TYPE paymentmethod ADD VALUE IF NOT EXISTS '{val}'")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # Enum qiymatini o'chirish PostgreSQL'da mumkin emas (type'ni qayta yaratish
    # kerak bo'lardi — bu payments jadvalini qulflaydi va xavfli). Shuning uchun
    # faqat TEKSHIRAMIZ: bu qiymatlarda yozuv qolgan bo'lsa — ogohlantiramiz.
    rows = bind.execute(sa.text(
        "SELECT method::text AS m, count(*) AS c FROM payments "
        "WHERE method::text IN ('CREDIT', 'ROOM_CHARGE') GROUP BY 1"
    )).fetchall()
    if rows:
        detail = ", ".join(f"{r.m}={r.c}" for r in rows)
        print(f"[downgrade] DIQQAT: enum qiymatlari saqlanib qoldi — {detail} "
              f"yozuv mavjud. Enum qiymati o'chirilmadi (ma'lumot yo'qolmasin).")
    else:
        print("[downgrade] CREDIT/ROOM_CHARGE yozuvlari yo'q; enum qiymati "
              "PostgreSQL cheklovi sabab baribir o'chirilmaydi (zararsiz).")
