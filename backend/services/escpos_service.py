"""ESC/POS yadro — chek baytlarini generatsiya qiladi (IZOLYATSIYALANGAN).

Bu modul FAQAT ma'lumotdan ESC/POS baytlar yasaydi — hech qayerga ulanmaydi,
hech narsa yubormaydi. Ulanish (mock/network/usb/spooler) alohida qatlamda
(`printer_service.py`). Shu sabab printer bo'lmasa ham bayt generatsiyasini
sinash mumkin (fiskal OFD yadrosi kabi).

80mm termal = 48 belgi, 58mm = 32 belgi (sozlanadigan).
"""
from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional

from escpos.printer import Dummy

# Qog'oz kengligi (mm) → bir qatordagi belgilar soni (Font A)
CHARS_BY_WIDTH: Dict[int, int] = {58: 32, 80: 48}


def _chars(width_mm: int) -> int:
    return CHARS_BY_WIDTH.get(int(width_mm), 48)


def _money(n: Optional[float]) -> str:
    """Narxni '12 000' ko'rinishida."""
    try:
        return f"{float(n or 0):,.0f}".replace(",", " ")
    except (TypeError, ValueError):
        return "0"


def _sanitize(s: Any) -> str:
    """Termal printer kod-sahifasi qo'llab-quvvatlamaydigan belgilarni almashtirish.
    O'zbek lotin apostroflari va ba'zi belgilar CP1251/CP437 da yo'q — soddalashtiramiz."""
    s = "" if s is None else str(s)
    repl = {
        "ʻ": "'", "ʼ": "'", "‘": "'", "’": "'",
        "“": '"', "”": '"', "–": "-", "—": "-",
        "…": "...", "•": "*", " ": " ",
    }
    for a, b in repl.items():
        s = s.replace(a, b)
    return s


def _row(left: str, right: str, width: int) -> str:
    """Chap va o'ng ustun — bir qatorda, kenglik bo'yicha tekislangan."""
    left = _sanitize(left)
    right = _sanitize(right)
    space = width - len(left) - len(right)
    if space < 1:
        # Chap juda uzun — qisqartiramiz
        left = left[: max(0, width - len(right) - 1)]
        space = max(1, width - len(left) - len(right))
    return f"{left}{' ' * space}{right}"


def _sub_label(data) -> str:
    """Chekda chegirma bo'lsa "Chegirmasiz:", aks holda "Jami:" (chegirmasiz chek o'zgarmaydi).
    `had_discount` — kelishilgan narxli chekda qolgan chegirma 0 bo'lsa ham true."""
    if data.get("had_discount") or (data.get("discount") or 0) > 0:
        return "Chegirmasiz:"
    return "Jami:"


def _disc_label(data) -> str:
    """BOSQICH S3: chegirma yorlig'iga foiz (discount/subtotal'dan hosila).

    Manba (mijoz/qo'lda) SERVER tomonda noma'lum (client-only) — faqat foiz.
    subtotal 0/yo'q bo'lsa oddiy "Chegirma:" (xato bermaydi).
    """
    d = data.get("discount") or 0
    sub = data.get("subtotal") or 0
    if d > 0 and sub > 0:
        pct = round(d / sub * 100, 1)
        pct_s = str(int(pct)) if pct == int(pct) else str(pct)
        return f"Chegirma -{pct_s}%:"
    return "Chegirma:"


def _wrap(text: str, width: int) -> List[str]:
    """Uzun matnni kenglik bo'yicha bo'lish."""
    text = _sanitize(text)
    words = text.split()
    lines: List[str] = []
    cur = ""
    for w in words:
        if len(cur) + len(w) + (1 if cur else 0) <= width:
            cur = f"{cur} {w}".strip()
        else:
            if cur:
                lines.append(cur)
            cur = w[:width]
    if cur:
        lines.append(cur)
    return lines or [""]


