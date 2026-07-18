"""
Bir martalik tozalash: eski soft-delete (is_active=False) mahsulotlarning
barkod/sku'sini bo'shatadi + ularning ProductBarcode (PLU/qo'shimcha) qatorlarini
o'chiradi.

NEGA: BUG 8 tuzatilishidan OLDIN o'chirilgan mahsulotlar hali barkodini ushlab
turibdi (ular yangi delete_product mantig'idan o'tmagan). Shu bois o'sha barkodni
yangi mahsulotga berib bo'lmaydi ("barcode band"). Bu skript o'sha barkodlarni
bo'shatadi — huddi yangi delete_product qanday qilsa, shunday.

XAVFSIZLIK:
  • FAQAT is_active == False (soft-delete) qatorlar tegiladi.
    FAOL mahsulot (is_active=True) barkodi/sku'si HECH QACHON o'zgarmaydi.
  • Idempotent — allaqachon bo'shatilgan (barcode/sku=None) qatorlar o'tkaziladi;
    ikki marta ishga tushirilsa zarar qilmaydi.
  • Tenant bo'yicha xavfsiz — --tenant bilan bitta do'kon, aks holda barcha tenant.
  • Bu MIGRATSIYA EMAS — bir martalik ma'lumot tozalash. alembic'ga qo'shilmaydi.

ISHGA TUSHIRISH (backend/ katalogidan):
    # 1) Preview (hech narsa o'zgartirmaydi — nechta qator tegilishini sanaydi):
    py scripts/cleanup_deleted_barcodes.py

    # 2) Haqiqiy bajarish (tasdiqlab):
    py scripts/cleanup_deleted_barcodes.py --apply

    # 3) Faqat bitta tenant (do'kon):
    py scripts/cleanup_deleted_barcodes.py --tenant 3 --apply
"""
import argparse
import os
import sys

# Skript scripts/ ichida — backend/ ni import yo'liga qo'shamiz ("from database ..." ishlashi uchun)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import or_
from database import SessionLocal
from models import Product, ProductBarcode


def _chunked(seq, size=500):
    """IN (...) ro'yxati juda uzun bo'lmasligi uchun bo'laklarga bo'lish."""
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def main():
    parser = argparse.ArgumentParser(
        description="Eski soft-delete mahsulotlar barkod/sku'sini bo'shatish (bir martalik)"
    )
    parser.add_argument("--apply", action="store_true",
                        help="Haqiqiy o'zgartirish. Berilmasa — faqat preview (o'qish).")
    parser.add_argument("--tenant", type=int, default=None,
                        help="Faqat shu tenant_id. Berilmasa — barcha tenant.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        # ── Faqat SOFT-DELETE (is_active=False) mahsulotlar bilan ishlaymiz ──────────
        soft_q = db.query(Product).filter(Product.is_active == False)
        if args.tenant is not None:
            soft_q = soft_q.filter(Product.tenant_id == args.tenant)

        # 1) Barkod/sku bo'shatiladiganlar — faqat hali BAND bo'lganlari (idempotent)
        to_clear = soft_q.filter(
            or_(Product.barcode.isnot(None), Product.sku.isnot(None))
        ).all()

        # 2) O'chiriladigan ProductBarcode qatorlari — barcha soft-delete mahsulotlarniki
        #    (join'siz DELETE uchun avval id ro'yxatini olamiz)
        soft_ids = [r[0] for r in soft_q.with_entities(Product.id).all()]
        pb_count = 0
        for ch in _chunked(soft_ids):
            if ch:
                pb_count += db.query(ProductBarcode).filter(
                    ProductBarcode.product_id.in_(ch)
                ).count()

        # ── Preview chiqishi ────────────────────────────────────────────────────────
        line = "-" * 62
        print(line)
        print("Tozalash rejasi (FAQAT is_active=False soft-delete mahsulotlar):")
        print(f"  Tenant filtri                        : "
              f"{args.tenant if args.tenant is not None else 'BARCHA'}")
        print(f"  Barkod/sku bo'shatiladigan mahsulot   : {len(to_clear)} ta")
        print(f"  O'chiriladigan ProductBarcode qatori  : {pb_count} ta")
        print(line)

        # Namuna: birinchi 20 ta (nima tegilishini ko'rish uchun)
        for p in to_clear[:20]:
            print(f"  #{p.id:<6} tenant={p.tenant_id}  "
                  f"barcode={p.barcode!r}  sku={p.sku!r}  name={p.name!r}")
        if len(to_clear) > 20:
            print(f"  ... yana {len(to_clear) - 20} ta")
        print(line)

        if not args.apply:
            print("PREVIEW rejimi — HECH NARSA o'zgartirilmadi.")
            print("Bajarish uchun --apply bayrog'i bilan qayta ishga tushiring.")
            return

        # ── Haqiqiy o'zgartirish ────────────────────────────────────────────────────
        for p in to_clear:
            p.barcode = None
            p.sku = None

        deleted_pb = 0
        for ch in _chunked(soft_ids):
            if ch:
                deleted_pb += db.query(ProductBarcode).filter(
                    ProductBarcode.product_id.in_(ch)
                ).delete(synchronize_session=False)

        db.commit()
        print(f"BAJARILDI: {len(to_clear)} ta mahsulot barkod/sku bo'shatildi, "
              f"{deleted_pb} ta ProductBarcode o'chirildi.")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
