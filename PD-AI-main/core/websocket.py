# core/websocket.py
from typing import Dict
from fastapi import WebSocket


class ConnectionManager:
    """WebSocket连接管理器"""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        """建立连接"""
        await websocket.accept()
        self.active_connections[user_id] = websocket
        print(f"用户 {user_id} 已连接，当前连接数: {len(self.active_connections)}")

    def disconnect(self, user_id: str):
        """断开连接"""
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            print(f"用户 {user_id} 已断开，剩余连接数: {len(self.active_connections)}")

    async def send_message(self, message: dict, user_id: str):
        """发送消息给指定用户"""
        if user_id in self.active_connections:
            try:
                await self.active_connections[user_id].send_json(message)
            except Exception as e:
                print(f"发送消息给用户 {user_id} 失败: {e}")
                self.disconnect(user_id)

    async def broadcast(self, message: dict):
        """广播消息给所有用户"""
        disconnected_users = []
        for user_id, connection in self.active_connections.items():
            try:
                await connection.send_json(message)
            except:
                disconnected_users.append(user_id)

        for user_id in disconnected_users:
            self.disconnect(user_id)


# 创建全局连接管理器实例
manager = ConnectionManager()