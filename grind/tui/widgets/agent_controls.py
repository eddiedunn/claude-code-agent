#!/usr/bin/env python3
"""
Agent control panel for Grind TUI.

Provides buttons for start/stop/restart individual agents via Orchestrator.
"""

import logging
from typing import Callable

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Button, Static

from grind.tui.core.models import AgentInfo, AgentStatus

logger = logging.getLogger(__name__)


class AgentControlPanel(Static):
    """
    Control panel widget with buttons for agent management.

    Provides interactive buttons to:
    - Start individual agents
    - Stop running agents
    - Restart completed/failed agents

    The widget dynamically enables/disables buttons based on agent status:
    - Start: Enabled for PENDING agents
    - Stop: Enabled for RUNNING agents
    - Restart: Enabled for COMPLETE, FAILED, STUCK, CANCELLED agents

    Usage Example:
    ==============

    # In MainScreen or AgentTUI:
    control_panel = AgentControlPanel(agent=agent_info)
    control_panel.on_start = self._handle_agent_start
    control_panel.on_stop = self._handle_agent_stop
    control_panel.on_restart = self._handle_agent_restart

    Callbacks:
    ==========

    - on_start: Called when start button is pressed
      Signature: (agent_id: str) -> None
    - on_stop: Called when stop button is pressed
      Signature: (agent_id: str) -> None
    - on_restart: Called when restart button is pressed
      Signature: (agent_id: str) -> None
    """

    def __init__(self, agent: AgentInfo | None = None, *args, **kwargs):
        """
        Initialize the agent control panel.

        Args:
            agent: AgentInfo instance to control (optional, can be set later)
            *args: Additional positional arguments for Static
            **kwargs: Additional keyword arguments for Static
        """
        super().__init__(*args, **kwargs)
        self.agent = agent
        self.on_start: Callable[[str], None] | None = None
        self.on_stop: Callable[[str], None] | None = None
        self.on_restart: Callable[[str], None] | None = None

    def compose(self) -> ComposeResult:
        """Compose the control panel layout."""
        with Container(classes="agent-controls"):
            if self.agent:
                yield Static(
                    f"[bold]Agent:[/bold] {self.agent.agent_id}\n"
                    f"[bold]Status:[/bold] {self.agent.status.value}",
                    classes="agent-info",
                )
            else:
                yield Static("[dim]No agent selected[/dim]", classes="agent-info")

            with Horizontal(classes="control-buttons"):
                yield Button("Start", id="btn-start", variant="success")
                yield Button("Stop", id="btn-stop", variant="error")
                yield Button("Restart", id="btn-restart", variant="primary")

    def on_mount(self) -> None:
        """Handle mount event - update button states."""
        self._update_button_states()

    def update_agent(self, agent: AgentInfo) -> None:
        """
        Update the agent being controlled.

        Args:
            agent: New AgentInfo instance to control
        """
        self.agent = agent
        self._update_display()
        self._update_button_states()

    def _update_display(self) -> None:
        """Update the agent info display."""
        try:
            info_widget = self.query_one(".agent-info", Static)
            if self.agent:
                info_widget.update(
                    f"[bold]Agent:[/bold] {self.agent.agent_id}\n"
                    f"[bold]Status:[/bold] {self.agent.status.value}"
                )
            else:
                info_widget.update("[dim]No agent selected[/dim]")
        except Exception as e:
            logger.debug(f"Failed to update display: {e}")

    def _update_button_states(self) -> None:
        """Update button enabled/disabled states based on agent status."""
        if not self.agent:
            # Disable all buttons if no agent
            self._disable_all_buttons()
            return

        try:
            start_btn = self.query_one("#btn-start", Button)
            stop_btn = self.query_one("#btn-stop", Button)
            restart_btn = self.query_one("#btn-restart", Button)

            # Start button: enabled for PENDING agents
            start_btn.disabled = self.agent.status != AgentStatus.PENDING

            # Stop button: enabled for RUNNING agents
            stop_btn.disabled = self.agent.status != AgentStatus.RUNNING

            # Restart button: enabled for completed/failed/stuck/cancelled agents
            restart_btn.disabled = self.agent.status not in (
                AgentStatus.COMPLETE,
                AgentStatus.FAILED,
                AgentStatus.STUCK,
                AgentStatus.CANCELLED,
            )
        except Exception as e:
            logger.debug(f"Failed to update button states: {e}")

    def _disable_all_buttons(self) -> None:
        """Disable all control buttons."""
        try:
            self.query_one("#btn-start", Button).disabled = True
            self.query_one("#btn-stop", Button).disabled = True
            self.query_one("#btn-restart", Button).disabled = True
        except Exception as e:
            logger.debug(f"Failed to disable buttons: {e}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """
        Handle button press events.

        Args:
            event: Button.Pressed event
        """
        if not self.agent:
            logger.warning("Button pressed but no agent is set")
            return

        button_id = event.button.id
        agent_id = self.agent.agent_id

        if button_id == "btn-start" and self.on_start:
            logger.info(f"Start button pressed for agent {agent_id}")
            self.on_start(agent_id)
        elif button_id == "btn-stop" and self.on_stop:
            logger.info(f"Stop button pressed for agent {agent_id}")
            self.on_stop(agent_id)
        elif button_id == "btn-restart" and self.on_restart:
            logger.info(f"Restart button pressed for agent {agent_id}")
            self.on_restart(agent_id)
