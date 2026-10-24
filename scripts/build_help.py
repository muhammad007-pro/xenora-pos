#!/usr/bin/env python3
"""
XENORA — Yordam bo'limi matnini yig'ish: docs/help/*.md -> frontend/js/core/help-content.js

    py scripts/build_help.py            # help-content.js ni qayta yozadi
    py scripts/build_help.py --check    # eskirgan bo'lsa 1 qaytaradi (test/CI)

NEGA .md TO'G'RIDAN O'QILMAYDI
──────────────────────────────
.exe frontendni `file://` dan ochadi — u yerda `fetch('*.md')` ishonchsiz, va
`.md` fayl service worker keshida ham yo'q (offline'da yordam ochilmasdi).
Shuning uchun matn BUILD paytida bitta classic JS faylga (`window.XENORA_HELP`)
yig'iladi: u `frontend/` ichida, demak `.exe` ga (electron `extraResources`
`../frontend/**`) va SW keshiga avtomatik tushadi.

FORMAT — docs/help/README.md ga qarang. Qisqasi:
    # Bo'lim           (faylda bitta, birinchi)
    ## Savol?           (savol)
    Kalit: a, b         (ixtiyoriy, faqat qidiruv uchun, ko'rinmaydi)
    1. qadam / - band / > eslatma / oddiy paragraf / **qalin** / `kod`

XAVFSIZLIK: hamma matn HTML-ekranlanadi, faqat yuqoridagi belgilash HTML'ga
aylanadi — .md ichidagi `<script>` ekranda matn bo'lib ko'rinadi.
"""
from __future__ import annotations

import html
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT, "docs", "help")
OUT = os.path.join(ROOT, "frontend", "js", "core", "help-content.js")

FILE_RE = re.compile(r"^(\d{2})-([a-z0-9-]+)\.md$")
OL_RE = re.compile(r"^(\d+)\.\s+(.*)$")
UL_RE = re.compile(r"^-\s+(.*)$")
SUB_UL_RE = re.compile(r"^\s{2,}-\s+(.*)$")
KEYS_RE = re.compile(r"^Kalit:\s*(.*)$")

HEADER = (
    "/* AVTO-YARATILGAN — QO'LDA TAHRIRLAMANG.\n"
    " * Manba: docs/help/*.md   Yaratish: py scripts/build_help.py\n"
    " * Tekshiruv: py scripts/build_help.py --check (test_help_center.mjs ham)\n"
    " */\n"
)


class HelpError(Exception):
    pass


