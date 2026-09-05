"""Open Food Facts CSV eksportidan KESIM olish — bu mashinada, prod'da EMAS.

NEGA SHU YERDA: OFF ning to'liq CSV eksporti siqilgan holda ~1.2 GB, ochilganda
~9 GB. Uni 1 vCPU / 1 GB serverda qayta ishlash soatlar oladi va do'kon ishiga
xalaqit beradi. Shu sabab filtr DEV mashinada (yoki CI'da) yuguradi, serverga
esa faqat tayyor, kichik TSV yuboriladi (`off_import.py` uni o'qiydi).

QANDAY ISHLAYDI: 9 GB fayl DISKKA YOZILMAYDI — HTTP oqimi to'g'ridan gzip'dan
o'tkaziladi va qatorma-qator o'qiladi. Diskda faqat natija qoladi.

XOTIRA: o'qish oqim bilan, lekin dublikatni tutish uchun QABUL QILINGAN
barkodlar to'plami xotirada turadi — har 100 ming qator uchun ~10 MB. Butun
dunyo skani (~1.5 mln qator) ~150 MB oladi. Shu sabab ham bu skript DEV
mashinada yuguradi, serverda emas.

FILTR (uch bosqich, hammasi majburiy):
  1. Shtrix-kod `core.catalog.is_shareable_barcode()` dan o'tsin — EAN-8/UPC-A/
     EAN-13, nazorat raqami to'g'ri, prefiks 2 emas. Katalogning qolgan qismi
     bilan AYNI qoida (ikki xil filtr paydo bo'lmasin).
  2. GS1 mamlakat prefiksi tanlangan to'plamda bo'lsin (`--prefiks`).
  3. Nom SIFATLI bo'lsin: bo'sh emas, shtrix-kodning o'zi emas, faqat raqam
     emas, `normalize_name()` dan keyin ham bo'sh qolmasin.

2026-09-05 o'lchovi: OFF dagi O'zbekiston yozuvlarining yarmidan ko'pi nomsiz
yoki nomi o'rniga shtrix-kod turibdi — shuning uchun 3-bosqich shart.

ISHGA TUSHIRISH (backend/ katalogidan):
    # To'liq skan, keng prefiks to'plami (~40 daqiqa, 1.2 GB yuklab olinadi):
    py scripts/off_filter.py --prefiks keng --out off_cut.tsv

    # Faqat asosiy mamlakatlar:
    py scripts/off_filter.py --prefiks asosiy --out off_cut.tsv

    # Mahalliy fayldan (qayta yuklab olmasdan):
    py scripts/off_filter.py --manba D:\\off\\products.csv.gz --out off_cut.tsv

    # Tayyor kesimni yana toraytirish (kichik faylni qayta o'qiydi, tez):
    py scripts/off_filter.py --manba off_cut.tsv --out off_ship.tsv --prefiks asosiy

Chiqish formati: TSV, sarlavhasiz, 5 ustun —
    barcode <TAB> name <TAB> brand <TAB> quantity <TAB> category
"""
import argparse
import gzip
import io
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from core.catalog import is_shareable_barcode, normalize_name  # noqa: E402

MANBA = "https://static.openfoodfacts.org/data/en.openfoodfacts.org.products.csv.gz"
UA = ("XenoraPOS-CatalogImport/1.0 "
      "(offline catalog; contact via github.com/muhammad007-pro)")

# ── GS1 mamlakat prefikslari ────────────────────────────────────────────────
# Kalit — prefiksning boshlanishi (2 yoki 3 raqam), qiymat — mamlakat nomi.
# Solishtirish uzunroq prefiksdan boshlanadi, ya'ni "869" (Turkiya) "86"
# (Serbiya) dan oldin tekshiriladi.
GS1 = {
    "478": "O'zbekiston", "487": "Qozog'iston", "488": "Tojikiston",
    "486": "Gruziya", "485": "Armaniston", "484": "Moldova",
    "482": "Ukraina", "481": "Belarus", "476": "Ozarbayjon",
    "477": "Litva", "475": "Latviya", "474": "Estoniya",
    "869": "Turkiya", "626": "Eron", "629": "BAA", "590": "Polsha",
    "594": "Ruminiya", "599": "Vengriya", "880": "Koreya",
    "885": "Tailand", "888": "Singapur", "890": "Hindiston",
    "893": "Vetnam", "899": "Indoneziya",
}
for _i in range(460, 470):
    GS1[str(_i)] = "Rossiya"
for _i in range(690, 700):
    GS1[str(_i)] = "Xitoy"
for _i in range(30, 38):
    GS1[str(_i)] = "Fransiya"
