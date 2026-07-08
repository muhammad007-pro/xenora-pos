"""
OFD Fiskal Integratsiya Xizmati — BOSQICH 28

Ikkita rejim:
  mock — haqiqiy OFD yo'q, test uchun soxta chek raqami/sign generatsiyasi
  live — real OFD API ga POST (soliq.uz yoki SoliqPro)

Bu fayl butunlay izolyatsiya qilingan: payment.py faqat send_to_ofd() ni chaqiradi.
Real API formati o'zgarganda FAQAT shu faylni o'zgartirish kifoya.
"""

import logging
import hashlib
import time
import json
from datetime import datetime
from typing import Optional

log = logging.getLogger(__name__)

# ── OFD javob modeli ──────────────────────────────────────────────────────────

class OFDResult:
    __slots__ = ("success", "fiscal_number", "fiscal_sign", "qr_url", "raw", "error")

    def __init__(
        self,
        success: bool,
        fiscal_number: Optional[int] = None,
        fiscal_sign: Optional[str] = None,
        qr_url: Optional[str] = None,
        raw: Optional[dict] = None,
        error: Optional[str] = None,
    ):
        self.success       = success
        self.fiscal_number = fiscal_number
        self.fiscal_sign   = fiscal_sign
        self.qr_url        = qr_url
        self.raw           = raw or {}
        self.error         = error


# ── QR URL formatlovchi ───────────────────────────────────────────────────────

def _build_qr_url(
    amount: float,
    fiscal_number: int,
    fiscal_sign: str,
    kassa_id: str,
    dt: datetime,
) -> str:
    """O'zbekiston OFD QR formati: consumer.invoice.uz/check"""
    date_str = dt.strftime("%Y%m%d%H%M%S")
    amount_tiyin = int(round(amount * 100))
    return (
        f"https://consumer.invoice.uz/check"
        f"?t={date_str}"
        f"&s={amount_tiyin}"
        f"&fn={kassa_id}"
        f"&i={fiscal_number}"
        f"&fp={fiscal_sign}"
        f"&n=1"
    )


# ── MOCK rejim ────────────────────────────────────────────────────────────────

def _next_mock_fiscal_number() -> int:
    """Mock: oddiy vaqt asosidagi pseudo-unikal raqam."""
    ts = int(time.time() * 1000) % 10_000_000
    return ts


def _mock_fiscal_sign(order_id: int, amount: float, inn: str) -> str:
    """Mock: deterministik test sign (haqiqiy kriptografiya emas)."""
    raw = f"{order_id}:{amount:.2f}:{inn}:{time.time()}"
    return hashlib.md5(raw.encode()).hexdigest()[:8].upper()


def _send_mock(order, fiscal_config: dict) -> OFDResult:
    """Mock rejim — OFD ga haqiqiy so'rov ketmaydi."""
    kassa_id = fiscal_config.get("kassa_id") or "TEST001"
    inn      = fiscal_config.get("inn")      or "000000000"
    amount   = float(order.final_amount or 0)
    fn       = _next_mock_fiscal_number()
    sign     = _mock_fiscal_sign(order.id, amount, inn)
    qr       = _build_qr_url(amount, fn, sign, kassa_id, datetime.now())

    log.info(
        "[OFD MOCK] order=%s fn=%s sign=%s qr=%s",
        order.id, fn, sign, qr[:60]
    )
    return OFDResult(
        success=True,
        fiscal_number=fn,
        fiscal_sign=sign,
        qr_url=qr,
        raw={"mode": "mock", "fn": fn, "sign": sign},
    )


# ── LIVE rejim ────────────────────────────────────────────────────────────────

def _build_ofd_payload(order, fiscal_config: dict) -> dict:
    """
    Umumiy chek payload — soliq.uz va SoliqPro uchun asosiy format.
    Operatorga qarab _send_live_* funksiyalar buni moslashtiradi.
    """
    items = []
    for item in (order.items or []):
        items.append({
            "name":     item.product.name if item.product else f"Mahsulot #{item.product_id}",
            "qty":      float(item.quantity or 1),
            "price":    float(item.price or 0),
            "amount":   float(item.total_price or 0),
            "vat_pct":  12,  # O'zbekistonda standart QQS 12%
        })

    return {
        "terminal_id":  fiscal_config.get("kassa_id", ""),
        "inn":          fiscal_config.get("inn", ""),
        "order_id":     str(order.id),
        "order_number": str(order.order_number),
        "amount":       float(order.final_amount or 0),
        "vat_amount":   float(order.tax_amount or 0),
        "items":        items,
        "payment_type": "cash",   # payment.py da to'g'ri qiymat beriladi
        "time":         datetime.now().isoformat(),
    }


