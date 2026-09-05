"""Open Food/Beauty/Products Facts qamrovini sinash — FAQAT O'QISH.

Shtrix-kodlar ro'yxatini fayldan yoki argument sifatida oladi (bazaga
umuman tegmaydi). Har kod uchun uch ochiq bazani ketma-ket so'raydi va
birinchi topilganda to'xtaydi.

Ishlatish:
    py scripts/off_probe.py codes.txt
    py scripts/off_probe.py 4780015690121 8690504081234
    py scripts/off_probe.py codes.txt --out natija.json --pause 0.6

Fayl formati: har qatorda bitta kod. `#` bilan boshlangan qatorlar va
bo'sh qatorlar tashlab ketiladi. Qatorda `|` bo'lsa, birinchi ustun kod
deb olinadi (eski `kod|biznes|kategoriya` formati ham ishlaydi).
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

UA = ("XenoraPOS-CatalogResearch/1.0 "
      "(coverage test; contact via github.com/muhammad007-pro)")
BAZALAR = [
    ("OFF", "https://world.openfoodfacts.org/api/v2/product/{}.json"),
    ("OBF", "https://world.openbeautyfacts.org/api/v2/product/{}.json"),
    ("OPF", "https://world.openproductsfacts.org/api/v2/product/{}.json"),
]
FIELDS = "?fields=product_name,brands,quantity,categories,countries"

# GS1 prefiks -> mamlakat (faqat hisobot uchun, kodni cheklamaydi)
PREFIKS = [
    (("478",), "O'zbekiston"),
    (tuple(str(i) for i in range(460, 470)), "Rossiya"),
    (("869",), "Turkiya"),
    (("487",), "Qozog'iston"),
    (("484",), "Moldova"),
    (("482",), "Ukraina"),
]


def mamlakat(bc):
    p = bc[:3]
    for prefikslar, nom in PREFIKS:
        if p in prefikslar:
            return nom
    return "boshqa"


def kodlarni_oq(argv):
    """Argumentlardan kodlar ro'yxatini yig'adi: fayl yoki to'g'ridan kod."""
    kodlar, manba = [], []
    for a in argv:
        if os.path.isfile(a):
            manba.append(a)
            with open(a, encoding="utf-8-sig") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    kodlar.append(line.split("|")[0].strip())
        else:
            manba.append("(argument)")
            kodlar.append(a.strip())

    toza, korilgan = [], set()
    for k in kodlar:
        k = re.sub(r"\D", "", k)
        if len(k) < 8 or len(k) > 14 or k in korilgan:
            continue
        korilgan.add(k)
        toza.append(k)
    return toza, manba


def sora(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"status": 0}
        return {"_xato": f"HTTP {e.code}"}
    except Exception as e:  # tarmoq / timeout
        return {"_xato": str(e)[:60]}


def main():
    argv = sys.argv[1:]
    out = "off_result.json"
    pauza = 0.6
    limit = None

    pozitsion = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--out" and i + 1 < len(argv):
            out = argv[i + 1]
            i += 2
        elif a == "--pause" and i + 1 < len(argv):
            pauza = float(argv[i + 1])
            i += 2
        elif a == "--limit" and i + 1 < len(argv):
            limit = int(argv[i + 1])
            i += 2
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            pozitsion.append(a)
            i += 1

    if not pozitsion:
        print(__doc__)
        return 2

    kodlar, manba = kodlarni_oq(pozitsion)
    if limit:
        kodlar = kodlar[:limit]
    if not kodlar:
        print("Yaroqli shtrix-kod topilmadi.")
        return 2

    print(f"Manba: {', '.join(sorted(set(manba)))} | "
          f"unikal kod: {len(kodlar)}", flush=True)

    natija, sorovlar = [], 0
    boshlandi = time.time()
    for n, bc in enumerate(kodlar, 1):
        topildi = None
        for nom, shablon in BAZALAR:
            d = sora(shablon.format(bc) + FIELDS)
            sorovlar += 1
            time.sleep(pauza)
            if d.get("_xato"):
                continue
            if d.get("status") == 1 and d.get("product"):
                p = d["product"]
                topildi = {
                    "baza": nom,
                    "nom": (p.get("product_name") or "").strip(),
                    "brend": (p.get("brands") or "").strip(),
                    "hajm": (p.get("quantity") or "").strip(),
                    "kat": (p.get("categories") or "").strip(),
                    "mamlakat": (p.get("countries") or "").strip(),
                }
                break
        natija.append({"bc": bc, "prefiks": mamlakat(bc), "off": topildi})
        belgi = "+" if topildi else "-"
        nomi = topildi["nom"] if topildi else ""
        print(f"  {n:>3}/{len(kodlar)} {belgi} {bc} {nomi}"[:100], flush=True)

    with open(out, "w", encoding="utf-8") as f:
        json.dump(natija, f, ensure_ascii=False, indent=1)

    topilgan = [x for x in natija if x["off"]]
    print(f"\nTUGADI: {len(natija)} kod, {len(topilgan)} topildi "
          f"({100 * len(topilgan) / len(natija):.0f}%), "
          f"{sorovlar} so'rov, {time.time() - boshlandi:.0f}s")

    per_baza = {}
    per_mam = {}
    for x in natija:
        m = x["prefiks"]
        per_mam.setdefault(m, [0, 0])
        per_mam[m][0] += 1
        if x["off"]:
            per_mam[m][1] += 1
            per_baza[x["off"]["baza"]] = per_baza.get(x["off"]["baza"], 0) + 1
    print("Baza kesimi:", ", ".join(f"{k}={v}" for k, v in
                                    sorted(per_baza.items())) or "yo'q")
    for m, (jami, top) in sorted(per_mam.items(), key=lambda z: -z[1][0]):
        print(f"  {m:<12} {top}/{jami}")
    print(f"Natija fayli: {os.path.abspath(out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
