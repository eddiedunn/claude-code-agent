"""FastAPI application factory."""
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from grind.server.exceptions import (
    GrindServerError,
    SessionNotFoundError,
    SessionNotRunningError,
    SessionLimitReachedError,
)
from grind.server.logging import get_logger
from grind.server.routes import health, sessions, websocket
from grind.server.routes.health import set_server_start_time
from grind.server.services.event_bridge import EventBridge
from grind.server.services.session_manager import SessionManager

logger = get_logger("app")

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifecycle."""
    import os
    logger.info("Starting Grind Server...")

    # Initialize services
    event_bridge = EventBridge()
    max_sessions = int(os.getenv("GRIND_MAX_CONCURRENT_SESSIONS", "10"))
    session_manager = SessionManager(event_bridge=event_bridge, max_concurrent_sessions=max_sessions)
    await session_manager.recover_sessions()

    app.state.event_bridge = event_bridge
    app.state.session_manager = session_manager

    set_server_start_time()
    logger.info("Grind Server started")
    logger.info("Metrics available at http://localhost:8420/metrics")

    yield  # Server is running

    # Shutdown
    logger.info("Shutting down Grind Server...")
    await session_manager.shutdown()
    logger.info("Grind Server stopped")

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Grind Server",
        version="0.1.0",
        description="""
REST API for the Grind autonomous agent engine.

Grind Server allows you to:
- Create and manage agent sessions via REST API
- Stream real-time events via WebSocket
- Inject human messages into running sessions
- Monitor session logs via Server-Sent Events

## Authentication

Currently no authentication is required (localhost only).

## Rate Limiting

No rate limiting is applied.
        """,
        contact={
            "name": "Grind Server",
            "url": "https://github.com/your-repo/grind",
        },
        license_info={
            "name": "MIT",
        },
        openapi_tags=[
            {"name": "health", "description": "Server health and status"},
            {"name": "sessions", "description": "Session management"},
        ],
        lifespan=lifespan,
    )

    # Exception handlers - convert domain exceptions to HTTP responses
    @app.exception_handler(SessionNotFoundError)
    async def session_not_found_handler(request: Request, exc: SessionNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(SessionNotRunningError)
    async def session_not_running_handler(request: Request, exc: SessionNotRunningError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(SessionLimitReachedError)
    async def session_limit_handler(request: Request, exc: SessionLimitReachedError) -> JSONResponse:
        return JSONResponse(
            status_code=429,  # Too Many Requests
            content={"detail": str(exc), "limit": exc.limit, "current": exc.current}
        )

    @app.exception_handler(GrindServerError)
    async def grind_server_error_handler(request: Request, exc: GrindServerError) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    # CORS for local development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers (health includes /metrics endpoint)
    app.include_router(health.router)
    app.include_router(sessions.router)
    app.include_router(websocket.router)

    return app
