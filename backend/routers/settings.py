from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Any, Dict

from database import get_db
from models import User
from deps import get_current_user, has_permission, resolve_tenant_id
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
    current_user: User = Depends(get_current_user),
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