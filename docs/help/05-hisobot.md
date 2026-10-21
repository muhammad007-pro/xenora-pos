# Hisobot

## Bugun qancha sotdim?
Kalit: bugungi savdo, kassa, tushum, qancha sotildi, kunlik savdo

Admin panel → **Dashboard** → **Bugungi savdo** kartasi:

- **Naqd**, **Karta**, **Nasiya** — to'lov usullari bo'yicha;
- **Qaytarish** — bugun qaytarilgan summa (ayriladi);
- **Sof savdo** — qaytarishdan keyingi savdo;
- **Kassadan olingan** — kassadan olingan pul (inkassatsiya), faqat ma'lumot uchun.

Boshqa joylar:

- POS → **Sotuvlar tarixi** → **Bugun** — har bir chek va kun jami.
- Kassaga aynan qancha **pul** tushgani — smena hisobotida (**Smena** bo'limiga qarang).

## Foyda qayerda ko'rinadi?
Kalit: foyda, daromad, marja, sof foyda, yalpi foyda, pribil

- Tez ko'rish: **Dashboard** → **Bugungi foyda** kartasi: Sof savdo − Tan narx = **Yalpi foyda**, undan **Xarajat ulushi** ayrilib — **sof foyda**.
- Batafsil: Admin panel → **Moliya**. Yorliqlar:
  - **Foyda tahlili** — davr bo'yicha savdo, foyda, eng foydali va eng kam foydali mahsulotlar;
  - **Foyda marjasi** — mahsulotlar bo'yicha marja;
  - **Chek bo'yicha foyda** — har bir chekdan qancha foyda;
  - **Xarajatlar**.

> Foyda **Tan narx** dan hisoblanadi. Mahsulotga tan narx yozilmagan bo'lsa, foyda haqiqiydan katta ko'rinadi — mahsulotlarda **Tan narx (UZS)** ni to'ldiring.

## Dashboard va hisobot nega farq qiladi?
Kalit: farq, mos kelmaydi, boshqacha, z-hisobot farq, dashboard farq, raqamlar har xil

Ular har xil narsani sanaydi:

- **Dashboard → Bugungi savdo** — sotilgan tovar summasi. **Nasiya ham kiradi**, garchi pul hali kelmagan bo'lsa ham.
- **Smena / Z-hisobot** — kassaga tushgan **pul** (naqd, karta). Nasiya bu yerga kirmaydi.
- **Moliya** → **Foyda tahlili** → **Jami savdo** — chegirma va vozvrat ayirilgan summa.

Yana sabablar:

- **Vozvrat qaytarilgan kunda ayriladi.** Kecha sotilgan tovar bugun qaytsa — bugungi savdo kamayadi.
- **Davr har xil.** Bir joyda "Bugun", boshqasida "7 kun" tanlangan bo'lishi mumkin — sanalarni tekshiring.
- **Tungi savdo.** Yarim tundan keyingi savdo odatda keyingi kalendar kunga yoziladi. Kechasi ishlasangiz, "smena bo'yicha" hisobot kuni sozlamasi bor — yoqish uchun qo'ng'iroq qiling.

## Qaysi xodim qancha sotdi?
Kalit: xodim, xodimlar, sotuvchi, ishchi, kim sotdi, xodim savdosi, bonus, premiya, foiz, ish haqi

1. Admin panel → **Moliya** → **Xodimlar** yorlig'i.
2. Davrni tanlang: **Bugun**, **7 kun**, **30 kun** yoki ikkita sana → **Ko'rsatish**.
3. Jadvalda har xodim: **Chek** soni, **Savdo**, **Vozvrat**, **Sof savdo**.
4. Xodim qatorini bosing — kunlar bo'yicha ochiladi. Yana bossangiz yopiladi.

- **Savdo** — chegirma ayirilgan summa.
- **Vozvrat** qaytarilgan kunda, tovarni **sotgan** xodimdan ayriladi (vozvratni rasmiylashtirgan kassirdan emas).
- Jami **Sof savdo** — **Foyda tahlili** dagi savdo bilan bir xil.
- **Belgilanmagan** qatori — sotuvchisi noma'lum: chekka bog'lanmagan vozvrat yoki sotuvchisiz chek.

Xodimga foiz yoki mukofot hisoblamoqchi bo'lsangiz — **Sof savdo** (yoki **Alohida** ustuni) dan hisoblang. Dastur summani o'zi hisoblamaydi.

> **Hisobotlar** → **Xodimlar** yorlig'ida ham jadval bor, lekin u oddiy: vozvrat ayirilmaydi. Hisob-kitob uchun **Moliya** → **Xodimlar** dan foydalaning.

## Ma'lum kategoriya savdosini alohida ko'rish
Kalit: kategoriya, alohida, asosiy, kiyim, atir, kategoriya bo'yicha, ajratish, alohida hisob

Masalan, kiyim savdosini atir va boshqa tovarlardan alohida ko'rish:

1. Admin panel → **Moliya** → **Xodimlar**.
2. **⚙️ Alohida kategoriyalar** tugmasini bosing.
3. Kerakli kategoriyalarni belgilang. Ichidagi kichik kategoriyalar ham avtomatik kiradi.
4. **Saqlash**.

Endi jadvalda ikki ustun chiqadi: **Alohida** — belgilangan kategoriyalar savdosi, **Asosiy** — qolgani. Yuqorida ham shu ikki karta. Vozvrat ham tovar kategoriyasi bo'yicha o'z ustunidan ayriladi.

- Hech narsa belgilanmasa — bu ustunlar ko'rinmaydi.
- Butun do'kon bo'yicha kategoriyalar savdosi: **Moliya** → **Foyda tahlili** → **Kategoriya bo'yicha foyda**.

## Hamma savdo bitta xodimga yozilyapti
Kalit: hamma savdo bitta odamda, sotuvchi almashtirish, pin, qulf, xodim qo'shish, sotuvchi kirishi

Sotuv POS'ga **kim kirgan bo'lsa** o'shaning nomiga yoziladi. Hamma bitta login bilan ishlasa, hammasi bir odamga tushadi.

Har sotuvchiga o'z hisobi:

1. Admin panel → **Xodimlar** → **Xodim qo'shish**.
2. **Ism familiya**, **Parol**, **Rol** (masalan, Kassir) va **PIN kod** (4 raqam) ni yozing.
3. **Saqlash**.

Bitta kassada sotuvchilar almashganda:

1. POS tepasidagi qulf tugmasini bosing (unda hozirgi sotuvchi ismi yozilgan).
2. **Sotuvchi kirishi** oynasida o'z **PIN** kodingizni tering.
3. Shundan keyingi sotuvlar sizning nomingizga yoziladi.

> Admin panel → **Xodimlar** — xodim hisoblari. **Moliya** → **Xodimlar** — ularning savdosi. Ikkalasi boshqa-boshqa joy.

## Xarajat qanday kiritaman?
Kalit: xarajat, rasxod, ijara, oylik, maosh, kommunal, svet, gaz

1. Admin panel → **Moliya** → **Xarajatlar** yorlig'i.
2. Turini tanlang: **Ijara**, **Oylik**, **Kommunal**, **Xomashyo/jihoz**, **Marketing**, **Boshqa**.
3. **Nomi** (masalan: Yanvar ijara), **Summa (UZS)** va sanani yozing.
4. Har oy takrorlansa — **🔁 Takroriy** ni belgilang va oyning nechanchi kuni ekanini yozing.
5. Oylik ijara yoki maosh bo'lsa — **🗓 Kunlarga taqsimla** ni belgilang: summa kunlarga bo'linadi, bir kun sun'iy minusga tushmaydi.
6. **+ Qo'shish**.

- Xarajat sof foydadan ayriladi.
- Xarajat pulini kassadan olgan bo'lsangiz, uni smenada **Kassa harakati** sifatida ham yozing — aks holda smena yopilganda kamomad chiqadi.

## Sana oralig'ini qanday tanlayman?
Kalit: sana, davr, oraliq, oy, hafta, kecha, filter, kalendar

- **Moliya**: yuqoridagi **Bugun**, **7 kun**, **30 kun** tugmalari — yoki ikkita sana maydoniga boshlanish va tugash sanasini yozing va **Ko'rsatish** ni bosing.
- **Sotuvlar tarixi** (POS va Admin): **Bugun**, **Kecha**, **7 kun**, **30 kun** yoki ikkita sana.
- **Qaytarish Jurnali**: sana maydonlari va **Tozalash**.

Tanlangan davr ekranda yoziladi — raqamlarni solishtirishdan oldin davr bir xil ekanini tekshiring.
