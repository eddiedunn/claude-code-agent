import asyncio
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect

from grind.server.logging import get_logger
from grind.server.services.event_bridge import EventBridge

logger = get_logger("websocket")
router = APIRouter()

def get_event_bridge(request: Request) -> EventBridge:
    return request.app.state.event_bridge

@router.websocket("/ws/events")
async def events_websocket(
    websocket: WebSocket,
    session_id: Annotated[str | None, Query()] = None,
    since: Annotated[str | None, Query()] = None,  # ISO timestamp
) -> None:
    """WebSocket endpoint for real-time events with catch-up."""
    event_bridge: EventBridge = websocket.app.state.event_bridge

    await event_bridge.connect(websocket, session_id)

    # Send missed events if catch-up requested
    if session_id and since:
        try:
            since_dt = datetime.fromisoformat(since)
            missed = await event_bridge._event_log.get_since(session_id, since_dt)
            for event in missed:
                await websocket.send_json({"type": "replay", **event})
        except Exception:
            logger.exception("Failed to replay events")
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=30.0)
                # Handle client messages
                action = data.get("action")
                if action == "ping":
                    await websocket.send_json({"action": "pong"})
                elif action == "subscribe":
                    # Update session filter
                    new_session_id = data.get("session_id")
                    event_bridge._session_filters[id(websocket)] = new_session_id
            except asyncio.TimeoutError:
                # Send keepalive ping
                await websocket.send_json({"action": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        await event_bridge.disconnect(websocket)
