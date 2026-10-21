/* AVTO-YARATILGAN — QO'LDA TAHRIRLAMANG.
 * Manba: docs/help/*.md   Yaratish: py scripts/build_help.py
 * Tekshiruv: py scripts/build_help.py --check (test_help_center.mjs ham)
 */
window.XENORA_HELP = {
 "sections": [
  {
   "id": "sotuv",
   "title": "Sotuv",
   "items": [
    {
     "id": "sotuv-1",
     "q": "Kg/metr mahsulotni qanday sotaman?",
     "html": "<p>Mahsulotning o'lchov birligi <b>Kg</b>, <b>Gramm</b>, <b>Litr</b>, <b>Metr</b> yoki <b>Sm</b> bo'lsa, POS'da uni bosganda <b>Og'irlik kiriting</b> oynasi ochiladi.</p><ol><li>POS'da mahsulotni bosing yoki shtrix-kodini skanerlang.</li><li>Oynada miqdorni yozing: masalan <code>0.5</code> — yarim kilo (yoki yarim metr). Yoki tayyor tugmalardan birini bosing (<b>100g</b>, <b>250g</b>, <b>1 kg</b>, metrda <b>0.5 m</b>, <b>1 m</b> ...).</li><li><b>Jami narx</b> to'g'riligini tekshiring.</li><li><b>Savatga qo'shish</b> ni bosing.</li></ol><p>Mijoz \"5 000 so'mlik bering\" desa — oynadagi <b>Summa</b> tugmasini bosing va summani yozing: og'irlik o'zi hisoblanadi.</p><ul><li>Miqdor 3 xonagacha yoziladi (0.001).</li><li>Elektron tarozi ulangan bo'lsa — oynadagi <b>⚖️ Tarozi</b> tugmasi.</li></ul><div class=\"xh-note\">Mahsulot dona bo'lib sotilyaptimi, kg emasmi? Admin panel → <b>Mahsulotlar</b> → mahsulotni tahrirlang → <b>O'lchov birligi</b> ni to'g'rilang.</div>",
     "text": "Mahsulotning o'lchov birligi Kg, Gramm, Litr, Metr yoki Sm bo'lsa, POS'da uni bosganda Og'irlik kiriting oynasi ochiladi. POS'da mahsulotni bosing yoki shtrix-kodini skanerlang. Oynada miqdorni yozing: masalan 0.5 — yarim kilo (yoki yarim metr). Yoki tayyor tugmalardan birini bosing (100g, 250g, 1 kg, metrda 0.5 m, 1 m ...). Jami narx to'g'riligini tekshiring. Savatga qo'shish ni bosing. Mijoz \"5 000 so'mlik bering\" desa — oynadagi Summa tugmasini bosing va summani yozing: og'irlik o'zi hisoblanadi. Miqdor 3 xonagacha yoziladi (0.001). Elektron tarozi ulangan bo'lsa — oynadagi ⚖️ Tarozi tugmasi. Mahsulot dona bo'lib sotilyaptimi, kg emasmi? Admin panel → Mahsulotlar → mahsulotni tahrirlang → O'lchov birligi ni to'g'rilang.",
     "keys": "og'irlik, tarozi, kilo, gramm, litr, uzunlik, metr, sm, kasr, yarim"
    },
    {
     "id": "sotuv-2",
     "q": "Pachka va dona farqi nima?",
     "html": "<p>Mahsulotga pachka sozlangan bo'lsa (pachka narxi + pachkadagi dona soni), POS <b>Qanday sotiladi?</b> deb so'raydi:</p><ul><li>chapda — <b>Dona</b> (kg/metr mahsulotda o'sha birlik), dona narxi bilan;</li><li>o'ngda — <b>📦 Pachka</b>, pachka narxi bilan. Tugma ostida <b>Ombordan N dona ayriladi</b> deb yoziladi.</li></ul><p>Shoshilib <b>Pachka</b> ni bossangiz, ombordan butun pachka (masalan 10 dona) ayriladi. Kerakli tugmani bosing. Qoldiq pachkaga yetmasa — sariq ogohlantirish chiqadi, lekin sotuv to'xtatilmaydi.</p><p>Pachkani sozlash:</p><ol><li>Admin panel → <b>Mahsulotlar</b> → mahsulotni oching.</li><li><b>Pachka bilan sotish (ixtiyoriy)</b> bo'limida <b>Pachka narxi</b> va <b>Pachkadagi dona</b> (kamida 2) ni yozing.</li><li>Yuqoridagi <b>Narxi</b> — bu <b>bitta DONA</b> narxi.</li><li><b>Saqlash</b>.</li></ol><p>Ko'p mahsulotga birdaniga: <b>Mahsulotlar</b> ro'yxatida mahsulotlarni belgilang → <b>📦 Pachka sozlash</b>.</p>",
     "text": "Mahsulotga pachka sozlangan bo'lsa (pachka narxi + pachkadagi dona soni), POS Qanday sotiladi? deb so'raydi: chapda — Dona (kg/metr mahsulotda o'sha birlik), dona narxi bilan; o'ngda — 📦 Pachka, pachka narxi bilan. Tugma ostida Ombordan N dona ayriladi deb yoziladi. Shoshilib Pachka ni bossangiz, ombordan butun pachka (masalan 10 dona) ayriladi. Kerakli tugmani bosing. Qoldiq pachkaga yetmasa — sariq ogohlantirish chiqadi, lekin sotuv to'xtatilmaydi. Pachkani sozlash: Admin panel → Mahsulotlar → mahsulotni oching. Pachka bilan sotish (ixtiyoriy) bo'limida Pachka narxi va Pachkadagi dona (kamida 2) ni yozing. Yuqoridagi Narxi — bu bitta DONA narxi. Saqlash. Ko'p mahsulotga birdaniga: Mahsulotlar ro'yxatida mahsulotlarni belgilang → 📦 Pachka sozlash.",
     "keys": "pachka, blok, quti, upakovka, dona, qop"
    },
    {
     "id": "sotuv-3",
     "q": "Chegirma qanday beraman?",
     "html": "<p>Butun chekka chegirma:</p><ol><li>Savatga mahsulotlarni qo'shing.</li><li>Savat ostidagi <b>Chegirma</b> tugmasini bosing.</li><li><b>Foiz (%)</b> yoki <b>Summa (UZS)</b> ni tanlang.</li><li>Qiymatni yozing yoki tayyor tugmani bosing (<b>5%</b> ... <b>50%</b>).</li><li><b>Qo'llash</b> — savatda <b>Chegirma:</b> qatori chiqadi.</li></ol><p>Chegirmani olib tashlash: yana <b>Chegirma</b> → <code>0</code> → <b>Qo'llash</b>.</p><p>Bitta mahsulot narxini kelishish: savatdagi qatorning <b>narxini</b> bosing, yangi narxni yozing va <b>Enter</b> bosing. Savat ostida <b>Narx kelishuvi:</b> qatori chiqadi.</p><ul><li>Mijozga doimiy chegirma (%) yozilgan bo'lsa, mijoz tanlanganda u o'zi qo'llanadi. Qo'lda bergan chegirmangiz ustun turadi — ikkalasi qo'shilmaydi.</li><li>Aksiyalar (Admin panel → <b>Aksiyalar</b>, <b>Chegirmalar</b>) savatda o'zi hisoblanadi: <b>Aksiya chegirma:</b> qatori.</li></ul>",
     "text": "Butun chekka chegirma: Savatga mahsulotlarni qo'shing. Savat ostidagi Chegirma tugmasini bosing. Foiz (%) yoki Summa (UZS) ni tanlang. Qiymatni yozing yoki tayyor tugmani bosing (5% ... 50%). Qo'llash — savatda Chegirma: qatori chiqadi. Chegirmani olib tashlash: yana Chegirma → 0 → Qo'llash. Bitta mahsulot narxini kelishish: savatdagi qatorning narxini bosing, yangi narxni yozing va Enter bosing. Savat ostida Narx kelishuvi: qatori chiqadi. Mijozga doimiy chegirma (%) yozilgan bo'lsa, mijoz tanlanganda u o'zi qo'llanadi. Qo'lda bergan chegirmangiz ustun turadi — ikkalasi qo'shilmaydi. Aksiyalar (Admin panel → Aksiyalar, Chegirmalar) savatda o'zi hisoblanadi: Aksiya chegirma: qatori.",
     "keys": "skidka, chegirma, foiz, arzonlashtirish, kelishuv, narx tushirish"
    },
    {
     "id": "sotuv-4",
     "q": "Nasiyaga qanday sotaman?",
     "html": "<ol><li>Savatni to'ldiring.</li><li><b>Mijoz tanlang</b> tugmasini bosing va mijozni ism yoki telefon bo'yicha toping.</li><li>Mijoz yo'q bo'lsa — <b>+ Yangi mijoz</b> → <b>Ism</b>, <b>Telefon</b> → <b>Qo'shish va tanlash</b>.</li><li><b>To'lov (F4)</b> → <b>Nasiya</b> → <b>To'lovni amalga oshirish</b>.</li></ol><ul><li>Mijoz tanlanmasa \"Nasiya uchun mijozni tanlang\" xatosi chiqadi — nasiya faqat mijoz nomiga yoziladi.</li><li>Qarz Admin panel → <b>Nasiya / Qarz</b> ro'yxatida ko'rinadi.</li></ul><div class=\"xh-note\"><b>Nasiya</b> tugmasi ko'rinmasa — do'koningizda nasiya funksiyasi yoqilmagan. Qo'ng'iroq qiling.</div>",
     "text": "Savatni to'ldiring. Mijoz tanlang tugmasini bosing va mijozni ism yoki telefon bo'yicha toping. Mijoz yo'q bo'lsa — + Yangi mijoz → Ism, Telefon → Qo'shish va tanlash. To'lov (F4) → Nasiya → To'lovni amalga oshirish. Mijoz tanlanmasa \"Nasiya uchun mijozni tanlang\" xatosi chiqadi — nasiya faqat mijoz nomiga yoziladi. Qarz Admin panel → Nasiya / Qarz ro'yxatida ko'rinadi. Nasiya tugmasi ko'rinmasa — do'koningizda nasiya funksiyasi yoqilmagan. Qo'ng'iroq qiling.",
     "keys": "qarz, nasiya, qarzga, kredit, keyin to'laydi"
    },
    {
     "id": "sotuv-5",
     "q": "Aralash to'lov (naqd + nasiya)",
     "html": "<p>Mijoz summaning bir qismini naqd (yoki karta), qolganini nasiyaga olsa:</p><ol><li>Kerak bo'lsa avval <b>Mijoz tanlang</b> (nasiya ulushi bo'lsa — shart).</li><li><b>To'lov (F4)</b> ni bosing.</li><li><b>Aralash to'lov (bir necha usul)</b> katagini belgilang.</li><li><b>Naqd</b>, <b>Karta/term.</b>, <b>Nasiya</b> maydonlariga summalarni yozing.</li><li>Pastdagi <b>Qolgan:</b> 0 bo'lishi kerak.</li><li><b>To'lovni amalga oshirish</b>.</li></ol><ul><li>Naqd ortiqcha berilsa — <b>Qaytim (naqd)</b> ko'rsatiladi. Karta va nasiya ortiqcha yozilmaydi.</li><li>Aralash to'lov faqat internet bor paytda ishlaydi.</li><li>Nasiya qismi mijozning qarziga yoziladi, naqd qismi smena kassasiga tushadi.</li></ul>",
     "text": "Mijoz summaning bir qismini naqd (yoki karta), qolganini nasiyaga olsa: Kerak bo'lsa avval Mijoz tanlang (nasiya ulushi bo'lsa — shart). To'lov (F4) ni bosing. Aralash to'lov (bir necha usul) katagini belgilang. Naqd, Karta/term., Nasiya maydonlariga summalarni yozing. Pastdagi Qolgan: 0 bo'lishi kerak. To'lovni amalga oshirish. Naqd ortiqcha berilsa — Qaytim (naqd) ko'rsatiladi. Karta va nasiya ortiqcha yozilmaydi. Aralash to'lov faqat internet bor paytda ishlaydi. Nasiya qismi mijozning qarziga yoziladi, naqd qismi smena kassasiga tushadi.",
     "keys": "aralash, bo'lib to'lash, qisman, naqd va karta, naqd va nasiya, split"
    }
   ]
  },
  {
   "id": "qaytarish",
   "title": "Qaytarish",
   "items": [
    {
     "id": "qaytarish-1",
     "q": "Vozvrat qanday qilinadi?",
     "html": "<ol><li>POS chap menyusida <b>Qaytarish</b> ni bosing — <b>Qaytarish Jurnali</b> ochiladi.</li><li><b>+ Yangi qaytarish</b> ni bosing.</li><li><b>Chek raqami</b> maydoniga chekdagi shtrix-kodni skanerlang yoki raqamni yozib <b>Topish</b> ni bosing. Chek yo'q bo'lsa — <b>📋 Ro'yxatdan</b> tanlang.</li><li>Sotuvdagi mahsulotlar va narxlar o'zi chiqadi. Har qatorga qaytariladigan <b>miqdorni</b> yozing. Pul bo'yicha qaytarish kerak bo'lsa — qatordagi <b>Summa</b> rejimini tanlang.</li><li><b>Sabab</b> ni tanlang: Buzuq, Yoqmadi, Muddati o'tgan, Noto'g'ri tovar, Boshqa.</li><li><b>Qaytarish usuli</b>: Naqd pul, Karta yoki Balansga.</li><li><b>Saqlash</b> — vozvrat <b>⏳ Kutilmoqda</b> holatida yoziladi.</li><li>Administrator yoki menejer uni tasdiqlaydi (pastdagi \"Nega tasdiqlash kerak\" savoliga qarang).</li></ol><ul><li>Sotilganidan ko'p qaytarib bo'lmaydi — dastur to'xtatadi.</li><li>Nasiyaga sotilgan tovarni faqat <b>Balansga</b> qaytarish mumkin: pul berilmaydi, mijozning qarzi kamayadi.</li><li>Chekni topmasdan \"qo'lda kiritish\" ham bor, lekin unda miqdor tekshirilmaydi — iloji boricha chek bilan qiling.</li></ul>",
     "text": "POS chap menyusida Qaytarish ni bosing — Qaytarish Jurnali ochiladi. + Yangi qaytarish ni bosing. Chek raqami maydoniga chekdagi shtrix-kodni skanerlang yoki raqamni yozib Topish ni bosing. Chek yo'q bo'lsa — 📋 Ro'yxatdan tanlang. Sotuvdagi mahsulotlar va narxlar o'zi chiqadi. Har qatorga qaytariladigan miqdorni yozing. Pul bo'yicha qaytarish kerak bo'lsa — qatordagi Summa rejimini tanlang. Sabab ni tanlang: Buzuq, Yoqmadi, Muddati o'tgan, Noto'g'ri tovar, Boshqa. Qaytarish usuli: Naqd pul, Karta yoki Balansga. Saqlash — vozvrat ⏳ Kutilmoqda holatida yoziladi. Administrator yoki menejer uni tasdiqlaydi (pastdagi \"Nega tasdiqlash kerak\" savoliga qarang). Sotilganidan ko'p qaytarib bo'lmaydi — dastur to'xtatadi. Nasiyaga sotilgan tovarni faqat Balansga qaytarish mumkin: pul berilmaydi, mijozning qarzi kamayadi. Chekni topmasdan \"qo'lda kiritish\" ham bor, lekin unda miqdor tekshirilmaydi — iloji boricha chek bilan qiling.",
     "keys": "vozvrat, qaytarish, qaytardi, pulini qaytarish, tovar qaytdi"
    },
    {
     "id": "qaytarish-2",
     "q": "Chek raqamini qayerdan topaman?",
     "html": "<ul><li>Qog'oz chekning tepasida <b>Chek #...</b> deb yoziladi. Chekda shtrix-kod bo'lsa, uni skaner bilan to'g'ridan-to'g'ri <b>Chek raqami</b> maydoniga o'qiting.</li><li>Chek yo'qolgan bo'lsa: vozvrat oynasida <b>📋 Ro'yxatdan</b> ni bosing va chek raqami, summa yoki mijoz ismi bo'yicha qidiring.</li><li>POS chap menyusidagi <b>Sotuvlar tarixi</b> da ham barcha cheklar bor (<b>Bugun</b>, <b>Kecha</b>, <b>7 kun</b>, <b>30 kun</b> yoki sanalar bo'yicha).</li><li>Admin panelda: <b>Sotuvlar tarixi</b> → <b>Chek №</b> ustuni.</li></ul>",
     "text": "Qog'oz chekning tepasida Chek #... deb yoziladi. Chekda shtrix-kod bo'lsa, uni skaner bilan to'g'ridan-to'g'ri Chek raqami maydoniga o'qiting. Chek yo'qolgan bo'lsa: vozvrat oynasida 📋 Ro'yxatdan ni bosing va chek raqami, summa yoki mijoz ismi bo'yicha qidiring. POS chap menyusidagi Sotuvlar tarixi da ham barcha cheklar bor (Bugun, Kecha, 7 kun, 30 kun yoki sanalar bo'yicha). Admin panelda: Sotuvlar tarixi → Chek № ustuni.",
     "keys": "chek raqami, chek nomeri, chek yo'q, chek yo'qolgan, shtrix-kod chekda"
    },
    {
     "id": "qaytarish-3",
     "q": "Nega \"tasdiqlash kerak\" deydi?",
     "html": "<p>Har bir vozvrat avval <b>Kutilmoqda</b> holatida saqlanadi. Pul va tovar faqat <b>tasdiqlangandan keyin</b> harakatlanadi — bu kassada yolg'on vozvratdan himoya (\"ikkinchi ko'z\").</p><p>Kim tasdiqlaydi: <b>administrator yoki menejer</b>. Kassirda bu huquq yo'q — u bossa \"Vozvratni tasdiqlash huquqi yo'q\" degan xabar chiqadi, vozvrat esa Kutilmoqda bo'lib qoladi.</p><p>Tasdiqlash:</p><ol><li>POS → <b>Qaytarish</b> (Qaytarish Jurnali).</li><li>Holat filtridan <b>Kutilmoqda</b> ni tanlang.</li><li>Kerakli qatorda <b>Ko'rish</b> ni bosing.</li><li>Ma'lumotni tekshiring va <b>✓ Tasdiqlash</b> (yoki <b>✗ Rad etish</b>) ni bosing.</li></ol><ul><li>Tasdiqlanganda tovar omborga qaytadi (brak qatorlardan tashqari).</li><li><b>Kim tasdiqladi</b> ustunida ⚠ belgisi — vozvratni yozgan odamning o'zi tasdiqlagan.</li><li>Sariq ogohlantirish — vozvrat chekka bog'lanmagan (qo'lda kiritilgan). Tasdiqlashdan oldin chekni tekshiring.</li></ul>",
     "text": "Har bir vozvrat avval Kutilmoqda holatida saqlanadi. Pul va tovar faqat tasdiqlangandan keyin harakatlanadi — bu kassada yolg'on vozvratdan himoya (\"ikkinchi ko'z\"). Kim tasdiqlaydi: administrator yoki menejer. Kassirda bu huquq yo'q — u bossa \"Vozvratni tasdiqlash huquqi yo'q\" degan xabar chiqadi, vozvrat esa Kutilmoqda bo'lib qoladi. Tasdiqlash: POS → Qaytarish (Qaytarish Jurnali). Holat filtridan Kutilmoqda ni tanlang. Kerakli qatorda Ko'rish ni bosing. Ma'lumotni tekshiring va ✓ Tasdiqlash (yoki ✗ Rad etish) ni bosing. Tasdiqlanganda tovar omborga qaytadi (brak qatorlardan tashqari). Kim tasdiqladi ustunida ⚠ belgisi — vozvratni yozgan odamning o'zi tasdiqlagan. Sariq ogohlantirish — vozvrat chekka bog'lanmagan (qo'lda kiritilgan). Tasdiqlashdan oldin chekni tekshiring.",
     "keys": "tasdiqlash, kutilmoqda, tasdiqlanmadi, huquq yo'q, ikkinchi ko'z, rad etish"
    },
    {
     "id": "qaytarish-4",
     "q": "Brak tovarni qanday qaytaraman?",
     "html": "<p>Mijoz buzuq tovarni qaytardi va u qayta sotilmaydi:</p><ol><li>Odatdagidek vozvrat qiling (chek raqami → <b>Topish</b>).</li><li>Mahsulot qatoridagi <b>Brak</b> katagini belgilang — bu tovar omborga <b>qaytmaydi</b>.</li><li><b>Sabab</b>: <b>Buzuq</b>.</li><li><b>Saqlash</b>, keyin tasdiqlang.</li></ol><p>Mijozga pul qaytariladi, ombor qoldig'i esa ko'paymaydi.</p><div class=\"xh-note\">Tovar sotilmagan, omborning o'zida buzilgan bo'lsa — bu vozvrat emas. <b>Ombor</b> bo'limidagi \"Hisobdan chiqarish qachon kerak\" savoliga qarang.</div>",
     "text": "Mijoz buzuq tovarni qaytardi va u qayta sotilmaydi: Odatdagidek vozvrat qiling (chek raqami → Topish). Mahsulot qatoridagi Brak katagini belgilang — bu tovar omborga qaytmaydi. Sabab: Buzuq. Saqlash, keyin tasdiqlang. Mijozga pul qaytariladi, ombor qoldig'i esa ko'paymaydi. Tovar sotilmagan, omborning o'zida buzilgan bo'lsa — bu vozvrat emas. Ombor bo'limidagi \"Hisobdan chiqarish qachon kerak\" savoliga qarang.",
     "keys": "brak, buzuq, yaroqsiz, singan, omborga qaytmasin, defekt"
    }
   ]
  },
  {
   "id": "printer",
   "title": "Printer",
   "items": [
    {
     "id": "printer-1",
     "q": "Chek chiqmayapti",
     "html": "<p>Avval ekrandagi xabarni o'qing — u sababni aytadi.</p><p><b>\"Chek chiqmadi: Printer javob bermayapti — qog'ozni tekshiring\"</b> — printer o'chiq, qog'oz tugagan, qopqog'i ochiq yoki kabel uzilgan. Qavs ichida aniq sabab yoziladi.</p><ol><li>Printer yoqilganini va chirog'i yonganini tekshiring.</li><li>Qog'oz bor-yo'qligini, qopqoq yopiqligini tekshiring.</li><li>USB kabelni (yoki tarmoq kabelini) qayta ulang.</li><li>Chekni qayta chiqaring: POS → <b>Sotuvlar tarixi</b> → kerakli chek yonidagi <b>🖨</b>.</li></ol><p>Sotuv baribir saqlangan — faqat qog'oz chiqmagan. Qaytadan sotmang.</p><p>Printer to'g'ri tanlanganini tekshirish (admin):</p><ol><li>Admin panel → <b>Chek Sozlama</b>.</li><li><b>Print turi</b>: printer USB bilan ulangan bo'lsa — <b>USB — SumatraPDF (do'kon)</b>, tarmoq orqali — <b>LAN — tarmoq printer (IP orqali)</b>.</li><li>USB: <b>Chek printeri (silent print)</b> — ro'yxatdan chek printeringizni tanlang. Nom Windows'dagi bilan aynan bir xil bo'lishi kerak. Bo'sh qolsa chek Windows standart printeriga ketadi.</li><li>LAN: <b>Printer IP</b> va <b>Port</b> ni yozing va <b>🖨 Test chek (LAN)</b> bilan sinab ko'ring.</li><li><b>Saqlash</b>, keyin POS'dan chiqib qayta kiring.</li></ol><ul><li>Chek jim (oynasiz) faqat <b>XENORA dasturida</b> (.exe) chiqadi. Brauzerda chop etish oynasi ochiladi.</li><li>Hammasi to'g'ri, lekin chiqmayapti — qo'ng'iroq qiling.</li></ul>",
     "text": "Avval ekrandagi xabarni o'qing — u sababni aytadi. \"Chek chiqmadi: Printer javob bermayapti — qog'ozni tekshiring\" — printer o'chiq, qog'oz tugagan, qopqog'i ochiq yoki kabel uzilgan. Qavs ichida aniq sabab yoziladi. Printer yoqilganini va chirog'i yonganini tekshiring. Qog'oz bor-yo'qligini, qopqoq yopiqligini tekshiring. USB kabelni (yoki tarmoq kabelini) qayta ulang. Chekni qayta chiqaring: POS → Sotuvlar tarixi → kerakli chek yonidagi 🖨. Sotuv baribir saqlangan — faqat qog'oz chiqmagan. Qaytadan sotmang. Printer to'g'ri tanlanganini tekshirish (admin): Admin panel → Chek Sozlama. Print turi: printer USB bilan ulangan bo'lsa — USB — SumatraPDF (do'kon), tarmoq orqali — LAN — tarmoq printer (IP orqali). USB: Chek printeri (silent print) — ro'yxatdan chek printeringizni tanlang. Nom Windows'dagi bilan aynan bir xil bo'lishi kerak. Bo'sh qolsa chek Windows standart printeriga ketadi. LAN: Printer IP va Port ni yozing va 🖨 Test chek (LAN) bilan sinab ko'ring. Saqlash, keyin POS'dan chiqib qayta kiring. Chek jim (oynasiz) faqat XENORA dasturida (.exe) chiqadi. Brauzerda chop etish oynasi ochiladi. Hammasi to'g'ri, lekin chiqmayapti — qo'ng'iroq qiling.",
     "keys": "printer, chek chiqmadi, pechat, chop etilmayapti, print, ishlamayapti"
    },
    {
     "id": "printer-2",
     "q": "Chek kichik chiqyapti (57mm o'rniga 80mm)",
     "html": "<p>Printeringiz 80mm, chek esa tor (57mm) chiqyapti — yoki aksincha:</p><ol><li>Admin panel → <b>Chek Sozlama</b>.</li><li><b>Qog'oz kengligi</b>: <b>80mm (standart)</b> yoki <b>57mm (kichik)</b> — printeringizga mosini tanlang.</li><li>Harflar mayda bo'lsa — <b>Shrift o'lchami</b>: <b>Katta</b>.</li><li><b>Saqlash</b>, keyin POS'dan chiqib qayta kiring va sinov chekini chiqaring.</li></ol><p>Chekning o'ng tomoni kesilib qolyaptimi? Windows printer sozlamasida qog'oz o'lchami ham to'g'ri bo'lishi kerak: Windows → <b>Printerlar</b> → printeringiz → <b>Printing preferences</b> (Настройки печати) → qog'oz o'lchami 80mm (yoki 58mm).</p><div class=\"xh-note\">XENORA dasturi juda eski bo'lsa, kenglik sozlamasini o'qimasligi mumkin — dasturni yangilang.</div>",
     "text": "Printeringiz 80mm, chek esa tor (57mm) chiqyapti — yoki aksincha: Admin panel → Chek Sozlama. Qog'oz kengligi: 80mm (standart) yoki 57mm (kichik) — printeringizga mosini tanlang. Harflar mayda bo'lsa — Shrift o'lchami: Katta. Saqlash, keyin POS'dan chiqib qayta kiring va sinov chekini chiqaring. Chekning o'ng tomoni kesilib qolyaptimi? Windows printer sozlamasida qog'oz o'lchami ham to'g'ri bo'lishi kerak: Windows → Printerlar → printeringiz → Printing preferences (Настройки печати) → qog'oz o'lchami 80mm (yoki 58mm). XENORA dasturi juda eski bo'lsa, kenglik sozlamasini o'qimasligi mumkin — dasturni yangilang.",
     "keys": "chek tor, chek kichik, 80mm, 58mm, 57mm, qog'oz kengligi, kesilyapti, shrift mayda"
    },
    {
     "id": "printer-3",
     "q": "Etiketka printeridan chek chiqdi",
     "html": "<p>Sabab: <b>Chek printeri</b> maydoni bo'sh — chek Windows standart printeriga ketadi, standart printer esa etiketka printeri bo'lib qolgan.</p><ol><li>Admin panel → <b>Chek Sozlama</b>.</li><li><b>Chek printeri (silent print)</b> ro'yxatidan <b>chek printerini</b> tanlang (etiketka printerini emas).</li><li><b>Saqlash</b>, keyin POS'dan chiqib qayta kiring.</li></ol><p>Etiketka printeri shu sahifaning pastida, alohida <b>Etiketka printeri</b> bo'limida sozlanadi — chek printeriga bog'liq emas.</p><p>Boshqa yo'l: Windows → <b>Printerlar</b> da chek printerini <b>standart</b> (по умолчанию) qilib qo'ying.</p>",
     "text": "Sabab: Chek printeri maydoni bo'sh — chek Windows standart printeriga ketadi, standart printer esa etiketka printeri bo'lib qolgan. Admin panel → Chek Sozlama. Chek printeri (silent print) ro'yxatidan chek printerini tanlang (etiketka printerini emas). Saqlash, keyin POS'dan chiqib qayta kiring. Etiketka printeri shu sahifaning pastida, alohida Etiketka printeri bo'limida sozlanadi — chek printeriga bog'liq emas. Boshqa yo'l: Windows → Printerlar da chek printerini standart (по умолчанию) qilib qo'ying.",
     "keys": "etiketka printeri, yorliq printeri, noto'g'ri printer, chek boshqa printerga, xprinter"
    },
    {
     "id": "printer-4",
     "q": "Printer qog'ozi tugasa nima bo'ladi?",
     "html": "<ul><li>Sotuv <b>saqlanadi</b>, pul hisoblanadi — faqat qog'oz chiqmaydi.</li><li>Ekranda <b>\"Chek chiqmadi: Printer javob bermayapti — qog'ozni tekshiring (qog'oz tugagan)\"</b> chiqadi.</li><li>XENORA chekni Windows navbatida qoldirmaydi: 10 soniyada chiqmagan chek bekor qilinadi, eski cheklar 5 daqiqadan keyin navbatdan o'chiriladi. Qog'oz qo'yilganda kechagi cheklar birdaniga chiqib ketmaydi.</li></ul><p>Qog'oz qo'ygandan keyin:</p><ol><li>Yangi rulon soling, qopqoqni yoping.</li><li>Chiqmagan chekni qayta chiqaring: POS → <b>Sotuvlar tarixi</b> → chek yonidagi <b>🖨</b>.</li></ol><div class=\"xh-note\">Bu himoya XENORA 1.14.3 va undan yangi versiyada. Eski versiyada cheklar Windows navbatida to'planib, printer qaytganda hammasi birdan chiqadi — dasturni yangilang.</div>",
     "text": "Sotuv saqlanadi, pul hisoblanadi — faqat qog'oz chiqmaydi. Ekranda \"Chek chiqmadi: Printer javob bermayapti — qog'ozni tekshiring (qog'oz tugagan)\" chiqadi. XENORA chekni Windows navbatida qoldirmaydi: 10 soniyada chiqmagan chek bekor qilinadi, eski cheklar 5 daqiqadan keyin navbatdan o'chiriladi. Qog'oz qo'yilganda kechagi cheklar birdaniga chiqib ketmaydi. Qog'oz qo'ygandan keyin: Yangi rulon soling, qopqoqni yoping. Chiqmagan chekni qayta chiqaring: POS → Sotuvlar tarixi → chek yonidagi 🖨. Bu himoya XENORA 1.14.3 va undan yangi versiyada. Eski versiyada cheklar Windows navbatida to'planib, printer qaytganda hammasi birdan chiqadi — dasturni yangilang.",
     "keys": "qog'oz tugadi, lenta tugadi, rulon, navbat, cheklar birdan chiqdi, eski cheklar"
    }
   ]
  },
  {
   "id": "ombor",
   "title": "Ombor",
   "items": [
    {
     "id": "ombor-1",
     "q": "Yangi mahsulot qanday qo'shaman?",
     "html": "<ol><li>Admin panel → <b>Mahsulotlar</b>.</li><li>Yuqori o'ngdagi <b>Mahsulot qo'shish</b> tugmasini bosing.</li><li>To'ldiring:<ul><li><b>Nomi</b> (majburiy)</li><li><b>Narxi (UZS)</b> — sotish narxi (majburiy)</li><li><b>Tan narx (UZS)</b> — kelish narxi; foyda shundan hisoblanadi</li><li><b>O'lchov birligi</b> — Dona, Kg, Gramm, Litr, Metr ...</li><li><b>Kategoriya</b></li><li><b>Shtrix-kod</b> — kursorni shu maydonga qo'yib skanerlang</li></ul></li><li>Pachkada ham sotilsa — <b>Pachka bilan sotish (ixtiyoriy)</b> ni to'ldiring.</li><li><b>Saqlash</b>.</li></ol><p>Mahsulot qo'shilgach qoldig'i 0 bo'ladi — keyin <b>kirim</b> qiling (keyingi savol).</p><div class=\"xh-note\"><b>Diqqat:</b> shtrix-kodni faqat <b>Shtrix-kod</b> maydoniga skanerlang. Kursor <b>Narxi</b> maydonida turganda skanerlasangiz, shtrix-kod raqami narxga qo'shilib ketadi (12 000 → 12000478...). Saqlashdan oldin narxni tekshiring.</div>",
     "text": "Admin panel → Mahsulotlar. Yuqori o'ngdagi Mahsulot qo'shish tugmasini bosing. To'ldiring: Nomi (majburiy) Narxi (UZS) — sotish narxi (majburiy) Tan narx (UZS) — kelish narxi; foyda shundan hisoblanadi O'lchov birligi — Dona, Kg, Gramm, Litr, Metr ... Kategoriya Shtrix-kod — kursorni shu maydonga qo'yib skanerlang Pachkada ham sotilsa — Pachka bilan sotish (ixtiyoriy) ni to'ldiring. Saqlash. Mahsulot qo'shilgach qoldig'i 0 bo'ladi — keyin kirim qiling (keyingi savol). Diqqat: shtrix-kodni faqat Shtrix-kod maydoniga skanerlang. Kursor Narxi maydonida turganda skanerlasangiz, shtrix-kod raqami narxga qo'shilib ketadi (12 000 → 12000478...). Saqlashdan oldin narxni tekshiring.",
     "keys": "mahsulot qo'shish, yangi tovar, tovar kiritish, shtrix-kod, narx qo'yish"
    },
    {
     "id": "ombor-2",
     "q": "Kirim qanday kiritaman?",
     "html": "<ol><li>Admin panel → <b>Ombor</b>.</li><li>Yuqoridagi <b>Kirim qilish</b> tugmasini bosing va mahsulotni tanlang — yoki mahsulot qatoridagi <b>+</b> tugmasini bosing.</li><li><b>Kirim birligi</b>: <b>Dona</b> yoki <b>Pachka</b> (pachka sozlangan mahsulotda).</li><li><b>Miqdor</b> ni yozing.</li><li><b>Kelish narxi</b> ni yozing.</li><li><b>Yetkazib beruvchi</b> — ixtiyoriy.</li><li><b>Kirim qilish</b> ni bosing.</li></ol><ul><li>Kiritilgan kirimlar: <b>Ombor</b> → <b>Kirim tarixi</b>.</li><li>Bu oynadagi kirim firma oldidagi <b>qarzni yaratmaydi</b>. Tovarni firmadan nasiyaga olgan bo'lsangiz va firma qarzini yuritmoqchi bo'lsangiz — <b>Firmalar</b> → <b>Priyomka</b> bo'limidan kiriting.</li></ul>",
     "text": "Admin panel → Ombor. Yuqoridagi Kirim qilish tugmasini bosing va mahsulotni tanlang — yoki mahsulot qatoridagi + tugmasini bosing. Kirim birligi: Dona yoki Pachka (pachka sozlangan mahsulotda). Miqdor ni yozing. Kelish narxi ni yozing. Yetkazib beruvchi — ixtiyoriy. Kirim qilish ni bosing. Kiritilgan kirimlar: Ombor → Kirim tarixi. Bu oynadagi kirim firma oldidagi qarzni yaratmaydi. Tovarni firmadan nasiyaga olgan bo'lsangiz va firma qarzini yuritmoqchi bo'lsangiz — Firmalar → Priyomka bo'limidan kiriting.",
     "keys": "kirim, prixod, tovar keldi, qoldiq qo'shish, omborga qo'shish, priyomka"
    },
    {
     "id": "ombor-3",
     "q": "Qoldiq noto'g'ri — nima qilay?",
     "html": "<p>Avval sababini toping:</p><ol><li>Admin panel → <b>Ombor</b> → mahsulotni qidiring.</li><li><b>Kirim tarixi</b> va <b>Ombor hisoboti</b> da shu mahsulot harakatlarini ko'ring (kirim, sotuv, qaytish, hisobdan o'chirish).</li></ol><p>Ko'p uchraydigan sabablar:</p><ul><li>Kirim kiritilmagan yoki ikki marta kiritilgan.</li><li>Sotuvda <b>📦 Pachka</b> bosilgan — ombordan butun pachka ayrilgan.</li><li>Vozvrat hali <b>Kutilmoqda</b> — tasdiqlanmaguncha tovar omborga qaytmaydi.</li><li>Vozvratda <b>Brak</b> belgilangan — tovar omborga qaytmaydi (bu to'g'ri).</li></ul><p>Tuzatish:</p><ul><li>Bitta mahsulot kam ko'rsatsa — <b>kirim</b> qiling; ko'p ko'rsatsa — <b>−</b> (Hisobdan o'chirish).</li><li>Ko'p mahsulotni sanab chiqish kerak bo'lsa — <b>Ombor</b> → <b>Inventarizatsiya</b> → <b>+ Yangi inventarizatsiya</b> → har mahsulotga <b>Haqiqiy miqdor</b> ni yozing → <b>Tasdiqlash</b>. Farqlar omborga o'zi yoziladi va <b>Kamomad (minus)</b> / <b>Ortiqcha (plus)</b> ko'rinadi.</li></ul><div class=\"xh-note\">Inventarizatsiya paytida sotuvni to'xtatish yaxshi — sanash va sotuv aralashsa farq noto'g'ri chiqadi.</div>",
     "text": "Avval sababini toping: Admin panel → Ombor → mahsulotni qidiring. Kirim tarixi va Ombor hisoboti da shu mahsulot harakatlarini ko'ring (kirim, sotuv, qaytish, hisobdan o'chirish). Ko'p uchraydigan sabablar: Kirim kiritilmagan yoki ikki marta kiritilgan. Sotuvda 📦 Pachka bosilgan — ombordan butun pachka ayrilgan. Vozvrat hali Kutilmoqda — tasdiqlanmaguncha tovar omborga qaytmaydi. Vozvratda Brak belgilangan — tovar omborga qaytmaydi (bu to'g'ri). Tuzatish: Bitta mahsulot kam ko'rsatsa — kirim qiling; ko'p ko'rsatsa — − (Hisobdan o'chirish). Ko'p mahsulotni sanab chiqish kerak bo'lsa — Ombor → Inventarizatsiya → + Yangi inventarizatsiya → har mahsulotga Haqiqiy miqdor ni yozing → Tasdiqlash. Farqlar omborga o'zi yoziladi va Kamomad (minus) / Ortiqcha (plus) ko'rinadi. Inventarizatsiya paytida sotuvni to'xtatish yaxshi — sanash va sotuv aralashsa farq noto'g'ri chiqadi.",
     "keys": "qoldiq xato, ombor noto'g'ri, minus qoldiq, sanash, inventarizatsiya, revizya, kamomad tovar"
    },
    {
     "id": "ombor-4",
     "q": "Hisobdan chiqarish qachon kerak?",
     "html": "<p>Tovar <b>sotilmasdan</b> ombordan ketganda:</p><ul><li><b>Buzilgan / Yaroqsiz</b></li><li><b>Yo'qolgan</b></li><li><b>Ichki ishlatish</b> (do'konning o'zi ishlatdi)</li><li><b>Muddati o'tgan</b></li><li><b>Boshqa</b></li></ul><p>Qanday qilinadi:</p><ol><li>Admin panel → <b>Ombor</b> → mahsulot qatoridagi <b>−</b> tugmasi (yoki <b>Chiqim / Hisobdan o'chirish</b> sahifasi).</li><li><b>Miqdor</b> ni yozing.</li><li><b>Sabab</b> ni tanlang, kerak bo'lsa <b>Izoh</b> yozing.</li><li><b>Hisobdan o'chirish</b> ni bosing.</li></ol><p>Qachon <b>ishlatmaslik</b> kerak:</p><ul><li>Mijoz tovarni qaytardi → bu <b>vozvrat</b> (buzuq bo'lsa — <b>Brak</b> belgisi bilan).</li><li>Sanashda farq chiqdi → <b>Inventarizatsiya</b> qulayroq.</li></ul>",
     "text": "Tovar sotilmasdan ombordan ketganda: Buzilgan / Yaroqsiz Yo'qolgan Ichki ishlatish (do'konning o'zi ishlatdi) Muddati o'tgan Boshqa Qanday qilinadi: Admin panel → Ombor → mahsulot qatoridagi − tugmasi (yoki Chiqim / Hisobdan o'chirish sahifasi). Miqdor ni yozing. Sabab ni tanlang, kerak bo'lsa Izoh yozing. Hisobdan o'chirish ni bosing. Qachon ishlatmaslik kerak: Mijoz tovarni qaytardi → bu vozvrat (buzuq bo'lsa — Brak belgisi bilan). Sanashda farq chiqdi → Inventarizatsiya qulayroq.",
     "keys": "hisobdan chiqarish, hisobdan o'chirish, spisanie, buzildi, yo'qoldi, muddati o'tdi, o'zimiz ishlatdik"
    },
    {
     "id": "ombor-5",
     "q": "Etiketka qanday chop etaman?",
     "html": "<ol><li>Admin panel → <b>Etiketka</b>.</li><li><b>Chop etish rejimi</b>: <b>🏷 Etiketka printeri</b> (TSPL · LAN) yoki <b>🖨 Oddiy printer</b> (A4 · brauzer).</li><li><b>O'lcham</b>: Kichik 40×25mm, Yorliq 40×30mm, O'rta 58×40mm, Katta 72×50mm (yoki kenglik/balandlikni o'zingiz yozing).</li><li><b>Barcode turi</b> — odatda <b>Code-128 (universal)</b>.</li><li>Mahsulotlarni belgilang: qidiruv, kategoriya yoki <b>Hammasini belgilash</b>. Har biriga nechta etiketka kerakligini yozing.</li><li><b>🖨 Chop Etish</b>.</li></ol><ul><li>Shtrix-kodi yo'q mahsulotlarga <b>🏷 Barchasiga kod berish</b> — do'kon ichki EAN-13 kodi beriladi.</li><li>Etiketka printerini sozlash: Admin panel → <b>Chek Sozlama</b> → <b>Etiketka printeri</b> → <b>🏷 Sinov etiketkasi</b> bilan tekshiring.</li></ul>",
     "text": "Admin panel → Etiketka. Chop etish rejimi: 🏷 Etiketka printeri (TSPL · LAN) yoki 🖨 Oddiy printer (A4 · brauzer). O'lcham: Kichik 40×25mm, Yorliq 40×30mm, O'rta 58×40mm, Katta 72×50mm (yoki kenglik/balandlikni o'zingiz yozing). Barcode turi — odatda Code-128 (universal). Mahsulotlarni belgilang: qidiruv, kategoriya yoki Hammasini belgilash. Har biriga nechta etiketka kerakligini yozing. 🖨 Chop Etish. Shtrix-kodi yo'q mahsulotlarga 🏷 Barchasiga kod berish — do'kon ichki EAN-13 kodi beriladi. Etiketka printerini sozlash: Admin panel → Chek Sozlama → Etiketka printeri → 🏷 Sinov etiketkasi bilan tekshiring.",
     "keys": "etiketka, yorliq, narx yorlig'i, shtrix-kod chop etish, label, cennik"
    }
   ]
  },
  {
   "id": "hisobot",
   "title": "Hisobot",
   "items": [
    {
     "id": "hisobot-1",
     "q": "Bugun qancha sotdim?",
     "html": "<p>Admin panel → <b>Dashboard</b> → <b>Bugungi savdo</b> kartasi:</p><ul><li><b>Naqd</b>, <b>Karta</b>, <b>Nasiya</b> — to'lov usullari bo'yicha;</li><li><b>Qaytarish</b> — bugun qaytarilgan summa (ayriladi);</li><li><b>Sof savdo</b> — qaytarishdan keyingi savdo;</li><li><b>Kassadan olingan</b> — kassadan olingan pul (inkassatsiya), faqat ma'lumot uchun.</li></ul><p>Boshqa joylar:</p><ul><li>POS → <b>Sotuvlar tarixi</b> → <b>Bugun</b> — har bir chek va kun jami.</li><li>Kassaga aynan qancha <b>pul</b> tushgani — smena hisobotida (<b>Smena</b> bo'limiga qarang).</li></ul>",
     "text": "Admin panel → Dashboard → Bugungi savdo kartasi: Naqd, Karta, Nasiya — to'lov usullari bo'yicha; Qaytarish — bugun qaytarilgan summa (ayriladi); Sof savdo — qaytarishdan keyingi savdo; Kassadan olingan — kassadan olingan pul (inkassatsiya), faqat ma'lumot uchun. Boshqa joylar: POS → Sotuvlar tarixi → Bugun — har bir chek va kun jami. Kassaga aynan qancha pul tushgani — smena hisobotida (Smena bo'limiga qarang).",
     "keys": "bugungi savdo, kassa, tushum, qancha sotildi, kunlik savdo"
    },
    {
     "id": "hisobot-2",
     "q": "Foyda qayerda ko'rinadi?",
     "html": "<ul><li>Tez ko'rish: <b>Dashboard</b> → <b>Bugungi foyda</b> kartasi: Sof savdo − Tan narx = <b>Yalpi foyda</b>, undan <b>Xarajat ulushi</b> ayrilib — <b>sof foyda</b>.</li><li>Batafsil: Admin panel → <b>Moliya</b>. Yorliqlar:<ul><li><b>Foyda tahlili</b> — davr bo'yicha savdo, foyda, eng foydali va eng kam foydali mahsulotlar;</li><li><b>Foyda marjasi</b> — mahsulotlar bo'yicha marja;</li><li><b>Chek bo'yicha foyda</b> — har bir chekdan qancha foyda;</li><li><b>Xarajatlar</b>.</li></ul></li></ul><div class=\"xh-note\">Foyda <b>Tan narx</b> dan hisoblanadi. Mahsulotga tan narx yozilmagan bo'lsa, foyda haqiqiydan katta ko'rinadi — mahsulotlarda <b>Tan narx (UZS)</b> ni to'ldiring.</div>",
     "text": "Tez ko'rish: Dashboard → Bugungi foyda kartasi: Sof savdo − Tan narx = Yalpi foyda, undan Xarajat ulushi ayrilib — sof foyda. Batafsil: Admin panel → Moliya. Yorliqlar: Foyda tahlili — davr bo'yicha savdo, foyda, eng foydali va eng kam foydali mahsulotlar; Foyda marjasi — mahsulotlar bo'yicha marja; Chek bo'yicha foyda — har bir chekdan qancha foyda; Xarajatlar. Foyda Tan narx dan hisoblanadi. Mahsulotga tan narx yozilmagan bo'lsa, foyda haqiqiydan katta ko'rinadi — mahsulotlarda Tan narx (UZS) ni to'ldiring.",
     "keys": "foyda, daromad, marja, sof foyda, yalpi foyda, pribil"
    },
    {
     "id": "hisobot-3",
     "q": "Dashboard va hisobot nega farq qiladi?",
     "html": "<p>Ular har xil narsani sanaydi:</p><ul><li><b>Dashboard → Bugungi savdo</b> — sotilgan tovar summasi. <b>Nasiya ham kiradi</b>, garchi pul hali kelmagan bo'lsa ham.</li><li><b>Smena / Z-hisobot</b> — kassaga tushgan <b>pul</b> (naqd, karta). Nasiya bu yerga kirmaydi.</li><li><b>Moliya → Savdo</b> — chegirma va vozvrat ayirilgan summa.</li></ul><p>Yana sabablar:</p><ul><li><b>Vozvrat qaytarilgan kunda ayriladi.</b> Kecha sotilgan tovar bugun qaytsa — bugungi savdo kamayadi.</li><li><b>Davr har xil.</b> Bir joyda \"Bugun\", boshqasida \"7 kun\" tanlangan bo'lishi mumkin — sanalarni tekshiring.</li><li><b>Tungi savdo.</b> Yarim tundan keyingi savdo odatda keyingi kalendar kunga yoziladi. Kechasi ishlasangiz, \"smena bo'yicha\" hisobot kuni sozlamasi bor — yoqish uchun qo'ng'iroq qiling.</li></ul>",
     "text": "Ular har xil narsani sanaydi: Dashboard → Bugungi savdo — sotilgan tovar summasi. Nasiya ham kiradi, garchi pul hali kelmagan bo'lsa ham. Smena / Z-hisobot — kassaga tushgan pul (naqd, karta). Nasiya bu yerga kirmaydi. Moliya → Savdo — chegirma va vozvrat ayirilgan summa. Yana sabablar: Vozvrat qaytarilgan kunda ayriladi. Kecha sotilgan tovar bugun qaytsa — bugungi savdo kamayadi. Davr har xil. Bir joyda \"Bugun\", boshqasida \"7 kun\" tanlangan bo'lishi mumkin — sanalarni tekshiring. Tungi savdo. Yarim tundan keyingi savdo odatda keyingi kalendar kunga yoziladi. Kechasi ishlasangiz, \"smena bo'yicha\" hisobot kuni sozlamasi bor — yoqish uchun qo'ng'iroq qiling.",
     "keys": "farq, mos kelmaydi, boshqacha, z-hisobot farq, dashboard farq, raqamlar har xil"
    },
    {
     "id": "hisobot-4",
     "q": "Xarajat qanday kiritaman?",
     "html": "<ol><li>Admin panel → <b>Moliya</b> → <b>Xarajatlar</b> yorlig'i.</li><li>Turini tanlang: <b>Ijara</b>, <b>Oylik</b>, <b>Kommunal</b>, <b>Xomashyo/jihoz</b>, <b>Marketing</b>, <b>Boshqa</b>.</li><li><b>Nomi</b> (masalan: Yanvar ijara), <b>Summa (UZS)</b> va sanani yozing.</li><li>Har oy takrorlansa — <b>🔁 Takroriy</b> ni belgilang va oyning nechanchi kuni ekanini yozing.</li><li>Oylik ijara yoki maosh bo'lsa — <b>🗓 Kunlarga taqsimla</b> ni belgilang: summa kunlarga bo'linadi, bir kun sun'iy minusga tushmaydi.</li><li><b>+ Qo'shish</b>.</li></ol><ul><li>Xarajat sof foydadan ayriladi.</li><li>Xarajat pulini kassadan olgan bo'lsangiz, uni smenada <b>Kassa harakati</b> sifatida ham yozing — aks holda smena yopilganda kamomad chiqadi.</li></ul>",
     "text": "Admin panel → Moliya → Xarajatlar yorlig'i. Turini tanlang: Ijara, Oylik, Kommunal, Xomashyo/jihoz, Marketing, Boshqa. Nomi (masalan: Yanvar ijara), Summa (UZS) va sanani yozing. Har oy takrorlansa — 🔁 Takroriy ni belgilang va oyning nechanchi kuni ekanini yozing. Oylik ijara yoki maosh bo'lsa — 🗓 Kunlarga taqsimla ni belgilang: summa kunlarga bo'linadi, bir kun sun'iy minusga tushmaydi. + Qo'shish. Xarajat sof foydadan ayriladi. Xarajat pulini kassadan olgan bo'lsangiz, uni smenada Kassa harakati sifatida ham yozing — aks holda smena yopilganda kamomad chiqadi.",
     "keys": "xarajat, rasxod, ijara, oylik, maosh, kommunal, svet, gaz"
    },
    {
     "id": "hisobot-5",
     "q": "Sana oralig'ini qanday tanlayman?",
     "html": "<ul><li><b>Moliya</b>: yuqoridagi <b>Bugun</b>, <b>7 kun</b>, <b>30 kun</b> tugmalari — yoki ikkita sana maydoniga boshlanish va tugash sanasini yozing va <b>Ko'rsatish</b> ni bosing.</li><li><b>Sotuvlar tarixi</b> (POS va Admin): <b>Bugun</b>, <b>Kecha</b>, <b>7 kun</b>, <b>30 kun</b> yoki ikkita sana.</li><li><b>Qaytarish Jurnali</b>: sana maydonlari va <b>Tozalash</b>.</li></ul><p>Tanlangan davr ekranda yoziladi — raqamlarni solishtirishdan oldin davr bir xil ekanini tekshiring.</p>",
     "text": "Moliya: yuqoridagi Bugun, 7 kun, 30 kun tugmalari — yoki ikkita sana maydoniga boshlanish va tugash sanasini yozing va Ko'rsatish ni bosing. Sotuvlar tarixi (POS va Admin): Bugun, Kecha, 7 kun, 30 kun yoki ikkita sana. Qaytarish Jurnali: sana maydonlari va Tozalash. Tanlangan davr ekranda yoziladi — raqamlarni solishtirishdan oldin davr bir xil ekanini tekshiring.",
     "keys": "sana, davr, oraliq, oy, hafta, kecha, filter, kalendar"
    }
   ]
  },
  {
   "id": "smena",
   "title": "Smena",
   "items": [
    {
     "id": "smena-1",
     "q": "Smena nima uchun kerak?",
     "html": "<p>Smena — kassadagi <b>pulni nazorat qilish</b> uchun. Smena ochilganda yashikdagi boshlang'ich pul yoziladi, yopilganda pul sanaladi va dastur qancha bo'lishi kerakligini ko'rsatadi.</p><ul><li>Smena ochilmagan bo'lsa POS <b>\"Avval smena oching\"</b> deydi va sotuvga ruxsat bermaydi.</li><li>Smenani <b>har kuni yoping</b> — ochiq qolgan smena kunlab yig'iladi va kamomadni topish qiyinlashadi.</li></ul><p>Smenani ochish:</p><ol><li>POS chap menyusidagi <b>Smena</b> ni bosing.</li><li><b>Boshlang'ich kassa miqdori (so'm)</b> — yashikdagi pulni yozing.</li><li><b>▶ Smenani ochish</b>.</li></ol><p>Admin panelda: <b>Smenalar</b> → <b>+ Smena ochish</b>. Smena o'zingizga ochiladi — boshqa xodim smenani o'zi ochadi.</p><p>Smenani yopish: POS → <b>Smena</b> → <b>⏹ Smenani yopish</b> → yashikdagi pulni <b>sanab</b> yozing → yoping.</p>",
     "text": "Smena — kassadagi pulni nazorat qilish uchun. Smena ochilganda yashikdagi boshlang'ich pul yoziladi, yopilganda pul sanaladi va dastur qancha bo'lishi kerakligini ko'rsatadi. Smena ochilmagan bo'lsa POS \"Avval smena oching\" deydi va sotuvga ruxsat bermaydi. Smenani har kuni yoping — ochiq qolgan smena kunlab yig'iladi va kamomadni topish qiyinlashadi. Smenani ochish: POS chap menyusidagi Smena ni bosing. Boshlang'ich kassa miqdori (so'm) — yashikdagi pulni yozing. ▶ Smenani ochish. Admin panelda: Smenalar → + Smena ochish. Smena o'zingizga ochiladi — boshqa xodim smenani o'zi ochadi. Smenani yopish: POS → Smena → ⏹ Smenani yopish → yashikdagi pulni sanab yozing → yoping.",
     "keys": "smena, smena ochish, smena yopish, avval smena oching, kassa ochish"
    },
    {
     "id": "smena-2",
     "q": "Z-hisobot nima?",
     "html": "<p><b>Z-hisobot</b> — smena yopilganda chiqadigan yakuniy hisobot:</p><ul><li><b>Jami savdo</b>, buyurtmalar soni, chegirmalar;</li><li><b>Kassaga tushgan</b> pul: naqd va karta alohida;</li><li><b>Yashikda bo'lishi kerak</b> — dastur hisoblagan naqd;</li><li><b>Farq</b> — siz sanagan pul bilan farqi.</li></ul><p>Qog'ozga chiqarish: smena yopilgandan keyin <b>🖨 Z-chek chiqarish</b>. Keyinroq: Admin panel → <b>Smenalar</b> → yopilgan smena qatorida <b>Z-hisobot</b> yoki <b>🖨 Z-chek</b>.</p><p><b>X-hisobot</b> — o'sha hisobot, lekin smena <b>yopilmaydi</b> (kun o'rtasida tekshirish uchun): Admin panel → <b>Smenalar</b> → ochiq smena qatorida <b>X-hisobot</b>.</p>",
     "text": "Z-hisobot — smena yopilganda chiqadigan yakuniy hisobot: Jami savdo, buyurtmalar soni, chegirmalar; Kassaga tushgan pul: naqd va karta alohida; Yashikda bo'lishi kerak — dastur hisoblagan naqd; Farq — siz sanagan pul bilan farqi. Qog'ozga chiqarish: smena yopilgandan keyin 🖨 Z-chek chiqarish. Keyinroq: Admin panel → Smenalar → yopilgan smena qatorida Z-hisobot yoki 🖨 Z-chek. X-hisobot — o'sha hisobot, lekin smena yopilmaydi (kun o'rtasida tekshirish uchun): Admin panel → Smenalar → ochiq smena qatorida X-hisobot.",
     "keys": "z-hisobot, z-otchet, x-hisobot, smena hisoboti, kun yakuni, z-chek"
    },
    {
     "id": "smena-3",
     "q": "Kamomad chiqdi — nega?",
     "html": "<p><b>Farq = siz sanagan pul − yashikda bo'lishi kerak.</b> \"Yashikda bo'lishi kerak\" = boshlang'ich pul + naqd sotuv − naqd vozvrat − kassadan olingan + kassaga qo'shilgan.</p><p>Ko'p uchraydigan sabablar:</p><ul><li><b>Kassadan pul olindi, lekin yozilmadi.</b> Har olingan pulni <b>Kassa harakati</b> bilan yozing (keyingi savol).</li><li><b>To'lov usuli noto'g'ri bosilgan.</b> Mijoz karta bilan to'lagan, kassir <b>Naqd</b> ni bosgan (yoki teskari). Tuzatish: Admin panel → <b>Sotuvlar tarixi</b> → chekni oching → <b>💳 To'lov usulini o'zgartirish</b>. Ombor va savdo summasi o'zgarmaydi, faqat pul turi tuzatiladi.</li><li><b>Qaytim noto'g'ri berilgan.</b></li><li><b>Naqd vozvrat</b> — mijozga yashikdan pul qaytarilgan.</li><li><b>Sanashda xato</b> — pulni qayta sanang.</li></ul><p>Ortiqcha chiqsa — ko'pincha teskari holat: naqd olingan, lekin <b>Karta</b> bosilgan.</p>",
     "text": "Farq = siz sanagan pul − yashikda bo'lishi kerak. \"Yashikda bo'lishi kerak\" = boshlang'ich pul + naqd sotuv − naqd vozvrat − kassadan olingan + kassaga qo'shilgan. Ko'p uchraydigan sabablar: Kassadan pul olindi, lekin yozilmadi. Har olingan pulni Kassa harakati bilan yozing (keyingi savol). To'lov usuli noto'g'ri bosilgan. Mijoz karta bilan to'lagan, kassir Naqd ni bosgan (yoki teskari). Tuzatish: Admin panel → Sotuvlar tarixi → chekni oching → 💳 To'lov usulini o'zgartirish. Ombor va savdo summasi o'zgarmaydi, faqat pul turi tuzatiladi. Qaytim noto'g'ri berilgan. Naqd vozvrat — mijozga yashikdan pul qaytarilgan. Sanashda xato — pulni qayta sanang. Ortiqcha chiqsa — ko'pincha teskari holat: naqd olingan, lekin Karta bosilgan.",
     "keys": "kamomad, nedostacha, pul kam, pul ortiqcha, farq, kassa to'g'ri kelmadi"
    },
    {
     "id": "smena-4",
     "q": "Kassadan pul olsam nima qilaman?",
     "html": "<p>Har safar yozib qo'ying — aks holda smena yopilganda kamomad chiqadi.</p><ol><li>POS → <b>Smena</b> → <b>💵 Kassa harakati</b> (Admin panelda: <b>Smenalar</b> → ochiq smena qatorida <b>💵 Kassa</b>).</li><li><b>Turi</b>:<ul><li><b>Kassadan olindi (inkassatsiya)</b> — pul olindi;</li><li><b>Kassaga qo'shildi (razmen)</b> — mayda pul qo'shildi.</li></ul></li><li><b>Summa (so'm)</b>.</li><li><b>Sababi</b> — masalan: egasiga topshirildi.</li><li><b>Saqlash</b>.</li></ol><ul><li>Yozuv <b>o'chirilmaydi</b>. Xato yozsangiz — teskari yozuv kiriting (masalan, ortiqcha \"olindi\" o'rniga shuncha \"qo'shildi\").</li><li>Kassadan olingan pul foydani kamaytirmaydi. Agar bu pul xarajatga ketgan bo'lsa (ijara, kommunal), uni <b>Moliya</b> → <b>Xarajatlar</b> da ham yozing.</li></ul>",
     "text": "Har safar yozib qo'ying — aks holda smena yopilganda kamomad chiqadi. POS → Smena → 💵 Kassa harakati (Admin panelda: Smenalar → ochiq smena qatorida 💵 Kassa). Turi: Kassadan olindi (inkassatsiya) — pul olindi; Kassaga qo'shildi (razmen) — mayda pul qo'shildi. Summa (so'm). Sababi — masalan: egasiga topshirildi. Saqlash. Yozuv o'chirilmaydi. Xato yozsangiz — teskari yozuv kiriting (masalan, ortiqcha \"olindi\" o'rniga shuncha \"qo'shildi\"). Kassadan olingan pul foydani kamaytirmaydi. Agar bu pul xarajatga ketgan bo'lsa (ijara, kommunal), uni Moliya → Xarajatlar da ham yozing.",
     "keys": "kassadan pul olish, inkassatsiya, egasiga topshirdim, razmen, mayda pul, pul qo'shish"
    }
   ]
  },
  {
   "id": "mijoz-nasiya",
   "title": "Mijoz va nasiya",
   "items": [
    {
     "id": "mijoz-nasiya-1",
     "q": "Mijoz qanday qo'shaman?",
     "html": "<p>Sotuv paytida (POS):</p><ol><li>Savatdagi <b>Mijoz tanlang</b> tugmasini bosing.</li><li><b>+ Yangi mijoz</b> ni bosing.</li><li><b>Ism</b> va <b>Telefon</b> (majburiy), kerak bo'lsa <b>Chegirma %</b>.</li><li><b>Qo'shish va tanlash</b> — mijoz shu sotuvga darhol tanlanadi.</li></ol><p>Admin panelda:</p><ol><li><b>Mijozlar</b> → yuqori o'ngdagi <b>Mijoz qo'shish</b>.</li><li><b>Ism</b>, <b>Telefon</b>, <b>Chegirma % (0–100)</b>.</li><li><b>Saqlash</b>.</li></ol><p>Mijozga chegirma % yozsangiz, POS'da u tanlanganda chegirma o'zi qo'llanadi.</p>",
     "text": "Sotuv paytida (POS): Savatdagi Mijoz tanlang tugmasini bosing. + Yangi mijoz ni bosing. Ism va Telefon (majburiy), kerak bo'lsa Chegirma %. Qo'shish va tanlash — mijoz shu sotuvga darhol tanlanadi. Admin panelda: Mijozlar → yuqori o'ngdagi Mijoz qo'shish. Ism, Telefon, Chegirma % (0–100). Saqlash. Mijozga chegirma % yozsangiz, POS'da u tanlanganda chegirma o'zi qo'llanadi.",
     "keys": "mijoz qo'shish, yangi mijoz, xaridor, klient, telefon"
    },
    {
     "id": "mijoz-nasiya-2",
     "q": "Qarzni qanday to'layman?",
     "html": "<p>Mijoz qarzini to'lashga keldi:</p><ol><li>Admin panel → <b>Nasiya / Qarz</b>.</li><li>Mijozni <b>Ism yoki telefon</b> bo'yicha toping.</li><li>Ikki yo'l:<ul><li><b>Umumiy to'lov (FIFO)</b> — mijoz bergan summani yozasiz, dastur uni <b>eng eski qarzdan boshlab</b> o'zi taqsimlaydi. Bir nechta qarzi bo'lsa — shu qulay.</li><li>Qarz qatoridagi <b>To'lash</b> — faqat shu bitta qarzga.</li></ul></li><li>Summani yozing va tasdiqlang.</li></ol><p>Qarz kartochkasidan ham bo'ladi: mijoz ismini bosing → <b>Qarz kartochkasi</b> → <b>Qarzni to'lash</b>.</p><ul><li>To'liq yopilgan qarz <b>✓ To'langan</b> holatiga o'tadi, qisman to'langani — <b>⏳ Qisman</b>.</li></ul>",
     "text": "Mijoz qarzini to'lashga keldi: Admin panel → Nasiya / Qarz. Mijozni Ism yoki telefon bo'yicha toping. Ikki yo'l: Umumiy to'lov (FIFO) — mijoz bergan summani yozasiz, dastur uni eng eski qarzdan boshlab o'zi taqsimlaydi. Bir nechta qarzi bo'lsa — shu qulay. Qarz qatoridagi To'lash — faqat shu bitta qarzga. Summani yozing va tasdiqlang. Qarz kartochkasidan ham bo'ladi: mijoz ismini bosing → Qarz kartochkasi → Qarzni to'lash. To'liq yopilgan qarz ✓ To'langan holatiga o'tadi, qisman to'langani — ⏳ Qisman.",
     "keys": "qarz to'lash, nasiya to'lash, qarzini berdi, qarz yopish, fifo"
    },
    {
     "id": "mijoz-nasiya-3",
     "q": "Qarz kartochkasi nima?",
     "html": "<p><b>Qarz kartochkasi</b> — bitta mijozning barcha nasiya va to'lovlari bitta varaqda: sana, hujjat (chek raqami yoki to'lov), summa va qolgan qarz.</p><p>Ochish: Admin panel → <b>Nasiya / Qarz</b> → mijoz <b>ismini</b> bosing.</p><ul><li>Kartochkadagi jami qoldiq <b>Nasiya / Qarz</b> ro'yxatidagi raqam bilan bir xil.</li><li>Chek raqamini bosing — o'sha nasiyada qaysi mahsulotlar olingani ochiladi.</li><li>Mijoz \"qancha qarzim bor, qachon nima oldim?\" desa — shu kartochkani ko'rsating.</li><li>Kartochka pastidagi <b>Qarzni to'lash</b> — shu mijoz uchun FIFO to'lov.</li></ul>",
     "text": "Qarz kartochkasi — bitta mijozning barcha nasiya va to'lovlari bitta varaqda: sana, hujjat (chek raqami yoki to'lov), summa va qolgan qarz. Ochish: Admin panel → Nasiya / Qarz → mijoz ismini bosing. Kartochkadagi jami qoldiq Nasiya / Qarz ro'yxatidagi raqam bilan bir xil. Chek raqamini bosing — o'sha nasiyada qaysi mahsulotlar olingani ochiladi. Mijoz \"qancha qarzim bor, qachon nima oldim?\" desa — shu kartochkani ko'rsating. Kartochka pastidagi Qarzni to'lash — shu mijoz uchun FIFO to'lov.",
     "keys": "qarz kartochkasi, qarz tarixi, akt sverka, mijoz qarzi, oborot"
    }
   ]
  }
 ]
};
