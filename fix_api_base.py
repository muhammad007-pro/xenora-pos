"""
Barcha frontend .html fayllarida hardcoded const BASE='/api/v1' ni
dev-aware versiyaga almashtiradi.
"""
import re
from pathlib import Path

DEV_LINES = (
    "const _lport = window.location.port;\n"
    "const _isDev = ['5500','5501','3000','4200','8080'].includes(_lport) "
    "&& ['localhost','127.0.0.1'].includes(window.location.hostname);\n"
)

# const BASE = '/api/v1'  yoki  const BASE='/api/v1'  (probelsiz yoki bo'shlikli)
PATTERN = re.compile(r"(const BASE\s*=\s*)('/api/v1')")

fixed = []
skipped = []

html_files = list(Path("D:/cafe/frontend").rglob("*.html"))

for fpath in html_files:
    text = fpath.read_text(encoding="utf-8", errors="replace")

    # Allaqachon tuzatilganmi?
    if "_isDev" in text and "const BASE" not in text.replace("const _lport", "").replace("const _isDev", ""):
        skipped.append(str(fpath.name))
        continue

    # BASE satri bor?
    if not PATTERN.search(text):
        continue

    # Allaqachon _isDev bor, lekin BASE ham bor → o'tkazib yuborish
    if "_isDev" in text:
        skipped.append(f"{fpath.name} (already has _isDev)")
        continue

    # Satrma-satr qayta yozamiz
    lines = text.splitlines(keepends=True)
    new_lines = []
    changed = False
    for line in lines:
        m = PATTERN.search(line)
        if m:
            indent = re.match(r"^(\s*)", line).group(1)
            # _lport/_isDev qatorlarini qo'shamiz
            new_lines.append(indent + "const _lport = window.location.port;\n")
            new_lines.append(
                indent + "const _isDev = ['5500','5501','3000','4200','8080'].includes(_lport) "
                "&& ['localhost','127.0.0.1'].includes(window.location.hostname);\n"
            )
            # '/api/v1' → _isDev ? 'http://localhost:8000/api/v1' : '/api/v1'
            new_line = PATTERN.sub(
                r"\1_isDev ? 'http://localhost:8000/api/v1' : '/api/v1'",
                line
            )
            new_lines.append(new_line)
            changed = True
        else:
            new_lines.append(line)

    if changed:
        fpath.write_text("".join(new_lines), encoding="utf-8")
        fixed.append(fpath.name)

print(f"\nTuzatildi ({len(fixed)}):")
for f in fixed:
    print(f"  + {f}")
if skipped:
    print(f"\nO'tkazib yuborildi ({len(skipped)}):")
    for s in skipped:
        print(f"  ~ {s}")
