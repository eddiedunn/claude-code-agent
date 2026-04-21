"""SQLite event store for observability data.

Why SQLite (Dan's choice):
- Portable: single file, no server process
- Fast: handles thousands of events per second
- Queryable: full SQL for analysis after the fact
- Simple: stdlib sqlite3, no ORM needed

The store is append-only during normal operation. Events flow in
from hooks and get persisted for later analysis. The WebSocket
stream is handled separately by the server.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from grind.observer.models import AgentEvent, EventType

DEFAULT_DB_PATH = Path.home() / ".grind" / "observer.db"


class EventStore:
    """SQLite-backed event storage.

    Thread-safe for single-writer, multiple-reader access.
    The observer server writes events; queries can read concurrently.
    """

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                session_id TEXT NOT NULL,
                agent_name TEXT DEFAULT '',
                tool_name TEXT DEFAULT '',
                tool_input TEXT DEFAULT '',
                tool_result TEXT DEFAULT '',
                duration_ms REAL DEFAULT 0,
                payload TEXT DEFAULT '{}',
                timestamp REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_session
            ON events(session_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_timestamp
            ON events(timestamp)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_type
            ON events(event_type)
        """)
        conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def insert(self, event: AgentEvent) -> int:
        """Insert a single event. Returns the row ID."""
        conn = self._get_conn()
        cursor = conn.execute(
            """
            INSERT INTO events
                (event_type, session_id, agent_name, tool_name,
                 tool_input, tool_result, duration_ms, payload, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_type.value,
                event.session_id,
                event.agent_name,
                event.tool_name,
                event.tool_input[:500],
                event.tool_result[:500],
                event.duration_ms,
                json.dumps(event.payload),
                event.timestamp,
            ),
        )
        conn.commit()
        return cursor.lastrowid

    def query(
        self,
        session_id: str | None = None,
        agent_name: str | None = None,
        event_type: EventType | None = None,
        since: float | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """Query events with optional filters.

        Returns list of event dicts, newest first.
        """
        conn = self._get_conn()
        conditions = []
        params: list = []

        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)
        if agent_name:
            conditions.append("agent_name = ?")
            params.append(agent_name)
        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type.value)
        if since:
            conditions.append("timestamp >= ?")
            params.append(since)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        rows = conn.execute(
            f"""
            SELECT * FROM events
            {where}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()

        results = []
        for row in rows:
            d = dict(row)
            d["payload"] = json.loads(d.get("payload", "{}"))
            results.append(d)
        return results

    def count(self, session_id: str | None = None) -> int:
        """Count events, optionally filtered by session."""
        conn = self._get_conn()
        if session_id:
            row = conn.execute(
                "SELECT COUNT(*) FROM events WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) FROM events").fetchone()
        return row[0] if row else 0

    def sessions(self) -> list[dict]:
        """List all unique sessions with event counts."""
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT session_id,
                   COUNT(*) as event_count,
                   MIN(timestamp) as started,
                   MAX(timestamp) as last_event
            FROM events
            GROUP BY session_id
            ORDER BY last_event DESC
        """).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
