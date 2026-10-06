"""CHEK PACHKA YORLIG'I — `sale_unit` bo'yicha va frontend bilan BIR XIL.

MUAMMO (2026-10-04): termal chek yo'li (`routers/order.py` →
`escpos_print_receipt`) pachka yorlig'ida "dona" ni QOTIB yozardi:

    f" (pachka, {int(base_qty / quantity)} dona)"

Natijada 20 kg qop chekda **"(pachka, 20 dona)"** bo'lib chiqardi, `int()`
esa kasrni kesib tashlardi (0.5 → 0). Frontend cheklari (POS ekrani va
bosiladigan HTML chek) allaqachon to'g'ri edi — ya'ni BIR SOTUV ikki xil
chekda ikki xil yozilardi.

Nimani qulflaydi:
  1. yorliq `sale_unit` ga qarab: kg → "qop, 20 kg", ml → "butun, 150 ml",
     pcs → "pachka, 10 dona" (AVVALGIDEK — mavjud cheklar o'zgarmaydi)
  2. 3 xonagacha yaxlitlash (`int()` emas)
  3. ⚠️ FRONTEND BILAN PARITY — matn ikki joyda yozilgan (backend JS faylini
     o'qiy olmaydi), shuning uchun birini o'zgartirib ikkinchisini unutish
     EHTIMOLI bor. 3-blok aynan shu xatoni ushlaydi.
  4. router HAQIQATAN helperni ishlatishi (qotib qolgan matn qaytib kelmasin)

Ishga tushirish:  cd backend && py -m pytest tests/test_pack_label.py -v
"""
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from services.unit_converter import (
    PACK_LENGTH_UNITS,
    PACK_VOL_UNITS,
    PACK_WEIGHT_UNITS,
    fmt_pack_qty,
    pack_size_label,
    pack_word,
)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RCPT_JS = os.path.join(ROOT, "frontend", "js", "core", "receipt-print.js")
ORDER_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "routers", "order.py")


# ═══════════════════════════════════════════════════════════════════════════
# 1. YORLIQ — sale_unit bo'yicha
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("unit,per,kutilgan", [
    # Og'irlik/suyuqlik → "qop"
    ("kg",   20,  "qop, 20 kg"),
    ("g",    500, "qop, 500 g"),
    ("l",    5,   "qop, 5 l"),
    ("litr", 5,   "qop, 5 litr"),
    ("KG",   20,  "qop, 20 kg"),       # katta harf
    ("  kg ", 20, "qop, 20 kg"),       # bo'shliq
    # Hajm (atir) → "butun"
    ("ml",   150, "butun, 150 ml"),
    ("dl",   5,   "butun, 5 dl"),
    # ⚠️ GOLDEN: mavjud cheklar BIT-BITIGA o'zgarmaydi
    ("pcs",  10,  "pachka, 10 dona"),
    ("dona", 12,  "pachka, 12 dona"),
    # Uzunlik (kabel/mato) → "o'ram" (2026-10-07: ilgari "pachka, 100 dona" — yolg'on birlik)
    ("m",    100, "o'ram, 100 m"),
    ("sm",   50,  "o'ram, 50 sm"),
    ("M",    150, "o'ram, 150 m"),
    (None,   6,   "pachka, 6 dona"),
    ("",     6,   "pachka, 6 dona"),
    ("quti", 4,   "pachka, 4 dona"),
])
def test_yorliq_sale_unit_boyicha(unit, per, kutilgan):
    assert pack_size_label(unit, per) == kutilgan


def test_pack_word_juftligi():
    assert pack_word("kg") == ("qop", "kg")
    assert pack_word("ml") == ("butun", "ml")
    assert pack_word("m") == ("o'ram", "m")
    assert pack_word("pcs") == ("pachka", "dona")


# ═══════════════════════════════════════════════════════════════════════════
# 2. YAXLITLASH — int() emas, 3 xona
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("qiymat,kutilgan", [
    (20,          "20"),          # butun — ortiqcha nol YO'Q ("20.000" emas)
    (20.0,        "20"),
    (0.5,         "0.5"),         # int() -> 0 (yo'qolardi), round() ham mumkin emas
    (0.7405882,   "0.741"),
    (1 / 3,       "0.333"),
    (2.5,         "2.5"),
    (19.9999,     "20"),
    (1000000,     "1000000"),     # ilmiy ko'rinish YO'Q ("1e+06" emas)
    (None,        "0"),
    (0,           "0"),
    ("x",         "0"),           # buzuq qiymat chekni yiqitmaydi
    (float("nan"), "0"),
    (float("inf"), "0"),
])
def test_yaxlitlash(qiymat, kutilgan):
    assert fmt_pack_qty(qiymat) == kutilgan


def test_yarim_kg_qop_butunlab_yoqolmaydi():
    """Eski `int()` xatosi: 0.5 → 0 → "pachka, 0 dona"."""
    assert pack_size_label("kg", 0.5) == "qop, 0.5 kg"
    assert "0.5" in pack_size_label("kg", 0.5)


