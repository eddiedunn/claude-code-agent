#!/usr/bin/env python3
"""
Status bar widget for Agent TUI.

Provides a persistent status bar with agent counts and status messages.
"""

from textual.reactive import reactive
from textual.widgets import Static

from ..core.models import AgentInfo, AgentStatus


class AgentStatusBar(Static):
    """
    Status bar widget with auto-updating counts using reactive properties.

    Displays:
    - Current status message
    - Total agent count
    - Running agents count
    - Completed agents count
    - Stuck agents count (if > 0)
    - Model in use

    Reactive Behavior:
    ==================

    This widget uses Textual's reactive() pattern for automatic UI updates:

    - message: Status message changes trigger immediate re-render
    - agent_count: Updates when agents are created/removed
    - running_count: Updates when agents start/complete
    - completed_count: Updates when agents finish
    - stuck_count: Updates when agents report stuck status
    - model_in_use: Updates when model selection changes

    Any change to these reactive properties automatically calls render()
    to update the displayed text without manual refresh calls.

    Visual Format:
    ==============

    Agents: {N} Running: {N} Done: {N} [Stuck: {N}] | Model: {model}
    ├──────────┤ ├─────────┤ ├─────┤  ├────────┤    ├──────────────┤
      Cyan bold   Yellow bold Green    Red bold      Normal
                              bold     (conditional)

    Usage Example:
    ==============

    # In MainScreen:
    self.status_bar = self.query_one("#status-bar", AgentStatusBar)

    # Update message only
    self.status_bar.update_status(message="Loading agents...")

    # Update counts
    self.status_bar.update_status(agents=self.agents, model="sonnet")

    # Periodic refresh (preserves message)
    self.status_bar.refresh_counts()

    Benefits:
    =========

    - No manual refresh() calls needed
    - Changes are atomic and consistent
    - Auto-batching prevents excessive re-renders
    - Clean separation between state and presentation
    """

    # Reactive properties for auto-updating UI
    message = reactive("Ready")
    agent_count = reactive(0)
    running_count = reactive(0)
    completed_count = reactive(0)
    stuck_count = reactive(0)
    model_in_use = reactive("sonnet")

    def render(self) -> str:
        """Render the status bar with current counts."""
        status_text = f"[bold cyan]Agents:[/] {self.agent_count}  "
        status_text += f"[bold yellow]Running:[/] {self.running_count}  "
        status_text += f"[bold green]Done:[/] {self.completed_count}"

        # Only show stuck count if there are stuck agents
        if self.stuck_count > 0:
            status_text += f"  [bold red]Stuck:[/] {self.stuck_count}"

        status_text += f"  | Model: {self.model_in_use}"

        return status_text

    def update_status(
        self,
        agents: list[AgentInfo] | None = None,
        message: str | None = None,
        model: str | None = None,
    ):
        """
        Update status bar with new information.

        Args:
            agents: List of agents (for count calculations)
            message: Status message to display
            model: Model name to display
        """
        if message is not None:
            self.message = message

        if model is not None:
            self.model_in_use = model

        if agents is not None:
            self.agent_count = len(agents)
            self.running_count = len([a for a in agents if a.status == AgentStatus.RUNNING])
            self.completed_count = len([a for a in agents if a.status == AgentStatus.COMPLETE])
            self.stuck_count = len([a for a in agents if a.status == AgentStatus.STUCK])

    def refresh_counts(self):
        """
        Refresh counts without changing message or model.

        Useful for periodic updates. This is a convenience method
        that manually triggers a re-render of the current state.
        """
        self.refresh()
