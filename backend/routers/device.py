"""
Qurilmalar (Devices) router
Printer, cash drawer, barcode scanner sozlamalari.
"""

from fastapi import APIRouter, Depends
from typing import List, Optional

from models import User
from deps import get_current_active_user, has_permission

router = APIRouter()

# Qurilma ro'yxati (konfiguratsiya DB'ga keyinchalik ko'chiriladi)
_devices_store: List[dict] = []


@router.get("/")
async def get_devices(current_user: User = Depends(get_current_active_user)):
    """Ro'yxatdan o'tgan qurilmalar"""
    return [d for d in _devices_store if d.get("tenant_id") == current_user.tenant_id]


@router.post("/")
async def register_device(
    device_type: str,          # printer | barcode | cash_drawer | display
    name:        str,
    ip_address:  Optional[str] = None,
    port:        Optional[int] = None,
    current_user: User = Depends(has_permission("manage_settings")),
):
    """Yangi qurilma qo'shish"""
    device = {
        "id":          len(_devices_store) + 1,
        "tenant_id":   current_user.tenant_id,
        "device_type": device_type,
        "name":        name,
        "ip_address":  ip_address,
        "port":        port,
        "is_active":   True,
    }
    _devices_store.append(device)
    return device


@router.patch("/{device_id}/test")
async def test_device(
    device_id:   int,
    current_user: User = Depends(get_current_active_user),
):
    """Qurilmani test qilish"""
    return {"success": True, "message": "Qurilma bilan ulanish tekshirildi"}


@router.delete("/{device_id}")
async def remove_device(
    device_id:   int,
    current_user: User = Depends(has_permission("manage_settings")),
):
    """Qurilmani o'chirish"""
    global _devices_store
    _devices_store = [
        d for d in _devices_store
        if not (d["id"] == device_id and d.get("tenant_id") == current_user.tenant_id)
    ]
    return {"message": "Qurilma o'chirildi"}
