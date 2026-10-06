# FISKAL CHEK (OFD) — holat, xavf va ulash tartibi

## 1. NIMA BO'LGAN (2026-10-06, huquqiy xavf)

Prod `backend/config/fiscal.json` quyidagicha edi:

```json
{"enabled": true, "mode": "mock", "operator": "soliquz",
 "inn": "123456789", "kassa_id": "TEST001"}
```

`tenant_settings` jadvalida `config_name='fiscal'` yozuvi **birortasi ham
yo'q** edi, ya'ni **beshta jonli do'kon ham** shu faylga tushardi
(`core/tenant_config.py` — tenant yozuvi bo'lmasa global fayl standart
bo'lib qoladi).

`enabled: true` → `routers/payment.py` har to'lovda `send_to_ofd()` ni
chaqiradi. `mode: "mock"` → `services/ofd_service.py:_send_mock()`:

- **OFD ga hech narsa yuborilmaydi** (tarmoqqa chiqish yo'q);
- fiskal raqam = `int(time.time() * 1000) % 10_000_000` — vaqtdan olingan
  psevdo-son (shu sababli chekda "№ 7114357" kabi 7 xonali raqam);
- `sign` — deterministik soxta satr, kriptografiya emas;
- QR = `https://consumer.invoice.uz/check?...&fn=TEST001&i=<soxta>&fp=<soxta>`
  — **haqiqiy soliq portali manzili**, lekin yasama parametrlar bilan.
  Mijoz yoki tekshiruvchi skanerlasa haqiqiy chek **chiqmaydi**.
- `tax_id` sifatida chekka test INN **`123456789`** bosilardi — do'konning
  haqiqiy INN'i emas.

**Oqibat:** bazada **3323 ta** buyurtmada soxta `fiscal_number`
(26 FAZZA 1296, 27 BARAKA 1728, 28 NICE 263, 5 lux 18, 20 eco 16, 30 MANHATTAN 2).

### Nega faqat 1001 BARAKA da ko'rinardi

`/orders/{id}/receipt` fiskal blokni `ReceiptSettings.qr_enabled` bilan
to'sardi, u esa prodda **faqat tenant 27 (1001 BARAKA)** da `true`.
POS sotuv cheki esa umuman lokal quriladi (`pos.js: showReceiptLocal` →
`fiscal_number: null` qattiq yozilgan), shuning uchun sotuv chekida QR
yo'q, **reprintda bor** edi.

⚠️ Lekin ESC/POS yo'li (`routers/order.py` → `escpos_print_receipt`) faqat
`enabled` ni tekshirardi — `qr_enabled` ni **emas**. Ya'ni u yo'l
**beshta do'konda ham** soxta raqam + TEST INN bosib chiqarishi mumkin edi.

## 2. QANDAY TO'XTATILDI

### a) Yagona qo'riqchi — `services/ofd_service.py: is_fiscal_live()`

```python
is_fiscal_live(cfg)  # True faqat: enabled=True VA mode=="live"
```

Ikki chek yo'li ham (`/orders/{id}/receipt` va ESC/POS) **shu bitta**
funksiyani chaqiradi. Ilgari ikki xil shart edi va aynan o'sha ajralish
xatoni yashirdi.

### b) QAROR: yashirish, "TEST" deb belgilash EMAS

`mode != "live"` bo'lsa chekda fiskal raqam ham, QR ham **umuman
chiqmaydi**. Muqobil variant ("TEST — fiskal emas" yorlig'i bilan
ko'rsatish) **rad etildi**:

1. Xavf — **QR ning o'zi**. U `consumer.invoice.uz` manzilini kodlaydi;
   o'zbekcha yorliq mijozni skanerlashdan to'xtatmaydi.
2. POS sotuv cheki allaqachon fiskal elementsiz. Yashirish reprintni
   do'konlar kunda ko'radigan formatga **qaytaradi** — "chek formati
   o'zgarmasin" talabiga mos.
3. Mijozga "TEST" deb chek berish — u so'ramagan narsa, xavfni kamaytirmaydi.
4. Operatorga ko'rinish kerak → u **chekda emas, API'da**:
   `/orders/{id}/receipt` endi `fiscal_mode`, `fiscal_configured`,
   `fiscal_suppressed` qaytaradi (`fiscal_suppressed: true` = raqam bazada
   bor, lekin rejim `live` emasligi uchun to'sildi).

### c) Yangi soxta yozuv ham yozilmaydi

`backend/config/fiscal.json` standarti **`enabled: false`** ga o'tdi va
test qiymatlari (`inn: "123456789"`, `kassa_id: "TEST001"`) tozalandi.
`send_to_ofd()` endi "Fiskal integratsiya o'chirilgan" deb qaytadi →
`order.fiscal_number` **to'ldirilmaydi**.

⚠️ **Bazadagi mavjud 3323 yozuvga TEGILMAGAN** — o'chirish/tuzatish
alohida qaror (audit izi). Ular endi chekka chiqmaydi.

## 3. HAQIQIY OFD ULASH (1001 BARAKA uchun)

Tenant bo'yicha sozlash **allaqachon mavjud** — yangi kod kerak emas:

| | |
|---|---|
| O'qish | `GET /api/v1/settings/fiscal` (`manage_settings` ruxsati) |
| Yozish | `PATCH /api/v1/settings/fiscal` |
| Saqlanadi | `tenant_settings` (`config_name='fiscal'`, tenant bo'yicha) |

Global fayl faqat **tenant yozuvi bo'lmaganda** standart bo'lib qoladi.

### Kerakli qiymatlar

```jsonc
{
  "enabled":  true,        // yoqish
  "mode":     "live",      // ⚠️ "mock" bo'lsa chekda hech narsa chiqmaydi
  "operator": "soliquz",   // yoki "soliqpro"
  "inn":      "<do'konning HAQIQIY INN/STIR>",
  "kassa_id": "<OFD bergan terminal/kassa ID>",
  "api_key":  "<OFD API tokeni>",
  "endpoint": "<ixtiyoriy — operator manzilini almashtirish>"
}
```

Namuna (super-admin yoki do'kon admini tokeni bilan):

```bash
curl -X PATCH https://app.xenora.uz/api/v1/settings/fiscal \
  -H "Authorization: Bearer <token>" -H 'Content-Type: application/json' \
  -d '{"enabled":true,"mode":"live","operator":"soliquz",
       "inn":"3xxxxxxxx","kassa_id":"KASSA-01","api_key":"<token>"}'
```

### Ulashdan OLDIN kerak bo'ladigan narsalar (texnik emas)

1. OFD operatori bilan shartnoma (soliq.uz yoki SoliqPro) va ro'yxatdan
   o'tgan **fiskal modul / kassa apparati**.
2. Do'konning haqiqiy **INN/STIR** va operator bergan **kassa_id** + **api_key**.
3. `receipt_settings.tax_id` ni to'ldirish (hozir beshta do'konda ham **bo'sh**)
   — chekda INN shu maydondan olinadi, bo'lmasa fiskal cfg `inn` dan.
4. `ReceiptSettings.qr_enabled = true` (BARAKA'da allaqachon `true`).

### Ulagandan keyin tekshirish

```bash
# 1) rejim live bo'ldimi
curl -s .../settings/fiscal -H "Authorization: Bearer <t>" | jq '.mode,.enabled'
# 2) sinov sotuvidan keyin
curl -s .../orders/<id>/receipt -H "Authorization: Bearer <t>" \
  | jq '{fiscal_mode,fiscal_configured,fiscal_suppressed,qr_enabled,fiscal_number}'
#    kutilgan: fiscal_mode="live", qr_enabled=true, fiscal_number=<OFD raqami>
# 3) QR ni telefonda skanerlab, consumer.invoice.uz da chek chiqishini ko'r
```

⚠️ **3-qadam majburiy.** `mode: "live"` bo'lsa-yu OFD rad etsa,
`payment.py` to'lovni buzmaydi — faqat `log.warning("[OFD] ... yuborilmadi")`
yozadi va `fiscal_number` bo'sh qoladi. Ya'ni chek fiskal **bo'lmaydi**,
lekin sotuv o'tadi. Shu sababli loglarni ham kuzatish kerak.

## 4. HOZIRGI HOLAT — qaysi chek rasmiy

**Hech biri.** Soliq nuqtai nazaridan fiskal chek ro'yxatdan o'tgan fiskal
modul / OFD operatoridan kelishi kerak. `mock` rejimda XENORA hech qanday
rasmiy chek bermaydi — na POS sotuvida, na reprintda.

Bu tuzatishdan keyin chek **ochiq-oydin nofiskal** bo'ldi (soxta QR yo'q).
Rasmiy chek faqat 3-bo'lim bajarilgandan keyin paydo bo'ladi.
