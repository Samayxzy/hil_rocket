import asyncio
import json
import logging
from typing import Set
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    Manages all active WebSocket connections and broadcasts telemetry to them.
    Supports multiple simultaneous clients (main dashboard + wind tunnel window).
    """

    def __init__(self):
        self._connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)
        logger.info(f"WS client connected  — total: {len(self._connections)}")

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            self._connections.discard(ws)
        logger.info(f"WS client disconnected — total: {len(self._connections)}")

    async def broadcast(self, payload: dict):
        """
        Send a JSON payload to every connected client.
        Dead connections are silently removed.
        """
        if not self._connections:
            return

        message = json.dumps(payload)
        dead: Set[WebSocket] = set()

        async with self._lock:
            targets = set(self._connections)

        for ws in targets:
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)

        if dead:
            async with self._lock:
                self._connections -= dead
            logger.info(f"Removed {len(dead)} dead WS connection(s)")

    @property
    def client_count(self) -> int:
        return len(self._connections)


# Single shared instance
ws_manager = WebSocketManager()
