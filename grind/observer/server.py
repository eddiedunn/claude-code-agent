"""Observer server — receives hook events and streams them live.

Architecture (mirrors Dan's Bun server, implemented in Python/FastAPI):

  Claude Code hooks → POST /events → EventStore (SQLite)
                                    → WebSocket broadcast (live stream)

  Browser/CLI      → GET /events  → Query from SQLite
                   → WS /stream   → Live event stream

The server is intentionally simple. It's a thin layer between
hooks and storage/streaming. No business logic beyond receiving,
storing, and forwarding events.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager

from grind.observer.models import AgentEvent, EventType
from grind.observer.store import EventStore

# Will be lazily imported to avoid hard dependency when not running server
_app = None


def create_app(db_path: str | None = None):
    """Create the FastAPI application.

    Lazy import so the observer module can be imported without
    FastAPI installed (it's only needed when running the server).
    """
    try:
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import JSONResponse
    except ImportError:
        raise ImportError(
            "FastAPI is required for the observer server. "
            "Install with: uv add fastapi uvicorn"
        )

    # Shared state
    store = EventStore(db_path)
    ws_clients: set[WebSocket] = set()
    event_queue: asyncio.Queue[dict] = asyncio.Queue()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Start the broadcast task
        task = asyncio.create_task(_broadcast_loop(ws_clients, event_queue))
        yield
        task.cancel()
        store.close()

    app = FastAPI(
        title="Grind Observer",
        description="Multi-agent observability server",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health():
        return {"status": "ok", "events": store.count(), "timestamp": time.time()}

    @app.post("/events")
    async def receive_event(payload: dict):
        """Receive an event from a Claude Code hook.

        The hook sends a JSON payload. We parse it into an AgentEvent,
        store it, and broadcast to WebSocket clients.
        """
        # Determine event type from payload or default
        event_type = payload.pop("event_type", payload.pop("hook_type", "error"))

        event = AgentEvent.from_hook_payload(event_type, payload)
        row_id = store.insert(event)

        # Queue for WebSocket broadcast
        event_dict = event.to_dict()
        event_dict["id"] = row_id
        await event_queue.put(event_dict)

        return {"ok": True, "id": row_id}

    @app.get("/events")
    async def query_events(
        session_id: str | None = None,
        agent_name: str | None = None,
        event_type: str | None = None,
        since: float | None = None,
        limit: int = 100,
        offset: int = 0,
    ):
        """Query stored events with optional filters."""
        et = EventType(event_type) if event_type else None
        events = store.query(
            session_id=session_id,
            agent_name=agent_name,
            event_type=et,
            since=since,
            limit=limit,
            offset=offset,
        )
        return {"events": events, "count": len(events)}

    @app.get("/sessions")
    async def list_sessions():
        """List all observed sessions."""
        return {"sessions": store.sessions()}

    @app.websocket("/stream")
    async def websocket_stream(websocket: WebSocket):
        """Live event stream via WebSocket.

        Clients connect here to receive events in real time.
        Each event is sent as a JSON message.
        """
        await websocket.accept()
        ws_clients.add(websocket)
        try:
            # Keep connection alive, handle client messages (pings, etc.)
            while True:
                try:
                    await websocket.receive_text()
                except WebSocketDisconnect:
                    break
        finally:
            ws_clients.discard(websocket)

    return app


async def _broadcast_loop(
    clients: set, queue: asyncio.Queue
) -> None:
    """Continuously broadcast queued events to all WebSocket clients."""
    while True:
        event = await queue.get()
        if not clients:
            continue

        message = json.dumps(event)
        dead = set()
        for ws in clients:
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        clients -= dead


async def run_server_async(
    host: str = "0.0.0.0",
    port: int = 8421,
    db_path: str | None = None,
) -> None:
    """Run the observer server (async version for use within an event loop).

    This is the entry point for `grind observe`.
    """
    try:
        import uvicorn
    except ImportError:
        raise ImportError(
            "uvicorn is required for the observer server. "
            "Install with: uv add uvicorn"
        )

    app = create_app(db_path)
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


def run_server(
    host: str = "0.0.0.0",
    port: int = 8421,
    db_path: str | None = None,
) -> None:
    """Run the observer server (blocking, creates its own event loop).

    Use run_server_async() if you're already in an async context.
    """
    try:
        import uvicorn
    except ImportError:
        raise ImportError(
            "uvicorn is required for the observer server. "
            "Install with: uv add uvicorn"
        )

    app = create_app(db_path)
    uvicorn.run(app, host=host, port=port, log_level="info")
