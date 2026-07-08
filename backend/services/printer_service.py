"""Universal printer ulanish qatlami (BOSQICH 2).

ESC/POS baytni (escpos_service yadrosi) ulanish REJIMIga qarab printerga
yuboradi. Yadro va ulanish AJRATILGAN (fiskal OFD kabi):

    escpos_service  →  bayt generatsiyasi (printerga bog'liq emas)
    printer_service →  baytni yuborish (mock / network / usb / spooler)

Rejim `config/printer.json` dan o'qiladi. DEFAULT = 'mock' — printer bo'lmasa
ham butun oqim ishlaydi (bayt faylga + matn log). Real printer kelganda faqat
sozlama o'zgaradi, kod tegmaydi.

config/printer.json kalitlari:
    mode        : "mock" | "network" | "usb" | "spooler" | "winprint"  (default "mock")
    enabled     : bool — umumiy yoqilgan/o'chirilgan
    width       : 58 | 80  (mm)
    ip          : "192.168.1.100" yoki "192.168.1.100:9100"  (network)
    net_port    : 9100  (network, ip ichida bo'lmasa)
    vendor_id   : "0x04b8"  (usb)
    product_id  : "0x0e15" (usb)
    spooler_port: "COM1" yoki "/dev/usb/lp0" yoki printer nomi  (spooler)
    printer_name: "Xprinter XP-58"  (winprint — Windows printer queue nomi)
"""
import os
import socket
from datetime import datetime
from typing import Any, Dict, Optional

from core.config_loader import config_loader
from services import escpos_service

RECEIPTS_DIR = "static/receipts"
DEFAULT_MODE = "mock"


# ── Config o'qish ─────────────────────────────────────────────────────────────
def get_config() -> Dict[str, Any]:
    """Joriy printer konfiguratsiyasi (config_loader global — settings PATCH
    in-memory'ni ham yangilaydi, shuning uchun har doim dolzarb)."""
    return config_loader.get("printer") or {}


def _mode(cfg: Dict[str, Any]) -> str:
    return (cfg.get("mode") or DEFAULT_MODE).lower()


def _width(cfg: Dict[str, Any]) -> int:
    return int(cfg.get("width") or cfg.get("paper_width") or 80)


def is_enabled(cfg: Optional[Dict[str, Any]] = None) -> bool:
    cfg = cfg if cfg is not None else get_config()
    return bool(cfg.get("enabled", False))