def build_receipt(data: Dict[str, Any], width_mm: int = 80) -> bytes:
    """Mijoz chekini ESC/POS bayt sifatida qaytaradi.

    data: {
      store_name, store_address, datetime, cashier, receipt_number,
      items: [{name, quantity, total, unit_price?}],
      subtotal, discount, tax, service, total,
      payment_method, fiscal_number?, fiscal_qr_url?
    }
    """
    w = _chars(width_mm)
    d = Dummy()
    # ESC @ — printerni boshlang'ich holatga keltirish (toza start)
    try:
        d._raw(b"\x1b@")
    except Exception:
        pass
    # Kod sahifasi (kirill/lotin uchun) — printer qo'llab-quvvatlasa
    try:
        d.charcode("CP1251")
    except Exception:
        pass

    # ── Sarlavha: do'kon nomi (markaz, katta) ──
    d.set(align="center", text_type="B", width=2, height=2)
    d.text(_sanitize(data.get("store_name") or "Do'kon") + "\n")
    d.set(align="center", text_type="normal", width=1, height=1)
    if data.get("store_address"):
        for ln in _wrap(data["store_address"], w):
            d.text(ln + "\n")
    if data.get("phone"):
        d.text(_sanitize("Tel: " + str(data["phone"])) + "\n")
    if data.get("header_text"):
        for ln in _wrap(data["header_text"], w):
            d.text(ln + "\n")
    d.text("=" * w + "\n")

    # ── Meta: chek №, sana, kassir ──
    d.set(align="left")
    if data.get("receipt_number") is not None:
        d.text(_row("Chek:", "#" + str(data["receipt_number"]), w) + "\n")
    dt = data.get("datetime") or datetime.now().strftime("%d.%m.%Y %H:%M")
    d.text(_row("Sana:", _sanitize(dt), w) + "\n")
    if data.get("cashier"):
        d.text(_row("Kassir:", _sanitize(data["cashier"]), w) + "\n")
    d.text("-" * w + "\n")

    # ── Mahsulotlar ──
    d.text(_row("Mahsulot", "Summa", w) + "\n")
    d.text("-" * w + "\n")
    for it in data.get("items", []):
        name = _sanitize(it.get("name") or it.get("product_name") or "")
        qty = it.get("quantity", it.get("qty", 1))
        total = it.get("total", it.get("total_price", 0))
        unit = it.get("unit_price")
        # 1-qator: mahsulot nomi (uzun bo'lsa o'raladi)
        for ln in _wrap(name, w):
            d.text(ln + "\n")
        # 2-qator: soni x narx ... jami (o'ngda)
        left = f"  {qty} x {_money(unit)}" if unit else f"  {qty} dona"
        d.text(_row(left, _money(total), w) + "\n")
    d.text("-" * w + "\n")

    # ── Jami / soliq / chegirma ──
    d.text(_row(_sub_label(data), _money(data.get("subtotal")), w) + "\n")
    if (data.get("discount") or 0) > 0:
        d.text(_row(_disc_label(data), "-" + _money(data["discount"]), w) + "\n")
    if (data.get("tax") or 0) > 0:
        d.text(_row("Soliq (12%):", _money(data["tax"]), w) + "\n")
    if (data.get("service") or 0) > 0:
        d.text(_row("Xizmat (10%):", _money(data["service"]), w) + "\n")
    d.text("=" * w + "\n")
    d.set(text_type="B")
    d.text(_row("UMUMIY:", _money(data.get("total")) + " UZS", w) + "\n")
    d.set(text_type="normal")

    # ── To'lov ──
    if data.get("payment_method"):
        methods = {"cash": "Naqd", "card": "Karta", "click": "Click",
                   "payme": "Payme", "credit": "Nasiya"}
        pm = methods.get(data["payment_method"], data["payment_method"])
        d.text(_row("To'lov:", _sanitize(pm), w) + "\n")
    d.text("=" * w + "\n")

    # ── Fiskal / QQS bloki — FAQAT fiscal cfg enabled bo'lsa ──
    # Do'konда fiscal o'chiq (enabled=false) → bu blok butunlay o'tkazib yuboriladi
    # (chekда QQS/STIR/fiskal raqam ko'rinmaydi). Fiskal ulanganda (enabled=true,
    # INN/kassa) → STIR, fiskal raqam, QQS summasi va QR avtomatik chiqadi.
    if data.get("fiscal_enabled"):
        d.set(align="center", text_type="B")
        d.text("FISKAL CHEK\n")
        d.set(align="left", text_type="normal")
        if data.get("tax_id"):
            d.text(_row("STIR:", _sanitize(data["tax_id"]), w) + "\n")
        if data.get("fiscal_number"):
            d.text(_row("Fiskal No:", _sanitize(data["fiscal_number"]), w) + "\n")
        if (data.get("tax") or 0) > 0:
            d.text(_row("Shu jumladan QQS:", _money(data["tax"]), w) + "\n")
        if data.get("fiscal_qr_url"):
            d.set(align="center")
            try:
                d.qr(data["fiscal_qr_url"], native=True, size=6)  # native=True → GS ( k baytlar
            except Exception:
                for ln in _wrap(data["fiscal_qr_url"], w):
                    d.text(ln + "\n")
            d.text("Soliq ilovasida skanerlang\n")
            d.text("1% keshbek olishingiz mumkin\n")
            d.set(align="left")
        d.text("=" * w + "\n")

    # ── Footer: rahmat yozuvi (tenant footer_text) + do'kon QR + sana ──
    d.set(align="center")
    footer = _sanitize(data.get("footer_text") or "Xaridingiz uchun rahmat!")
    for ln in _wrap(footer, w):
        d.text(ln + "\n")
    # Do'kon QR (fiskal emas — receipt_settings.qr_url, masalan Telegram/manzil)
    if data.get("qr_url"):
        try:
            d.qr(data["qr_url"], native=True, size=5)
        except Exception:
            for ln in _wrap(data["qr_url"], w):
                d.text(ln + "\n")
    d.text(_sanitize(data.get("datetime") or datetime.now().strftime("%d.%m.%Y %H:%M")) + "\n")
    d.set(align="left")
    d.text("\n\n")
    try:
        d.cut()
    except Exception:
        d.text("\n\n\n")

    return d.output


