"""Per-session event log for durability and replay."""
from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
from typing import Any

class EventLog:
    """Thread-safe in-memory event log with TTL."""

    def __init__(self, max_events: int = 1000, ttl_seconds: float = 3600):
        self._logs: dict[str, deque[dict[str, Any]]] = {}
        self._lock = asyncio.Lock()
        self._max_events = max_events
        self._ttl_seconds = ttl_seconds

    async def append(self, session_id: str, event: dict[str, Any]) -> None:
        """Append event to session log."""
        async with self._lock:
            if session_id not in self._logs:
                self._logs[session_id] = deque(maxlen=self._max_events)

            # Add timestamp if not present
            if "timestamp" not in event:
                event["timestamp"] = datetime.now(timezone.utc).isoformat()

            self._logs[session_id].append(event)

    async def get_since(
        self, session_id: str, since: datetime | None = None
    ) -> list[dict[str, Any]]:
        """Get events for a session since a given time."""
        async with self._lock:
            if session_id not in self._logs:
                return []

            events = list(self._logs[session_id])

            if since is None:
                return events

            # Filter by timestamp
            filtered = []
            for event in events:
                if "timestamp" in event:
                    event_time = datetime.fromisoformat(event["timestamp"])
                    if event_time > since:
                        filtered.append(event)
            return filtered

    async def cleanup_old_sessions(self, session_ids: set[str]) -> None:
        """Remove logs for sessions not in the active set."""
        async with self._lock:
            to_remove = [sid for sid in self._logs if sid not in session_ids]
            for sid in to_remove:
                del self._logs[sid]
