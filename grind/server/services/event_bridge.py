from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from weakref import WeakSet

from starlette.websockets import WebSocket, WebSocketState

from grind.server.logging import get_logger
from grind.server.services.event_log import EventLog

if TYPE_CHECKING:
    from grind.orchestration.events import AgentEvent, EventBus

logger = get_logger("event_bridge")

class EventBridge:
    """Bridges grind EventBus to WebSocket clients with event durability."""

    def __init__(self, event_log: EventLog | None = None) -> None:
        self._clients: WeakSet[WebSocket] = WeakSet()
        self._session_filters: dict[int, str | None] = {}  # id(ws) -> session_id
        self._lock = asyncio.Lock()
        self._event_log = event_log or EventLog()

    async def connect(self, websocket: WebSocket, session_id: str | None = None) -> None:
        """Register a WebSocket client."""
        await websocket.accept()
        async with self._lock:
            self._clients.add(websocket)
            self._session_filters[id(websocket)] = session_id
        logger.info(f"WebSocket connected (filter: {session_id})")

    async def disconnect(self, websocket: WebSocket) -> None:
        """Unregister a WebSocket client."""
        async with self._lock:
            self._clients.discard(websocket)
            self._session_filters.pop(id(websocket), None)
        logger.info("WebSocket disconnected")

    async def broadcast(self, event: AgentEvent) -> None:
        """Broadcast event to all connected clients (with filtering)."""
        event_data = event.model_dump() if hasattr(event, 'model_dump') else vars(event)
        session_id = event_data.get("session_id")

        # Log event for durability
        if session_id:
            await self._event_log.append(session_id, event_data)

        async with self._lock:
            clients = list(self._clients)

        for ws in clients:
            filter_id = self._session_filters.get(id(ws))
            if filter_id is not None and filter_id != session_id:
                continue  # Skip - client filtering different session

            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await asyncio.wait_for(ws.send_json(event_data), timeout=1.0)
            except asyncio.TimeoutError:
                logger.warning("WebSocket send timeout - disconnecting slow client")
                await self.disconnect(ws)
            except Exception:
                logger.exception("WebSocket send failed")
                await self.disconnect(ws)
