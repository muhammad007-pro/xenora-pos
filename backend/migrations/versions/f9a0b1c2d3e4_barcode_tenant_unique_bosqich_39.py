"""barcode_tenant_unique_bosqich_39

barcode/sku GLOBAL unique -> kompozit UNIQUE(tenant_id, ustun):
  products.barcode          : products_barcode_key            -> uq_products_tenant_barcode
  products.sku              : products_sku_key                -> uq_products_tenant_sku
  product_barcodes.barcode  : product_barcodes_barcode_key    -> uq_product_barcodes_tenant_barcode

Maqsad: ikki do'kon (tenant) bir xil zavod barcode'ini (masalan EAN-13) saqlay olishi.
Har tenant ICHIDA hali ham unikal. Baza bo'sh / tenant ichida takror yo'q -> xavfsiz.

Revision ID: f9a0b1c2d3e4
Revises: e8f9a0b1c2d3
Create Date: 2026-06-26 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op


revision: str = 'f9a0b1c2d3e4'
down_revision: Union[str, None] = 'e8f9a0b1c2d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Global unique constraint'larni olib tashlash
    op.drop_constraint('products_barcode_key', 'products', type_='unique')
    op.drop_constraint('products_sku_key', 'products', type_='unique')
    op.drop_constraint('product_barcodes_barcode_key', 'product_barcodes', type_='unique')
    # Kompozit (tenant_id, ustun) unique
    op.create_unique_constraint('uq_products_tenant_barcode', 'products', ['tenant_id', 'barcode'])
    op.create_unique_constraint('uq_products_tenant_sku', 'products', ['tenant_id', 'sku'])
    op.create_unique_constraint('uq_product_barcodes_tenant_barcode', 'product_barcodes', ['tenant_id', 'barcode'])


def downgrade() -> None:
    # Kompozitlarni olib tashlash
    op.drop_constraint('uq_product_barcodes_tenant_barcode', 'product_barcodes', type_='unique')
    op.drop_constraint('uq_products_tenant_sku', 'products', type_='unique')
    op.drop_constraint('uq_products_tenant_barcode', 'products', type_='unique')
    # Global unique'larni qayta tiklash
    op.create_unique_constraint('products_barcode_key', 'products', ['barcode'])
    op.create_unique_constraint('products_sku_key', 'products', ['sku'])
    op.create_unique_constraint('product_barcodes_barcode_key', 'product_barcodes', ['barcode'])
