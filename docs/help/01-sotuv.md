# Sotuv

## Kg/metr mahsulotni qanday sotaman?
Kalit: og'irlik, tarozi, kilo, gramm, litr, uzunlik, metr, sm, kasr, yarim

Mahsulotning o'lchov birligi **Kg**, **Gramm**, **Litr**, **Metr** yoki **Sm** bo'lsa, POS'da uni bosganda **Og'irlik kiriting** oynasi ochiladi.

1. POS'da mahsulotni bosing yoki shtrix-kodini skanerlang.
2. Oynada miqdorni yozing: masalan `0.5` — yarim kilo (yoki yarim metr). Yoki tayyor tugmalardan birini bosing (**100g**, **250g**, **1 kg**, metrda **0.5 m**, **1 m** ...).
3. **Jami narx** to'g'riligini tekshiring.
4. **Savatga qo'shish** ni bosing.

Mijoz "5 000 so'mlik bering" desa — oynadagi **Summa** tugmasini bosing va summani yozing: og'irlik o'zi hisoblanadi.

- Miqdor 3 xonagacha yoziladi (0.001).
- Elektron tarozi ulangan bo'lsa — oynadagi **⚖️ Tarozi** tugmasi.

> Mahsulot dona bo'lib sotilyaptimi, kg emasmi? Admin panel → **Mahsulotlar** → mahsulotni tahrirlang → **O'lchov birligi** ni to'g'rilang.

## Pachka va dona farqi nima?
Kalit: pachka, blok, quti, upakovka, dona, qop

Mahsulotga pachka sozlangan bo'lsa (pachka narxi + pachkadagi dona soni), POS **Qanday sotiladi?** deb so'raydi:

- chapda — **Dona** (kg/metr mahsulotda o'sha birlik), dona narxi bilan;
- o'ngda — **📦 Pachka**, pachka narxi bilan. Tugma ostida **Ombordan N dona ayriladi** deb yoziladi.

Shoshilib **Pachka** ni bossangiz, ombordan butun pachka (masalan 10 dona) ayriladi. Kerakli tugmani bosing. Qoldiq pachkaga yetmasa — sariq ogohlantirish chiqadi, lekin sotuv to'xtatilmaydi.

Pachkani sozlash:

1. Admin panel → **Mahsulotlar** → mahsulotni oching.
2. **Pachka bilan sotish (ixtiyoriy)** bo'limida **Pachka narxi** va **Pachkadagi dona** (kamida 2) ni yozing.
3. Yuqoridagi **Narxi** — bu **bitta DONA** narxi.
4. **Saqlash**.

Ko'p mahsulotga birdaniga: **Mahsulotlar** ro'yxatida mahsulotlarni belgilang → **📦 Pachka sozlash**.

## Chegirma qanday beraman?
Kalit: skidka, chegirma, foiz, arzonlashtirish, kelishuv, narx tushirish

Butun chekka chegirma:

1. Savatga mahsulotlarni qo'shing.
2. Savat ostidagi **Chegirma** tugmasini bosing.
3. **Foiz (%)** yoki **Summa (UZS)** ni tanlang.
4. Qiymatni yozing yoki tayyor tugmani bosing (**5%** ... **50%**).
5. **Qo'llash** — savatda **Chegirma:** qatori chiqadi.

Chegirmani olib tashlash: yana **Chegirma** → `0` → **Qo'llash**.

Bitta mahsulot narxini kelishish: savatdagi qatorning **narxini** bosing, yangi narxni yozing va **Enter** bosing. Savat ostida **Narx kelishuvi:** qatori chiqadi.

- Mijozga doimiy chegirma (%) yozilgan bo'lsa, mijoz tanlanganda u o'zi qo'llanadi. Qo'lda bergan chegirmangiz ustun turadi — ikkalasi qo'shilmaydi.
- Aksiyalar (Admin panel → **Aksiyalar**, **Chegirmalar**) savatda o'zi hisoblanadi: **Aksiya chegirma:** qatori.

## Nasiyaga qanday sotaman?
Kalit: qarz, nasiya, qarzga, kredit, keyin to'laydi

1. Savatni to'ldiring.
2. **Mijoz tanlang** tugmasini bosing va mijozni ism yoki telefon bo'yicha toping.
3. Mijoz yo'q bo'lsa — **+ Yangi mijoz** → **Ism**, **Telefon** → **Qo'shish va tanlash**.
4. **To'lov (F4)** → **Nasiya** → **To'lovni amalga oshirish**.

- Mijoz tanlanmasa "Nasiya uchun mijozni tanlang" xatosi chiqadi — nasiya faqat mijoz nomiga yoziladi.
- Qarz Admin panel → **Nasiya / Qarz** ro'yxatida ko'rinadi.

> **Nasiya** tugmasi ko'rinmasa — do'koningizda nasiya funksiyasi yoqilmagan. Qo'ng'iroq qiling.

## Aralash to'lov (naqd + nasiya)
Kalit: aralash, bo'lib to'lash, qisman, naqd va karta, naqd va nasiya, split

Mijoz summaning bir qismini naqd (yoki karta), qolganini nasiyaga olsa:

1. Kerak bo'lsa avval **Mijoz tanlang** (nasiya ulushi bo'lsa — shart).
2. **To'lov (F4)** ni bosing.
3. **Aralash to'lov (bir necha usul)** katagini belgilang.
4. **Naqd**, **Karta/term.**, **Nasiya** maydonlariga summalarni yozing.
5. Pastdagi **Qolgan:** 0 bo'lishi kerak.
6. **To'lovni amalga oshirish**.

- Naqd ortiqcha berilsa — **Qaytim (naqd)** ko'rsatiladi. Karta va nasiya ortiqcha yozilmaydi.
- Aralash to'lov faqat internet bor paytda ishlaydi.
- Nasiya qismi mijozning qarziga yoziladi, naqd qismi smena kassasiga tushadi.
