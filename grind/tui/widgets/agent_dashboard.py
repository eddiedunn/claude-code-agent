#!/usr/bin/env python3
"""
Compact text-based Agent Dashboard widget for Grind TUI.

Dense, CLI-native display showing:
- One-line status summary (Running: X | Pending: X | Completed: X | Failed: X)
- List of active agents in text format with status/task/iteration
- No decoration, minimal formatting
"""

import logging
from typing import Callable

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static, ListView

from grind.tui.core.models import AgentInfo, AgentStatus
from .list_items import AgentListItem

logger = logging.getLogger(__name__)


class AgentDashboard(Vertical):
    """
    Compact text-based agent dashboard - minimal, CLI-native display.

    Shows real-time status in a single-line format and lists active agents
    without decoration or visual clutter.

    Layout:
    =======

    Running: 3 | Pending: 2 | Completed: 15 | Failed: 1
    > agent-1 [running] Fix linting errors (1/5)
    > agent-2 [running] Write unit tests (2/5)
    P agent-3 [pending] Deploy to staging (0/5)

    Callbacks:
    ==========

    - on_spawn: Called when Spawn button is pressed
    - on_pause: Called when Pause button is pressed
    - on_resume: Called when Resume button is pressed
    - on_cancel: Called when Cancel button is pressed
    - on_clear: Called when Clear button is pressed

    Usage:
    ======

    dashboard = AgentDashboard()
    dashboard.on_spawn = lambda: self.handle_spawn_agent()
    dashboard.update_agents(self.session.agents)
    """

    DEFAULT_CSS = """
    /* dashboard layout - minimal, CLI-native design */
    AgentDashboard {
        layout: vertical;
        height: 1fr;
        width: 1fr;
    }

    AgentDashboard #status-overview {
        height: auto;
        padding: 0;
        background: transparent;
        border: none;
    }

    AgentDashboard #agent-feed {
        height: 1fr;
        border: none;
        background: transparent;
    }

    AgentDashboard #agent-feed-list {
        height: 1fr;
        width: 1fr;
    }
    """

    def __init__(self, *args, **kwargs):
        """Initialize the agent dashboard."""
        super().__init__(*args, **kwargs)
        self.agents: list[AgentInfo] = []

        # Callbacks for quick actions
        self.on_spawn: Callable[[], None] | None = None
        self.on_pause: Callable[[], None] | None = None
        self.on_resume: Callable[[], None] | None = None
        self.on_cancel: Callable[[], None] | None = None
        self.on_clear: Callable[[], None] | None = None

    def compose(self) -> ComposeResult:
        """Compose the dashboard layout."""
        # Status Overview Section (one-line format)
        yield Static(
            self._render_status_overview(),
            id="status-overview"
        )

        # Agent Feed Section (dense list)
        with Vertical(id="agent-feed"):
            yield ListView(id="agent-feed-list")

    def _render_status_overview(self) -> str:
        """Render compact one-line status summary."""
        if not self.agents:
            return "No agents yet"

        # Count agents by status
        running = len([a for a in self.agents if a.status == AgentStatus.RUNNING])
        pending = len([a for a in self.agents if a.status == AgentStatus.PENDING])
        completed = len([a for a in self.agents if a.status == AgentStatus.COMPLETE])
        failed = len([a for a in self.agents if a.status == AgentStatus.FAILED])

        return f"Running: {running} | Pending: {pending} | Completed: {completed} | Failed: {failed}"

    def update_agents(self, agents: list[AgentInfo]) -> None:
        """
        Update the dashboard with new agent information.

        Args:
            agents: List of all current agents
        """
        self.agents = agents
        self._update_status_overview()
        self._update_agent_feed()

    def _update_status_overview(self) -> None:
        """Update the status overview display."""
        try:
            status_overview = self.query_one("#status-overview", Static)
            status_overview.update(self._render_status_overview())
        except Exception as e:
            logger.debug(f"Failed to update status overview: {e}")

    def _update_agent_feed(self) -> None:
        """Update the agent feed list."""
        try:
            feed_list = self.query_one("#agent-feed-list", ListView)
            feed_list.clear()

            # Filter to active agents (not completed/failed/cancelled)
            active_agents = [
                a for a in self.agents
                if a.status in (
                    AgentStatus.RUNNING,
                    AgentStatus.PENDING,
                    AgentStatus.PAUSED
                )
            ]

            if not active_agents:
                # Show a placeholder when no active agents
                feed_list.append(
                    Static("[dim]No active agents. Completed agents shown in Completed tab.[/dim]")
                )
            else:
                # Show active agents with status indicators
                for agent in active_agents:
                    feed_list.append(AgentListItem(agent))

        except Exception as e:
            logger.debug(f"Failed to update agent feed: {e}")

