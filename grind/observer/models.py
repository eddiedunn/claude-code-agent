"""Event models for the observability system.

These models represent the events that Claude Code hooks fire.
The hook system sends JSON payloads — these models parse and
validate them for storage and streaming.

Event flow:
  Claude Code hook → HTTP POST → Observer server → EventStore (SQLite)
                                                  → WebSocket (live stream)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class EventType(str, Enum):
    """Types of events the observer can receive.

    Maps to Claude Code hook event types:
    - session_start: New Claude Code session begins
    - pre_tool_use: Before a tool executes
    - post_tool_use: After a tool executes (includes result)
    - agent_spawn: Sub-agent created (agent teams)
    - agent_complete: Sub-agent finished work
    - user_prompt: User sent a prompt
    - error: Something went wrong
    - worktree_spawn: Git worktree created for task isolation
    - worktree_accepted: Worktree accepted and merged to target branch
    - worktree_teardown: Worktree removed after completion or rejection
    - contract_violation: Execution contract was violated (Phase 3)
    """
    SESSION_START = "session_start"
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    AGENT_SPAWN = "agent_spawn"
    AGENT_COMPLETE = "agent_complete"
    USER_PROMPT = "user_prompt"
    ERROR = "error"
    WORKTREE_SPAWN = "worktree_spawn"
    WORKTREE_ACCEPTED = "worktree_accepted"
    WORKTREE_TEARDOWN = "worktree_teardown"
    CONTRACT_VIOLATION = "contract_violation"


@dataclass
class AgentEvent:
    """A single observable event from a Claude Code instance.

    Every hook fires one of these. The observer stores them and
    streams them to connected clients.
    """
    event_type: EventType
    session_id: str
    timestamp: float = field(default_factory=time.time)

    # Identity
    agent_name: str = ""

    # Tool events (pre/post_tool_use)
    tool_name: str = ""
    tool_input: str = ""
    tool_result: str = ""
    duration_ms: float = 0

    # General payload (arbitrary JSON data from the hook)
    payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to dict for JSON/SQLite storage."""
        return {
            "event_type": self.event_type.value,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "agent_name": self.agent_name,
            "tool_name": self.tool_name,
            "tool_input": self.tool_input[:500] if self.tool_input else "",
            "tool_result": self.tool_result[:500] if self.tool_result else "",
            "duration_ms": self.duration_ms,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict) -> AgentEvent:
        """Deserialize from dict."""
        return cls(
            event_type=EventType(data.get("event_type", "error")),
            session_id=data.get("session_id", "unknown"),
            timestamp=data.get("timestamp", time.time()),
            agent_name=data.get("agent_name", ""),
            tool_name=data.get("tool_name", ""),
            tool_input=data.get("tool_input", ""),
            tool_result=data.get("tool_result", ""),
            duration_ms=data.get("duration_ms", 0),
            payload=data.get("payload", {}),
        )

    @classmethod
    def from_hook_payload(cls, hook_type: str, payload: dict) -> AgentEvent:
        """Create an event from a raw Claude Code hook payload.

        Claude Code hooks pass JSON with fields like:
        - session_id
        - tool_name (for tool hooks)
        - tool_input (for tool hooks)
        """
        event_type = (
            EventType(hook_type)
            if hook_type in EventType._value2member_map_
            else EventType.ERROR
        )

        return cls(
            event_type=event_type,
            session_id=payload.get("session_id", "unknown"),
            agent_name=payload.get("agent_name", ""),
            tool_name=payload.get("tool_name", ""),
            tool_input=str(payload.get("tool_input", "")),
            tool_result=str(payload.get("tool_result", "")),
            duration_ms=payload.get("duration_ms", 0),
            payload=payload,
        )
