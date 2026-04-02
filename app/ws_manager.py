from fastapi import WebSocket
from typing import Dict, List, Set
import json


class ConnectionManager:
    def __init__(self):
        # Map of session_id -> set of connected websockets
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        """Accept a websocket connection and add it to the session."""
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = set()
        self.active_connections[session_id].add(websocket)

    async def disconnect(self, websocket: WebSocket, session_id: str):
        """Remove a websocket connection from the session."""
        if session_id in self.active_connections:
            self.active_connections[session_id].discard(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]

    async def broadcast(self, session_id: str, event_dict: dict):
        """Broadcast an event to all connected clients in a session."""
        if session_id not in self.active_connections:
            return

        disconnected = set()
        for websocket in self.active_connections[session_id]:
            try:
                await websocket.send_json(event_dict)
            except Exception:
                disconnected.add(websocket)

        # Clean up disconnected clients
        for websocket in disconnected:
            self.active_connections[session_id].discard(websocket)
