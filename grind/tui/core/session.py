#!/usr/bin/env python3
"""
Session management for Agent TUI.

Provides session directory management for agent execution,
with automatic cleanup on exit.
"""

import asyncio
import atexit
import logging
import shutil
import signal
import tempfile
from datetime import datetime
from pathlib import Path

from grind.tui.core.models import AgentInfo, AgentStatus

logger = logging.getLogger(__name__)


class AgentSession:
    """
    Manages a TUI session with agent execution tracking.

    Features:
    - Unique session directory per TUI instance
    - Automatic cleanup on exit (normal or crash)
    - Signal handlers for Ctrl+C cleanup
    - Context manager support for guaranteed cleanup
    - Agent lifecycle tracking

    Usage:
        session = AgentSession()
        log_path = session.get_agent_log_path("agent-1")
        session.add_agent(agent_info)
        # ... use session ...
        session.cleanup()  # Manual cleanup

    Or as context manager:
        with AgentSession() as session:
            # ... automatically cleaned up on exit
    """

    def __init__(self, session_id: str | None = None):
        """
        Initialize a new Agent TUI session.

        Args:
            session_id: Optional session identifier. If None, generates timestamp-based ID.
        """
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.session_dir = Path(tempfile.gettempdir()) / f"agent-tui-session-{self.session_id}"
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # Create output directory for agent logs
        self.output_dir = self.session_dir / "agent_logs"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Track agents in this session
        self.agents: list[AgentInfo] = []
        self.active_agents: dict[str, asyncio.Task] = {}  # agent_id -> task
        self._cleanup_done = False

        # Register cleanup handlers
        atexit.register(self.cleanup)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        logger.info(f"Created Agent TUI session {self.session_id} at {self.session_dir}")

    def get_agent_log_path(self, agent_id: str) -> Path:
        """
        Get path for an agent's log file.

        Args:
            agent_id: Unique agent identifier

        Returns:
            Path to agent log file
        """
        return self.output_dir / f"{agent_id}.log"

    def add_agent(self, agent: AgentInfo) -> None:
        """
        Add an agent to the session tracking.

        Args:
            agent: AgentInfo instance to track
        """
        # Check if agent already exists
        existing = self.get_agent(agent.agent_id)
        if existing:
            logger.warning(f"Agent {agent.agent_id} already exists in session, updating")
            # Remove old instance
            self.agents = [a for a in self.agents if a.agent_id != agent.agent_id]

        self.agents.append(agent)
        logger.debug(f"Added agent {agent.agent_id} to session {self.session_id}")

    def get_agent(self, agent_id: str) -> AgentInfo | None:
        """
        Get agent info by ID.

        Args:
            agent_id: Unique agent identifier

        Returns:
            AgentInfo if found, None otherwise
        """
        for agent in self.agents:
            if agent.agent_id == agent_id:
                return agent
        return None

    def get_running_agents(self) -> list[AgentInfo]:
        """
        Get all currently running agents.

        Returns:
            List of AgentInfo with RUNNING status
        """
        return [agent for agent in self.agents if agent.status == AgentStatus.RUNNING]

    def get_completed_agents(self) -> list[AgentInfo]:
        """
        Get all completed agents (success or failure).

        Returns:
            List of AgentInfo with terminal status (COMPLETE, FAILED, CANCELLED, STUCK)
        """
        terminal_statuses = {
            AgentStatus.COMPLETE,
            AgentStatus.FAILED,
            AgentStatus.CANCELLED,
            AgentStatus.STUCK,
        }
        return [agent for agent in self.agents if agent.status in terminal_statuses]

    def cleanup(self):
        """
        Clean up all session directories and files.

        Safe to call multiple times (idempotent).
        """
        if self._cleanup_done:
            return

        if self.session_dir.exists():
            logger.info(f"Cleaning up session {self.session_id}: {self.session_dir}")
            try:
                shutil.rmtree(self.session_dir, ignore_errors=True)
                logger.info(f"Session {self.session_id} cleaned up successfully")
            except Exception as e:
                logger.error(f"Error cleaning up session {self.session_id}: {e}")

        self._cleanup_done = True

    def _signal_handler(self, signum, _frame):
        """
        Handle signals (Ctrl+C, kill) by cleaning up before exit.

        Args:
            signum: Signal number
            _frame: Current stack frame
        """
        logger.warning(f"Received signal {signum}, cleaning up session {self.session_id}")
        self.cleanup()
        raise SystemExit(0)

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - always cleanup."""
        self.cleanup()
        return False  # Don't suppress exceptions

    def __repr__(self):
        """String representation for debugging."""
        return (
            f"AgentSession(id={self.session_id}, dir={self.session_dir}, agents={len(self.agents)})"
        )