def render_text(data: Dict[str, Any], width_mm: int = 80) -> str:
    """Chekning o'qiladigan MATN ko'rinishi (mock log / preview uchun).
    ESC/POS bayt EMAS — faqat odam ko'rishi uchun bir xil tartibда matn."""
    w = _chars(width_mm)
    L: List[str] = []
    L.append(_sanitize(data.get("store_name") or "Do'kon").center(w))
    for ln in _wrap(data.get("store_address") or "", w):
        if ln:
            L.append(ln.center(w))
    if data.get("phone"):
        L.append(_sanitize("Tel: " + str(data["phone"])).center(w))
    for ln in _wrap(data.get("header_text") or "", w):
        if ln:
            L.append(ln.center(w))
    L.append("=" * w)
    if data.get("receipt_number") is not None:
        L.append(_row("Chek:", "#" + str(data["receipt_number"]), w))
    L.append(_row("Sana:", _sanitize(data.get("datetime") or datetime.now().strftime("%d.%m.%Y %H:%M")), w))
    if data.get("cashier"):
        L.append(_row("Kassir:", _sanitize(data["cashier"]), w))
    L.append("-" * w)
    L.append(_row("Mahsulot", "Summa", w))
    L.append("-" * w)
    for it in data.get("items", []):
        name = _sanitize(it.get("name") or it.get("product_name") or "")
        qty = it.get("quantity", it.get("qty", 1))
        total = it.get("total", it.get("total_price", 0))
        unit = it.get("unit_price")
        for ln in _wrap(name, w):
            L.append(ln)
        left = f"  {qty} x {_money(unit)}" if unit else f"  {qty} dona"
        L.append(_row(left, _money(total), w))
    L.append("-" * w)
    L.append(_row(_sub_label(data), _money(data.get("subtotal")), w))
    if (data.get("discount") or 0) > 0:
        L.append(_row(_disc_label(data), "-" + _money(data["discount"]), w))
    if (data.get("tax") or 0) > 0:
        L.append(_row("Soliq (12%):", _money(data["tax"]), w))
    if (data.get("service") or 0) > 0:
        L.append(_row("Xizmat (10%):", _money(data["service"]), w))
    L.append("=" * w)
    L.append(_row("UMUMIY:", _money(data.get("total")) + " UZS", w))
    if data.get("payment_method"):
        methods = {"cash": "Naqd", "card": "Karta", "click": "Click", "payme": "Payme", "credit": "Nasiya"}
        L.append(_row("To'lov:", _sanitize(methods.get(data["payment_method"], data["payment_method"])), w))
    L.append("=" * w)
    if data.get("fiscal_enabled"):
        L.append("FISKAL CHEK".center(w))
        if data.get("tax_id"):
            L.append(_row("STIR:", _sanitize(data["tax_id"]), w))
        if data.get("fiscal_number"):
            L.append(_row("Fiskal No:", _sanitize(data["fiscal_number"]), w))
        if (data.get("tax") or 0) > 0:
            L.append(_row("Shu jumladan QQS:", _money(data["tax"]), w))
        if data.get("fiscal_qr_url"):
            L.append("[QR: " + _sanitize(data["fiscal_qr_url"]) + "]")
            L.append("Soliq ilovasida skanerlang".center(w))
        L.append("=" * w)
    L.append("")
    L.append(_sanitize(data.get("footer_text") or "Xaridingiz uchun rahmat!").center(w))
    if data.get("qr_url"):
        L.append(("[QR: " + _sanitize(data["qr_url"]) + "]").center(w))
    L.append(_sanitize(data.get("datetime") or datetime.now().strftime("%d.%m.%Y %H:%M")).center(w))
    return "\n".join(L)


