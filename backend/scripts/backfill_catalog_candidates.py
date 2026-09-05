"""
Bir martalik RETROSPEKTIV yig'ish: mavjud mahsulot nomlarini umumiy katalog
nomzodlari jadvaliga ko'chiradi (`source='backfill'`).

NEGA: yig'ish qatlami faqat YANGI harakatni (mahsulot yaratish/tahrirlash)
ushlaydi. O'lchov ko'rsatdi — Fazza haftasiga ~20-25 nomzod qo'shadi, ya'ni
mavjud 1136 ta mos mahsulot hajmiga tabiiy yo'l bilan yetishga bir yildan
ko'p ketardi. Bir martalik ko'chirish katalogni darrov to'ldiradi.

XAVFSIZLIK:
  • FAQAT `catalog_share_enabled = TRUE` bo'lgan do'konlar. Ruxsat bermagan
    do'kon mahsulotlari HECH QACHON ko'chirilmaydi — bu skript bayroqni
    chetlab o'tmaydi.
  • `products` jadvaliga TEGILMAYDI — faqat SELECT.
  • Oq ro'yxat `core/catalog.py: is_shareable_barcode()` — ya'ni endpoint bilan
    AYNI filtr (ikki xil qoida paydo bo'lmasin).
  • `ON CONFLICT DO NOTHING` — mavjud (jonli yozilgan) nomzod USTIGA
    YOZILMAYDI. Jonli nom har doim ustun, chunki u yangiroq va ishonchliroq.
  • Idempotent — ikki marta ishga tushirilsa ikkinchisida 0 qator qo'shiladi.
  • Bo'laklab yoziladi (--chunk, standart 500) — bitta ulkan INSERT ilovani
    to'sib qo'ymasin.
  • Bu MIGRATSIYA EMAS — bir martalik ma'lumot ko'chirish. alembic'ga qo'shilmaydi.

ISHGA TUSHIRISH (backend/ katalogidan):
    # 1) Preview — hech narsa yozmaydi, nima bo'lishini sanaydi va namuna beradi:
    venv/bin/python scripts/backfill_catalog_candidates.py

    # 2) Haqiqiy bajarish:
    venv/bin/python scripts/backfill_catalog_candidates.py --apply

    # 3) Bitta do'kon:
    venv/bin/python scripts/backfill_catalog_candidates.py --tenant 26 --apply
"""
import argparse
import collections
import os
import sys

# Skript scripts/ ichida — backend/ ni import yo'liga qo'shamiz
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.catalog import is_shareable_barcode, normalize_name
from database import SessionLocal
from models import Cafe, CatalogCandidate, Category, Product


def _sabab(barcode):
    """Kod nega o'tmadi — hisobot uchun aniq sabab."""
    code = (barcode or "").strip()
    if not code:
        return "barkod yo'q"
    if not code.isdigit():
        return "raqam emas / aralash"
    if len(code) not in (8, 12, 13):
        return f"nostandart uzunlik ({len(code)})"
    if code[0] == "2":
        return "ichki do'kon kodi (prefiks 2)"
    return "nazorat raqami (checksum) xato"


def main():
    ap = argparse.ArgumentParser(
        description="Mavjud mahsulot nomlarini katalog nomzodlariga ko'chirish (bir martalik)")
    ap.add_argument("--apply", action="store_true",
                    help="haqiqatan yozish (aks holda faqat preview)")
    ap.add_argument("--tenant", type=int, default=None,
                    help="faqat shu do'kon (aks holda ruxsat bergan hammasi)")
    ap.add_argument("--chunk", type=int, default=500,
                    help="bir tranzaksiyada nechta qator (standart 500)")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        # ── Ruxsat bergan do'konlar ────────────────────────────────────────
        q = db.query(Cafe).filter(Cafe.catalog_share_enabled == True)  # noqa: E712
        if args.tenant:
            q = q.filter(Cafe.id == args.tenant)
        cafes = q.all()
        if not cafes:
            print("Ruxsat bergan (catalog_share_enabled=TRUE) do'kon topilmadi — "
                  "hech narsa qilinmadi.")
            return
        print("Do'konlar: " + ", ".join(f"{c.id} ({c.name})" for c in cafes))

        kategoriya = {c.id: c.name for c in db.query(Category).all()}

        jami = 0
        otdi = 0
        sabablar = collections.Counter()
        namunalar = []
        yoziladi = []          # (tenant_id, barcode, norm, asl, kategoriya, unit)

        for cafe in cafes:
            mahsulotlar = (
                db.query(Product)
                .filter(Product.tenant_id == cafe.id, Product.is_active == True)  # noqa: E712
                .all()
            )
            for p in mahsulotlar:
                jami += 1
                if not is_shareable_barcode(p.barcode):
                    sabablar[_sabab(p.barcode)] += 1
                    continue
                norm = normalize_name(p.name)
                if not norm:
                    sabablar["nom bo'sh / faqat belgi"] += 1
                    continue
                otdi += 1
                qator = (
                    cafe.id,
                    p.barcode.strip(),
                    norm[:200],
                    (p.name or "").strip()[:200],
                    (kategoriya.get(p.category_id) or None),
                    (p.sale_unit or None),
                )
                yoziladi.append(qator)
                if len(namunalar) < 15:
                    namunalar.append(qator)

        print(f"\nKo'rib chiqildi: {jami} faol mahsulot")
        print(f"Filtrdan o'tdi:  {otdi}")
        print(f"O'tmadi:         {jami - otdi}")
        for sabab, n in sabablar.most_common():
            print(f"   {sabab:38} {n:>5}")

        # ── Mavjud nomzodlar (ON CONFLICT nechtasini tashlaydi) ────────────
        mavjud = {
            (r.tenant_id, r.barcode)
            for r in db.query(CatalogCandidate.tenant_id, CatalogCandidate.barcode).all()
        }
        yangi = [r for r in yoziladi if (r[0], r[1]) not in mavjud]
        print(f"\nMavjud nomzod:   {len(mavjud)}  (ular ustiga YOZILMAYDI)")
        print(f"Qo'shiladi:      {len(yangi)}")

        print("\nNAMUNA (yoziladigan qatorlardan):")
        for t, bc, norm, asl, kat, u in namunalar:
            print(f"  t{t} {bc}  {asl[:34]:34} -> {norm[:34]:34} | {kat or '-'} | {u or '-'}")

        if not args.apply:
            print("\n[PREVIEW] Hech narsa yozilmadi. Bajarish uchun --apply qo'shing.")
            return

        # ── Yozish: bo'laklab, ON CONFLICT DO NOTHING ──────────────────────
        qoshildi = 0
        for i in range(0, len(yangi), args.chunk):
            bolak = yangi[i:i + args.chunk]
            stmt = pg_insert(CatalogCandidate.__table__).values([
                {
                    "tenant_id": t, "barcode": bc,
                    "name_normalized": norm, "name_original": asl,
                    "category_hint": kat, "unit": u,
                    "source": "backfill",
                }
                for (t, bc, norm, asl, kat, u) in bolak
            ]).on_conflict_do_nothing(
                constraint="uq_catalog_candidate_tenant_barcode"
            )
            natija = db.execute(stmt)
            db.commit()
            qoshildi += natija.rowcount or 0
            print(f"  bo'lak {i // args.chunk + 1}: {len(bolak)} yuborildi, "
                  f"{natija.rowcount} qo'shildi")

        print(f"\nTAYYOR. Qo'shildi: {qoshildi}")
        print(f"Jadvalda jami:  {db.query(CatalogCandidate).count()}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