def inline(text: str) -> str:
    """Ekranlash + **qalin** + `kod`. Boshqa hech narsa HTML bo'lmaydi."""
    # quote=False: natija faqat element MATNIGA qo'yiladi (atributga hech qachon),
    # shuning uchun < > & yetarli; ' ni &#x27; qilish faqat hajmni oshirardi.
    s = html.escape(text, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    return s


def plain(text: str) -> str:
    """Qidiruv uchun belgilashsiz matn."""
    return re.sub(r"\*\*|`", "", text).strip()


def render_body(lines: list[str], where: str) -> tuple[str, str]:
    """Savol tanasini (qatorlar) HTML va oddiy matnga aylantiradi."""
    out: list[str] = []
    words: list[str] = []
    para: list[str] = []
    lst: dict | None = None   # {"tag": "ol"|"ul", "items": [[html, [sub...]], ...]}

    def flush_para():
        nonlocal para
        if para:
            out.append("<p>" + " ".join(inline(p) for p in para) + "</p>")
            para = []

    def flush_list():
        nonlocal lst
        if lst:
            parts = []
            for main, subs in lst["items"]:
                sub_html = ("<ul>" + "".join(f"<li>{s}</li>" for s in subs) + "</ul>") if subs else ""
                parts.append(f"<li>{main}{sub_html}</li>")
            out.append(f"<{lst['tag']}>" + "".join(parts) + f"</{lst['tag']}>")
            lst = None

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            flush_para()
            flush_list()
            continue
        m_sub = SUB_UL_RE.match(line)
        if m_sub:
            if not lst or not lst["items"]:
                raise HelpError(f"{where}: ichki ro'yxat bandi ro'yxatsiz turibdi: {line!r}")
            lst["items"][-1][1].append(inline(m_sub.group(1)))
            words.append(plain(m_sub.group(1)))
            continue
        stripped = line.strip()
        m_ol, m_ul = OL_RE.match(stripped), UL_RE.match(stripped)
        if m_ol or m_ul:
            flush_para()
            tag = "ol" if m_ol else "ul"
            body = (m_ol or m_ul).group(2 if m_ol else 1)
            if lst and lst["tag"] != tag:
                flush_list()
            if not lst:
                lst = {"tag": tag, "items": []}
            lst["items"].append([inline(body), []])
            words.append(plain(body))
            continue
        if stripped.startswith(">"):
            flush_para()
            flush_list()
            body = stripped[1:].strip()
            out.append('<div class="xh-note">' + inline(body) + "</div>")
            words.append(plain(body))
            continue
        if stripped.startswith("#"):
            raise HelpError(f"{where}: kutilmagan sarlavha: {line!r}")
        flush_list()
        para.append(stripped)
        words.append(plain(stripped))
    flush_para()
    flush_list()
    if not out:
        raise HelpError(f"{where}: javob bo'sh")
    return "".join(out), " ".join(words)


def parse_file(path: str, sec_id: str) -> dict:
    with open(path, "r", encoding="utf-8-sig") as f:
        lines = f.read().replace("\r\n", "\n").split("\n")
    title = None
    items: list[dict] = []
    cur: dict | None = None
    name = os.path.basename(path)

    def close():
        if cur is None:
            return
        where = f"{name} «{cur['q']}»"
        body_html, body_text = render_body(cur["lines"], where)
        items.append({
            "id": f"{sec_id}-{len(items) + 1}",
            "q": cur["q"],
            "html": body_html,
            "text": body_text,
            "keys": cur["keys"],
        })

    for i, line in enumerate(lines, 1):
        if line.startswith("# "):
            if title is not None:
                raise HelpError(f"{name}:{i}: faylda ikkinchi '# ' bo'lim sarlavhasi")
            if cur is not None or any(l.strip() for l in lines[: i - 1]):
                raise HelpError(f"{name}:{i}: '# ' sarlavha birinchi qator bo'lishi kerak")
            title = line[2:].strip()
            continue
        if line.startswith("## "):
            close()
            cur = {"q": line[3:].strip(), "lines": [], "keys": ""}
            continue
        if cur is None:
            if line.strip():
                raise HelpError(f"{name}:{i}: savoldan ('## ') oldin matn bor")
            continue
        m_keys = KEYS_RE.match(line.strip())
        if m_keys and not any(l.strip() for l in cur["lines"]):
            cur["keys"] = m_keys.group(1).strip()
            continue
        cur["lines"].append(line)
    close()
    if not title:
        raise HelpError(f"{name}: '# ' bo'lim sarlavhasi yo'q")
    if not items:
        raise HelpError(f"{name}: birorta savol ('## ') yo'q")
    return {"id": sec_id, "title": title, "items": items}


def build() -> str:
    if not os.path.isdir(SRC_DIR):
        raise HelpError(f"papka yo'q: {SRC_DIR}")
    sections = []
    for fname in sorted(os.listdir(SRC_DIR)):
        m = FILE_RE.match(fname)
        if not m:
            continue        # README.md va boshqalar — yordam matni emas
        sections.append(parse_file(os.path.join(SRC_DIR, fname), m.group(2)))
    if not sections:
        raise HelpError("docs/help da NN-nomi.md fayl topilmadi")
    data = {"sections": sections}
    body = json.dumps(data, ensure_ascii=False, indent=1, sort_keys=False)
    return HEADER + "window.XENORA_HELP = " + body + ";\n"


def main(argv: list[str]) -> int:
    check = "--check" in argv
    try:
        content = build()
    except HelpError as e:
        print(f"XATO: {e}", file=sys.stderr)
        return 2
    current = None
    if os.path.exists(OUT):
        with open(OUT, "r", encoding="utf-8") as f:
            current = f.read().replace("\r\n", "\n")
    if check:
        if current != content:
            print("ESKIRGAN: frontend/js/core/help-content.js docs/help bilan mos emas —"
                  " `py scripts/build_help.py` ni yurgizing", file=sys.stderr)
            return 1
        print("OK — help-content.js docs/help bilan mos")
        return 0
    if current == content:
        print("O'zgarish yo'q — help-content.js allaqachon yangi")
        return 0
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    n = sum(len(s["items"]) for s in json.loads(content[content.index("{"):content.rindex(";")])["sections"])
    print(f"Yozildi: {os.path.relpath(OUT, ROOT)} ({n} ta savol)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