def _shortage_label(data: Dict[str, Any]) -> str:
    """shortage qiymatiga qarab o'qiladigan yorliq."""
    st = data.get("shortage_type")
    if st == "ortiqcha":
        return "ORTIQCHA"
    if st == "kamomad":
        return "KAMOMAD"
    return "MOS"


def _z_money_lines(data: Dict[str, Any], w: int) -> List[tuple]:
    """Z-hisobotning pul qismi — (qalin?, satr) ro'yxati. ESC/POS va matn
    ko'rinishi SHU BITTA ro'yxatdan (ilgari ikki nusxa yozilgan edi).

    Uch blok (variant A, 2026-10):
      SAVDO — nima sotildi (nasiya bilan). Pul emas.
      PUL   — KASSAGA TUSHGAN: naqd + karta + qarz to'lovi − qaytarish.
      YASHIK — naqd: bo'lishi kerak / sanaldi / farq.
    """
    g = lambda k: data.get(k) or 0
    L: List[tuple] = []
    L.append((True, "SAVDO"))
    L.append((False, _row("Naqd:", _money(g("cash_sales")), w)))
    L.append((False, _row("Karta/Click:", _money(g("card_sales")), w)))
    if g("credit_total") > 0:
        L.append((False, _row("Nasiya:", _money(g("credit_total")), w)))
    L.append((True, _row("JAMI SAVDO:", _money(g("total_sales")) + " UZS", w)))
    L.append((False, _row("Sotuvlar soni:", str(g("sales_count")), w)))
    if g("discount_total") > 0:
        L.append((False, _row("Chegirmalar:", _money(g("discount_total")), w)))
    L.append((False, "-" * w))

    L.append((True, "PUL (KASSAGA TUSHGAN)"))
    L.append((False, _row("Naqd sotuv:", "+" + _money(g("cash_sales")), w)))
    L.append((False, _row("Karta sotuv:", "+" + _money(g("card_sales")), w)))
    # Nasiya qarzi to'lovi — kassaga tushgan pul, LEKIN sotuv emas
    if g("debt_paid_cash") > 0:
        L.append((False, _row("Qarz to'lovi (naqd):", "+" + _money(g("debt_paid_cash")), w)))
    if g("debt_paid_card") > 0:
        L.append((False, _row("Qarz to'lovi (karta):", "+" + _money(g("debt_paid_card")), w)))
    if g("cash_refunds") > 0:
        L.append((False, _row("Qaytarish (naqd):", "-" + _money(g("cash_refunds")), w)))
    if g("card_refunds") > 0:
        L.append((False, _row("Qaytarish (karta):", "-" + _money(g("card_refunds")), w)))
    L.append((True, _row("KASSAGA TUSHGAN:", _money(g("cash_in_total")) + " UZS", w)))
    L.append((False, "-" * w))

    L.append((True, "YASHIK (NAQD)"))
    L.append((False, _row("Boshlang'ich:", _money(g("starting_cash")), w)))
    L.append((False, _row("Naqd sotuv:", "+" + _money(g("cash_sales")), w)))
    if g("cash_refunds") > 0:
        L.append((False, _row("Naqd qaytarish:", "-" + _money(g("cash_refunds")), w)))
    if g("debt_paid_cash") > 0:
        L.append((False, _row("Qarz to'lovi (naqd):", "+" + _money(g("debt_paid_cash")), w)))
    if g("withdrawals") > 0:
        L.append((False, _row("Olindi (inkassatsiya):", "-" + _money(g("withdrawals")), w)))
    if g("deposits") > 0:
        L.append((False, _row("Qo'shildi:", "+" + _money(g("deposits")), w)))
    L.append((True, _row("Bo'lishi kerak:", _money(g("expected_cash")), w)))
    L.append((False, _row("Sanaldi:", _money(g("counted_cash")), w)))
    return L


