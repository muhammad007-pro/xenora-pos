#!/usr/bin/env python3
"""
XENORA — versiyani BIR BUYRUQDA hamma joyda ko'tarish.

    py scripts/bump_version.py 1.12.18      # hammasini 1.12.18 ga qo'yadi
    py scripts/bump_version.py --check      # mos kelmasa 1 qaytaradi (CI)

NEGA BOR
────────
Versiya 6 joyda yozilgan va ularni QO'LDA yangilash kerak edi (DEPLOY.md §4).
Natija: `frontend/pwa/service-worker.js` dagi `APP_VERSION` **v1.55.1 da
qotib qoldi** — v1.10.1 dan keyin 6+ reliz (1.10.x … 1.12.17) davomida
unutilgan. Service worker esa eski keshni FAQAT shu qiymat o'zgarganda
tozalaydi, ya'ni brauzerdan kirgan kassirlar oylar davomida eski frontendni
ko'rishda davom etgan. `shared/login.html` dagi yorliq ham v1.10.1 da qolgan.

Shuning uchun: bitta buyruq + CI'da `--check`.

⚠️ BOM TUZOG'I: `frontend/shared/version.js` BOM bilan saqlangan (shunday
qoldiriladi), `electron/package.json` esa BOM'SIZ bo'lishi SHART — BOM bilan
electron-builder yiqiladi. Shu sabab har fayl o'z kodlashida qayta yoziladi
va satr oxirlari (`newline=''`) tegilmaydi.
"""
from __future__ import annotations

import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


class Target:
    """Bitta fayldagi bitta versiya o'rni."""

    def __init__(self, path: str, pattern: str, template: str, label: str,
                 no_bom: bool = False):
        self.path = path
        self.pattern = re.compile(pattern, re.MULTILINE)
        self.template = template          # {v} bilan
        self.label = label
        # True — fayl BOM bilan BUZILADI (electron-builder JSON, Groovy/gradle).
        # Yozishda BOM olib tashlanadi, --check esa BOM topsa xato beradi.
        self.no_bom = no_bom

    def has_bom(self) -> bool:
        with open(os.path.join(ROOT, self.path), "rb") as f:
            return f.read(3) == b"\xef\xbb\xbf"

    def read(self) -> tuple[str, str]:
        """(mazmun, kodlash) — BOM bor/yo'qligini SAQLAYDI (no_bom fayldan tashqari)."""
        full = os.path.join(ROOT, self.path)
        with open(full, "rb") as f:
            raw = f.read()
        enc = "utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else "utf-8"
        text = raw.decode(enc)
        return text, ("utf-8" if self.no_bom else enc)

    def current(self) -> str | None:
        text, _ = self.read()
        m = self.pattern.search(text)
        return m.group("v") if m else None

    def write(self, version: str) -> bool:
        """True — o'zgardi."""
        text, enc = self.read()
        m = self.pattern.search(text)
        if not m:
            raise SystemExit(f"XATO: {self.path} — versiya namunasi topilmadi")
        new_line = self.template.format(v=version)
        if m.group(0) == new_line and not (self.no_bom and self.has_bom()):
            return False
        text = text[: m.start()] + new_line + text[m.end():]
        full = os.path.join(ROOT, self.path)
        # newline='' — mavjud satr oxirlari (CRLF/LF) o'zgarmaydi
        with io.open(full, "w", encoding=enc, newline="") as f:
            f.write(text)
        return True


