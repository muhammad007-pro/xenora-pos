#!/usr/bin/env python3
"""Frontend sintaksis qo'riqchisi — HTML ichidagi <script> bloklarini ham tekshiradi.

NEGA KERAK: ESLint faqat `.js` fayllarni ko'radi. Loyihadagi kodning KATTA
qismi esa `frontend/app/*.html` ichidagi inline `<script>` bloklarida yashaydi
(masalan `settings.html` — 560 qator JS). Ular ESLint qamrovidan TASHQARIDA.

2026-09-01 da aynan shu teshik tufayli `settings.html` dagi bitta apostrof
(`'[TARIF] Noma'lum tarif:'`) ishlab chiqarishga chiqib ketdi va sahifaning
BUTUN skripti parse bo'lmay qoldi — hamma funksiya `undefined` edi.
`loyalty.html` da ham xuddi shu sinf xatosi bor edi.

Bu skript hech qanday npm paketiga bog'liq emas — `node --check` ishlatadi
(Node allaqachon kerak). Shuning uchun CI'da ham, mahalliy ham bir xil ishlaydi.

ISHLATISH:
    py scripts/check_syntax.py            # butun frontend
    py scripts/check_syntax.py frontend/app/settings.html
Chiqish kodi: 0 — toza, 1 — buzuq fayl bor.
"""
from __future__ import annotations

import io
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_TARGET = os.path.join(ROOT, "frontend")
SKIP_DIRS = {"node_modules", "dist", "dist_artifacts", "__pycache__", ".git"}

# HTML izohi YOKI skript bloki — chapdan o'ngga, qaysi biri OLDIN kelsa.
# Skriptdan TASHQARIDAGI izoh butunlay yutiladi (ichida "oddiy <script>" kabi
# matn bo'lishi mumkin), skript ICHIDAGI `<!--` esa kodning bir qismi bo'lib
# qoladi va TEKSHIRILADI.
#
# ⚠️ Ilgari izohlar butun fayldan skriptlarni ajratishdan OLDIN o'chirilardi —
# shu jumladan JS shablon (`...`) ICHIDAGI `<!-- -->` lar ham. inventory.html
# da aynan shunday izoh ichidagi backtick shablonni yopib BUTUN skriptni
# buzgan (v1.12.10 → v1.13.0), lekin bu tekshiruv "OK" degan: buzuq qismni
# o'zi o'chirib, toza kodni tekshirgan edi.
_COMMENT_OR_SCRIPT = re.compile(r"<!--.*?-->|<script([^>]*)>(.*?)</script>", re.S | re.I)


def _node_check(code: str, as_module: bool, tmpdir: str) -> str | None:
    """Xato matnini qaytaradi, toza bo'lsa None."""
    path = os.path.join(tmpdir, "chunk" + (".mjs" if as_module else ".cjs"))
    io.open(path, "w", encoding="utf-8", newline="\n").write(code)
    res = subprocess.run(["node", "--check", path], capture_output=True, text=True)
    if res.returncode == 0:
        return None
    for line in res.stderr.splitlines():
        if "Error" in line:
            return line.strip()
    return res.stderr.strip().splitlines()[0] if res.stderr.strip() else "noma'lum xato"


def check_file(path: str, tmpdir: str) -> list[tuple[str, str]]:
    """[(joy, xato)] ro'yxati."""
    src = io.open(path, encoding="utf-8", errors="replace").read()
    try:
        rel = os.path.relpath(path, ROOT).replace("\\", "/")
    except ValueError:      # Windows: boshqa disk (masalan C:\Temp) — mutlaq yo'l
        rel = path.replace("\\", "/")
    out: list[tuple[str, str]] = []

    if path.endswith((".js", ".mjs")):
        # ES modul sifatida tekshiramiz: `import` bo'lgan fayllar CJS'da yiqiladi,
        # modul parseri esa classic skriptlarni ham qabul qiladi.
        err = _node_check(src, True, tmpdir)
        if err:
            out.append((rel, err))
        return out

    if not path.endswith(".html"):
        return out

    for m in _COMMENT_OR_SCRIPT.finditer(src):
        if m.group(0).startswith("<!--"):
            continue            # skriptdan tashqaridagi HTML izohi
        attrs, code = m.group(1), m.group(2)
        if "src=" in attrs or not code.strip():
            continue
        line = src[: m.start()].count("\n") + 1
        err = _node_check(code, "module" in attrs, tmpdir)
        if err:
            out.append((f"{rel}:{line} (<script>)", err))
    return out


def main(argv: list[str]) -> int:
    targets = argv[1:] or [DEFAULT_TARGET]
    files: list[str] = []
    for t in targets:
        t = t if os.path.isabs(t) else os.path.join(ROOT, t)
        if os.path.isfile(t):
            files.append(t)
            continue
        for dp, dns, fns in os.walk(t):
            dns[:] = [d for d in dns if d not in SKIP_DIRS]
            files += [os.path.join(dp, f) for f in fns
                      if f.endswith((".js", ".mjs", ".html")) and not f.endswith(".min.js")]

    bad: list[tuple[str, str]] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for f in sorted(files):
            bad += check_file(f, tmpdir)

    if not bad:
        print(f"OK — {len(files)} ta fayl tekshirildi, sintaksis xatosi yo'q")
        return 0

    print(f"BUZUQ: {len(bad)} ta skript\n")
    for where, err in bad:
        print(f"  {where}\n      {err}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
