"""Tayyor OFF kesimini `off_products` jadvaliga yuklaydi.

Bu skript SERVERDA yuguradi, lekin OG'IR ISH EMAS: u faqat `off_filter.py`
tayyorlagan kichik TSV ni (~10-60 MB) o'qiydi. To'liq 9 GB CSV serverga
umuman kelmaydi.

XOTIRA: fayl OQIM bilan o'qiladi va bo'lak-bo'lak yoziladi — butun ro'yxat
xotiraga yig'ilmaydi. 1 GB RAM li serverda ham sarf ~30 MB atrofida qoladi
(shu sabab bu yerda "hammasini o'qib, keyin yozish" qilinmagan).

XAVFSIZLIK / XULQ:
  • `products`, `catalog_candidates` va boshqa jadvallarga TEGILMAYDI.
  • Upsert: `ON CONFLICT (barcode) DO UPDATE` — qayta yuklansa yangilanadi,
    dublikat paydo bo'lmaydi. Ya'ni idempotent.
  • Bir bo'lak ichida bir barkod IKKI marta kelsa PostgreSQL xato beradi
    ("cannot affect row a second time"), shuning uchun bo'lak ichida
    dublikat o'chiriladi (oxirgi qator yutadi).
  • Standart holatda PREVIEW: hech narsa yozilmaydi. Yozish uchun `--apply`.
  • Bu MIGRATSIYA EMAS — ma'lumot yuklash. Jadvalni migratsiya yaratadi
    (`a7c3e91f4b60_off_products`).

ISHGA TUSHIRISH (backend/ katalogidan):
    # 1) Preview — nima bo'lishini sanaydi, hech narsa yozmaydi:
    venv/bin/python scripts/off_import.py off_cut.tsv

    # 2) Haqiqiy yuklash:
    venv/bin/python scripts/off_import.py off_cut.tsv --apply

    # 3) Faylning faqat bir qismi (masalan asosiy mamlakatlar):
    venv/bin/python scripts/off_import.py off_cut.tsv --prefiks asosiy --apply
"""
import argparse
import os
import sys
import time

_BU = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_BU))   # backend/ — database, models, core
sys.path.insert(0, _BU)                    # scripts/ — off_filter
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import func, text                               # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert   # noqa: E402

from core.catalog import is_shareable_barcode                    # noqa: E402
from database import SessionLocal                                # noqa: E402
from models import OffProduct                                    # noqa: E402
from off_filter import TOPLAM, mamlakat, prefiks_mos             # noqa: E402


def qatorlar(yol, prefikslar, tashlandi):
    """TSV ni oqim bilan o'qiydi, har qatordan yozuv lug'atini beradi.

    Filtr `off_filter.py` da allaqachon qo'llangan — bu yerdagisi himoya
    takrori (fayl qo'lda tahrirlangan yoki boshqa manbadan bo'lishi mumkin).
    """
    with open(yol, encoding="utf-8") as f:
        for qator in f:
            b = qator.rstrip("\r\n").split("\t")
            if len(b) < 5:
                tashlandi["ustun yetmadi"] += 1
                continue
            code, nom, brend, hajm, kat = (x.strip() for x in b[:5])
            if not is_shareable_barcode(code):
                tashlandi["kod yaroqsiz"] += 1
                continue
            if prefikslar and not prefiks_mos(code, prefikslar):
                tashlandi["prefiks mos emas"] += 1
                continue
            if not nom:
                tashlandi["nom bo'sh"] += 1
                continue
            yield {
                "barcode": code,
                "name": nom[:200],
                "brand": brend[:120] or None,
                "quantity": hajm[:50] or None,
                "category": kat[:100] or None,
                "source": "off",
            }


def bolakni_yoz(db, bolak):
    """Bitta bo'lakni upsert qiladi (bo'lak ichidagi dublikat o'chiriladi)."""
    yagona = {r["barcode"]: r for r in bolak}
    stmt = pg_insert(OffProduct.__table__).values(list(yagona.values()))
    stmt = stmt.on_conflict_do_update(
        constraint="uq_off_products_barcode",
        set_={
            "name": stmt.excluded.name,
            "brand": stmt.excluded.brand,
            "quantity": stmt.excluded.quantity,
            "category": stmt.excluded.category,
            "updated_at": func.now(),
        },
    )
    db.execute(stmt)
    db.commit()
    return len(yagona)