for _i in range(40, 45):
    GS1[str(_i)] = "Germaniya"
for _i in range(80, 84):
    GS1[str(_i)] = "Italiya"
GS1["84"] = "Ispaniya"
GS1["87"] = "Niderlandiya"
GS1["50"] = "Buyuk Britaniya"
GS1["45"] = "Yaponiya"
GS1["49"] = "Yaponiya"
GS1["94"] = "Yangi Zelandiya"
GS1["93"] = "Avstraliya"

# Nomlangan to'plamlar.
#   asosiy — buyurtmada aytilgan besh yo'nalish;
#   keng   — asosiy + O'zbekiston do'konlarida haqiqatan uchraydigan importchi
#            mamlakatlar (qo'shni davlatlar, Eron/BAA/Hindiston/Koreya, Polsha);
#   hammasi — yuqoridagi GS1 lug'atining barchasi (o'lchov uchun; hajmni
#            baholab, keyin toraytirish oson).
TOPLAM = {
    "asosiy": ["478"] + [str(i) for i in range(460, 470)] + ["869", "487"]
              + [str(i) for i in range(690, 700)],
    "keng": None,     # quyida to'ldiriladi
    "hammasi": sorted(GS1),
}
TOPLAM["keng"] = TOPLAM["asosiy"] + [
    "488", "486", "485", "484", "482", "481", "476",   # qo'shni/MDH
    "626", "629", "890", "880", "590",                 # Eron, BAA, Hindiston, Koreya, Polsha
]

# CSV ustun indekslari (2026-09-05 dagi eksportda tekshirilgan, 211 ustun).
# Sarlavha qatoridan qayta o'qiladi — indeks siljisa avtomatik moslashadi.
KERAK = ["code", "product_name", "brands", "quantity", "categories_en", "categories"]


def mamlakat(barcode):
    """Shtrix-kod bo'yicha GS1 mamlakati (topilmasa None)."""
    return GS1.get(barcode[:3]) or GS1.get(barcode[:2])


def prefiks_mos(barcode, prefikslar):
    return barcode[:3] in prefikslar or barcode[:2] in prefikslar


def eng_aniq_kategoriya(matn):
    """OFF kategoriyalari umumiydan xususiyga qarab keladi — oxirgisi aniqrog'i.

    "Plant-based foods, Cereals, Breakfasts, Rolled oats" -> "Rolled oats"
    """
    if not matn:
        return ""
    qismlar = [q.strip() for q in matn.split(",") if q.strip()]
    return qismlar[-1] if qismlar else ""


def oqim_och(manba):
    """Manbani (URL yoki mahalliy fayl, .gz yoki oddiy) matn oqimi qilib beradi."""
    if manba.startswith(("http://", "https://")):
        req = urllib.request.Request(manba, headers={"User-Agent": UA})
        xom = urllib.request.urlopen(req, timeout=120)
        ikkilik = gzip.GzipFile(fileobj=xom)
    elif manba.endswith(".gz"):
        ikkilik = gzip.open(manba, "rb")
    else:
        ikkilik = open(manba, "rb")
    return io.TextIOWrapper(ikkilik, encoding="utf-8", errors="replace",
                            newline="")


def sarlavhani_oq(oqim):
    """Birinchi qatordan ustun indekslarini oladi.

    Tayyor kesim (5 ustunli TSV) berilsa sarlavha yo'q — None qaytadi va
    qator to'g'ridan-to'g'ri o'qiladi.
    """
    birinchi = oqim.readline().rstrip("\r\n")
    ustunlar = birinchi.split("\t")
    if "code" in ustunlar and "product_name" in ustunlar:
        return {n: ustunlar.index(n) for n in KERAK if n in ustunlar}, None
    return None, birinchi   # sarlavha yo'q — bu qator ma'lumot


def qatorni_ajrat(qator, idx):
    """Xom CSV qatoridan (yoki tayyor kesim qatoridan) beshlik chiqaradi."""
    f = qator.split("\t")
    if idx is None:
        if len(f) < 5:
            return None
        return f[0], f[1], f[2], f[3], f[4]
    if len(f) <= idx["product_name"]:
        return None     # buzuq qator (ichida yangi qator belgisi bo'lgan yozuv)
    kat = eng_aniq_kategoriya(
        f[idx["categories_en"]] if idx.get("categories_en") is not None
        and len(f) > idx["categories_en"] else ""
    ) or eng_aniq_kategoriya(
        f[idx["categories"]] if idx.get("categories") is not None
        and len(f) > idx["categories"] else ""
    )
    return (
        f[idx["code"]],
        f[idx["product_name"]],
        f[idx["brands"]] if len(f) > idx["brands"] else "",
        f[idx["quantity"]] if len(f) > idx["quantity"] else "",
        kat,
    )


