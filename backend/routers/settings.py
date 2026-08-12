from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Any, Dict

from database import get_db
from models import User
from deps import get_current_user, has_permission, resolve_tenant_id, get_current_active_user
from schemas import MessageResponse
from core.tenant_config import get_tenant_config, set_tenant_config

router = APIRouter()

@router.get("/")
async def get_all_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_settings"))
):
    """Barcha sozlamalarni olish"""
    tid = resolve_tenant_id(db, current_user)
    return {
        # BOSQICH 41: app/kitchen/printer endi tenant-scoped — har tenant o'z qiymati.
        # Tenant yozuvi bo'lmasa global qiymat DEFAULT bo'lib qoladi (ma'lumot yo'qolmaydi).
        "app": get_tenant_config(db, tid, "app"),
        "printer": get_tenant_config(db, tid, "printer"),
        "kitchen": get_tenant_config(db, tid, "kitchen"),
        # payment tenant-scoped (Click/Payme kalitlari)
        "payment": get_tenant_config(db, tid, "payment")
    }

@router.post("/printer/test")
async def test_printer(
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_settings"))
):
    """Printerni test qilish (BOSQICH 40: tenant-scoped)"""
    from services.printer_service import PrinterService

    tid = resolve_tenant_id(db, current_user)
    cfg = get_tenant_config(db, tid, "printer")
    result = PrinterService.test_printer(cfg=cfg)
    mode = result.get("mode")
    if result.get("success"):
        result["message"] = f"Test cheki yuborildi (rejim: {mode})"
    else:
        d = result.get("detail") or {}
        result["message"] = f"Xato (rejim: {mode}): {d.get('error') or d.get('reason') or 'nomaʼlum'}"
    return result


@router.get("/printer/status")
async def printer_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),   # auth majburiy → token'siz toza 401 (500 emas)
):
    """POS uchun yengil printer holati (kassir ham o'qiy oladi — to'liq sozlama emas).

    BOSQICH 40: tenant-scoped printer config."""
    from services.printer_service import is_enabled

    tid = resolve_tenant_id(db, current_user)
    cfg = get_tenant_config(db, tid, "printer") or {}
    return {
        "enabled":    is_enabled(cfg),
        "auto_print": bool(cfg.get("auto_print")),
        "mode":       cfg.get("mode", "mock"),
        "width":      int(cfg.get("width") or 80),
        # LOKAL silent print uchun Windows printer nomi (bo'sh → OS default printer)
        "printer_name": cfg.get("printer_name") or "",
        # Pul qutisi (cash drawer, LAN 2-bosqich) — TenantSettings JSON'ga qo'shildi,
        # migratsiya YO'Q (printer_name bilan bir xil config_name="printer" blob).
        "open_drawer_enabled": bool(cfg.get("open_drawer_enabled", False)),
        "open_drawer_mode":    cfg.get("open_drawer_mode", "cash_only"),   # 'always' | 'cash_only'
    }


@router.get("/printer")
async def get_printer_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_settings"))
):
    """To'liq printer sozlamalari (BOSQICH 40: tenant-scoped)"""
    tid = resolve_tenant_id(db, current_user)
    return get_tenant_config(db, tid, "printer") or {}


@router.patch("/printer")
async def update_printer_settings(
    settings: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_settings"))
):
    """Printer sozlamalarini yangilash (BOSQICH 40: tenant-scoped)"""
    tid = resolve_tenant_id(db, current_user)
    if tid is None:
        raise HTTPException(status_code=400, detail="Printer sozlama saqlash uchun tenant (kafe) aniqlanmadi")
    config = get_tenant_config(db, tid, "printer") or {}
    config.update(settings)
    set_tenant_config(db, tid, "printer", config)
    return MessageResponse(message="Printer sozlamalari saqlandi")

# ── ETIKETKA PRINTERI (TSPL: Xprinter XP-350B / XP-365B) ─────────────────────
# Chek printeri sozlamalaridan (yuqoridagi /printer va ReceiptSettings jadvali)
# MUTLAQO ALOHIDA: bu boshqa qurilma, boshqa til (TSPL), o'z ulanishi.
# Saqlanish joyi: TenantSettings(config_name="label_printer") — MIGRATSIYA YO'Q.
#
# ULANISH TURI:
#   "usb" — Windows drayveri o'rnatilgan printer (XP-365B da LAN porti YO'Q).
#           TSPL baytlari printer NAVBATIGA RAW yuboriladi → printer_name kerak.
#   "lan" — tarmoq printeri (XP-350B), TCP 9100 → printer_ip kerak.
# Standart "usb" — jonli mijozda (Faza Parfum) aynan shunday.
#
# DIQQAT: bu marshrutlar fayl oxiridagi umumiy `/{config_name}` dan OLDIN
# turishi SHART (FastAPI ro'yxatga olish tartibida moslaydi), aks holda
# "label-printer" catch-all'ga tushib, yozuv yo'q tenantda 404 qaytarardi.
LABEL_PRINTER_DEFAULTS = {
    "enabled": False,
    "connection_type": "usb",   # "usb" | "lan"
    "printer_name": "",         # USB: Windows'dagi printer nomi
    "printer_ip": "",           # LAN: IP manzil
    "printer_port": 9100,       # LAN: RAW/JetDirect
    "label_width": 40,          # mm
    "label_height": 30,         # mm
    "gap": 2,                   # mm — etiketkalar orasidagi bo'shliq
    "density": 8,               # 0..15 qoralik
    "speed": 4,                 # dyuym/sekund
}