def main():
    ap = argparse.ArgumentParser(
        description="OFF kesimini off_products jadvaliga yuklash")
    ap.add_argument("fayl", help="off_filter.py tayyorlagan TSV")
    ap.add_argument("--apply", action="store_true",
                    help="haqiqatan yozish (aks holda faqat preview)")
    ap.add_argument("--prefiks", default="",
                    help="faqat shu prefikslar: 'asosiy'|'keng'|'hammasi'|ro'yxat")
    ap.add_argument("--chunk", type=int, default=2000,
                    help="bir tranzaksiyada nechta qator (standart 2000)")
    args = ap.parse_args()

    if not os.path.isfile(args.fayl):
        print(f"XATO: fayl topilmadi: {args.fayl}")
        return 2

    prefikslar = set()
    if args.prefiks:
        prefikslar = set(TOPLAM.get(
            args.prefiks, [p.strip() for p in args.prefiks.split(",") if p.strip()]))
        print(f"Prefiks filtri '{args.prefiks}': {len(prefikslar)} ta")

    hajm_mb = os.path.getsize(args.fayl) / 1024 / 1024
    print(f"Fayl: {os.path.abspath(args.fayl)} ({hajm_mb:.1f} MB)")
    print(f"Rejim: {'YOZISH (--apply)' if args.apply else 'PREVIEW'}\n")

    tashlandi = {"ustun yetmadi": 0, "kod yaroqsiz": 0,
                 "prefiks mos emas": 0, "nom bo'sh": 0}
    per_mamlakat, namuna = {}, {}
    olindi = brendli = katli = yozildi = 0
    boshlandi = time.time()

    db = SessionLocal() if args.apply else None
    avvalgi = 0
    try:
        if db is not None:
            avvalgi = db.query(func.count(OffProduct.id)).scalar() or 0

        bolak = []
        for yozuv in qatorlar(args.fayl, prefikslar, tashlandi):
            olindi += 1
            if yozuv["brand"]:
                brendli += 1
            if yozuv["category"]:
                katli += 1
            m = mamlakat(yozuv["barcode"]) or "boshqa"
            per_mamlakat[m] = per_mamlakat.get(m, 0) + 1
            namuna.setdefault(m, yozuv)

            if db is not None:
                bolak.append(yozuv)
                if len(bolak) >= args.chunk:
                    yozildi += bolakni_yoz(db, bolak)
                    bolak = []
                    if yozildi % (args.chunk * 20) == 0:
                        print(f"  {yozildi:>8,} yozildi "
                              f"({time.time() - boshlandi:.0f}s)", flush=True)
        if db is not None and bolak:
            yozildi += bolakni_yoz(db, bolak)

        # ── Hisobot ───────────────────────────────────────────────────────
        print(f"O'qildi va filtrdan o'tdi: {olindi:,} qator")
        for k, v in sorted(tashlandi.items(), key=lambda z: -z[1]):
            if v:
                print(f"   tashlandi — {k:18} {v:>8,}")

        b = max(olindi, 1)
        print(f"\nSIFAT: brendi bor {brendli:,} ({100 * brendli / b:.0f}%), "
              f"kategoriyasi bor {katli:,} ({100 * katli / b:.0f}%)")

        print("\nMAMLAKAT KESIMI:")
        for m, n in sorted(per_mamlakat.items(), key=lambda z: -z[1]):
            print(f"   {m:22} {n:>8,}")

        print("\nNAMUNA (har mamlakatdan bittadan):")
        for m, r in sorted(namuna.items()):
            print(f"   {m:14} {r['barcode']}  {r['name'][:38]:38} | "
                  f"{(r['brand'] or '-')[:16]:16} | {r['quantity'] or '-'}")

        if db is None:
            print("\n[PREVIEW] Hech narsa yozilmadi. Bajarish uchun --apply qo'shing.")
            return 0

        keyingi = db.query(func.count(OffProduct.id)).scalar() or 0
        print(f"\nTAYYOR. Yuborildi {yozildi:,} qator, "
              f"jadvalda {keyingi:,} (yangi {keyingi - avvalgi:,}, "
              f"yangilandi {yozildi - (keyingi - avvalgi):,}) — "
              f"{time.time() - boshlandi:.0f}s")

        # VACUUM ANALYZE — e'tiborsiz qoldirilmasin.
        # UPDATE PostgreSQL'da eski qator versiyasini o'chirmaydi, "o'lik" qilib
        # qoldiradi: birinchi yuklashdan keyin jadval 28 MB, qayta yuklashdan
        # keyin 53 MB bo'ldi (o'lchangan). VACUUM (FULL emas) bo'shliqni
        # operatsion tizimga QAYTARMAYDI, lekin uni qayta ishlatiladigan qilib
        # belgilaydi — ya'ni jadval har yuklashda o'sib ketmaydi, ~53 MB da
        # turg'unlashadi. ANALYZE rejalashtiruvchiga yangi statistikani beradi.
        try:
            xom = db.get_bind().engine.connect().execution_options(
                isolation_level="AUTOCOMMIT")
            with xom:
                xom.execute(text("VACUUM ANALYZE off_products"))
            print("VACUUM ANALYZE bajarildi (o'lik qatorlar tozalandi)")
        except Exception as exc:      # PostgreSQL bo'lmasa — muhim emas
            print(f"(VACUUM o'tkazilmadi: {exc})")

        try:
            olcham = db.execute(text(
                "SELECT pg_size_pretty(pg_total_relation_size('off_products')), "
                "       pg_size_pretty(pg_indexes_size('off_products'))"
            )).first()
            print(f"Baza hajmi: {olcham[0]} (shundan indeks {olcham[1]})")
        except Exception as exc:      # PostgreSQL bo'lmasa — muhim emas
            print(f"(hajm o'lchanmadi: {exc})")
    finally:
        if db is not None:
            db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