# ── Ulanish rejimlari (har biri bayt qabul qiladi, natija dict qaytaradi) ──────
def _send_mock(raw: bytes, label: str, text: Optional[str]) -> Dict[str, Any]:
    """Printer yo'q — baytni .bin ga, o'qiladigan matnni .txt ga yozadi + log."""
    os.makedirs(RECEIPTS_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    bin_path = os.path.join(RECEIPTS_DIR, f"{label}_{ts}.bin")
    with open(bin_path, "wb") as f:
        f.write(raw)
    txt_path = None
    if text is not None:
        txt_path = os.path.join(RECEIPTS_DIR, f"{label}_{ts}.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(text)
    print(f"[PRINTER:mock] {label} -> {bin_path} ({len(raw)} bayt)")
    return {"ok": True, "mode": "mock", "bytes": len(raw),
            "bin": bin_path, "txt": txt_path}


def _send_network(raw: bytes, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """IP:9100 raw socket orqali yuborish."""
    ip = (cfg.get("ip") or "").strip()
    if not ip:
        return {"ok": False, "mode": "network", "error": "IP ko'rsatilmagan"}
    port = int(cfg.get("net_port") or 9100)
    if ":" in ip:
        host, _, p = ip.partition(":")
        ip, port = host, int(p or port)
    try:
        with socket.create_connection((ip, port), timeout=5) as s:
            s.sendall(raw)
        print(f"[PRINTER:network] {ip}:{port} -> {len(raw)} bayt")
        return {"ok": True, "mode": "network", "bytes": len(raw), "target": f"{ip}:{port}"}
    except Exception as e:
        print(f"[PRINTER:network] XATO {ip}:{port}: {e}")
        return {"ok": False, "mode": "network", "error": str(e), "target": f"{ip}:{port}"}


def _send_usb(raw: bytes, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """USB printer (python-escpos Usb, vendor/product id bilan)."""
    vid = cfg.get("vendor_id")
    pid = cfg.get("product_id")
    if not vid or not pid:
        return {"ok": False, "mode": "usb", "error": "vendor_id/product_id ko'rsatilmagan"}
    try:
        vid_i = int(str(vid), 16) if isinstance(vid, str) else int(vid)
        pid_i = int(str(pid), 16) if isinstance(pid, str) else int(pid)
        from escpos.printer import Usb
        p = Usb(vid_i, pid_i)
        p._raw(raw)
        try:
            p.close()
        except Exception:
            pass
        print(f"[PRINTER:usb] {hex(vid_i)}:{hex(pid_i)} -> {len(raw)} bayt")
        return {"ok": True, "mode": "usb", "bytes": len(raw)}
    except Exception as e:
        print(f"[PRINTER:usb] XATO: {e}")
        return {"ok": False, "mode": "usb", "error": str(e)}


def _send_spooler(raw: bytes, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Lokal port/spooler — ESC/POS baytni to'g'ridan-to'g'ri portga yozish."""
    port = (cfg.get("spooler_port") or cfg.get("port") or "").strip()
    if not port:
        return {"ok": False, "mode": "spooler", "error": "port ko'rsatilmagan"}
    try:
        target = port
        if os.name == "nt" and port.upper().startswith("COM"):
            target = r"\\.\{}".format(port)  # Windows COM raw
        with open(target, "wb") as f:
            f.write(raw)
        print(f"[PRINTER:spooler] {port} -> {len(raw)} bayt")
        return {"ok": True, "mode": "spooler", "bytes": len(raw), "target": port}
    except Exception as e:
        print(f"[PRINTER:spooler] XATO {port}: {e}")
        return {"ok": False, "mode": "spooler", "error": str(e), "target": port}


def _send_winprint(raw: bytes, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Windows printer queue'siga RAW ESC/POS yuborish (pywin32 / win32print).

    COM port ochmaydigan USB printerlar uchun (mas. Xprinter XP-58, port
    USB001) — baytni bevosita Windows spooler queue'ga RAW datatype bilan
    yuboradi. `import win32print` FUNKSIYA ICHIDA — Windows'siz / pywin32'siz
    muhitda modul yuklanishi buzilmaydi."""
    name = (cfg.get("printer_name") or cfg.get("queue_name") or "Xprinter XP-58").strip()
    if not name:
        return {"ok": False, "mode": "winprint", "error": "printer_name ko'rsatilmagan"}
    try:
        import win32print
    except Exception as e:
        return {"ok": False, "mode": "winprint",
                "error": f"win32print import xato (pywin32 yo'q?): {e}", "target": name}
    try:
        h = win32print.OpenPrinter(name)
        try:
            win32print.StartDocPrinter(h, 1, ("Chek", None, "RAW"))
            try:
                win32print.StartPagePrinter(h)
                win32print.WritePrinter(h, raw)
                win32print.EndPagePrinter(h)
            finally:
                win32print.EndDocPrinter(h)
        finally:
            win32print.ClosePrinter(h)
        print(f"[PRINTER:winprint] {name} -> {len(raw)} bayt")
        return {"ok": True, "mode": "winprint", "bytes": len(raw), "target": name}
    except Exception as e:
        print(f"[PRINTER:winprint] XATO {name}: {e}")
        return {"ok": False, "mode": "winprint", "error": str(e), "target": name}


def _dispatch(raw: bytes, label: str, text: Optional[str] = None, cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Baytni joriy rejimga qarab yuboradi. Real rejim muvaffaqiyatsiz bo'lsa —
    mock'ga tushib qoladi (chek yo'qolmaydi).

    cfg berilsa o'shani ishlatadi (tenant-scoped), berilmasa global get_config()
    fallback (orqaga moslik)."""
    cfg = cfg if cfg is not None else get_config()
    mode = _mode(cfg)
    if mode == "network":
        res = _send_network(raw, cfg)
    elif mode == "usb":
        res = _send_usb(raw, cfg)
    elif mode == "spooler":
        res = _send_spooler(raw, cfg)
    elif mode == "winprint":
        res = _send_winprint(raw, cfg)
    else:
        return _send_mock(raw, label, text)
    # Real rejim xato bersa — mock zaxira (bayt fayl saqlanadi)
    if not res.get("ok"):
        fallback = _send_mock(raw, label + "_failed", text)
        res["fallback"] = fallback
    return res


# ── Asosiy API ────────────────────────────────────────────────────────────────
def print_receipt(data: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Mijoz chekini chiqarish (rejimga qarab).

    cfg berilsa tenant-scoped, berilmasa global get_config() fallback."""
    cfg = cfg if cfg is not None else get_config()
    if not is_enabled(cfg):
        return {"ok": False, "reason": "disabled", "mode": _mode(cfg)}
    w = _width(cfg)
    raw = escpos_service.build_receipt(data, w)
    text = escpos_service.render_text(data, w)
    return _dispatch(raw, "receipt", text, cfg)


def print_z_report(data: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Z-hisobot (kun yakuni / smena yopilishi) chekini chiqarish.

    cfg berilsa tenant-scoped, berilmasa global get_config() fallback."""
    cfg = cfg if cfg is not None else get_config()
    if not is_enabled(cfg):
        return {"ok": False, "reason": "disabled", "mode": _mode(cfg)}
    w = _width(cfg)
    raw = escpos_service.build_z_report(data, w)
    text = escpos_service.render_z_report(data, w)
    return _dispatch(raw, "zreport", text, cfg)


def print_test(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Test cheki chiqarish (enabled tekshiruvisiz — sozlashda sinash uchun).

    cfg berilsa tenant-scoped, berilmasa global get_config() fallback."""
    cfg = cfg if cfg is not None else get_config()
    w = _width(cfg)
    raw = escpos_service.build_test_receipt(w)
    text = escpos_service.render_text(escpos_service.TEST_DATA, w)
    res = _dispatch(raw, "test", text, cfg)
    res["mode"] = _mode(cfg)
    res["width"] = w
    return res


# ── Orqaga moslik: eski PrinterService API (order.py, settings.py ishlatadi) ──
class PrinterService:
    """Eski chaqiruvlar buzilmasligi uchun moslik qatlami."""

    @staticmethod
    def is_available() -> bool:
        return is_enabled()

    @staticmethod
    def print_receipt(data: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return print_receipt(data, cfg)

    @staticmethod
    def print_customer_receipt(order, payment) -> bool:
        """Order/Payment ORM dan chek ma'lumotini yig'ib chiqaradi (BOSQICH 4'da
        to'liq ulanadi)."""
        try:
            data = _order_to_receipt(order, payment)
            return bool(print_receipt(data).get("ok"))
        except Exception as e:
            print(f"[PRINTER] customer receipt xato: {e}")
            return False

    @staticmethod
    def print_kitchen_receipt(order, cfg: Optional[Dict[str, Any]] = None) -> bool:
        """Oshxona cheki — sodda matnli ESC/POS ticket.

        cfg berilsa tenant-scoped, berilmasa global get_config() fallback."""
        try:
            cfg = cfg if cfg is not None else get_config()
            if not is_enabled(cfg):
                return False
            from escpos.printer import Dummy
            w = _width(cfg)
            d = Dummy()
            try:
                d._raw(b"\x1b@")
            except Exception:
                pass
            d.set(align="center", text_type="B", width=2, height=2)
            d.text("OSHXONA\n")
            d.set(align="left", text_type="normal", width=1, height=1)
            d.text(f"Buyurtma #{getattr(order, 'order_number', getattr(order, 'id', '-'))}\n")
            d.text("-" * w + "\n")
            for it in getattr(order, "items", []) or []:
                nm = getattr(getattr(it, "product", None), "name", "")
                d.text(f"{getattr(it, 'quantity', 1)} x {nm}\n")
            d.text("-" * w + "\n\n")
            try:
                d.cut()
            except Exception:
                pass
            _dispatch(d.output, "kitchen", None, cfg)
            return True
        except Exception as e:
            print(f"[PRINTER] kitchen receipt xato: {e}")
            return False

    @staticmethod
    def test_printer(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        res = print_test(cfg)
        return {
            "success": bool(res.get("ok")),
            "mode": res.get("mode"),
            "width": res.get("width"),
            "detail": res,
        }


def _order_to_receipt(order, payment=None) -> Dict[str, Any]:
    """ORM Order → build_receipt data dict (eng yaxshi imkon bo'yicha)."""
    items = []
    for it in getattr(order, "items", []) or []:
        prod = getattr(it, "product", None)
        items.append({
            "name": getattr(prod, "name", ""),
            "quantity": getattr(it, "quantity", 1),
            "unit_price": getattr(it, "unit_price", None),
            "total": getattr(it, "total_price", 0),
        })
    cashier = None
    w = getattr(order, "waiter", None)
    if w:
        cashier = getattr(w, "full_name", None)
    # Do'kon nomi order.cafe'dan (qattiq kod "RestoPOS" emas — tenant ma'lumoti)
    cafe = getattr(order, "cafe", None)
    store_name = getattr(cafe, "name", None) or "Do'kon"
    return {
        "store_name": store_name,
        "store_address": getattr(cafe, "address", None),
        "receipt_number": getattr(order, "order_number", getattr(order, "id", "")),
        "cashier": cashier,
        "items": items,
        "subtotal": getattr(order, "total_amount", 0),
        "discount": getattr(order, "discount_amount", 0),
        "tax": getattr(order, "tax_amount", 0),
        "service": getattr(order, "service_charge", 0),
        "total": getattr(order, "final_amount", getattr(order, "total_amount", 0)),
        "payment_method": getattr(payment, "method", None) if payment else None,
        "fiscal_number": getattr(order, "fiscal_number", None),
        "fiscal_qr_url": getattr(order, "fiscal_qr_url", None),
    }
