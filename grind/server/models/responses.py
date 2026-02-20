"""Pydantic models for HTTP responses from the grind server."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SessionStatus(StrEnum):
    """Status of a grind session."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SessionInfo(BaseModel):
    """Information about a grind session."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "sess_abc123",
                "task": "Fix the bug in auth.py",
                "status": "running",
                "model": "sonnet",
                "current_iteration": 3,
                "max_iterations": 10,
                "cwd": "/Users/user/project",
                "tags": ["bugfix", "auth"],
                "created_at": "2024-01-10T12:00:00Z",
                "started_at": "2024-01-10T12:00:05Z",
                "completed_at": None,
                "error": None,
                "idempotency_key": "key_abc123",
            }
        }
    )

    id: str = Field(..., description="Unique session identifier")
    task: str = Field(..., description="The task description for this session")
    status: SessionStatus = Field(..., description="Current status of the session")
    model: str = Field(..., description="Claude model being used (haiku, sonnet, or opus)")
    current_iteration: int = Field(..., description="Current iteration number", ge=0)
    max_iterations: int = Field(..., description="Maximum allowed iterations", ge=1)
    cwd: str = Field(..., description="Working directory for task execution")
    tags: list[str] = Field(
        default_factory=list, description="Tags for filtering and organizing sessions"
    )
    created_at: datetime = Field(..., description="When the session was created")
    started_at: datetime | None = Field(None, description="When the session started execution")
    completed_at: datetime | None = Field(None, description="When the session completed")
    error: str | None = Field(None, description="Error message if session failed")
    idempotency_key: str | None = Field(
        None, description="Unique key for idempotent request processing"
    )


class SessionListResponse(BaseModel):
    """Response containing a list of sessions."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "sessions": [
                    {
                        "id": "sess_abc123",
                        "task": "Fix the bug in auth.py",
                        "status": "running",
                        "model": "sonnet",
                        "current_iteration": 3,
                        "max_iterations": 10,
                        "cwd": "/Users/user/project",
                        "tags": ["bugfix", "auth"],
                        "created_at": "2024-01-10T12:00:00Z",
                        "started_at": "2024-01-10T12:00:05Z",
                        "completed_at": None,
                        "error": None,
                        "idempotency_key": None,
                    }
                ],
                "total": 1,
            }
        }
    )

    sessions: list[SessionInfo] = Field(..., description="List of session information")
    total: int = Field(..., description="Total number of sessions", ge=0)


class HealthResponse(BaseModel):
    """Health check response."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ok",
                "version": "0.1.0",
                "active_sessions": 3,
                "uptime_seconds": 3600.5,
                "accepting_new_sessions": True,
                "session_capacity": {"current": 3, "max": 10},
                "failure_rate": 0.05,
            }
        }
    )

    status: str = Field(..., description="Overall health status: ok, degraded, unhealthy")
    version: str
    active_sessions: int
    uptime_seconds: float
    accepting_new_sessions: bool = Field(..., description="Whether server accepts new sessions")
    session_capacity: dict[str, int] = Field(..., description="Current vs max sessions")
    failure_rate: float = Field(..., description="Recent session failure rate (0.0-1.0)")