# ═══════════════════════════════════════════════════════════════════════════
# 3. FRONTEND BILAN PARITY — ikki manba ajralib ketmasin
# ═══════════════════════════════════════════════════════════════════════════
def _js_src() -> str:
    with open(RCPT_JS, encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


def test_birlik_royxatlari_frontend_bilan_bir_xil():
    """`_PACK_WEIGHT_UNITS` / `_PACK_VOL_UNITS` ikki tomonda mos bo'lsin.

    Node TALAB QILINMAYDI — ro'yxatlar JS manbasidan o'qiladi. Kimdir
    frontendga yangi birlik qo'shsa-yu backendni unutsa, test yiqiladi."""
    src = _js_src()

    def js_list(name):
        m = re.search(rf"const {name}\s*= \[([^\]]*)\];", src)
        assert m, f"{name} JS manbasida topilmadi — test eskirgan"
        return tuple(re.findall(r"'([^']*)'", m.group(1)))

    assert js_list("_PACK_WEIGHT_UNITS") == PACK_WEIGHT_UNITS
    assert js_list("_PACK_VOL_UNITS") == PACK_VOL_UNITS
    assert js_list("_PACK_LENGTH_UNITS") == PACK_LENGTH_UNITS


def test_frontend_yaxlitlash_formulasi_ozgarmagan():
    """`fmtPackQty` AYNAN `Math.round(n * 1000) / 1000` bo'lib qolsin.

    Backend `math.floor(n * 1000 + 0.5) / 1000` ni ishlatadi — bu JS
    `Math.round` ning aynan ekvivalenti. Frontend formulasi o'zgarsa
    (masalan `toFixed(3)` ga) ikkisi ajralib ketadi."""
    src = _js_src()
    assert re.search(r"Math\.round\(\(Number\(n\) \|\| 0\) \* 1000\) / 1000", src), \
        "frontend fmtPackQty formulasi o'zgargan — backend bilan solishtir"


_NODE = shutil.which("node")


@pytest.mark.skipif(_NODE is None, reason="node o'rnatilmagan — parity faqat manba bo'yicha tekshirildi")
def test_matn_frontend_bilan_AYNAN_bir_xil():
    """HAQIQIY taqqoslash: frontend funksiyasini node'da yugurtiramiz.

    Faqat katta/kichik harf farq qiladi (backend yorlig'i mahsulot nomidan
    keyin qavs ichida turadi): frontend "Qop (20 kg)", backend "qop, 20 kg".
    Shu sabab so'z va MIQDOR MATNI solishtiriladi."""
    src = _js_src()
    parts = []
    for pat, nom in [
        (r"const _PACK_WEIGHT_UNITS = \[[^\]]*\];", "_PACK_WEIGHT_UNITS"),
        (r"const _PACK_VOL_UNITS\s*= \[[^\]]*\];", "_PACK_VOL_UNITS"),
        (r"const _PACK_LENGTH_UNITS\s*= \[[^\]]*\];", "_PACK_LENGTH_UNITS"),
        (r"export function fmtPackQty\(n\)[\s\S]*?\n}\n", "fmtPackQty"),
        (r"export function packKind\(saleUnit\)[\s\S]*?\n}\n", "packKind"),
        (r"export function packSizeLabel\(saleUnit, per\)[\s\S]*?\n}\n", "packSizeLabel"),
    ]:
        m = re.search(pat, src)
        assert m, f"{nom} JS manbasida topilmadi — test eskirgan"
        parts.append(m.group(0).replace("export ", ""))

    holatlar = [
        ("kg", 20), ("g", 500), ("l", 5), ("litr", 5),
        ("ml", 150), ("dl", 5),
        ("pcs", 10), ("dona", 12), ("m", 100), ("sm", 50), ("quti", 4),
        ("kg", 0.5), ("kg", 0.7405882), ("kg", 1000000), ("pcs", 19.9999),
    ]
    script = "\n".join(parts) + f"""
const holatlar = {json.dumps(holatlar)};
const out = holatlar.map(([u, p]) => {{
  const k = packKind(u);
  return [k.pack, fmtPackQty(p), k.perUnit ? k.unitWord : 'dona'];
}});
console.log(JSON.stringify(out));
"""
    res = subprocess.run([_NODE, "-e", script], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, f"node xatosi: {res.stderr}"
    js = json.loads(res.stdout.strip())

    for (unit, per), (js_word, js_qty, js_unit) in zip(holatlar, js):
        py_word, py_unit = pack_word(unit)
        py_qty = fmt_pack_qty(per)
        assert js_word.lower() == py_word, f"{unit}: so'z JS={js_word} PY={py_word}"
        assert js_unit.lower() == py_unit.lower(), f"{unit}: birlik JS={js_unit} PY={py_unit}"
        assert js_qty == py_qty, f"{unit}/{per}: miqdor JS={js_qty} PY={py_qty}"


# ═══════════════════════════════════════════════════════════════════════════
# 4. ROUTER helperni HAQIQATAN ishlatadi (qotib qolgan matn qaytmasin)
# ═══════════════════════════════════════════════════════════════════════════
def _order_src() -> str:
    with open(ORDER_PY, encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


def test_router_helperni_ishlatadi():
    src = _order_src()
    assert "from services.unit_converter import pack_size_label" in src
    assert "pack_size_label(getattr(it.product, 'sale_unit', None)" in src


def test_router_da_qotib_qolgan_dona_YOQ():
    """Eski qator qaytib kelmasin."""
    src = _order_src()
    assert 'f" (pachka, {int(' not in src
    assert "int(it.base_qty / it.quantity)" not in src