TARGETS = [
    Target(
        "backend/config.py",
        r'^    VERSION: str = "(?P<v>\d+\.\d+\.\d+)"',
        '    VERSION: str = "{v}"',
        "backend config",
    ),
    Target(
        "frontend/shared/version.js",
        r"^window\.APP_VERSION = '(?P<v>\d+\.\d+\.\d+)';",
        "window.APP_VERSION = '{v}';",
        "frontend version.js",
    ),
    # Service worker — eski keshni tozalash AYNAN shu qiymatga bog'liq
    Target(
        "frontend/service-worker.js",
        r"^const APP_VERSION   = '(?P<v>\d+\.\d+\.\d+)';",
        "const APP_VERSION   = '{v}';",
        "service worker",
    ),
    Target(
        "electron/package.json",
        r'^  "version": "(?P<v>\d+\.\d+\.\d+)",',
        '  "version": "{v}",',
        "electron package.json",
        no_bom=True,
    ),
    # Groovy BOM'ni o'qiy olmaydi: "Unexpected character: '﻿' @ line 1" —
    # v1.10.6..v1.13.2 da APK shu sabab qurilmadi (2026-10-07 aniqlandi).
    Target(
        "android/android/app/build.gradle",
        r'^        versionName "(?P<v>\d+\.\d+\.\d+)"',
        '        versionName "{v}"',
        "android versionName",
        no_bom=True,
    ),
    # Login sahifasidagi yorliq — runtime'da version.js bosadi, lekin
    # version.js yuklanmasa KO'RINADIGAN qiymat shu (fallback).
    Target(
        "frontend/shared/login.html",
        r'id="appVersion">v(?P<v>\d+\.\d+\.\d+)<',
        'id="appVersion">v{v}<',
        "login.html yorligi",
    ),
]

VERSION_CODE = Target(
    "android/android/app/build.gradle",
    r"^        versionCode (?P<v>\d+)",
    "        versionCode {v}",
    "android versionCode",
    no_bom=True,
)


def cmd_check() -> int:
    """Hamma joy bir xilmi? CI uchun."""
    found = {}
    for t in TARGETS:
        found[t.label] = t.current()

    width = max(len(k) for k in found)
    for label, ver in found.items():
        print(f"  {label:<{width}} : {ver}")

    bom_bad = sorted({t.path for t in TARGETS + [VERSION_CODE] if t.no_bom and t.has_bom()})
    if bom_bad:
        print(f"\nXATO: BOM bo'lmasligi kerak (build yiqiladi): {', '.join(bom_bad)}")
        print("Tuzatish: py scripts/bump_version.py <joriy versiya>  (BOM olib tashlanadi)")
        return 1

    values = set(found.values())
    if None in values:
        print("\nXATO: ba'zi joyda versiya topilmadi")
        return 1
    if len(values) != 1:
        print(f"\nXATO: versiyalar MOS KELMAYDI -> {sorted(values)}")
        print("Tuzatish: py scripts/bump_version.py <versiya>")
        return 1
    print(f"\nOK — hamma joyda {values.pop()}")
    return 0


def cmd_bump(version: str) -> int:
    if not VERSION_RE.match(version):
        print(f"XATO: versiya 'X.Y.Z' shaklida bo'lsin (berilgan: {version})")
        return 2

    # `version.js` — ASOSIY manba. Versiya RAQAMI haqiqatan o'zgaradimi?
    # Agar yo'q (ya'ni biz shunchaki orqada qolgan faylni tuzatayotgan
    # bo'lsak), `versionCode` OSHMASLIGI kerak: u allaqachon shu reliz uchun
    # ishlatilgan va bekordan-bekor oshirish Play Store raqamini chalkashtiradi.
    canonical = next(t for t in TARGETS if t.path == "frontend/shared/version.js")
    real_bump = canonical.current() != version

    changed = []
    for t in TARGETS:
        if t.write(version):
            changed.append(t.label)

    print(f"Versiya -> {version}")
    for c in changed:
        print(f"  yangilandi: {c}")
    if not changed:
        print("  (hamma joyda allaqachon shu versiya edi)")

    code = VERSION_CODE.current()
    if code is None:
        print("XATO: android versionCode topilmadi")
        return 1
    if real_bump:
        # versionCode — Play Store uchun har YANGI relizda oshishi shart
        new_code = str(int(code) + 1)
        VERSION_CODE.write(new_code)
        print(f"  android versionCode: {code} -> {new_code}")
    else:
        print(f"  android versionCode: {code} (o'zgarmadi — versiya raqami bir xil)")
    print("\nKeyingi qadam: CHANGELOG.md ga yozuv qo'shing.")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    if argv[1] == "--check":
        return cmd_check()
    return cmd_bump(argv[1])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
