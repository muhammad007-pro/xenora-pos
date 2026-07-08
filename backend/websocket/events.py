"""
WebSocket eventlarini boshqarish
"""

from fastapi import WebSocket, WebSocketDisconnect
import json
import logging
from typing import Optional

from websocket.manager import manager

logger = logging.getLogger(__name__)


async def handle_websocket_connection(websocket: WebSocket, user_id: Optional[int] = None):
    """WebSocket ulanishini boshqarish"""
    connection_id = await manager.connect(websocket, user_id)
    
    try:
        while True:
            # Xabarni qabul qilish
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                message_type = message.get("type")
                
                # Ping
                if message_type == "ping":
                    await manager.send_personal_message({"type": "pong"}, connection_id)
                
                # Xonaga qo'shilish
                elif message_type == "join_room":
                    room = message.get("room")
                    if room:
                        manager.join_room(connection_id, room)
                        await manager.send_personal_message({
                            "type": "room_joined",
                            "room": room
                        }, connection_id)
                        
                        # Xonadagilarga xabar
                        await manager.broadcast_to_room(room, {
                            "type": "user_joined",
                            "user_id": user_id,
                            "room": room
                        }, exclude=connection_id)
                
                # Xonadan chiqish
                elif message_type == "leave_room":
                    room = message.get("room")
                    if room:
                        manager.leave_room(connection_id, room)
                        await manager.send_personal_message({
                            "type": "room_left",
                            "room": room
                        }, connection_id)
                        
                        # Xonadagilarga xabar
                        await manager.broadcast_to_room(room, {
                            "type": "user_left",
                            "user_id": user_id,
                            "room": room
                        })
                
                # Xonaga xabar yuborish
                elif message_type == "room_message":
                    room = message.get("room")
                    msg_data = message.get("data")
                    if room and msg_data:
                        await manager.broadcast_to_room(room, {
                            "type": "room_broadcast",
                            "room": room,
                            "sender": user_id,
                            "data": msg_data
                        }, exclude=connection_id)
                
                # Foydalanuvchiga shaxsiy xabar
                elif message_type == "user_message":
                    target_user_id = message.get("user_id")
                    msg_data = message.get("data")
                    if target_user_id and msg_data:
                        await manager.send_to_user(target_user_id, {
                            "type": "personal_message",
                            "sender": user_id,
                            "data": msg_data
                        })
                
                # Holatni so'rash
                elif message_type == "get_status":
                    await manager.send_personal_message({
                        "type": "status",
                        "online_users": list(manager.get_online_users()),
                        "rooms": {
                            room: manager.get_room_count(room)
                            for room in manager.rooms.keys()
                        },
                        "total_connections": len(manager.active_connections)
                    }, connection_id)
                
                # Noma'lum xabar turi
                else:
                    await manager.send_personal_message({
                        "type": "error",
                        "message": f"Noma'lum xabar turi: {message_type}"
                    }, connection_id)
                    
            except json.JSONDecodeError:
                logger.warning(f"[WS] Invalid JSON received: {data[:100]}")
                await manager.send_personal_message({
                    "type": "error",
                    "message": "Noto'g'ri JSON format"
                }, connection_id)
                
    except WebSocketDisconnect:
        manager.disconnect(connection_id)
        logger.info(f"[WS] Client disconnected: {connection_id}")
        
        # Xonalarga chiqish haqida xabar
        for room in list(manager.rooms.keys()):
            if connection_id in manager.rooms.get(room, set()):
                await manager.broadcast_to_room(room, {
                    "type": "user_disconnected",
                    "user_id": user_id,
                    "room": room
                })


async def broadcast_order_update(order_data: dict):
    """Buyurtma yangilanishini barchaga yuborish"""
    await manager.broadcast_to_pos({
        "type": "order_updated",
        "data": order_data
    })
    
    await manager.broadcast_to_kitchen({
        "type": "order_updated",
        "data": order_data
    })


async def broadcast_table_status(table_id: int, status: str):
    """Stol holati o'zgarishini yuborish"""
    await manager.broadcast_to_pos({
        "type": "table_status_changed",
        "data": {
            "table_id": table_id,
            "status": status
        }
    })


async def broadcast_new_order(order_data: dict):
    """Yangi buyurtmani yuborish"""
    await manager.broadcast_to_kitchen({
        "type": "new_order",
        "data": order_data
    })


async def broadcast_order_ready(order_id: int, order_number: str, table_number: str):
    """Buyurtma tayyorligini yuborish"""
    await manager.broadcast_to_pos({
        "type": "order_ready",
        "data": {
            "order_id": order_id,
            "order_number": order_number,
            "table_number": table_number
        }
    })


async def send_notification_to_user(user_id: int, notification: dict):
    """Foydalanuvchiga bildirishnoma yuborish"""
    await manager.send_to_user(user_id, {
        "type": "notification",
        "data": notification
    })


async def broadcast_notification_to_role(role: str, notification: dict):
    """Rol bo'yicha bildirishnoma yuborish"""
    await manager.broadcast_to_room(role, {
        "type": "notification",
        "data": notification
    })