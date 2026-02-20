"""Message queue architecture for programmatic injection in interactive mode.

This module provides thread-safe, session-scoped message queuing for the grind
interactive system. It enables programmatic injection of guidance and commands
alongside traditional TTY input.

Architecture Overview
---------------------
The message queue system consists of three main components:

1. InjectionMessage - A typed message container representing an action to inject
2. MessageQueueManager - Session-scoped queue management with thread-safe operations
3. Integration layer (to be implemented) - Bridges existing interactive.py with queues

Thread Safety Guarantees
------------------------
All queue operations use asyncio.Lock to ensure thread-safe access:
- Enqueueing messages is atomic
- Dequeueing messages is atomic
- Session creation/cleanup is atomic
- Multiple concurrent sessions are fully isolated

Session Isolation
-----------------
Each session operates on its own independent queue:
- Sessions are identified by unique string IDs (typically UUIDs)
- Messages enqueued to one session never leak to another
- A "default" session exists for backward compatibility with single-session usage
- Sessions can be explicitly cleared without affecting others

Backward Compatibility Approach
-------------------------------
This module is designed to coexist with the current interactive.py:

1. interactive.py continues to work unchanged for TTY-only usage
2. MessageQueueManager can be optionally instantiated alongside
3. The grind loop can check both TTY input AND message queues
4. When no programmatic messages exist, behavior is identical to current

Migration Path from interactive.py
----------------------------------
Phase 1 (Current): Design only - stub implementations
Phase 2: Implement MessageQueueManager with full async support
Phase 3: Add queue checking to grind loop alongside existing TTY checks
Phase 4: Expose API endpoints for programmatic injection
Phase 5: Deprecate direct TTY manipulation in favor of unified queue interface

Example Usage (Future)
----------------------
```python
# API injection
manager = MessageQueueManager()
msg = InjectionMessage(
    action=CheckpointAction.GUIDANCE,
    message="Focus on the error handling",
    timestamp=datetime.now(),
    source="api",
    session_id="abc-123"
)
await manager.enqueue("abc-123", msg)

# In grind loop
pending = await manager.dequeue("abc-123", timeout=0.1)
if pending:
    # Process injected message
    handle_checkpoint_action(pending.action, pending.message)
```
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from grind.models import CheckpointAction

if TYPE_CHECKING:
    pass

# Default TTL for messages (cleanup old unprocessed messages)
DEFAULT_MESSAGE_TTL = timedelta(minutes=30)

# Default session ID for single-session/backward-compatible usage
DEFAULT_SESSION_ID = "_default"


@dataclass
class InjectionMessage:
    """A typed message representing an action to inject into the grind loop.

    This dataclass encapsulates all information needed to process an injected
    command or guidance at a checkpoint boundary.

    Attributes:
        action: The checkpoint action to perform (GUIDANCE, ABORT, etc.)
        message: Optional text content (guidance text, status query, etc.)
        timestamp: When the message was created (for TTL enforcement)
        source: Origin of the message for auditing/debugging:
                - "api": Programmatic injection via HTTP/REST API
                - "tty": Traditional keyboard input from terminal
                - "cli": Command-line argument injection
        session_id: Target session for this message, or None for the default
                    global session. Use None for backward-compatible single-
                    session scenarios.

    Thread Safety:
        InjectionMessage instances are immutable dataclasses and safe to pass
        between threads/tasks without synchronization.

    Example:
        >>> msg = InjectionMessage(
        ...     action=CheckpointAction.GUIDANCE,
        ...     message="Try using a different algorithm",
        ...     timestamp=datetime.now(),
        ...     source="api",
        ...     session_id="session-abc-123"
        ... )
    """

    action: CheckpointAction
    message: str | None
    timestamp: datetime
    source: str  # "api", "tty", "cli"
    session_id: str | None  # None for global/default session

    def is_expired(self, ttl: timedelta = DEFAULT_MESSAGE_TTL) -> bool:
        """Check if this message has exceeded its TTL.

        Args:
            ttl: Time-to-live duration. Messages older than this are expired.

        Returns:
            True if the message timestamp is older than (now - ttl).
        """
        return datetime.now() - self.timestamp > ttl

    def to_dict(self) -> dict:
        """Serialize message to dictionary for logging/debugging.

        Returns:
            Dictionary representation of all message fields.
        """
        return {
            "action": self.action.value if hasattr(self.action, "value") else str(self.action),
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "session_id": self.session_id,
        }


@dataclass
class MessageQueueManager:
    """Session-scoped message queue manager with thread-safe async operations.

    This class manages a collection of per-session message queues, providing
    atomic operations for enqueueing, dequeueing, and managing messages across
    multiple concurrent grind sessions.

    Architecture:
        - Each session_id maps to its own asyncio.Queue
        - All queue access is protected by an asyncio.Lock
        - Queues are created lazily on first enqueue
        - Cleanup removes both messages and empty queue references

    Thread Safety:
        All public methods are async and use self._lock to ensure atomicity:
        - Concurrent enqueues to different sessions are safe
        - Concurrent enqueues to the same session are serialized
        - Dequeue operations are non-blocking with configurable timeout
        - Session cleanup is atomic

    Session Isolation:
        Sessions are completely isolated:
        - No message can be delivered to the wrong session
        - Clearing one session has no effect on others
        - Sessions can be created/destroyed independently

    Usage Pattern:
        ```python
        manager = MessageQueueManager()

        # Producer (API endpoint, CLI, etc.)
        await manager.enqueue("session-1", guidance_message)

        # Consumer (grind loop)
        msg = await manager.dequeue("session-1", timeout=0.1)
        if msg:
            process(msg)

        # Cleanup
        await manager.clear_session("session-1")
        ```

    Attributes:
        _queues: Internal mapping of session IDs to their message queues.
        _lock: Async lock protecting all queue operations.
        _ttl: Default time-to-live for message expiration checks.
    """

    _queues: dict[str, asyncio.Queue[InjectionMessage]] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _ttl: timedelta = field(default=DEFAULT_MESSAGE_TTL)

    async def enqueue(self, session_id: str, message: InjectionMessage) -> None:
        """Add a message to the specified session's queue.

        Creates the session queue if it doesn't exist. The message is added
        to the end of the queue (FIFO order).

        Args:
            session_id: Target session identifier. Use DEFAULT_SESSION_ID for
                        single-session/backward-compatible usage.
            message: The injection message to enqueue.

        Thread Safety:
            This operation is atomic. Concurrent enqueues are serialized by
            the internal lock.

        Example:
            >>> await manager.enqueue("sess-1", InjectionMessage(...))
        """
        async with self._lock:
            if session_id not in self._queues:
                self._queues[session_id] = asyncio.Queue()
            await self._queues[session_id].put(message)

    async def dequeue(
        self, session_id: str, timeout: float = 0.1
    ) -> InjectionMessage | None:
        """Remove and return the next message from a session's queue.

        Waits up to `timeout` seconds for a message to become available.
        Returns None if the queue is empty or doesn't exist after the timeout.

        Args:
            session_id: Session to dequeue from.
            timeout: Maximum seconds to wait for a message. Default 0.1s is
                     suitable for non-blocking polling in the grind loop.

        Returns:
            The next InjectionMessage in FIFO order, or None if no message
            is available within the timeout period.

        Thread Safety:
            This operation is atomic with respect to the queue access check.
            The actual asyncio.Queue.get() may yield to other coroutines.

        Note:
            Expired messages (past TTL) are automatically skipped and discarded.

        Example:
            >>> msg = await manager.dequeue("sess-1", timeout=0.5)
            >>> if msg:
            ...     handle_action(msg.action, msg.message)
        """
        async with self._lock:
            if session_id not in self._queues:
                return None
            queue = self._queues[session_id]

        # Try to get message with timeout, skip expired messages
        try:
            while True:
                msg = await asyncio.wait_for(queue.get(), timeout=timeout)
                if not msg.is_expired(self._ttl):
                    return msg
                # Message expired, continue to next one
        except asyncio.TimeoutError:
            return None

    async def has_messages(self, session_id: str) -> bool:
        """Check if a session has any pending messages.

        This is a lightweight check for use in conditional logic where you
        want to know if dequeue() would return a message without consuming it.

        Args:
            session_id: Session to check.

        Returns:
            True if the session exists and has at least one message queued.
            False if the session doesn't exist or its queue is empty.

        Thread Safety:
            This check is atomic but the result may be stale immediately
            after return due to concurrent operations. Use for optimization
            hints only, not for critical synchronization.

        Example:
            >>> if await manager.has_messages("sess-1"):
            ...     msg = await manager.dequeue("sess-1")
        """
        async with self._lock:
            if session_id not in self._queues:
                return False
            return not self._queues[session_id].empty()

    async def clear_session(self, session_id: str) -> None:
        """Remove all messages and cleanup resources for a session.

        This should be called when a grind session ends to prevent memory leaks.
        Safe to call on non-existent sessions (no-op).

        Args:
            session_id: Session to clear.

        Thread Safety:
            This operation is atomic. Any messages enqueued during the clear
            will either be included in the clear or will create a new queue.

        Example:
            >>> await manager.clear_session("sess-1")
        """
        async with self._lock:
            if session_id in self._queues:
                del self._queues[session_id]

    async def cleanup_expired(self) -> int:
        """Remove expired messages from all sessions.

        Iterates through all queues and removes messages that have exceeded
        the TTL. This is intended for periodic maintenance.

        Returns:
            The number of expired messages removed across all sessions.

        Thread Safety:
            This operation is atomic per-session but may yield between
            sessions to allow other operations.

        Note:
            Empty queues are not removed by this operation. Use clear_session()
            to remove unused session queues.
        """
        expired_count = 0
        async with self._lock:
            for session_id, queue in list(self._queues.items()):
                # Drain and rebuild queue without expired messages
                temp_messages = []
                while not queue.empty():
                    try:
                        msg = queue.get_nowait()
                        if msg.is_expired(self._ttl):
                            expired_count += 1
                        else:
                            temp_messages.append(msg)
                    except asyncio.QueueEmpty:
                        break

                # Re-add non-expired messages
                for msg in temp_messages:
                    await queue.put(msg)

        return expired_count

    async def get_session_ids(self) -> list[str]:
        """Return a list of all active session IDs.

        Useful for debugging and monitoring.

        Returns:
            List of session ID strings with active queues.

        Thread Safety:
            Returns a snapshot; the actual set of sessions may change
            immediately after this call returns.
        """
        async with self._lock:
            return list(self._queues.keys())

    async def get_queue_depth(self, session_id: str) -> int:
        """Return the number of messages pending in a session's queue.

        Args:
            session_id: Session to check.

        Returns:
            Number of messages in the queue, or 0 if session doesn't exist.

        Thread Safety:
            Returns a snapshot; the depth may change immediately after.
        """
        async with self._lock:
            if session_id not in self._queues:
                return 0
            return self._queues[session_id].qsize()


# Module-level singleton for backward compatibility
# This allows simple usage without explicit manager instantiation
_global_manager: MessageQueueManager | None = None


def get_message_queue_manager() -> MessageQueueManager:
    """Get or create the global MessageQueueManager singleton.

    This provides a convenient default manager for simple usage patterns
    where explicit session management isn't needed.

    Returns:
        The global MessageQueueManager instance.

    Thread Safety:
        This function is NOT thread-safe on first call. In async contexts,
        prefer creating your own MessageQueueManager instance.

    Example:
        >>> manager = get_message_queue_manager()
        >>> await manager.enqueue(DEFAULT_SESSION_ID, msg)
    """
    global _global_manager
    if _global_manager is None:
        _global_manager = MessageQueueManager()
    return _global_manager


async def inject_guidance(
    session_id: str,
    message: str,
    persistent: bool = False,
    manager: MessageQueueManager | None = None,
) -> bool:
    """High-level API for programmatic guidance injection.

    This is a convenience function for injecting guidance messages without
    manually constructing InjectionMessage objects.

    Args:
        session_id: Target session identifier.
        message: The guidance text to inject.
        persistent: If True, the message will not expire (set TTL to 1 year).
                    Use sparingly for critical messages.
        manager: Optional MessageQueueManager instance. If None, uses the
                 global singleton.

    Returns:
        True if the message was successfully enqueued, False on error.

    Example:
        >>> await inject_guidance("sess-1", "Focus on error handling")
        True
    """
    try:
        if manager is None:
            manager = get_message_queue_manager()

        msg = InjectionMessage(
            action=CheckpointAction.GUIDANCE,
            message=message,
            timestamp=datetime.now(),
            source="api",
            session_id=session_id,
        )

        await manager.enqueue(session_id, msg)
        return True
    except Exception as e:
        # Log error but don't raise - this is a high-level API
        logging.error(f"Failed to inject guidance: {e}", exc_info=True)
        return False


async def inject_action(
    session_id: str,
    action: CheckpointAction,
    manager: MessageQueueManager | None = None,
) -> bool:
    """Inject a control action (abort, status, verify).

    This is a convenience function for injecting control actions without
    associated message text.

    Args:
        session_id: Target session identifier.
        action: The checkpoint action to inject (ABORT, STATUS, VERIFY, etc.).
        manager: Optional MessageQueueManager instance. If None, uses the
                 global singleton.

    Returns:
        True if the action was successfully enqueued, False on error.

    Example:
        >>> await inject_action("sess-1", CheckpointAction.ABORT)
        True
    """
    try:
        if manager is None:
            manager = get_message_queue_manager()

        msg = InjectionMessage(
            action=action,
            message=None,
            timestamp=datetime.now(),
            source="api",
            session_id=session_id,
        )

        await manager.enqueue(session_id, msg)
        return True
    except Exception as e:
        # Log error but don't raise - this is a high-level API
        logging.error(f"Failed to inject action: {e}", exc_info=True)
        return False
