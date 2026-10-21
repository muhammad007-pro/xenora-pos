# Yordam bo'limi — manba fayllar

Bu papkadagi `NN-nomi.md` fayllar do'konchi ko'radigan **"? Yordam"** oynasining
matni. Oyna POS (header) va Admin panel (sidebar pasti) da ochiladi.

## Qanday ishlaydi

```
docs/help/*.md  ──(py scripts/build_help.py)──►  frontend/js/core/help-content.js
                                                  (window.XENORA_HELP)
```

* Ilova `.md` ni o'zi o'qimaydi — `help-content.js` ga yig'ilgan nusxani o'qiydi.
  Sabab: `.exe` frontendni `file://` dan ochadi, u yerda `fetch('*.md')` ishonchsiz;
  JS fayl esa `frontend/` ichida bo'lgani uchun `.exe` ga (`extraResources`) va
  service worker keshiga avtomatik tushadi.
* **Matnni o'zgartirsangiz** — `py scripts/build_help.py` ni yurgizing va ikkala
  faylni birga commit qiling. `py scripts/build_help.py --check` (va
  `frontend/tests/test_help_center.mjs`) nusxa eskirgan bo'lsa yiqiladi.

## Format

```markdown
# Bo'lim nomi                     ← faylda bitta, birinchi qator

## Savol matni?                    ← savol (qidiruv shu va javob matni bo'yicha)
Kalit: vozvrat, qaytarish          ← ixtiyoriy, ko'rinmaydi — faqat qidiruv uchun

Oddiy paragraf.

1. Raqamli qadam                   ← ketma-ket qadamlar
2. **Tugma nomi** — qalin

- Ro'yxat bandi

> Eslatma (sariq blok)
```

## Qoidalar

* **Menyu va tugma nomlarini KODDAN ko'chiring** (`admin.html`, `pos.html`,
  `returns.html` ...) — to'qima nom do'konchini adashtiradi. Nom o'zgarsa, shu
  yerni ham yangilang.
* Faqat do'kon (store/supermarket) oqimi yoziladi — to'rt jonli do'kon shu turda.
* HTML yozilmaydi: `build_help.py` hammasini ekranlaydi (`<` → `&lt;`).
