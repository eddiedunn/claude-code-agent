"""Session Manager for grind server."""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from grind.server.exceptions import (
    SessionNotFoundError,
    SessionNotRunningError,
    SessionAlreadyExistsError,
    SessionLimitReachedError,
    GrindServerError,
)
from grind.server.logging import get_logger, LogContext
from grind.server.metrics import sessions_total, sessions_active, session_duration_seconds
from grind.server.models.requests import CreateSessionRequest
from grind.server.models.responses import SessionInfo, SessionStatus
from grind.server.models.state_machine import is_valid_transition, is_terminal_state

if TYPE_CHECKING:
    from grind.models import TaskDefinition

logger = get_logger("session_manager")


class SessionManager:
    """Manages grind sessions - the core service bridging FastAPI to the grind engine."""

    def __init__(
        self,
        event_bridge: Any | None = None,
        max_concurrent_sessions: int = 10,
        enable_watchdog: bool | None = None,
        watchdog_stuck_threshold: float | None = None,
    ) -> None:
        """Initialize the session manager.

        Args:
            event_bridge: Optional EventBridge for WebSocket event streaming.
            max_concurrent_sessions: Maximum number of concurrent sessions allowed.
            enable_watchdog: Enable watchdog to detect stuck sessions (default: from env or True).
            watchdog_stuck_threshold: Seconds before marking session as stuck (default: from env or 1800).
        """
        self._sessions: dict[str, SessionInfo] = {}
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self._status_queue: asyncio.Queue[tuple[str, SessionStatus, str | None]] = asyncio.Queue()
        self._event_bridge = event_bridge
        self._accepting_new = True
        self._status_processor_task: asyncio.Task | None = None
        self._max_concurrent_sessions = max_concurrent_sessions

        # Watchdog configuration
        if enable_watchdog is None:
            enable_watchdog = os.getenv("GRIND_WATCHDOG_ENABLED", "true").lower() in ("true", "1", "yes")
        if watchdog_stuck_threshold is None:
            watchdog_stuck_threshold = float(os.getenv("GRIND_WATCHDOG_THRESHOLD_SECONDS", "1800"))

        self._enable_watchdog = enable_watchdog
        self._watchdog_stuck_threshold = watchdog_stuck_threshold
        self._watchdog_task: asyncio.Task | None = None

    async def _start_status_processor(self) -> None:
        """Start background task to process status updates."""
        self._status_processor_task = asyncio.create_task(self._process_status_updates())

    async def _ensure_watchdog_running(self) -> None:
        """Start watchdog if enabled and not running."""
        if not self._enable_watchdog:
            return
        if self._watchdog_task is None or self._watchdog_task.done():
            self._watchdog_task = asyncio.create_task(
                self._watchdog_loop(stuck_threshold=self._watchdog_stuck_threshold)
            )

    async def _watchdog_loop(self, check_interval: float = 60.0, stuck_threshold: float = 1800.0) -> None:
        """Background task to detect stuck sessions.

        Args:
            check_interval: How often to check (default: 60s)
            stuck_threshold: Mark session stuck after this long (default: 30min)
        """
        logger.info(f"Starting watchdog (check every {check_interval}s, threshold {stuck_threshold}s)")

        while True:
            try:
                await asyncio.sleep(check_interval)

                now = datetime.now(timezone.utc)
                async with self._lock:
                    stuck_sessions = []
                    for session in self._sessions.values():
                        if session.status != SessionStatus.RUNNING:
                            continue

                        if not session.started_at:
                            continue

                        elapsed = (now - session.started_at).total_seconds()
                        if elapsed > stuck_threshold:
                            stuck_sessions.append((session, elapsed))

                # Update stuck sessions outside lock
                for session, elapsed in stuck_sessions:
                    logger.warning(
                        f"Session {session.id} stuck for {elapsed:.0f}s, marking as failed",
                        extra={"session_id": session.id, "elapsed_seconds": elapsed}
                    )
                    await self._update_status(
                        session.id,
                        SessionStatus.FAILED,
                        error=f"Session timeout - stuck for {elapsed:.0f}s (threshold: {stuck_threshold}s)"
                    )
                    # Cancel the task
                    if session.id in self._running_tasks:
                        self._running_tasks[session.id].cancel()

            except asyncio.CancelledError:
                logger.info("Watchdog stopping")
                break
            except Exception:
                logger.exception("Watchdog error")

    async def _process_status_updates(self) -> None:
        """Process status updates from queue (runs in background)."""
        while True:
            try:
                session_id, new_status, error = await self._status_queue.get()
                async with self._lock:
                    if session_id in self._sessions:
                        session = self._sessions[session_id]
                        session.status = new_status
                        if error:
                            session.error = error
                        if new_status == SessionStatus.RUNNING:
                            session.started_at = datetime.now(timezone.utc)
                            sessions_active.inc()
                        elif new_status in (SessionStatus.COMPLETED, SessionStatus.FAILED, SessionStatus.CANCELLED):
                            session.completed_at = datetime.now(timezone.utc)
                            sessions_total.labels(status=new_status.value).inc()
                            sessions_active.dec()

                            # Record duration if we have timestamps
                            if session.started_at and session.completed_at:
                                duration = (session.completed_at - session.started_at).total_seconds()
                                session_duration_seconds.observe(duration)
                self._status_queue.task_done()
            except asyncio.CancelledError:
                break

    async def _update_status(self, session_id: str, status: SessionStatus, error: str | None = None) -> None:
        """Queue a status update with validation (thread-safe)."""
        async with self._lock:
            if session_id not in self._sessions:
                logger.warning(f"Cannot update status for unknown session: {session_id}")
                return

            current = self._sessions[session_id].status

            # Allow retrying terminal states (for recovery scenarios)
            if is_terminal_state(current) and current == status:
                logger.debug(f"Allowing re-transition to terminal state {status} for {session_id}")
            elif not is_valid_transition(current, status):
                logger.warning(
                    f"Invalid state transition for session {session_id}: {current} -> {status}. Ignoring."
                )
                return

        await self._status_queue.put((session_id, status, error))

    async def _run_session(self, session_id: str, task_def: TaskDefinition) -> None:
        """Run a grind session and update status on completion."""
        try:
            await self._update_status(session_id, SessionStatus.RUNNING)
            from grind.engine import grind
            await grind(task_def)
            await self._update_status(session_id, SessionStatus.COMPLETED)
        except asyncio.CancelledError:
            await self._update_status(session_id, SessionStatus.CANCELLED)
            raise
        except Exception as e:
            logger.exception(f"Session {session_id} failed")
            await self._update_status(session_id, SessionStatus.FAILED, error=str(e))
        finally:
            async with self._lock:
                self._running_tasks.pop(session_id, None)

    async def create_session(self, request: CreateSessionRequest) -> SessionInfo:
        """Create and start a new grind session.

        Args:
            request: The session creation request.

        Returns:
            SessionInfo for the newly created session.

        Raises:
            SessionAlreadyExistsError: If idempotency key matches existing session.
            SessionLimitReachedError: If max concurrent sessions limit is reached.
        """
        if not self._accepting_new:
            raise GrindServerError("Server is shutting down, not accepting new sessions")

        # Ensure watchdog is running
        await self._ensure_watchdog_running()

        # Check idempotency key first
        if request.idempotency_key:
            async with self._lock:
                for session in self._sessions.values():
                    if session.idempotency_key == request.idempotency_key:
                        logger.info(f"Returning existing session for idempotency key: {request.idempotency_key}")
                        return session

        # Check concurrency limit
        async with self._lock:
            running_count = sum(
                1 for s in self._sessions.values()
                if s.status == SessionStatus.RUNNING
            )
            if running_count >= self._max_concurrent_sessions:
                raise SessionLimitReachedError(running_count, self._max_concurrent_sessions)

        # Generate 8-char session ID
        session_id = uuid.uuid4().hex[:8]

        # Determine working directory
        cwd = request.cwd or str(Path.cwd())

        # Create session info
        session = SessionInfo(
            id=session_id,
            task=request.task,
            status=SessionStatus.PENDING,
            model=request.model,
            current_iteration=0,
            max_iterations=request.max_iterations,
            cwd=cwd,
            tags=request.tags,
            created_at=datetime.now(timezone.utc),
            started_at=None,
            completed_at=None,
            error=None,
            idempotency_key=request.idempotency_key,
        )

        # Store session
        async with self._lock:
            self._sessions[session_id] = session

        # Create task definition
        from grind.models import TaskDefinition
        task_def = TaskDefinition(
            task=request.task,
            verify=request.verify or "echo 'No verify command'",
            max_iterations=request.max_iterations,
            cwd=cwd,
            model=request.model,  # type: ignore[arg-type]
            session_id=session_id,
        )

        # Start the session task
        task = asyncio.create_task(self._run_session(session_id, task_def))
        async with self._lock:
            self._running_tasks[session_id] = task

        with LogContext(logger, session_id=session_id):
            logger.info("Session created", extra={
                "task": request.task[:100],  # Truncate long tasks
                "model": request.model,
                "max_iterations": request.max_iterations,
            })

        return session

    async def get_session(self, session_id: str) -> SessionInfo:
        """Get information about a session.

        Args:
            session_id: The session ID to look up.

        Returns:
            SessionInfo for the requested session.

        Raises:
            SessionNotFoundError: If session does not exist.
        """
        async with self._lock:
            if session_id not in self._sessions:
                raise SessionNotFoundError(session_id)
            return self._sessions[session_id]

    async def list_sessions(self, tag: str | None = None) -> list[SessionInfo]:
        """List all sessions, optionally filtered by tag.

        Args:
            tag: Optional tag to filter by.

        Returns:
            List of SessionInfo objects.
        """
        async with self._lock:
            sessions = list(self._sessions.values())

        if tag:
            sessions = [s for s in sessions if tag in s.tags]

        return sessions

    async def cancel_session(self, session_id: str) -> bool:
        """Cancel a running session.

        Args:
            session_id: The session ID to cancel.

        Returns:
            True if cancellation was initiated.

        Raises:
            SessionNotFoundError: If session does not exist.
        """
        async with self._lock:
            if session_id not in self._sessions:
                raise SessionNotFoundError(session_id)

            task = self._running_tasks.get(session_id)
            if task and not task.done():
                task.cancel()
                logger.info(f"Cancelling session {session_id}")
                return True

        return False

    def get_log_path(self, session_id: str) -> Path:
        """Get the log file path for a session.

        Args:
            session_id: The session ID.

        Returns:
            Path to the session log file.
        """
        return Path.home() / ".grind" / "sessions" / session_id / "session.log"

    async def inject(self, session_id: str, message: str) -> bool:
        """Inject a message into a running session.

        Args:
            session_id: The session ID.
            message: The message to inject.

        Returns:
            True if injection was successful.

        Raises:
            SessionNotFoundError: If session does not exist.
            SessionNotRunningError: If session is not running.
        """
        async with self._lock:
            if session_id not in self._sessions:
                raise SessionNotFoundError(session_id)

            session = self._sessions[session_id]
            if session.status != SessionStatus.RUNNING:
                raise SessionNotRunningError(session_id, session.status.value)

        # Use the new programmatic injection API
        from grind.interactive_v2 import inject_guidance

        success = await inject_guidance(
            session_id=session_id,
            message=message,
            persistent=False,  # Could be made configurable via request
        )

        if success:
            logger.info(
                f"Injected guidance into session {session_id}: {message[:100]}...",
                extra={"session_id": session_id, "message_length": len(message)}
            )
        else:
            logger.warning(
                f"Failed to inject guidance into session {session_id}",
                extra={"session_id": session_id}
            )

        return success

    async def _wait_for_sessions(self, sessions: list[SessionInfo]) -> None:
        """Wait for sessions to complete."""
        session_ids = {s.id for s in sessions}
        while True:
            async with self._lock:
                still_running = [
                    s for s in self._sessions.values()
                    if s.id in session_ids and s.status == SessionStatus.RUNNING
                ]
            if not still_running:
                break
            await asyncio.sleep(0.5)

    def _save_session_state(self, session_id: str) -> None:
        """Persist session state to disk."""
        session = self._sessions.get(session_id)
        if not session:
            return

        state_dir = Path.home() / ".grind" / "sessions" / session_id
        state_dir.mkdir(parents=True, exist_ok=True)
        state_file = state_dir / "state.json"

        state = {
            "id": session.id,
            "task": session.task,
            "status": session.status.value,
            "current_iteration": session.current_iteration,
            "error": session.error,
            "created_at": session.created_at.isoformat(),
            "completed_at": session.completed_at.isoformat() if session.completed_at else None,
        }
        state_file.write_text(json.dumps(state, indent=2))

    async def shutdown(self, timeout: float = 30.0, force_kill_delay: float = 5.0) -> None:
        """Gracefully shutdown, with hard kill for unresponsive sessions.

        Args:
            timeout: Wait this long for sessions to complete gracefully
            force_kill_delay: After cancelling, wait this long before force-killing
        """
        logger.info(f"Shutting down, waiting up to {timeout}s for sessions...")

        self._accepting_new = False

        # Stop watchdog first
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass

        # Stop status processor
        if self._status_processor_task and not self._status_processor_task.done():
            self._status_processor_task.cancel()
            try:
                await self._status_processor_task
            except asyncio.CancelledError:
                pass

        # Wait for running sessions
        running = [s for s in self._sessions.values() if s.status == SessionStatus.RUNNING]
        if running:
            try:
                await asyncio.wait_for(
                    self._wait_for_sessions(running),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                logger.warning(f"Timeout waiting for {len(running)} sessions, cancelling...")
                # Cancel all running tasks
                for session in running:
                    if session.id in self._running_tasks:
                        task = self._running_tasks[session.id]
                        if not task.done():
                            logger.info(f"Cancelling session {session.id}")
                            task.cancel()

                # Wait briefly for cancellation to take effect
                logger.info(f"Waiting {force_kill_delay}s for cancellation...")
                await asyncio.sleep(force_kill_delay)

                # Force-kill any still-running tasks
                still_running = []
                for session in running:
                    if session.id in self._running_tasks:
                        task = self._running_tasks[session.id]
                        if not task.done():
                            still_running.append(session.id)
                            logger.error(
                                f"Force-killing unresponsive session {session.id}",
                                extra={"session_id": session.id}
                            )
                            task.cancel()
                            try:
                                await task
                            except asyncio.CancelledError:
                                pass
                            except Exception:
                                logger.exception(f"Error force-killing {session.id}")

                if still_running:
                    logger.warning(f"Force-killed {len(still_running)} unresponsive sessions")

        # Save state for all sessions
        for session_id in self._sessions:
            self._save_session_state(session_id)

        logger.info("Shutdown complete")

    async def recover_sessions(self) -> int:
        """Recover session state from disk. Returns count of recovered sessions."""
        # Start the status processor
        await self._start_status_processor()

        # Ensure watchdog is running
        await self._ensure_watchdog_running()

        sessions_dir = Path.home() / ".grind" / "sessions"
        if not sessions_dir.exists():
            return 0

        recovered = 0
        for state_file in sessions_dir.glob("*/state.json"):
            try:
                state = json.loads(state_file.read_text())
                session_id = state["id"]

                # Mark interrupted sessions as failed
                if state["status"] == SessionStatus.RUNNING:
                    state["status"] = SessionStatus.FAILED
                    state["error"] = "Server restart"
                    state_file.write_text(json.dumps(state, indent=2))

                # Reconstruct SessionInfo
                session = SessionInfo(
                    id=session_id,
                    task=state["task"],
                    status=SessionStatus(state["status"]),
                    model=state.get("model", "sonnet"),
                    current_iteration=state.get("current_iteration", 0),
                    max_iterations=state.get("max_iterations", 10),
                    cwd=state.get("cwd", str(Path.cwd())),
                    tags=state.get("tags", []),
                    created_at=datetime.fromisoformat(state["created_at"]),
                    started_at=datetime.fromisoformat(state["started_at"]) if state.get("started_at") else None,
                    completed_at=datetime.fromisoformat(state["completed_at"]) if state.get("completed_at") else None,
                    error=state.get("error"),
                )

                async with self._lock:
                    self._sessions[session_id] = session
                recovered += 1

            except Exception:
                logger.exception(f"Failed to recover session from {state_file}")

        logger.info(f"Recovered {recovered} sessions from disk")
        return recovered
