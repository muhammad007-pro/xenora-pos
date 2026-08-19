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
    d.text(_row("Jami:", _money(data.get("subtotal")), w) + "\n")
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
    L.append(_row("Jami:", _money(data.get("subtotal")), w))
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

    # ── Savdo taqsimoti ──
    d.set(text_type="B")
    d.text("SAVDO\n")
    d.set(text_type="normal")
    d.text(_row("Naqd:", _money(data.get("cash_sales")), w) + "\n")
    d.text(_row("Karta/Click:", _money(data.get("card_sales")), w) + "\n")
    if (data.get("credit_total") or 0) > 0:
        d.text(_row("Nasiya:", _money(data["credit_total"]), w) + "\n")
    d.set(text_type="B")
    d.text(_row("JAMI SOTUV:", _money(data.get("total_sales")) + " UZS", w) + "\n")
    d.set(text_type="normal")
    d.text(_row("Sotuvlar soni:", str(data.get("sales_count") or 0), w) + "\n")
    if (data.get("discount_total") or 0) > 0:
        d.text(_row("Chegirmalar:", _money(data["discount_total"]), w) + "\n")
    if (data.get("returns_total") or 0) > 0:
        d.text(_row("Qaytarishlar:", _money(data["returns_total"]), w) + "\n")
    d.text("-" * w + "\n")

    # ── Kassa hisob-kitobi ──
    d.set(text_type="B")
    d.text("KASSA\n")
    d.set(text_type="normal")
    d.text(_row("Boshlang'ich:", _money(data.get("starting_cash")), w) + "\n")
    d.text(_row("Naqd savdo:", "+" + _money(data.get("cash_sales")), w) + "\n")
    if (data.get("cash_refunds") or 0) > 0:
        d.text(_row("Naqd qaytarish:", "-" + _money(data["cash_refunds"]), w) + "\n")
    # Nasiya qarzi to'lovi — kassaga tushgan pul, LEKIN sotuv emas (sotuv o'z
    # kunida hisoblangan). Faqat NAQD qismi "bo'lishi kerak" ga kiradi.
    if (data.get("debt_paid_cash") or 0) > 0:
        d.text(_row("Nasiya to'lovi (naqd):", "+" + _money(data["debt_paid_cash"]), w) + "\n")
    if (data.get("debt_paid_card") or 0) > 0:
        d.text(_row("Nasiya to'lovi (karta):", _money(data["debt_paid_card"]), w) + "\n")
    d.text(_row("Bo'lishi kerak:", _money(data.get("expected_cash")), w) + "\n")
    d.text(_row("Sanaldi:", _money(data.get("counted_cash")), w) + "\n")
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
    L.append("SAVDO")
    L.append(_row("Naqd:", _money(data.get("cash_sales")), w))
    L.append(_row("Karta/Click:", _money(data.get("card_sales")), w))
    if (data.get("credit_total") or 0) > 0:
        L.append(_row("Nasiya:", _money(data["credit_total"]), w))
    L.append(_row("JAMI SOTUV:", _money(data.get("total_sales")) + " UZS", w))
    L.append(_row("Sotuvlar soni:", str(data.get("sales_count") or 0), w))
    if (data.get("discount_total") or 0) > 0:
        L.append(_row("Chegirmalar:", _money(data["discount_total"]), w))
    if (data.get("returns_total") or 0) > 0:
        L.append(_row("Qaytarishlar:", _money(data["returns_total"]), w))
    L.append("-" * w)
    L.append("KASSA")
    L.append(_row("Boshlang'ich:", _money(data.get("starting_cash")), w))
    L.append(_row("Naqd savdo:", "+" + _money(data.get("cash_sales")), w))
    if (data.get("cash_refunds") or 0) > 0:
        L.append(_row("Naqd qaytarish:", "-" + _money(data["cash_refunds"]), w))
    # Nasiya qarzi to'lovi — sotuv emas; faqat NAQD qismi kassa hisobiga kiradi
    if (data.get("debt_paid_cash") or 0) > 0:
        L.append(_row("Nasiya to'lovi (naqd):", "+" + _money(data["debt_paid_cash"]), w))
    if (data.get("debt_paid_card") or 0) > 0:
        L.append(_row("Nasiya to'lovi (karta):", _money(data["debt_paid_card"]), w))
    L.append(_row("Bo'lishi kerak:", _money(data.get("expected_cash")), w))
    L.append(_row("Sanaldi:", _money(data.get("counted_cash")), w))
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
