"""
Bir martalik ko'chirish: eski mahsulot rasmlari (`/uploads/products/<fayl>.jpg`,
siqilmagan, tenant papkasisiz) → yangi format (`/uploads/products/tenant_<id>/
product_<pid>_<hex>.webp` + `_thumb.webp`, 800px/200px WebP).

Yangi yuklashlar bilan AYNAN bir xil yo'l ishlatiladi (core/product_images).

XAVFSIZLIK:
  • Default — PREVIEW, hech narsa yozilmaydi.
  • --apply: yangi fayllar yoziladi, image_url yangilanadi (bitta commit).
    Commit yiqilsa — yozilgan yangi fayllar o'chiriladi.
  • ESKI fayllar default'da QOLDIRILADI (orqaga qaytish uchun: image_url ni
    eski qiymatga qaytarish kifoya). Tekshirilgach --delete-old bilan o'chiriladi.
  • Idempotent — yangi formatdagi URL'lar o'tkazib yuboriladi.
  • Fayli diskda yo'q yoki buzuq rasm — o'tkazib yuboriladi, image_url TEGILMAYDI.
  • Bu MIGRATSIYA EMAS (alembic'ga qo'shilmaydi) — sxema o'zgarmaydi.

ISHGA TUSHIRISH (backend/ katalogidan):
    venv/bin/python scripts/migrate_product_images.py               # preview
    venv/bin/python scripts/migrate_product_images.py --apply       # ko'chirish
    venv/bin/python scripts/migrate_product_images.py --apply --delete-old
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import product_images  # noqa: E402
from models import Product  # noqa: E402


def migrate(db, apply: bool = False, delete_old: bool = False) -> dict:
    """Ko'chirish rejasi/natijasi. Test ham shu funksiyani chaqiradi."""
    rows = (db.query(Product)
              .filter(Product.image_url.like(product_images.URL_PREFIX + "/%"))
              .order_by(Product.id).all())
    report = {"migrated": [], "skipped": [], "already": 0}
    written = []        # commit yiqilsa tozalash uchun
    old_urls = set()

    for p in rows:
        if product_images.thumb_url(p.image_url):      # allaqachon yangi format
            report["already"] += 1
            continue
        path = product_images._local_path(p.image_url)
        if not path or not os.path.isfile(path):
            report["skipped"].append((p.id, p.image_url, "fayl topilmadi"))
            continue
        with open(path, "rb") as f:
            raw = f.read()
        try:
            main_bytes, thumb_bytes = product_images.process_image(raw)
        except product_images.ProductImageError as e:
            report["skipped"].append((p.id, p.image_url, str(e)))
            continue

        entry = {"id": p.id, "tenant_id": p.tenant_id, "old": p.image_url,
                 "old_kb": len(raw) // 1024, "new_kb": len(main_bytes) // 1024,
                 "thumb_kb": len(thumb_bytes) // 1024, "new": None}
        if apply:
            new_url = product_images.write_product_image(p.tenant_id, p.id, raw)
            written.append(new_url)
            old_urls.add(p.image_url)
            p.image_url = new_url
            entry["new"] = new_url
        report["migrated"].append(entry)

    if apply:
        try:
            db.commit()
        except Exception:
            db.rollback()
            for u in written:
                product_images.delete_image_files(u)
            raise
        if delete_old:
            for u in old_urls:
                # Boshqa (ko'chirilmagan) mahsulot hali shu faylni ko'rsatsa — tegilmaydi
                if not db.query(Product.id).filter(Product.image_url == u).first():
                    product_images.delete_image_files(u)
    return report


def main():
    parser = argparse.ArgumentParser(description="Eski mahsulot rasmlarini WebP + tenant papkaga ko'chirish")
    parser.add_argument("--apply", action="store_true", help="Haqiqiy ko'chirish. Berilmasa — preview.")
    parser.add_argument("--delete-old", action="store_true", help="--apply bilan: eski fayllarni o'chirish.")
    args = parser.parse_args()
    if args.delete_old and not args.apply:
        parser.error("--delete-old faqat --apply bilan ishlaydi")

    from database import SessionLocal
    db = SessionLocal()
    try:
        r = migrate(db, apply=args.apply, delete_old=args.delete_old)
    finally:
        db.close()

    line = "-" * 70
    print(line)
    for e in r["migrated"]:
        print(f"  #{e['id']:<6} tenant={e['tenant_id']}  {e['old']}  "
              f"{e['old_kb']} KB -> {e['new_kb']} KB (+thumb {e['thumb_kb']} KB)"
              + (f"\n          -> {e['new']}" if e["new"] else ""))
    for pid, url, why in r["skipped"]:
        print(f"  O'TKAZILDI #{pid}: {url} — {why}")
    print(line)
    print(f"Ko'chiriladi/ko'chirildi: {len(r['migrated'])}, o'tkazildi: {len(r['skipped'])}, "
          f"allaqachon yangi: {r['already']}")
    if not args.apply:
        print("PREVIEW rejimi — HECH NARSA o'zgartirilmadi. Bajarish: --apply")


if __name__ == "__main__":
    main()
