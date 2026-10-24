# Ombor

## Yangi mahsulot qanday qo'shaman?
Kalit: mahsulot qo'shish, yangi tovar, tovar kiritish, shtrix-kod, narx qo'yish

1. Admin panel → **Mahsulotlar**.
2. Yuqori o'ngdagi **Mahsulot qo'shish** tugmasini bosing.
3. To'ldiring:
   - **Nomi** (majburiy)
   - **Narxi (UZS)** — sotish narxi (majburiy)
   - **Tan narx (UZS)** — kelish narxi; foyda shundan hisoblanadi
   - **O'lchov birligi** — Dona, Kg, Gramm, Litr, Metr ...
   - **Kategoriya**
   - **Shtrix-kod** — kursorni shu maydonga qo'yib skanerlang
4. Pachkada ham sotilsa — **Pachka bilan sotish (ixtiyoriy)** ni to'ldiring.
5. **Saqlash**.

Mahsulot qo'shilgach qoldig'i 0 bo'ladi — keyin **kirim** qiling (keyingi savol).

> **Diqqat:** shtrix-kodni faqat **Shtrix-kod** maydoniga skanerlang. Kursor **Narxi** maydonida turganda skanerlasangiz, shtrix-kod raqami narxga qo'shilib ketadi (12 000 → 12000478...). Saqlashdan oldin narxni tekshiring.

## Kirim qanday kiritaman?
Kalit: kirim, prixod, tovar keldi, qoldiq qo'shish, omborga qo'shish, priyomka

1. Admin panel → **Ombor**.
2. Yuqoridagi **Kirim qilish** tugmasini bosing va mahsulotni tanlang — yoki mahsulot qatoridagi **+** tugmasini bosing.
3. **Kirim birligi**: **Dona** yoki **Pachka** (pachka sozlangan mahsulotda).
4. **Miqdor** ni yozing.
5. **Kelish narxi** ni yozing.
6. **Yetkazib beruvchi** — ixtiyoriy.
7. **Kirim qilish** ni bosing.

- Kiritilgan kirimlar: **Ombor** → **Kirim tarixi**.
- Bu oynadagi kirim firma oldidagi **qarzni yaratmaydi**. Tovarni firmadan nasiyaga olgan bo'lsangiz va firma qarzini yuritmoqchi bo'lsangiz — **Firmalar** → **Priyomka** bo'limidan kiriting.

## Qoldiq noto'g'ri — nima qilay?
Kalit: qoldiq xato, ombor noto'g'ri, minus qoldiq, sanash, inventarizatsiya, revizya, kamomad tovar

Avval sababini toping:

1. Admin panel → **Ombor** → mahsulotni qidiring.
2. **Kirim tarixi** va **Ombor hisoboti** da shu mahsulot harakatlarini ko'ring (kirim, sotuv, qaytish, hisobdan o'chirish).

Ko'p uchraydigan sabablar:

- Kirim kiritilmagan yoki ikki marta kiritilgan.
- Sotuvda **📦 Pachka** bosilgan — ombordan butun pachka ayrilgan.
- Vozvrat hali **Kutilmoqda** — tasdiqlanmaguncha tovar omborga qaytmaydi.
- Vozvratda **Brak** belgilangan — tovar omborga qaytmaydi (bu to'g'ri).

Tuzatish:

- Bitta mahsulot kam ko'rsatsa — **kirim** qiling; ko'p ko'rsatsa — **−** (Hisobdan o'chirish).
- Ko'p mahsulotni sanab chiqish kerak bo'lsa — **Ombor** → **Inventarizatsiya** → **+ Yangi inventarizatsiya** → har mahsulotga **Haqiqiy miqdor** ni yozing → **Tasdiqlash**. Farqlar omborga o'zi yoziladi va **Kamomad (minus)** / **Ortiqcha (plus)** ko'rinadi.

> Inventarizatsiya paytida sotuvni to'xtatish yaxshi — sanash va sotuv aralashsa farq noto'g'ri chiqadi.

## Hisobdan chiqarish qachon kerak?
Kalit: hisobdan chiqarish, hisobdan o'chirish, spisanie, buzildi, yo'qoldi, muddati o'tdi, o'zimiz ishlatdik

Tovar **sotilmasdan** ombordan ketganda:

- **Buzilgan / Yaroqsiz**
- **Yo'qolgan**
- **Ichki ishlatish** (do'konning o'zi ishlatdi)
- **Muddati o'tgan**
- **Boshqa**

Qanday qilinadi:

1. Admin panel → **Ombor** → mahsulot qatoridagi **−** tugmasi (yoki **Chiqim / Hisobdan o'chirish** sahifasi).
2. **Miqdor** ni yozing.
3. **Sabab** ni tanlang, kerak bo'lsa **Izoh** yozing.
4. **Hisobdan o'chirish** ni bosing.

Qachon **ishlatmaslik** kerak:

- Mijoz tovarni qaytardi → bu **vozvrat** (buzuq bo'lsa — **Brak** belgisi bilan).
- Sanashda farq chiqdi → **Inventarizatsiya** qulayroq.

## Etiketka qanday chop etaman?
Kalit: etiketka, yorliq, narx yorlig'i, shtrix-kod chop etish, label, cennik

1. Admin panel → **Etiketka**.
2. **Chop etish rejimi**: **🏷 Etiketka printeri** (TSPL · LAN) yoki **🖨 Oddiy printer** (A4 · brauzer).
3. **O'lcham**: Kichik 40×25mm, Yorliq 40×30mm, O'rta 58×40mm, Katta 72×50mm (yoki kenglik/balandlikni o'zingiz yozing).
4. **Barcode turi** — odatda **Code-128 (universal)**.
5. Mahsulotlarni belgilang: qidiruv, kategoriya yoki **Hammasini belgilash**. Har biriga nechta etiketka kerakligini yozing.
6. **🖨 Chop Etish**.

- Shtrix-kodi yo'q mahsulotlarga **🏷 Barchasiga kod berish** — do'kon ichki EAN-13 kodi beriladi.
- Etiketka printerini sozlash: Admin panel → **Chek Sozlama** → **Etiketka printeri** → **🏷 Sinov etiketkasi** bilan tekshiring.
