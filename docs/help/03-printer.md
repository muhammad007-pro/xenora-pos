# Printer

## Chek chiqmayapti
Kalit: printer, chek chiqmadi, pechat, chop etilmayapti, print, ishlamayapti

Avval ekrandagi xabarni o'qing — u sababni aytadi.

**"Chek chiqmadi: Printer javob bermayapti — qog'ozni tekshiring"** — printer o'chiq, qog'oz tugagan, qopqog'i ochiq yoki kabel uzilgan. Qavs ichida aniq sabab yoziladi.

1. Printer yoqilganini va chirog'i yonganini tekshiring.
2. Qog'oz bor-yo'qligini, qopqoq yopiqligini tekshiring.
3. USB kabelni (yoki tarmoq kabelini) qayta ulang.
4. Chekni qayta chiqaring: POS → **Sotuvlar tarixi** → kerakli chek yonidagi **🖨**.

Sotuv baribir saqlangan — faqat qog'oz chiqmagan. Qaytadan sotmang.

Printer to'g'ri tanlanganini tekshirish (admin):

1. Admin panel → **Chek Sozlama**.
2. **Print turi**: printer USB bilan ulangan bo'lsa — **USB — SumatraPDF (do'kon)**, tarmoq orqali — **LAN — tarmoq printer (IP orqali)**.
3. USB: **Chek printeri (silent print)** — ro'yxatdan chek printeringizni tanlang. Nom Windows'dagi bilan aynan bir xil bo'lishi kerak. Bo'sh qolsa chek Windows standart printeriga ketadi.
4. LAN: **Printer IP** va **Port** ni yozing va **🖨 Test chek (LAN)** bilan sinab ko'ring.
5. **Saqlash**, keyin POS'dan chiqib qayta kiring.

- Chek jim (oynasiz) faqat **XENORA dasturida** (.exe) chiqadi. Brauzerda chop etish oynasi ochiladi.
- Hammasi to'g'ri, lekin chiqmayapti — qo'ng'iroq qiling.

## Chek kichik chiqyapti (57mm o'rniga 80mm)
Kalit: chek tor, chek kichik, 80mm, 58mm, 57mm, qog'oz kengligi, kesilyapti, shrift mayda

Printeringiz 80mm, chek esa tor (57mm) chiqyapti — yoki aksincha:

1. Admin panel → **Chek Sozlama**.
2. **Qog'oz kengligi**: **80mm (standart)** yoki **57mm (kichik)** — printeringizga mosini tanlang.
3. Harflar mayda bo'lsa — **Shrift o'lchami**: **Katta**.
4. **Saqlash**, keyin POS'dan chiqib qayta kiring va sinov chekini chiqaring.

Chekning o'ng tomoni kesilib qolyaptimi? Windows printer sozlamasida qog'oz o'lchami ham to'g'ri bo'lishi kerak: Windows → **Printerlar** → printeringiz → **Printing preferences** (Настройки печати) → qog'oz o'lchami 80mm (yoki 58mm).

> XENORA dasturi juda eski bo'lsa, kenglik sozlamasini o'qimasligi mumkin — dasturni yangilang.

## Etiketka printeridan chek chiqdi
Kalit: etiketka printeri, yorliq printeri, noto'g'ri printer, chek boshqa printerga, xprinter

Sabab: **Chek printeri** maydoni bo'sh — chek Windows standart printeriga ketadi, standart printer esa etiketka printeri bo'lib qolgan.

1. Admin panel → **Chek Sozlama**.
2. **Chek printeri (silent print)** ro'yxatidan **chek printerini** tanlang (etiketka printerini emas).
3. **Saqlash**, keyin POS'dan chiqib qayta kiring.

Etiketka printeri shu sahifaning pastida, alohida **Etiketka printeri** bo'limida sozlanadi — chek printeriga bog'liq emas.

Boshqa yo'l: Windows → **Printerlar** da chek printerini **standart** (по умолчанию) qilib qo'ying.

## Printer qog'ozi tugasa nima bo'ladi?
Kalit: qog'oz tugadi, lenta tugadi, rulon, navbat, cheklar birdan chiqdi, eski cheklar

- Sotuv **saqlanadi**, pul hisoblanadi — faqat qog'oz chiqmaydi.
- Ekranda **"Chek chiqmadi: Printer javob bermayapti — qog'ozni tekshiring (qog'oz tugagan)"** chiqadi.
- XENORA chekni Windows navbatida qoldirmaydi: 10 soniyada chiqmagan chek bekor qilinadi, eski cheklar 5 daqiqadan keyin navbatdan o'chiriladi. Qog'oz qo'yilganda kechagi cheklar birdaniga chiqib ketmaydi.

Qog'oz qo'ygandan keyin:

1. Yangi rulon soling, qopqoqni yoping.
2. Chiqmagan chekni qayta chiqaring: POS → **Sotuvlar tarixi** → chek yonidagi **🖨**.

> Bu himoya XENORA 1.14.3 va undan yangi versiyada. Eski versiyada cheklar Windows navbatida to'planib, printer qaytganda hammasi birdan chiqadi — dasturni yangilang.
