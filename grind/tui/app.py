"""
Main TUI Application for Agent Orchestration.

Assembles all TUI components into a complete application with tabbed interface,
status bar, log streaming, and REPL shell.
"""

import asyncio
import logging
from datetime import datetime
from typing import Iterator

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    ListView,
    Static,
    TabbedContent,
    TabPane,
)

from grind.orchestration.events import EventBus
from grind.tui.core.agent_executor import AgentExecutor
from grind.tui.core.log_stream import AgentLogStreamer
from grind.tui.core.models import AgentInfo, AgentStatus
from grind.tui.core.session import AgentSession
from grind.tui.core.shell_commands import CommandRegistry, ShellContext
from grind.tui.core.tab_registry import TabConfig, TabRegistry
from grind.tui.widgets.agent_controls import AgentControlPanel
from grind.tui.widgets.agents_manager import CompletedAgentsManager, RunningAgentsManager
from grind.tui.widgets.event_handler import EventHandler
from grind.tui.widgets.log_viewer import StreamingLogViewer
from grind.tui.widgets.metrics_view import MetricsView
from grind.tui.widgets.shell import AgentShell
from grind.tui.widgets.status_bar import AgentStatusBar

logger = logging.getLogger(__name__)


class AgentTUI(App):
    """Main TUI application for agent orchestration.

    Provides a tabbed interface for:
    - Viewing all agents
    - DAG visualization
    - Monitoring running agents
    - Viewing completed agents
    - Real-time log streaming
    - Interactive REPL shell
    """

    TITLE = "Grind - Agent Orchestration"
    CSS_PATH = "styles/app.tcss"

    # Bindings will be dynamically set based on TabRegistry
    BINDINGS = [
        ("1", "switch_agents", "Agents"),
        ("2", "switch_dag", "DAG"),
        ("3", "switch_running", "Running"),
        ("4", "switch_completed", "Completed"),
        ("5", "switch_logs", "Logs"),
        ("6", "switch_shell", "Shell"),
        ("7", "switch_metrics", "Metrics"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self):
        """Initialize the Agent TUI application."""
        super().__init__()

        # Core components
        self.event_bus = EventBus()
        self.session = AgentSession()
        self.executor = AgentExecutor(self.session, event_bus=self.event_bus)
        self.tab_registry = TabRegistry()
        self.log_streamer = AgentLogStreamer()
        self.command_registry = CommandRegistry()

        # Managers (initialized on mount)
        self.running_agents_manager: RunningAgentsManager | None = None
        self.completed_agents_manager: CompletedAgentsManager | None = None
        self.shell_context: ShellContext | None = None
        self.event_handler: EventHandler | None = None

        # Startup configuration
        self.startup_task_file: str | None = None
        self.default_model: str = "sonnet"

        # Register tabs
        self._register_tabs()

    def _register_tabs(self) -> None:
        """Register all tabs with the TabRegistry."""
        self.tab_registry.register_many(
            [
                TabConfig(
                    id="tab-agents",
                    title="Agents",
                    key="1",
                    action_name="switch_agents",
                    binding_description="Agents",
                    compose_fn=self._compose_agents_tab,
                    category="agents",
                ),
                TabConfig(
                    id="tab-dag",
                    title="DAG",
                    key="2",
                    action_name="switch_dag",
                    binding_description="DAG",
                    compose_fn=self._compose_dag_tab,
                    category="agents",
                ),
                TabConfig(
                    id="tab-running",
                    title="Running",
                    key="3",
                    action_name="switch_running",
                    binding_description="Running",
                    compose_fn=self._compose_running_tab,
                    category="monitoring",
                ),
                TabConfig(
                    id="tab-completed",
                    title="Completed",
                    key="4",
                    action_name="switch_completed",
                    binding_description="Completed",
                    compose_fn=self._compose_completed_tab,
                    category="monitoring",
                ),
                TabConfig(
                    id="tab-logs",
                    title="Logs",
                    key="5",
                    action_name="switch_logs",
                    binding_description="Logs",
                    compose_fn=self._compose_logs_tab,
                    category="logs",
                ),
                TabConfig(
                    id="tab-shell",
                    title="Shell",
                    key="6",
                    action_name="switch_shell",
                    binding_description="Shell",
                    compose_fn=self._compose_shell_tab,
                    category="tools",
                ),
                TabConfig(
                    id="tab-metrics",
                    title="Metrics",
                    key="7",
                    action_name="switch_metrics",
                    binding_description="Metrics",
                    compose_fn=self._compose_metrics_tab,
                    category="monitoring",
                ),
            ]
        )

    def compose(self) -> ComposeResult:
        """Compose the application layout."""
        yield Header()
        yield AgentStatusBar(id="status-bar")
        yield EventHandler(event_bus=self.event_bus, id="event-handler")
        with TabbedContent(initial="tab-agents"):
            for tab in self.tab_registry.get_enabled_tabs():
                with TabPane(tab.title, id=tab.id):
                    if tab.compose_fn:
                        yield from tab.compose_fn()
                    else:
                        yield Static(f"Content for {tab.title}")
        yield Footer()

    def _compose_agents_tab(self) -> Iterator[ComposeResult]:
        """Compose content for the Agents tab."""
        with Container(classes="agent-overview"):
            yield Static(
                "[bold]Agent Overview[/bold]\n\n"
                "Use the shell tab (press 6) to manage agents.\n"
                "Commands: agents, spawn, cancel, pause, resume",
                id="agents-overview",
            )

    def _compose_dag_tab(self) -> Iterator[ComposeResult]:
        """Compose content for the DAG tab."""
        yield Static(
            "[dim]DAG Visualization[/dim]\n\n"
            "Task dependency graph will be displayed here\n"
            "when tasks are loaded from a task file.",
            id="dag-placeholder",
        )

    def _compose_running_tab(self) -> Iterator[ComposeResult]:
        """Compose content for the Running tab."""
        yield AgentControlPanel(id="agent-control-panel")
        yield ListView(id="running-agents-list")

    def _compose_completed_tab(self) -> Iterator[ComposeResult]:
        """Compose content for the Completed tab."""
        yield DataTable(id="completed-agents-table")

    def _compose_logs_tab(self) -> Iterator[ComposeResult]:
        """Compose content for the Logs tab."""
        yield StreamingLogViewer(id="log-viewer")

    def _compose_shell_tab(self) -> Iterator[ComposeResult]:
        """Compose content for the Shell tab."""
        yield AgentShell(
            id="agent-shell",
            command_registry=self.command_registry,
        )

    def _compose_metrics_tab(self) -> Iterator[ComposeResult]:
        """Compose content for the Metrics tab."""
        yield MetricsView(id="metrics-view")

    def on_mount(self) -> None:
        """Handle application mount event."""
        # Initialize status bar
        try:
            status_bar = self.query_one("#status-bar", AgentStatusBar)
            status_bar.update_status(agents=[], model=self.default_model)
        except Exception:
            pass

        # Initialize managers with widget references
        try:
            running_list = self.query_one("#running-agents-list", ListView)
            self.running_agents_manager = RunningAgentsManager(running_list)
        except Exception:
            pass

        try:
            completed_table = self.query_one("#completed-agents-table", DataTable)
            self.completed_agents_manager = CompletedAgentsManager(completed_table)
        except Exception:
            pass

        # Initialize event handler
        try:
            self.event_handler = self.query_one("#event-handler", EventHandler)
            self.event_handler.on_agent_updated = self._on_agent_status_changed
        except Exception:
            pass

        # Initialize agent control panel callbacks
        try:
            control_panel = self.query_one("#agent-control-panel", AgentControlPanel)
            control_panel.on_start = self._handle_agent_start
            control_panel.on_stop = self._handle_agent_stop
            control_panel.on_restart = self._handle_agent_restart
        except Exception:
            pass

        # Initialize shell context
        self.shell_context = ShellContext(
            session=self.session,
            agents=self.session.agents,
            current_agent_id=None,
            history=[],
            variables={},
            executor=self.executor,
        )

        # Update shell widget with context
        try:
            shell = self.query_one("#agent-shell", AgentShell)
            shell.shell_context = self.shell_context
            shell.command_registry = self.command_registry
        except Exception:
            pass

        # Register executor callbacks
        self.executor.add_status_callback(self._on_agent_status_changed)
        self.executor.add_log_callback(self._on_agent_log_line)

        # Update status bar
        self._update_status_bar()

        # Load startup task file if specified
        if self.startup_task_file:
            self.run_worker(self._load_and_run_task_file(self.startup_task_file))

    def _update_status_bar(self) -> None:
        """Update the status bar with current agent counts."""
        try:
            status_bar = self.query_one("#status-bar", AgentStatusBar)
            status_bar.update_status(agents=self.session.agents)
        except Exception:
            pass

    def _update_shell_context(self) -> None:
        """Update shell context with current agent list."""
        if self.shell_context:
            self.shell_context.agents = self.session.agents

    async def _load_and_run_task_file(self, task_file: str) -> None:
        """Load and execute a task file on startup.

        Args:
            task_file: Path to tasks.yaml file
        """
        try:
            from grind.tasks import load_tasks

            # Load tasks from file
            tasks = await asyncio.to_thread(load_tasks, task_file)

            # Create agents for each task
            for task_def in tasks:
                agent = self.executor.create_agent(task_def)

            # Update shell context with new agents
            self._update_shell_context()
            self._update_status_bar()

            # Start executing agents (respect max_parallel)
            for agent in self.session.agents:
                self.executor.start_agent(agent.agent_id)

        except Exception as e:
            # Log error but don't crash the TUI
            logger.error(f"Failed to load task file {task_file}: {e}")

    def _on_agent_status_changed(self, agent: AgentInfo) -> None:
        """Handle agent status change callback.

        Args:
            agent: The agent whose status changed
        """
        # Update status bar
        self._update_status_bar()

        # Update managers
        if self.running_agents_manager:
            self.running_agents_manager.update(self.session.agents)
        if self.completed_agents_manager:
            self.completed_agents_manager.update(self.session.agents)

        # Update shell context
        self._update_shell_context()

    def _on_agent_log_line(self, agent_id: str, line: str, ts: datetime) -> None:
        """Handle agent log line callback.

        Args:
            agent_id: ID of the agent that produced the log line
            line: The log line content
            ts: Timestamp of the log line
        """
        try:
            log_viewer = self.query_one("#log-viewer", StreamingLogViewer)
            # Only append if we're viewing this agent's logs
            if log_viewer.current_agent_id == agent_id or log_viewer.current_agent_id is None:
                log_viewer.append_line(line, ts)
        except Exception:
            pass

    def _handle_agent_start(self, agent_id: str) -> None:
        """Handle start button press from AgentControlPanel.

        Args:
            agent_id: ID of the agent to start
        """
        self.executor.start_agent(agent_id)

    def _handle_agent_stop(self, agent_id: str) -> None:
        """Handle stop button press from AgentControlPanel.

        Args:
            agent_id: ID of the agent to stop
        """
        # Cancel agent asynchronously
        self.run_worker(self.executor.cancel_agent(agent_id))

    def _handle_agent_restart(self, agent_id: str) -> None:
        """Handle restart button press from AgentControlPanel.

        Args:
            agent_id: ID of the agent to restart
        """
        # Get the agent
        agent = self.session.get_agent(agent_id)
        if agent:
            # Reset the agent to pending status
            agent.status = AgentStatus.PENDING
            agent.start_time = None
            agent.end_time = None
            agent.result = None
            # Start the agent
            self.executor.start_agent(agent_id)

    # Action methods for tab switching
    def action_switch_agents(self) -> None:
        """Switch to the Agents tab."""
        self.query_one(TabbedContent).active = "tab-agents"

    def action_switch_dag(self) -> None:
        """Switch to the DAG tab."""
        self.query_one(TabbedContent).active = "tab-dag"

    def action_switch_running(self) -> None:
        """Switch to the Running tab."""
        self.query_one(TabbedContent).active = "tab-running"

    def action_switch_completed(self) -> None:
        """Switch to the Completed tab."""
        self.query_one(TabbedContent).active = "tab-completed"

    def action_switch_logs(self) -> None:
        """Switch to the Logs tab."""
        self.query_one(TabbedContent).active = "tab-logs"

    def action_switch_shell(self) -> None:
        """Switch to the Shell tab."""
        self.query_one(TabbedContent).active = "tab-shell"
        # Focus the shell input after switching
        try:
            shell = self.query_one("#agent-shell", AgentShell)
            shell.call_later(shell._focus_input)
        except Exception:
            pass

    def action_switch_metrics(self) -> None:
        """Switch to the Metrics tab."""
        self.query_one(TabbedContent).active = "tab-metrics"

    async def on_unmount(self) -> None:
        """Handle application unmount event."""
        # Cleanup executor
        await self.executor.cleanup()
        # Cleanup session
        self.session.cleanup()
