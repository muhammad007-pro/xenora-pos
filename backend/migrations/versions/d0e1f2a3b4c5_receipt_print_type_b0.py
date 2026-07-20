"""print servis B0: receipt_settings.print_type/printer_ip/printer_port

Markaziy print servis poydevori — do'kon print turini tanlaydi:
  print_type   "usb" (SumatraPDF, hozirgi) | "lan" (IP:port, kelajak) | "qr" (ekran)
  printer_ip   LAN/API uchun (kelajak), nullable
  printer_port LAN/API porti (mas. 9100), nullable

FAQAT sozlama maydonlari — HECH QAYSI print kod bu bosqichda o'zgarmaydi. default
"usb" → mavjud do'kon avvalgidek SumatraPDF (regressiya yo'q). NULLABLE / IF NOT
EXISTS bilan idempotent (B0 uslubi), mavjud data buzilmaydi.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-07-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd0e1f2a3b4c5'
down_revision: Union[str, None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        "ALTER TABLE receipt_settings ADD COLUMN IF NOT EXISTS print_type VARCHAR(10) DEFAULT 'usb'"
    ))
    conn.execute(sa.text(
        "ALTER TABLE receipt_settings ADD COLUMN IF NOT EXISTS printer_ip VARCHAR(45)"
    ))
    conn.execute(sa.text(
        "ALTER TABLE receipt_settings ADD COLUMN IF NOT EXISTS printer_port INTEGER"
    ))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE receipt_settings DROP COLUMN IF EXISTS printer_port"))
    conn.execute(sa.text("ALTER TABLE receipt_settings DROP COLUMN IF EXISTS printer_ip"))
    conn.execute(sa.text("ALTER TABLE receipt_settings DROP COLUMN IF EXISTS print_type"))