def toza(matn, uzunlik):
    """TSV ni buzmaydigan, ustunga sig'adigan matn."""
    return (matn or "").replace("\t", " ").replace("\r", " ") \
                       .replace("\n", " ").strip()[:uzunlik]


def main():
    ap = argparse.ArgumentParser(
        description="OFF CSV eksportidan mamlakat kesimi (DEV mashinada yuguradi)")
    ap.add_argument("--manba", default=MANBA,
                    help="URL yoki mahalliy fayl (standart: OFF nightly CSV)")
    ap.add_argument("--out", default="off_cut.tsv", help="natija TSV fayli")
    ap.add_argument("--prefiks", default="keng",
                    help="'asosiy' | 'keng' | 'hammasi' | vergul bilan ro'yxat")
    ap.add_argument("--limit", type=int, default=0,
                    help="faqat shuncha qator o'qish (sinov uchun)")
    args = ap.parse_args()

    if args.prefiks in TOPLAM:
        prefikslar = set(TOPLAM[args.prefiks])
    else:
        prefikslar = {p.strip() for p in args.prefiks.split(",") if p.strip()}
    print(f"Prefiks to'plami '{args.prefiks}': {len(prefikslar)} ta")
    print(f"Manba: {args.manba}")

    oqim = oqim_och(args.manba)
    idx, birinchi_qator = sarlavhani_oq(oqim)
    if idx is not None:
        yoq = [n for n in ("code", "product_name", "brands", "quantity") if n not in idx]
        if yoq:
            print(f"XATO: ustun topilmadi: {yoq}")
            return 2
        print(f"Sarlavha o'qildi, ustun indekslari: {idx}")
    else:
        print("Sarlavha yo'q — tayyor kesim formati (5 ustun) deb o'qiladi")

    jami = otdi = 0
    sabab = {"kod yaroqsiz": 0, "prefiks mos emas": 0, "nom bo'sh": 0,
             "nom = shtrix-kod": 0, "buzuq qator": 0, "dublikat": 0}
    per_mamlakat = {}
    korilgan = set()
    boshlandi = time.time()

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    chiqish = open(args.out, "w", encoding="utf-8", newline="\n")

    def qayta_ishla(xom):
        nonlocal jami, otdi
        jami += 1
        beshlik = qatorni_ajrat(xom, idx)
        if beshlik is None:
            sabab["buzuq qator"] += 1
            return
        code, nom, brend, hajm, kat = beshlik
        code = code.strip()
        if not is_shareable_barcode(code):
            sabab["kod yaroqsiz"] += 1
            return
        if not prefiks_mos(code, prefikslar):
            sabab["prefiks mos emas"] += 1
            return
        nom = toza(nom, 200)
        if not nom or not normalize_name(nom):
            sabab["nom bo'sh"] += 1
            return
        if nom == code or nom.isdigit():
            sabab["nom = shtrix-kod"] += 1
            return
        if code in korilgan:
            sabab["dublikat"] += 1
            return
        korilgan.add(code)
        otdi += 1
        m = mamlakat(code) or "boshqa"
        per_mamlakat[m] = per_mamlakat.get(m, 0) + 1
        chiqish.write("\t".join((code, nom, toza(brend, 120),
                                 toza(hajm, 50), toza(kat, 100))) + "\n")

    if birinchi_qator:
        qayta_ishla(birinchi_qator)
    for xom in oqim:
        qayta_ishla(xom.rstrip("\r\n"))
        if jami % 500000 == 0:
            print(f"  {jami:>9,} qator, {otdi:>7,} olindi, "
                  f"{time.time() - boshlandi:.0f}s", flush=True)
        if args.limit and jami >= args.limit:
            break

    chiqish.close()
    oqim.close()

    hajm_mb = os.path.getsize(args.out) / 1024 / 1024
    print(f"\nTUGADI: {jami:,} qator o'qildi, {otdi:,} olindi, "
          f"{time.time() - boshlandi:.0f}s")
    print(f"Natija: {os.path.abspath(args.out)}  ({hajm_mb:.1f} MB)")
    print("\nO'TMAGANLAR:")
    for k, v in sorted(sabab.items(), key=lambda z: -z[1]):
        print(f"   {k:22} {v:>10,}")
    print("\nMAMLAKAT KESIMI:")
    for m, n in sorted(per_mamlakat.items(), key=lambda z: -z[1]):
        print(f"   {m:22} {n:>8,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
