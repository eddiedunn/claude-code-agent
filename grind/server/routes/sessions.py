"""Session CRUD endpoints for grind server."""

import asyncio
from typing import Annotated, AsyncGenerator

import aiofiles
from fastapi import APIRouter, Depends, Query, Request
from sse_starlette.sse import EventSourceResponse

from grind.server.models.requests import CreateSessionRequest, InjectRequest
from grind.server.models.responses import SessionInfo, SessionListResponse, SessionStatus
from grind.server.services.session_manager import SessionManager

router = APIRouter(prefix="/sessions", tags=["sessions"])


def get_session_manager(request: Request) -> SessionManager:
    """Get the session manager from app state."""
    return request.app.state.session_manager


@router.post("/", response_model=SessionInfo, status_code=201)
async def create_session(
    request: CreateSessionRequest,
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
) -> SessionInfo:
    """Create and start a new grind session."""
    return await session_manager.create_session(request)


@router.get("/", response_model=SessionListResponse)
async def list_sessions(
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
    tag: Annotated[str | None, Query(description="Filter sessions by tag")] = None,
) -> SessionListResponse:
    """List all sessions, optionally filtered by tag."""
    sessions = await session_manager.list_sessions(tag=tag)
    return SessionListResponse(sessions=sessions, total=len(sessions))


@router.get("/{session_id}", response_model=SessionInfo)
async def get_session(
    session_id: str,
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
) -> SessionInfo:
    """Get details for a specific session."""
    return await session_manager.get_session(session_id)


@router.delete("/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
) -> None:
    """Cancel and stop a running session."""
    await session_manager.cancel_session(session_id)


@router.post("/{session_id}/inject", response_model=dict)
async def inject_message(
    session_id: str,
    request: InjectRequest,
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
) -> dict:
    """Inject a message or control action into a running session.

    This endpoint enables programmatic control of running grind sessions without
    requiring TTY/keyboard input. Messages are delivered at the next checkpoint.

    ## Use Cases

    - **Remote Guidance**: Provide hints or corrections during execution
    - **Control Actions**: Abort, request status, or trigger verify command
    - **Multi-Agent Coordination**: One session can guide another

    ## Action Types

    - `guidance`: One-shot guidance for the current iteration
    - `guidance_persist`: Guidance that persists across iterations
    - `abort`: Abort the session immediately
    - `status`: Show current status
    - `verify`: Run the verify command

    ## Session State Requirements

    The session must be in RUNNING state. Attempting to inject into a session
    in any other state (PENDING, COMPLETED, FAILED, CANCELLED) will return a 400 error.

    ## Examples

    Inject guidance:
    ```json
    {
      "message": "Try using the builder pattern instead",
      "action": "guidance",
      "persistent": false
    }
    ```

    Abort session:
    ```json
    {
      "message": "Deadline reached",
      "action": "abort"
    }
    ```

    ## Response

    Returns a JSON object with status and session_id.

    ## Error Responses

    - **404 Not Found**: Session with given session_id does not exist
    - **400 Bad Request**: Session is not in RUNNING state or invalid action type
    """
    await session_manager.inject(session_id, request.message)
    return {"status": "injected", "session_id": session_id}


@router.get("/{session_id}/logs")
async def stream_logs(
    session_id: str,
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
    from_start: Annotated[bool, Query()] = False,
) -> EventSourceResponse:
    """Stream session logs via Server-Sent Events."""
    # Validate session exists (raises SessionNotFoundError if not)
    session = await session_manager.get_session(session_id)
    log_path = session_manager.get_log_path(session_id)

    async def log_generator() -> AsyncGenerator[dict, None]:
        position = 0 if from_start else -1

        while True:
            session = await session_manager.get_session(session_id)
            if session.status in (SessionStatus.COMPLETED, SessionStatus.FAILED, SessionStatus.CANCELLED):
                # Send remaining lines then close
                if log_path.exists():
                    async with aiofiles.open(log_path, mode="r") as f:
                        if position > 0:
                            await f.seek(position)
                        async for line in f:
                            yield {"event": "log", "data": line.rstrip()}
                yield {"event": "done", "data": session.status}
                break

            if log_path.exists():
                async with aiofiles.open(log_path, mode="r") as f:
                    if position > 0:
                        await f.seek(position)
                    elif position == -1:
                        # Tail mode - seek to end
                        await f.seek(0, 2)
                        position = await f.tell()

                    async for line in f:
                        yield {"event": "log", "data": line.rstrip()}
                    position = await f.tell()

            await asyncio.sleep(0.25)  # 250ms polling interval

    return EventSourceResponse(log_generator())
