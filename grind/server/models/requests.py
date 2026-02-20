"""Pydantic models for HTTP requests to the grind server."""

from pydantic import BaseModel, ConfigDict, Field


class CreateSessionRequest(BaseModel):
    """Request to create and start a new grind session.

    A session encapsulates a task to be solved by the Claude agent,
    with optional verification steps and configuration parameters.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "task": "Fix the bug in auth.py",
                "model": "sonnet",
                "max_iterations": 10,
            }
        }
    )

    task: str = Field(..., description="The task description for the agent to complete")
    verify: str | None = Field(
        None, description="Optional verification command to run after task completion"
    )
    cwd: str | None = Field(
        None, description="Working directory for task execution (defaults to current directory)"
    )
    model: str = Field(
        "sonnet",
        description="Claude model to use for the session (haiku, sonnet, or opus)",
    )
    max_iterations: int = Field(
        10,
        description="Maximum number of iterations before stopping",
        ge=1,
    )
    tags: list[str] = Field(
        default_factory=list, description="Optional tags for filtering and organizing sessions"
    )
    idempotency_key: str | None = Field(
        None, description="Unique key for idempotent request processing (prevents duplicates)"
    )


class InjectRequest(BaseModel):
    """Request to inject a message into an active grind session.

    Used to send additional instructions, feedback, or corrections to an
    ongoing session without creating a new one.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "This approach won't work, try a different strategy",
                "action": "guidance",
                "persistent": False,
            }
        }
    )

    message: str = Field(..., description="Message or action to inject")
    action: str = Field(
        default="guidance",
        description="Action type: guidance, guidance_persist, abort, status, verify"
    )
    persistent: bool = Field(
        default=False,
        description="Whether guidance should persist across iterations"
    )
