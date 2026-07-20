# vendor/ — SumatraPDF (chek PDF print uchun)

Chek RASTER print (Chrome kabi) uchun **SumatraPDF** kerak. Bu yerga qo'ying:

    electron/vendor/SumatraPDF.exe

## Qanday olish
1. https://www.sumatrapdfreader.org/download-free-pdf-viewer → **64-bit portable** (`.exe`) yuklab oling.
2. Faylni **`SumatraPDF.exe`** deb nomlang (versiya raqamsiz).
3. Shu `electron/vendor/` papkasiga joylang.

## Nega
- `main.js` chekни `printToPDF` bilan PDF qiladi (Chromium engine — Chrome "Save as PDF" kabi).
- So'ng SumatraPDF `-print-to "XP-58C" -silent` bilan PDF'ни LOKAL printerga **raster** qilib yuboradi.
- PDF'da "matn baytlari" yo'q → termal drayver CP437 talqin qilolmaydi → krakozyabra IMKONSIZ.

## Bo'lmasa
SumatraPDF.exe topilmasa — `main.js` avtomatik `webContents.print` (GDI) fallback'ga tushadi
(regressiya yo'q, lekin krakozyabra qaytishi mumkin). Toza chek uchun SumatraPDF.exe SHART.

Build (`electron-builder`) — `extraResources` orqali `SumatraPDF.exe` ni `resources/` ga nusxalaydi.
