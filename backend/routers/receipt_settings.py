"""Chek / Kvitansiya sozlamalari — do'kon nomi, manzil, rahmat yozuvi, QR"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import ReceiptSettings, User
from deps import resolve_tenant_id, get_current_active_user, has_permission

router = APIRouter()


@router.get("/")
async def get_receipt_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Joriy tenant chek sozlamalarini olish"""
    tid = resolve_tenant_id(db, current_user)
    settings = db.query(ReceiptSettings).filter(ReceiptSettings.tenant_id == tid).first()
    if not settings:
        return _default_settings(tid)
    return _settings_dict(settings)


@router.put("/")
async def update_receipt_settings(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_settings")),
):
    """Chek sozlamalarini yangilash (yo'q bo'lsa yaratish)"""
    tid = resolve_tenant_id(db, current_user)
    settings = db.query(ReceiptSettings).filter(ReceiptSettings.tenant_id == tid).first()

    allowed = {"store_name", "address", "phone", "tax_id", "header_text",
               "footer_text", "show_logo", "qr_enabled", "qr_url",
               "paper_width", "font_size"}

    if not settings:
        settings = ReceiptSettings(tenant_id=tid)
        db.add(settings)

    for k, v in data.items():
        if k in allowed:
            setattr(settings, k, v)

    db.commit()
    db.refresh(settings)
    return _settings_dict(settings)


@router.get("/preview")
async def preview_receipt(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Namunaviy chek HTML (printga tayyor)"""
    tid = resolve_tenant_id(db, current_user)
    s = db.query(ReceiptSettings).filter(ReceiptSettings.tenant_id == tid).first()
    cfg = _settings_dict(s) if s else _default_settings(tid)

    html = _build_receipt_html(cfg, sample=True)
    return {"html": html}


def _build_receipt_html(cfg: dict, sample: bool = False) -> str:
    width = cfg.get("paper_width", 80)
    font = "11px" if cfg.get("font_size") == "small" else ("14px" if cfg.get("font_size") == "large" else "12px")
    lines = []
    lines.append(f'<div style="font-family:monospace;font-size:{font};width:{width}mm;margin:0 auto;">')
    if cfg.get("store_name"):
        lines.append(f'<div style="text-align:center;font-weight:bold;font-size:1.2em">{cfg["store_name"]}</div>')
    if cfg.get("address"):
        lines.append(f'<div style="text-align:center">{cfg["address"]}</div>')
    if cfg.get("phone"):
        lines.append(f'<div style="text-align:center">Tel: {cfg["phone"]}</div>')
    if cfg.get("header_text"):
        lines.append(f'<div style="text-align:center;margin:4px 0">{cfg["header_text"]}</div>')
    lines.append('<hr style="border-top:1px dashed #000">')
    if sample:
        lines.append('<div><span>Non</span><span style="float:right">1×5,000 = 5,000</span></div>')
        lines.append('<div><span>Suv 0.5L</span><span style="float:right">2×2,000 = 4,000</span></div>')
        lines.append('<hr style="border-top:1px dashed #000">')
        lines.append('<div><b>JAMI: 9,000 so\'m</b></div>')
        lines.append('<div>To\'lov: Naqd</div>')
    lines.append('<hr style="border-top:1px dashed #000">')
    if cfg.get("footer_text"):
        lines.append(f'<div style="text-align:center;margin:4px 0">{cfg["footer_text"]}</div>')
    if cfg.get("qr_enabled") and cfg.get("qr_url"):
        lines.append(f'<div style="text-align:center;margin:6px 0">'
                     f'<img id="receiptQR" style="width:80px;height:80px"/></div>')
        lines.append(f'<script>try{{JsBarcode("#receiptQR","'
                     f'{cfg["qr_url"]}",{{format:"QR_CODE",width:2,height:80}})}}'
                     f'catch(e){{}}</script>')
    lines.append('</div>')
    return "\n".join(lines)


def _settings_dict(s: ReceiptSettings) -> dict:
    return {
        "tenant_id": s.tenant_id,
        "store_name": s.store_name,
        "address": s.address,
        "phone": s.phone,
        "tax_id": s.tax_id,
        "header_text": s.header_text,
        "footer_text": s.footer_text,
        "show_logo": s.show_logo,
        "qr_enabled": s.qr_enabled,
        "qr_url": s.qr_url,
        "paper_width": s.paper_width,
        "font_size": s.font_size,
    }


def _default_settings(tenant_id: int) -> dict:
    return {
        "tenant_id": tenant_id,
        "store_name": None,
        "address": None,
        "phone": None,
        "tax_id": None,
        "header_text": None,
        "footer_text": "Xarid uchun rahmat!",
        "show_logo": False,
        "qr_enabled": False,
        "qr_url": None,
        "paper_width": 80,
        "font_size": "normal",
    }
