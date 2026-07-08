"""
WebSocket ulanishlarini boshqarish
"""

from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Set, Any, Optional, List
import json
import asyncio
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket ulanishlarini boshqaruvchi"""
    
    def __init__(self):
        # Faol ulanishlar (connection_id -> websocket)
        self.active_connections: Dict[str, WebSocket] = {}
        
        # Foydalanuvchi ulanishlari (user_id -> set of connection_ids)
        self.user_connections: Dict[int, Set[str]] = {}
        
        # Xonalar (room_id -> set of connection_ids)
        self.rooms: Dict[str, Set[str]] = {}
        
        # Connection ID uchun hisoblagich
        self._connection_counter = 0
        
        # Ulanish ma'lumotlari (connection_id -> metadata)
        self.connection_metadata: Dict[str, Dict[str, Any]] = {}
    
    def _generate_connection_id(self) -> str:
        """Yangi connection ID yaratish"""
        self._connection_counter += 1
        return f"conn_{self._connection_counter}"
    
    async def connect(self, websocket: WebSocket, user_id: Optional[int] = None, tenant_id: Optional[int] = None) -> str:
        """Yangi ulanishni qabul qilish"""
        await websocket.accept()

        connection_id = self._generate_connection_id()
        self.active_connections[connection_id] = websocket

        self.connection_metadata[connection_id] = {
            "connected_at": asyncio.get_event_loop().time(),
            "user_id": user_id,
            "tenant_id": tenant_id,  # BOSQICH 2.5: tenant izolyatsiyasi
        }
        
        if user_id:
            if user_id not in self.user_connections:
                self.user_connections[user_id] = set()
            self.user_connections[user_id].add(connection_id)
        
        logger.info(f"[WS] Connected: {connection_id}, User: {user_id}")
        
        # Ulanish haqida xabar yuborish
        await self.send_personal_message({
            "type": "connected",
            "connection_id": connection_id,
            "message": "WebSocket connected successfully"
        }, connection_id)
        
        return connection_id
    
    def disconnect(self, connection_id: str):
        """Ulanishni uzish"""
        if connection_id not in self.active_connections:
            return
        
        metadata = self.connection_metadata.get(connection_id, {})
        user_id = metadata.get("user_id")
        
        # Faol ulanishlardan o'chirish
        del self.active_connections[connection_id]
        
        # Foydalanuvchi ulanishlaridan o'chirish
        if user_id and user_id in self.user_connections:
            self.user_connections[user_id].discard(connection_id)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]
        
        # Xonalardan o'chirish
        for room_id, connections in self.rooms.items():
            connections.discard(connection_id)
        
        # Metadata dan o'chirish
        if connection_id in self.connection_metadata:
            del self.connection_metadata[connection_id]
        
        logger.info(f"[WS] Disconnected: {connection_id}")
    
    async def send_personal_message(self, message: Any, connection_id: str):
        """Bitta ulanishga xabar yuborish"""
        if connection_id not in self.active_connections:
            return
        
        try:
            websocket = self.active_connections[connection_id]
            
            if isinstance(message, dict):
                await websocket.send_json(message)
            else:
                await websocket.send_text(str(message))
                
        except Exception as e:
            logger.error(f"[WS] Failed to send message to {connection_id}: {e}")
    
    async def send_to_user(self, user_id: int, message: Any):
        """Foydalanuvchining barcha ulanishlariga xabar yuborish"""
        if user_id not in self.user_connections:
            return
        
        for conn_id in list(self.user_connections[user_id]):
            await self.send_personal_message(message, conn_id)
    
    async def broadcast(self, message: Any, exclude: Optional[str] = None):
        """Barcha ulanishlarga xabar yuborish"""
        for conn_id in list(self.active_connections.keys()):
            if conn_id != exclude:
                await self.send_personal_message(message, conn_id)
    
    async def broadcast_to_room(self, room: str, message: Any, exclude: Optional[str] = None):
        """Xonadagi barcha ulanishlarga xabar yuborish"""
        if room not in self.rooms:
            return
        
        for conn_id in list(self.rooms[room]):
            if conn_id != exclude:
                await self.send_personal_message(message, conn_id)
    
    async def broadcast_to_pos(self, message: Any, tenant_id: Optional[int] = None):
        """POS terminallarga xabar yuborish — tenant_id berilsa faqat o'sha tenant'ga (BOSQICH 2.5)"""
        room = f"pos_{tenant_id}" if tenant_id else "pos"
        await self.broadcast_to_room(room, message)

    async def broadcast_to_kitchen(self, message: Any, tenant_id: Optional[int] = None):
        """Oshxona displeylariga xabar yuborish — tenant_id berilsa faqat o'sha tenant'ga (BOSQICH 2.5)"""
        room = f"kitchen_{tenant_id}" if tenant_id else "kitchen"
        await self.broadcast_to_room(room, message)

    async def broadcast_to_admins(self, message: Any, tenant_id: Optional[int] = None):
        """Adminlarga xabar yuborish"""
        room = f"admin_{tenant_id}" if tenant_id else "admin"
        await self.broadcast_to_room(room, message)
    
    def join_room(self, connection_id: str, room: str):
        """Xonaga qo'shilish"""
        if connection_id not in self.active_connections:
            return
        
        if room not in self.rooms:
            self.rooms[room] = set()
        
        self.rooms[room].add(connection_id)
        logger.info(f"[WS] {connection_id} joined room: {room}")
    
    def leave_room(self, connection_id: str, room: str):
        """Xonadan chiqish"""
        if room in self.rooms:
            self.rooms[room].discard(connection_id)
            if not self.rooms[room]:
                del self.rooms[room]
            logger.info(f"[WS] {connection_id} left room: {room}")
    
    def get_room_members(self, room: str) -> Set[str]:
        """Xonadagi a'zolar"""
        return self.rooms.get(room, set())
    
    def get_room_count(self, room: str) -> int:
        """Xonadagi a'zolar soni"""
        return len(self.rooms.get(room, set()))
    
    def get_online_users(self) -> Set[int]:
        """Online foydalanuvchilar"""
        return set(self.user_connections.keys())
    
    def get_online_count(self) -> int:
        """Online foydalanuvchilar soni"""
        return len(self.user_connections)
    
    def is_user_online(self, user_id: int) -> bool:
        """Foydalanuvchi onlineligini tekshirish"""
        return user_id in self.user_connections and len(self.user_connections[user_id]) > 0
    
    def get_user_connections(self, user_id: int) -> List[str]:
        """Foydalanuvchining barcha ulanishlarini olish"""
        return list(self.user_connections.get(user_id, set()))
    
    async def ping(self, connection_id: str) -> bool:
        """Ping yuborish"""
        try:
            await self.send_personal_message({"type": "ping"}, connection_id)
            return True
        except:
            return False
    
    async def ping_all(self):
        """Barchaga ping yuborish"""
        await self.broadcast({"type": "ping"})
    
    def get_status(self) -> Dict[str, Any]:
        """Holat ma'lumotlarini olish"""
        return {
            "active_connections": len(self.active_connections),
            "online_users": len(self.user_connections),
            "rooms": {
                room: len(members)
                for room, members in self.rooms.items()
            }
        }
    
    async def close_all(self):
        """Barcha ulanishlarni yopish"""
        for conn_id in list(self.active_connections.keys()):
            try:
                await self.active_connections[conn_id].close()
            except:
                pass
        
        self.active_connections.clear()
        self.user_connections.clear()
        self.rooms.clear()
        self.connection_metadata.clear()


# Global manager instance
manager = ConnectionManager()