def build_z_report(data: Dict[str, Any], width_mm: int = 80) -> bytes:
    """Z-hisobot (kun yakuni / smena yopilishi) chekini ESC/POS bayt qaytaradi.

    data: {
      store_name, store_address, datetime,
      shift_id, cashier, register_name,
      start_time, end_time,
      starting_cash, cash_sales, card_sales, credit_total, total_sales,
      sales_count, discount_total, returns_total, cash_refunds,
      expected_cash, counted_cash, shortage, shortage_type, notes
    }
    """
    w = _chars(width_mm)
    d = Dummy()
    try:
        d._raw(b"\x1b@")
    except Exception:
        pass
    try:
        d.charcode("CP1251")
    except Exception:
        pass

    # ── Sarlavha ──
    d.set(align="center", text_type="B", width=2, height=2)
    d.text(_sanitize(data.get("store_name") or "RestoPOS") + "\n")
    d.set(align="center", text_type="B", width=1, height=1)
    d.text("Z-HISOBOT (KUN YAKUNI)\n")
    d.set(align="center", text_type="normal", width=1, height=1)
    if data.get("store_address"):
        for ln in _wrap(data["store_address"], w):
            d.text(ln + "\n")
    d.text("=" * w + "\n")

    # ── Meta ──
    d.set(align="left")
    dt = data.get("datetime") or datetime.now().strftime("%d.%m.%Y %H:%M")
    d.text(_row("Chop etildi:", _sanitize(dt), w) + "\n")
    if data.get("shift_id") is not None:
        d.text(_row("Smena:", "#" + str(data["shift_id"]), w) + "\n")
    if data.get("cashier"):
        d.text(_row("Kassir:", _sanitize(data["cashier"]), w) + "\n")
    if data.get("register_name"):
        d.text(_row("Kassa:", _sanitize(data["register_name"]), w) + "\n")
    if data.get("start_time"):
        d.text(_row("Ochildi:", _sanitize(data["start_time"]), w) + "\n")
    if data.get("end_time"):
        d.text(_row("Yopildi:", _sanitize(data["end_time"]), w) + "\n")
    d.text("-" * w + "\n")

    # ── SAVDO / PUL / YASHIK — bitta ro'yxatdan (`_z_money_lines`) ──
    for bold, ln in _z_money_lines(data, w):
        d.set(text_type="B" if bold else "normal")
        d.text(ln + "\n")
    d.set(text_type="normal")
    d.text("=" * w + "\n")

    # ── Farq ──
    d.set(text_type="B", width=1, height=2)
    label = _shortage_label(data)
    d.text(_row(label + ":", _money(data.get("shortage")) + " UZS", w) + "\n")
    d.set(text_type="normal", width=1, height=1)
    d.text("=" * w + "\n")

    if data.get("notes"):
        d.set(align="left")
        d.text("Izoh: " + _sanitize(data["notes"]) + "\n")

    # ── Footer + cut ──
    d.set(align="center")
    d.text("\nKassir imzosi: ____________\n\n")
    d.set(align="left")
    d.text("\n\n")
    try:
        d.cut()
    except Exception:
        d.text("\n\n\n")

    return d.output


