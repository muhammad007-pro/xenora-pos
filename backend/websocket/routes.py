"""
WebSocket endpointlari (BOSQICH 2.5)

Har bir ulanish turining o'z tenant-izolyatsiyalangan xonasi bor:
  /ws/       — umumiy kanal (istalgan foydalanuvchi)
  /ws/pos    — POS terminal (xona: pos_{tenant_id})
  /ws/kitchen — Oshxona displey (xona: kitchen_{tenant_id})

Heartbeat: server har WS_HEARTBEAT_INTERVAL soniyada ping yuboradi,
agar javob kelmasa ulanishni uzadi.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from typing import Optional
import json
import asyncio
import logging

from websocket.manager import manager
from core.security import verify_access_token
from config import settings
from database import SessionLocal
from models import User

router = APIRouter()
logger = logging.getLogger(__name__)


async def _get_user_from_token(token: Optional[str]) -> Optional[User]:
    """Token orqali foydalanuvchini olish"""
    if not token:
        return None
    payload = verify_access_token(token)
    if not payload:
        return None
    username = payload.get("sub")
    if not username:
        return None
    db = SessionLocal()
    try:
        return db.query(User).filter(User.username == username).first()
    finally:
        db.close()


async def _heartbeat(connection_id: str):
    """Heartbeat — ulanish tirikligini tekshirish (BOSQICH 2.5)"""
    while connection_id in manager.active_connections:
        await asyncio.sleep(settings.WS_HEARTBEAT_INTERVAL)
        if connection_id not in manager.active_connections:
            break
        alive = await manager.ping(connection_id)
        if not alive:
            manager.disconnect(connection_id)
            break


@router.websocket("/")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None)
):
    """Asosiy WebSocket endpoint — umumiy kanal"""
    user = await _get_user_from_token(token)
    user_id = user.id if user else None
    tenant_id = user.tenant_id if user else None

    connection_id = await manager.connect(websocket, user_id=user_id, tenant_id=tenant_id)
    asyncio.create_task(_heartbeat(connection_id))

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                msg_type = message.get("type")

                if msg_type == "ping":
                    await manager.send_personal_message({"type": "pong"}, connection_id)

                elif msg_type == "join_room":
                    room = message.get("room")
                    if room:
                        manager.join_room(connection_id, room)
                        await manager.send_personal_message({"type": "room_joined", "room": room}, connection_id)

                elif msg_type == "leave_room":
                    room = message.get("room")
                    if room:
                        manager.leave_room(connection_id, room)
                        await manager.send_personal_message({"type": "room_left", "room": room}, connection_id)

                elif msg_type == "room_message":
                    room = message.get("room")
                    msg_data = message.get("data")
                    if room and msg_data:
                        await manager.broadcast_to_room(
                            room,
                            {"type": "room_broadcast", "room": room, "sender": user_id, "data": msg_data},
                            exclude=connection_id
                        )

                elif msg_type == "user_message":
                    target_user_id = message.get("user_id")
                    msg_data = message.get("data")
                    if target_user_id and msg_data:
                        await manager.send_to_user(
                            target_user_id,
                            {"type": "personal_message", "sender": user_id, "data": msg_data}
                        )

                elif msg_type == "get_status":
                    await manager.send_personal_message({
                        "type": "status",
                        **manager.get_status()
                    }, connection_id)

                else:
                    await manager.send_personal_message(
                        {"type": "error", "message": f"Noma'lum xabar turi: {msg_type}"},
                        connection_id
                    )

            except json.JSONDecodeError:
                await manager.send_personal_message(
                    {"type": "error", "message": "Noto'g'ri JSON format"},
                    connection_id
                )

    except WebSocketDisconnect:
        manager.disconnect(connection_id)


@router.websocket("/pos")
async def pos_websocket(
    websocket: WebSocket,
    token: Optional[str] = Query(None)
):
    """POS terminal uchun WebSocket — xona: pos_{tenant_id}"""
    user = await _get_user_from_token(token)
    user_id = user.id if user else None
    tenant_id = user.tenant_id if user else None

    connection_id = await manager.connect(websocket, user_id=user_id, tenant_id=tenant_id)

    # Tenant-izolyatsiyalangan xona (BOSQICH 2.5)
    room = f"pos_{tenant_id}" if tenant_id else "pos"
    manager.join_room(connection_id, room)

    asyncio.create_task(_heartbeat(connection_id))

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                if message.get("type") == "order_update":
                    kitchen_room = f"kitchen_{tenant_id}" if tenant_id else "kitchen"
                    await manager.broadcast_to_room(kitchen_room, {
                        "type": "order_updated",
                        "data": message.get("data")
                    })
                elif message.get("type") == "voice_order":
                    kitchen_room = f"kitchen_{tenant_id}" if tenant_id else "kitchen"
                    await manager.broadcast_to_room(kitchen_room, {
                        "type" : "voice_order",
                        "table": message.get("table"),
                        "items": message.get("items", []),
                    })
                elif message.get("type") == "ping":
                    await manager.send_personal_message({"type": "pong"}, connection_id)
            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        manager.disconnect(connection_id)


@router.websocket("/kitchen")
async def kitchen_websocket(
    websocket: WebSocket,
    token: Optional[str] = Query(None)
):
    """Oshxona displey uchun WebSocket — xona: kitchen_{tenant_id}"""
    user = await _get_user_from_token(token)
    user_id = user.id if user else None
    tenant_id = user.tenant_id if user else None

    connection_id = await manager.connect(websocket, user_id=user_id, tenant_id=tenant_id)

    # Tenant-izolyatsiyalangan xona (BOSQICH 2.5)
    room = f"kitchen_{tenant_id}" if tenant_id else "kitchen"
    manager.join_room(connection_id, room)

    asyncio.create_task(_heartbeat(connection_id))

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                if message.get("type") == "item_status_update":
                    pos_room = f"pos_{tenant_id}" if tenant_id else "pos"
                    await manager.broadcast_to_room(pos_room, {
                        "type": "item_status_changed",
                        "data": message.get("data")
                    })
                elif message.get("type") == "ping":
                    await manager.send_personal_message({"type": "pong"}, connection_id)
            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        manager.disconnect(connection_id)


@router.websocket("/waiter")
async def waiter_call_websocket(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
    cafe_id: Optional[int] = Query(None),
):
    """
    Ofitsiant chaqirish WebSocket (BOSQICH 9.8).
    Mijoz QR-menyu orqali signal yuborganda ofitsiant telefoniga signal keladi.
    Xonalar: waiter_{tenant_id}
    cafe_id — autentifikatsiyasiz mijozlar uchun (QR sahifa)
    """
    user = await _get_user_from_token(token)
    user_id = user.id if user else None
    tenant_id = (user.tenant_id if user else None) or cafe_id

    connection_id = await manager.connect(websocket, user_id=user_id, tenant_id=tenant_id)
    room = f"waiter_{tenant_id}" if tenant_id else "waiter"
    manager.join_room(connection_id, room)
    asyncio.create_task(_heartbeat(connection_id))

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                msg_type = message.get("type")

                if msg_type == "call_waiter":
                    # Mijoz ofitsiant chaqirdi — xonadagi barcha ofitsianlarga yuborish
                    await manager.broadcast_to_room(room, {
                        "type": "waiter_called",
                        "table_id": message.get("table_id"),
                        "table_name": message.get("table_name"),
                        "reason": message.get("reason", "call"),  # call | bill | help
                        "timestamp": message.get("timestamp"),
                    })
                elif msg_type == "call_acknowledged":
                    # Ofitsiant signalga javob berdi
                    await manager.broadcast_to_room(room, {
                        "type": "call_cleared",
                        "table_id": message.get("table_id"),
                        "by_user": user_id,
                    })
                elif msg_type == "ping":
                    await manager.send_personal_message({"type": "pong"}, connection_id)

            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        manager.disconnect(connection_id)
