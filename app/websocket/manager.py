import asyncio
import json
import logging
from typing import Dict, Set
from fastapi import WebSocket, WebSocketDisconnect
from collections import defaultdict

logger = logging.getLogger(__name__)

class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[int, Set[WebSocket]] = defaultdict(set)
        self.lock = asyncio.Lock()
    
    async def connect(self, user_id: int, websocket: WebSocket):
        """Connect a user's WebSocket"""
        await websocket.accept()
        
        async with self.lock:
            self.active_connections[user_id].add(websocket)
        
        logger.info(f"User {user_id} connected to WebSocket. Total connections: {len(self.active_connections[user_id])}")
    
    async def disconnect(self, user_id: int, websocket: WebSocket):
        """Disconnect a user's WebSocket"""
        async with self.lock:
            if user_id in self.active_connections:
                self.active_connections[user_id].discard(websocket)
                if not self.active_connections[user_id]:
                    del self.active_connections[user_id]
        
        logger.info(f"User {user_id} disconnected from WebSocket")
    
    async def send_personal_notification(self, user_id: int, notification: dict):
        """Send notification to a specific user"""
        connections = self.active_connections.get(user_id, set())
        
        if not connections:
            logger.debug(f"No active WebSocket connections for user {user_id}")
            return
        
        message = json.dumps({
            "type": "notification",
            "action": "new",
            "data": notification
        })
        
        tasks = []
        for connection in connections.copy():  # Use copy to avoid modification during iteration
            tasks.append(self._send_message(connection, message))
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Remove broken connections
            async with self.lock:
                for connection, result in zip(connections.copy(), results):
                    if isinstance(result, Exception):
                        logger.warning(f"Removing broken connection for user {user_id}: {result}")
                        self.active_connections[user_id].discard(connection)
    
    async def broadcast_notification(self, notification: dict, exclude_users: Set[int] = None):
        """Broadcast notification to all connected users"""
        if exclude_users is None:
            exclude_users = set()
        
        message = json.dumps({
            "type": "notification",
            "action": "broadcast",
            "data": notification
        })
        
        tasks = []
        async with self.lock:
            for user_id, connections in self.active_connections.items():
                if user_id in exclude_users:
                    continue
                
                for connection in connections:
                    tasks.append(self._send_message(connection, message))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _send_message(self, websocket: WebSocket, message: str):
        """Send message to WebSocket with error handling"""
        try:
            await websocket.send_text(message)
            return True
        except WebSocketDisconnect:
            raise
        except Exception as e:
            logger.error(f"Error sending WebSocket message: {e}")
            return False
    
    async def get_connected_users_count(self) -> int:
        """Get count of connected users"""
        async with self.lock:
            return len(self.active_connections)
    
    async def get_total_connections_count(self) -> int:
        """Get total count of WebSocket connections"""
        async with self.lock:
            total = 0
            for connections in self.active_connections.values():
                total += len(connections)
            return total