def render_z_report(data: Dict[str, Any], width_mm: int = 80) -> str:
    """Z-hisobotning o'qiladigan MATN ko'rinishi (mock log / preview)."""
    w = _chars(width_mm)
    L: List[str] = []
    L.append(_sanitize(data.get("store_name") or "RestoPOS").center(w))
    L.append("Z-HISOBOT (KUN YAKUNI)".center(w))
    for ln in _wrap(data.get("store_address") or "", w):
        if ln:
            L.append(ln.center(w))
    L.append("=" * w)
    L.append(_row("Chop etildi:", _sanitize(data.get("datetime") or datetime.now().strftime("%d.%m.%Y %H:%M")), w))
    if data.get("shift_id") is not None:
        L.append(_row("Smena:", "#" + str(data["shift_id"]), w))
    if data.get("cashier"):
        L.append(_row("Kassir:", _sanitize(data["cashier"]), w))
    if data.get("register_name"):
        L.append(_row("Kassa:", _sanitize(data["register_name"]), w))
    if data.get("start_time"):
        L.append(_row("Ochildi:", _sanitize(data["start_time"]), w))
    if data.get("end_time"):
        L.append(_row("Yopildi:", _sanitize(data["end_time"]), w))
    L.append("-" * w)
    L.extend(ln for _, ln in _z_money_lines(data, w))
    L.append("=" * w)
    L.append(_row(_shortage_label(data) + ":", _money(data.get("shortage")) + " UZS", w))
    L.append("=" * w)
    if data.get("notes"):
        L.append("Izoh: " + _sanitize(data["notes"]))
    return "\n".join(L)


TEST_DATA: Dict[str, Any] = {
    "store_name": "RestoPOS TEST",
    "store_address": "Toshkent sh., Test ko'chasi 1",
    "cashier": "Test Kassir",
    "receipt_number": "TEST-001",
    "items": [
        {"name": "Kofe Amerikano", "quantity": 2, "unit_price": 15000, "total": 30000},
        {"name": "Sendvich (uzun nom misoli uchun)", "quantity": 1, "unit_price": 25000, "total": 25000},
    ],
    "subtotal": 55000, "discount": 5000, "tax": 0, "service": 0, "total": 50000,
    "payment_method": "cash",
    "fiscal_number": "FK-2026-0001",
    "fiscal_qr_url": "https://ofd.soliq.uz/check?t=TEST123456",
}


def build_test_receipt(width_mm: int = 80) -> bytes:
    """Printerni tekshirish uchun namuna chek."""
    return build_receipt(TEST_DATA, width_mm)