def _send_live_soliquz(order, fiscal_config: dict) -> OFDResult:
    """
    soliq.uz OFD API integratsiyasi.
    Hujjat: https://ofd.soliq.uz/docs (davlat operatori)
    """
    try:
        import httpx
    except ImportError:
        return OFDResult(False, error="httpx kutubxonasi o'rnatilmagan: pip install httpx")

    endpoint = fiscal_config.get("endpoint") or "https://ofd.soliq.uz/api/v1/receipt"
    api_key  = fiscal_config.get("api_key", "")
    payload  = _build_ofd_payload(order, fiscal_config)

    # soliq.uz o'ziga xos format
    body = {
        "TerminalID": payload["terminal_id"],
        "TIN":        payload["inn"],
        "ReceiptSeq": payload["order_number"],
        "DateTime":   payload["time"],
        "TotalAmount": int(payload["amount"] * 100),  # tiyin
        "VATAmount":   int(payload["vat_amount"] * 100),
        "Items": [
            {
                "Name":   i["name"],
                "SPIC":   "0",          # mahsulot kodi — ixtiyoriy
                "Units":  796,          # dona
                "Amount": int(i["amount"] * 100),
                "VATPercent": i["vat_pct"],
                "Price":  int(i["price"] * 100),
                "Qty":    i["qty"] * 1000,  # ming ulush
            }
            for i in payload["items"]
        ],
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(endpoint, json=body, headers=headers)
        data = resp.json()

        if resp.status_code == 200 and data.get("ReceiptID"):
            fn    = int(data["ReceiptID"])
            sign  = str(data.get("FiscalSign", ""))
            kassa = fiscal_config.get("kassa_id", "")
            qr    = _build_qr_url(payload["amount"], fn, sign, kassa, datetime.now())
            return OFDResult(success=True, fiscal_number=fn, fiscal_sign=sign, qr_url=qr, raw=data)
        else:
            err = data.get("Message") or data.get("error") or str(resp.status_code)
            return OFDResult(False, error=f"soliq.uz: {err}", raw=data)

    except Exception as exc:
        return OFDResult(False, error=f"soliq.uz ulanish xatosi: {exc}")


def _send_live_soliqpro(order, fiscal_config: dict) -> OFDResult:
    """
    SoliqPro OFD API integratsiyasi.
    Hujjat: https://soliqpro.uz/docs/api (xususiy operator)
    """
    try:
        import httpx
    except ImportError:
        return OFDResult(False, error="httpx kutubxonasi o'rnatilmagan: pip install httpx")

    endpoint = fiscal_config.get("endpoint") or "https://api.soliqpro.uz/v2/receipts"
    api_key  = fiscal_config.get("api_key", "")
    payload  = _build_ofd_payload(order, fiscal_config)

    # SoliqPro o'ziga xos format
    body = {
        "kassaId":    payload["terminal_id"],
        "tin":        payload["inn"],
        "docNo":      payload["order_number"],
        "docTime":    payload["time"],
        "totalSum":   payload["amount"],
        "vatSum":     payload["vat_amount"],
        "items": [
            {
                "name":    i["name"],
                "barcode": "",
                "qty":     i["qty"],
                "price":   i["price"],
                "total":   i["amount"],
                "vat":     i["vat_pct"],
            }
            for i in payload["items"]
        ],
    }

    headers = {
        "X-Api-Key":    api_key,
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(endpoint, json=body, headers=headers)
        data = resp.json()

        if resp.status_code in (200, 201) and data.get("fiscalNumber"):
            fn    = int(data["fiscalNumber"])
            sign  = str(data.get("fiscalSign", ""))
            kassa = fiscal_config.get("kassa_id", "")
            qr    = _build_qr_url(payload["amount"], fn, sign, kassa, datetime.now())
            return OFDResult(success=True, fiscal_number=fn, fiscal_sign=sign, qr_url=qr, raw=data)
        else:
            err = data.get("message") or data.get("error") or str(resp.status_code)
            return OFDResult(False, error=f"SoliqPro: {err}", raw=data)

    except Exception as exc:
        return OFDResult(False, error=f"SoliqPro ulanish xatosi: {exc}")


# ── Asosiy kirish nuqtasi ─────────────────────────────────────────────────────

def send_to_ofd(order, fiscal_config: dict) -> OFDResult:
    """
    OFD ga chek yuboradi.

    fiscal_config:
        enabled   : bool         — yoqilganmi
        mode      : 'mock'|'live'
        operator  : 'soliquz'|'soliqpro'
        inn       : str          — INN/STIR
        kassa_id  : str          — terminal ID
        api_key   : str          — OFD API token
        endpoint  : str          — ixtiyoriy endpoint override

    Qaytaradi: OFDResult (success, fiscal_number, qr_url, error)
    """
    if not fiscal_config.get("enabled"):
        return OFDResult(False, error="Fiskal integratsiya o'chirilgan")

    mode = fiscal_config.get("mode", "mock")

    if mode == "mock":
        return _send_mock(order, fiscal_config)

    # live rejim — operator tanlash
    operator = fiscal_config.get("operator", "soliquz")
    if operator == "soliqpro":
        return _send_live_soliqpro(order, fiscal_config)
    else:
        return _send_live_soliquz(order, fiscal_config)