LABEL_CONNECTION_TYPES = ("usb", "lan")

# Har maydon uchun (tur, min, maks). Chegaralar TSPL/XP-350B doirasida —
# noto'g'ri qiymat printerni "osib" qo'yishi yoki bo'sh etiketka chiqarishi mumkin.
_LABEL_NUM_RANGES = {
    "printer_port": (int, 1, 65535),
    "label_width": (int, 10, 120),
    "label_height": (int, 10, 120),
    "gap": (int, 0, 20),
    "density": (int, 0, 15),
    "speed": (int, 1, 15),
}


def _label_printer_normalize(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Saqlangan (yoki kelgan) dict'ni to'liq va tur-jihatdan to'g'ri holatga keltiradi.

    Yetishmagan kalit → default. Shu sabab ESKI tenant (yozuv yo'q) ham 404/500
    emas, to'liq default oladi — orqaga moslik.
    """
    src = raw if isinstance(raw, dict) else {}
    out = dict(LABEL_PRINTER_DEFAULTS)

    out["enabled"] = bool(src.get("enabled", LABEL_PRINTER_DEFAULTS["enabled"]))

    conn = str(src.get("connection_type", LABEL_PRINTER_DEFAULTS["connection_type"]) or "").strip().lower()
    if conn not in LABEL_CONNECTION_TYPES:
        raise HTTPException(status_code=400,
                            detail=f"'connection_type' faqat {' yoki '.join(LABEL_CONNECTION_TYPES)} bo'lishi mumkin")
    out["connection_type"] = conn

    for key in ("printer_name", "printer_ip"):
        val = src.get(key, LABEL_PRINTER_DEFAULTS[key])
        out[key] = str(val).strip() if val is not None else ""

    for key, (_cast, lo, hi) in _LABEL_NUM_RANGES.items():
        val = src.get(key, LABEL_PRINTER_DEFAULTS[key])
        try:
            num = int(float(val))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"'{key}' butun son bo'lishi kerak")
        if num < lo or num > hi:
            raise HTTPException(status_code=400, detail=f"'{key}' {lo}..{hi} oralig'ida bo'lishi kerak")
        out[key] = num

    return out


@router.get("/label-printer")
async def get_label_printer_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_settings"))
):
    """Etiketka printeri sozlamalari (yozuv bo'lmasa — to'liq default)."""
    tid = resolve_tenant_id(db, current_user)
    stored = get_tenant_config(db, tid, "label_printer") if tid else {}
    return _label_printer_normalize(stored)


@router.patch("/label-printer")
async def update_label_printer_settings(
    settings: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_settings"))
):
    """Etiketka printeri sozlamalarini saqlash (qisman yuborish mumkin).

    Chek printeri sozlamalariga TEGMAYDI — alohida config_name.
    """
    tid = resolve_tenant_id(db, current_user)
    if not tid:
        raise HTTPException(status_code=400, detail="Sozlama saqlash uchun tenant (kafe) aniqlanmadi")

    current = _label_printer_normalize(get_tenant_config(db, tid, "label_printer"))
    # Faqat tanilgan kalitlar qabul qilinadi — begona maydonlar JSON'ni shishirmasin.
    incoming = {k: v for k, v in (settings or {}).items() if k in LABEL_PRINTER_DEFAULTS}
    current.update(incoming)
    saved = _label_printer_normalize(current)   # yangi qiymatlarni ham validatsiya qiladi

    # Yoqilgan bo'lsa ulanish ma'lumoti majburiy — aks holda kassir "yoqdim,
    # ishlamayapti" holatiga tushadi. Talab ulanish TURIGA bog'liq.
    if saved["enabled"]:
        if saved["connection_type"] == "usb" and not saved["printer_name"]:
            raise HTTPException(status_code=400,
                                detail="USB etiketka printeri yoqilgan — printer nomi tanlanishi shart")
        if saved["connection_type"] == "lan" and not saved["printer_ip"]:
            raise HTTPException(status_code=400,
                                detail="LAN etiketka printeri yoqilgan — IP manzil kiritilishi shart")

    set_tenant_config(db, tid, "label_printer", saved)
    return saved


@router.get("/fiscal")
async def get_fiscal_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_settings"))
):
    """Fiskal/soliq sozlamalarini olish (BOSQICH 40: tenant-scoped)"""
    tid = resolve_tenant_id(db, current_user)
    config = get_tenant_config(db, tid, "fiscal") or {}
    # API kalitini maskalash (faqat mavjudligini ko'rsatish)
    if config.get("api_key"):
        config = {**config, "api_key_set": True, "api_key": ""}
    return config

@router.patch("/fiscal")
async def update_fiscal_settings(
    settings: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_settings"))
):
    """Fiskal sozlamalarni yangilash (BOSQICH 40: tenant-scoped)"""
    tid = resolve_tenant_id(db, current_user)
    if tid is None:
        raise HTTPException(status_code=400, detail="Fiskal sozlama saqlash uchun tenant (kafe) aniqlanmadi")
    # bo'sh api_key ni e'tiborsiz qoldirish (maskalangan bo'lsa)
    if "api_key" in settings and not settings["api_key"]:
        settings.pop("api_key")
    # mavjud tenant qiymati ustiga merge (faqat berilgan kalitlar yangilanadi)
    config = get_tenant_config(db, tid, "fiscal") or {}
    config.update(settings)
    set_tenant_config(db, tid, "fiscal", config)
    return {"message": "Fiskal sozlamalar saqlandi"}

@router.get("/payment")
async def get_payment_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_settings"))
):
    """To'lov shlyuzi sozlamalari (Click/Payme) — BOSQICH 40: tenant-scoped"""
    tid = resolve_tenant_id(db, current_user)
    return get_tenant_config(db, tid, "payment") or {}

@router.patch("/payment")
async def update_payment_settings(
    settings: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_settings"))
):
    """To'lov sozlamalarini yangilash (Click/Payme) — BOSQICH 40: tenant-scoped"""
    tid = resolve_tenant_id(db, current_user)
    if tid is None:
        raise HTTPException(status_code=400, detail="To'lov sozlama saqlash uchun tenant (kafe) aniqlanmadi")
    config = get_tenant_config(db, tid, "payment") or {}
    config.update(settings)
    set_tenant_config(db, tid, "payment", config)
    return MessageResponse(message="To'lov sozlamalari saqlandi")

@router.post("/fiscal/test")
async def test_fiscal_connection(
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_settings"))
):
    """Fiskal OFD ulanishini tekshirish (BOSQICH 40: tenant-scoped)"""
    tid = resolve_tenant_id(db, current_user)
    config = get_tenant_config(db, tid, "fiscal") or {}
    if not config.get("enabled"):
        return {"success": False, "message": "Fiskal integratsiya yoqilmagan"}
    if not config.get("inn"):
        return {"success": False, "message": "INN kiritilmagan"}
    return {"success": True, "message": f"INN {config.get('inn')} — sozlama to'g'ri. Real OFD ulanish uchun API kalit kerak."}

# ── Oylik savdo maqsadi (dashboard ring) — MOLIYAVIY: view_finance bilan ──
@router.get("/monthly-goal")
async def get_monthly_goal(
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_finance"))
):
    """Oylik savdo maqsadini o'qish (tenant-scoped)."""
    tid = resolve_tenant_id(db, current_user)
    cfg = get_tenant_config(db, tid, "monthly_goal") if tid is not None else {}
    return {"target": float((cfg or {}).get("target") or 0)}


@router.patch("/monthly-goal")
async def update_monthly_goal(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_finance"))
):
    """Oylik savdo maqsadini belgilash (egasi) — tenant-scoped."""
    tid = resolve_tenant_id(db, current_user)
    if tid is None:
        raise HTTPException(status_code=400, detail="Maqsad saqlash uchun tenant (kafe) aniqlanmadi")
    try:
        target = float(payload.get("target") or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Noto'g'ri maqsad qiymati")
    if target < 0:
        raise HTTPException(status_code=400, detail="Maqsad manfiy bo'lishi mumkin emas")
    set_tenant_config(db, tid, "monthly_goal", {"target": target})
    return {"target": target, "message": "Oylik maqsad saqlandi"}


@router.get("/{config_name}")
async def get_settings(
    config_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_settings"))
):
    """Sozlamalarni olish (BOSQICH 41: tenant-scoped; yozuv bo'lmasa global default)"""
    tid = resolve_tenant_id(db, current_user)
    config = get_tenant_config(db, tid, config_name)
    if not config:
        raise HTTPException(status_code=404, detail="Sozlamalar topilmadi")
    return config

@router.patch("/{config_name}")
async def update_settings(
    config_name: str,
    settings: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("manage_settings"))
):
    """Sozlamalarni yangilash (BOSQICH 41: FAQAT shu tenant o'zgaradi, global emas).

    - Boshlang'ich qiymat get_tenant_config (yozuv bo'lmasa global default) —
      shu sabab version/debug kabi app maydonlari default/meros bo'lib saqlanadi.
    - Dot-path 'a.b.c' kalitlar ichma-ich yoziladi (eski set_value bilan bir xil)."""
    tid = resolve_tenant_id(db, current_user)
    if not tid:
        raise HTTPException(status_code=400, detail="Sozlama saqlash uchun tenant (kafe) aniqlanmadi")

    config = get_tenant_config(db, tid, config_name) or {}
    for key, value in settings.items():
        parts = str(key).split(".")
        node = config
        for p in parts[:-1]:
            if not isinstance(node.get(p), dict):
                node[p] = {}
            node = node[p]
        node[parts[-1]] = value

    set_tenant_config(db, tid, config_name, config)
    return MessageResponse(message="Sozlamalar yangilandi")