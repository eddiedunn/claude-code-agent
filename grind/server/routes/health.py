from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from grind.server.models.responses import HealthResponse
from grind.server.services.session_manager import SessionManager

router = APIRouter(tags=["health"])

# Track server start time
_server_start_time: datetime | None = None

def set_server_start_time() -> None:
    global _server_start_time
    _server_start_time = datetime.now(timezone.utc)

def get_session_manager(request: Request) -> SessionManager:
    return request.app.state.session_manager

@router.get("/health", response_model=HealthResponse)
async def health_check(
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
) -> HealthResponse:
    """Check server health and status with circuit breaker logic."""
    uptime = 0.0
    if _server_start_time:
        uptime = (datetime.now(timezone.utc) - _server_start_time).total_seconds()

    sessions = await session_manager.list_sessions()
    active = sum(1 for s in sessions if s.status == "running")

    # Calculate failure rate (recent sessions only, last hour)
    recent_cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    recent_sessions = [
        s for s in sessions
        if s.created_at > recent_cutoff and s.status in ("completed", "failed")
    ]

    failure_rate = 0.0
    if recent_sessions:
        failed = sum(1 for s in recent_sessions if s.status == "failed")
        failure_rate = failed / len(recent_sessions)

    # Determine overall status
    status = "ok"
    if failure_rate > 0.5:  # >50% failure rate
        status = "unhealthy"
    elif failure_rate > 0.2 or not session_manager._accepting_new:
        status = "degraded"

    return HealthResponse(
        status=status,
        version="0.1.0",
        active_sessions=active,
        uptime_seconds=uptime,
        accepting_new_sessions=session_manager._accepting_new,
        session_capacity={
            "current": active,
            "max": session_manager._max_concurrent_sessions,
        },
        failure_rate=round(failure_rate, 3),
    )

@router.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )
