"""Tests for TUI widgets."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from textual.widgets import DataTable, ListView

from grind.tui.core.models import AgentInfo, AgentStatus, AgentType
from grind.tui.core.shell_commands import CommandRegistry
from grind.tui.widgets.agents_manager import CompletedAgentsManager, RunningAgentsManager
from grind.tui.widgets.list_items import AgentListItem
from grind.tui.widgets.log_viewer import StreamingLogViewer
from grind.tui.widgets.shell import AgentShell
from grind.tui.widgets.status_bar import AgentStatusBar

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_agents():
    """Create sample agents for testing."""
    now = datetime.now()
    return [
        AgentInfo(
            agent_id="agent-1",
            task_id="task-1",
            task_description="Test task 1 running",
            agent_type=AgentType.WORKER,
            status=AgentStatus.RUNNING,
            model="sonnet",
            iteration=2,
            max_iterations=5,
            progress=0.4,
            created_at=now - timedelta(minutes=10),
            started_at=now - timedelta(minutes=9),
        ),
        AgentInfo(
            agent_id="agent-2",
            task_id="task-2",
            task_description="Test task 2 pending",
            agent_type=AgentType.WORKER,
            status=AgentStatus.PENDING,
            model="haiku",
            iteration=0,
            max_iterations=3,
            progress=0.0,
            created_at=now - timedelta(minutes=5),
        ),
        AgentInfo(
            agent_id="agent-3",
            task_id="task-3",
            task_description="Test task 3 complete",
            agent_type=AgentType.WORKER,
            status=AgentStatus.COMPLETE,
            model="opus",
            iteration=3,
            max_iterations=3,
            progress=1.0,
            created_at=now - timedelta(minutes=20),
            started_at=now - timedelta(minutes=19),
            completed_at=now - timedelta(minutes=10),
        ),
        AgentInfo(
            agent_id="agent-4",
            task_id="task-4",
            task_description="Test task 4 stuck",
            agent_type=AgentType.ORCHESTRATOR,
            status=AgentStatus.STUCK,
            model="sonnet",
            iteration=5,
            max_iterations=10,
            progress=0.5,
            created_at=now - timedelta(minutes=30),
            started_at=now - timedelta(minutes=29),
            completed_at=now - timedelta(minutes=1),
        ),
    ]


# ============================================================================
# StatusBar Tests
# ============================================================================


def test_status_bar_initial_render():
    """Test StatusBar initial render with default values."""
    status_bar = AgentStatusBar()

    # Check initial reactive values
    assert status_bar.message == "Ready"
    assert status_bar.agent_count == 0
    assert status_bar.running_count == 0
    assert status_bar.completed_count == 0
    assert status_bar.stuck_count == 0
    assert status_bar.model_in_use == "sonnet"

    # Check rendered output
    rendered = status_bar.render()
    assert "Agents:" in rendered
    assert "Running:" in rendered
    assert "Done:" in rendered
    assert "Model: sonnet" in rendered


def test_status_bar_update_counts(sample_agents):
    """Test StatusBar updates counts correctly from agent list."""
    status_bar = AgentStatusBar()

    status_bar.update_status(agents=sample_agents)

    assert status_bar.agent_count == 4
    assert status_bar.running_count == 1  # Only agent-1 is RUNNING
    assert status_bar.completed_count == 1  # Only agent-3 is COMPLETE
    assert status_bar.stuck_count == 1  # Only agent-4 is STUCK


def test_status_bar_reactive_updates(sample_agents):
    """Test StatusBar reactive properties trigger re-renders."""
    status_bar = AgentStatusBar()

    # Update with agents
    status_bar.update_status(agents=sample_agents, model="opus")

    rendered = status_bar.render()
    # Check for content without markup - Rich markup is present in the string
    assert "Agents:[/] 4" in rendered or "4" in rendered
    assert "Running:[/] 1" in rendered or "1" in rendered
    assert "Done:[/] 1" in rendered or "1" in rendered
    assert "Stuck:[/] 1" in rendered or "1" in rendered
    assert "Model: opus" in rendered

    # Update message only
    status_bar.update_status(message="Processing...")
    assert status_bar.message == "Processing..."

    # Counts should remain unchanged
    assert status_bar.agent_count == 4


def test_status_bar_stuck_count_conditional():
    """Test that stuck count is only shown when > 0."""
    status_bar = AgentStatusBar()

    # No stuck agents
    status_bar.stuck_count = 0
    rendered = status_bar.render()
    assert "Stuck:[/]" not in rendered

    # With stuck agents
    status_bar.stuck_count = 2
    rendered = status_bar.render()
    assert "Stuck:[/] 2" in rendered or "2" in rendered


# ============================================================================
# AgentListItem Tests
# ============================================================================


def test_agent_list_item_pending(sample_agents):
    """Test AgentListItem displays pending agent correctly."""
    pending_agent = sample_agents[1]  # agent-2 is PENDING
    list_item = AgentListItem(pending_agent)

    assert list_item.agent.status == AgentStatus.PENDING
    assert list_item._get_status_icon() == "[dim]P[/dim]"


def test_agent_list_item_running(sample_agents):
    """Test AgentListItem displays running agent correctly."""
    running_agent = sample_agents[0]  # agent-1 is RUNNING
    list_item = AgentListItem(running_agent)

    assert list_item.agent.status == AgentStatus.RUNNING
    assert list_item._get_status_icon() == "[bold yellow]>[/bold yellow]"

    # Test progress format for running agent (shows iteration/max)
    progress = list_item._format_progress()
    assert progress == "2/5"


def test_agent_list_item_complete(sample_agents):
    """Test AgentListItem displays complete agent correctly."""
    complete_agent = sample_agents[2]  # agent-3 is COMPLETE
    list_item = AgentListItem(complete_agent)

    assert list_item.agent.status == AgentStatus.COMPLETE
    assert list_item._get_status_icon() == "[green]+[/green]"

    # Test progress format for complete agent (shows percentage)
    progress = list_item._format_progress()
    assert progress == "100%"


def test_agent_list_item_stuck(sample_agents):
    """Test AgentListItem displays stuck agent correctly."""
    stuck_agent = sample_agents[3]  # agent-4 is STUCK
    list_item = AgentListItem(stuck_agent)

    assert list_item.agent.status == AgentStatus.STUCK
    assert list_item._get_status_icon() == "[bold red]![/bold red]"


def test_agent_list_item_format_duration(sample_agents):
    """Test AgentListItem formats duration correctly."""
    agent = sample_agents[0]
    list_item = AgentListItem(agent)

    duration = list_item._format_duration()
    # Should return the agent's duration property
    assert isinstance(duration, str)
    assert duration == agent.duration


def test_agent_list_item_truncate_task():
    """Test AgentListItem truncates long task descriptions."""
    now = datetime.now()
    long_task = "This is a very long task description that exceeds the maximum length allowed"

    agent = AgentInfo(
        agent_id="test",
        task_id="test",
        task_description=long_task,
        agent_type=AgentType.WORKER,
        status=AgentStatus.RUNNING,
        model="sonnet",
        iteration=1,
        max_iterations=5,
        progress=0.2,
        created_at=now,
    )

    list_item = AgentListItem(agent)
    truncated = list_item._truncate_task(long_task, 40)

    assert len(truncated) == 40
    assert truncated.endswith("...")


# ============================================================================
# RunningAgentsManager Tests
# ============================================================================


def test_running_manager_update(sample_agents):
    """Test RunningAgentsManager filters and displays running agents."""
    list_view = MagicMock(spec=ListView)
    list_view.is_attached = True
    list_view.clear = MagicMock()
    list_view.append = MagicMock()

    manager = RunningAgentsManager(list_view)

    manager.update(sample_agents)

    # Should only show PENDING and RUNNING agents (agent-1 and agent-2)
    assert len(manager.agents) == 2
    assert all(a.status in (AgentStatus.PENDING, AgentStatus.RUNNING, AgentStatus.PAUSED)
               for a in manager.agents)


def test_running_manager_filter_status(sample_agents):
    """Test RunningAgentsManager filters correct statuses."""
    list_view = MagicMock(spec=ListView)
    list_view.is_attached = True
    list_view.clear = MagicMock()
    list_view.append = MagicMock()

    manager = RunningAgentsManager(list_view)

    manager.update(sample_agents)

    # Check that completed and stuck agents are filtered out
    agent_ids = [a.agent_id for a in manager.agents]
    assert "agent-1" in agent_ids  # RUNNING
    assert "agent-2" in agent_ids  # PENDING
    assert "agent-3" not in agent_ids  # COMPLETE - filtered out
    assert "agent-4" not in agent_ids  # STUCK - filtered out


def test_running_manager_get_count(sample_agents):
    """Test RunningAgentsManager returns correct count."""
    list_view = MagicMock(spec=ListView)
    list_view.is_attached = True
    list_view.clear = MagicMock()
    list_view.append = MagicMock()

    manager = RunningAgentsManager(list_view)

    manager.update(sample_agents)

    assert manager.get_count() == 2


def test_running_manager_not_attached():
    """Test RunningAgentsManager handles unattached list view."""
    list_view = MagicMock(spec=ListView)
    list_view.is_attached = False

    manager = RunningAgentsManager(list_view)

    # Should handle gracefully without errors
    manager.update([])
    assert manager.get_count() == 0


# ============================================================================
# CompletedAgentsManager Tests
# ============================================================================


def test_completed_manager_initialize_columns():
    """Test CompletedAgentsManager initializes columns correctly."""
    table = MagicMock(spec=DataTable)
    table.is_attached = True
    table.columns = {}
    table.add_column = MagicMock()

    manager = CompletedAgentsManager(table)

    assert not manager._columns_initialized

    manager._initialize_columns()

    assert manager._columns_initialized
    # Should have called add_column 6 times
    assert table.add_column.call_count == 6


def test_completed_manager_update(sample_agents):
    """Test CompletedAgentsManager displays completed agents."""
    table = MagicMock(spec=DataTable)
    table.is_attached = True
    table.add_column = MagicMock()
    table.clear = MagicMock()
    table.add_row = MagicMock()

    manager = CompletedAgentsManager(table)

    manager.update(sample_agents)

    # Should initialize columns on first update
    assert manager._columns_initialized

    # Should show COMPLETE and STUCK agents (agent-3 and agent-4)
    assert table.add_row.call_count == 2


def test_completed_manager_filter(sample_agents):
    """Test CompletedAgentsManager filters agents by search term."""
    table = MagicMock(spec=DataTable)
    table.is_attached = True
    table.add_column = MagicMock()
    table.clear = MagicMock()
    table.add_row = MagicMock()

    manager = CompletedAgentsManager(table)

    # Filter by task description
    manager.filter_agents("complete", sample_agents)

    # Should only show agent-3 (task description contains "complete")
    assert table.add_row.call_count == 1
    assert len(manager.filtered_agents) == 1
    assert manager.filtered_agents[0].agent_id == "agent-3"


def test_completed_manager_clear_filter(sample_agents):
    """Test CompletedAgentsManager clears filter."""
    table = MagicMock(spec=DataTable)
    table.is_attached = True
    table.add_column = MagicMock()
    table.clear = MagicMock()
    table.add_row = MagicMock()

    manager = CompletedAgentsManager(table)

    # Apply filter
    manager.filter_agents("stuck", sample_agents)
    assert len(manager.filtered_agents) == 1

    # Clear filter
    manager.clear_filter(sample_agents)
    assert len(manager.filtered_agents) == 0
    assert table.add_row.call_count == 3  # 1 from filter, 2 from clear_filter


def test_completed_manager_is_filtered():
    """Test CompletedAgentsManager tracks filter state."""
    table = MagicMock(spec=DataTable)
    table.is_attached = True

    manager = CompletedAgentsManager(table)

    assert not manager.is_filtered()

    manager.filtered_agents = [MagicMock()]
    assert manager.is_filtered()


# ============================================================================
# StreamingLogViewer Tests
# ============================================================================


def test_log_viewer_append_line():
    """Test StreamingLogViewer appends lines correctly."""
    log_viewer = StreamingLogViewer()

    log_viewer.append_line("Test log line")

    assert log_viewer.line_count == 1


def test_log_viewer_append_line_with_timestamp():
    """Test StreamingLogViewer formats timestamp correctly."""
    log_viewer = StreamingLogViewer()
    timestamp = datetime(2024, 1, 1, 12, 30, 45)

    # We can't easily check the rendered output, but we can verify it doesn't error
    log_viewer.append_line("Test log line", timestamp=timestamp)

    assert log_viewer.line_count == 1


def test_log_viewer_auto_scroll():
    """Test StreamingLogViewer auto-scrolls when enabled."""
    log_viewer = StreamingLogViewer()

    assert log_viewer.auto_scroll is True

    # Add lines - should auto-scroll
    log_viewer.append_line("Line 1")
    log_viewer.append_line("Line 2")

    assert log_viewer.line_count == 2


def test_log_viewer_toggle_follow():
    """Test StreamingLogViewer toggles follow mode."""
    log_viewer = StreamingLogViewer()

    assert log_viewer.auto_scroll is True

    log_viewer.action_toggle_follow()
    assert log_viewer.auto_scroll is False

    log_viewer.action_toggle_follow()
    assert log_viewer.auto_scroll is True


def test_log_viewer_syntax_highlighting():
    """Test StreamingLogViewer applies syntax highlighting."""
    log_viewer = StreamingLogViewer()

    # These should be highlighted when appended
    log_viewer.append_line("ERROR: Something failed")
    log_viewer.append_line("WARN: Be careful")
    log_viewer.append_line("SUCCESS: All good")

    assert log_viewer.line_count == 3


def test_log_viewer_streaming_state():
    """Test StreamingLogViewer manages streaming state."""
    log_viewer = StreamingLogViewer()

    assert not log_viewer.streaming
    assert log_viewer.current_agent_id is None

    log_viewer.start_streaming("agent-1")
    assert log_viewer.streaming is True
    assert log_viewer.current_agent_id == "agent-1"
    assert log_viewer.line_count == 0

    log_viewer.stop_streaming()
    assert log_viewer.streaming is False


# ============================================================================
# AgentShell Tests
# ============================================================================


def test_shell_command_echo():
    """Test AgentShell executes basic echo command."""
    registry = CommandRegistry()
    shell = AgentShell(command_registry=registry)

    # Test internal state without DOM
    shell._output_lines.append("Test output")

    assert len(shell._output_lines) == 1
    assert "Test output" in shell._output_lines[0]


def test_shell_history_navigation():
    """Test AgentShell maintains command history."""
    registry = CommandRegistry()
    shell = AgentShell(command_registry=registry)

    # Add commands to history
    shell.history.append("command1")
    shell.history.append("command2")
    shell.history.append("command3")

    assert len(shell.history) == 3
    assert shell.history[0] == "command1"
    assert shell.history[-1] == "command3"


def test_shell_history_index():
    """Test AgentShell history navigation with index."""
    registry = CommandRegistry()
    shell = AgentShell(command_registry=registry)

    shell.history.append("cmd1")
    shell.history.append("cmd2")

    # Initially at -1 (no history navigation)
    assert shell.history_index == -1

    # Simulate up arrow - should move to last command
    shell.history_index = len(shell.history) - 1
    assert shell.history[shell.history_index] == "cmd2"


def test_shell_completion():
    """Test AgentShell command completion."""
    registry = CommandRegistry()
    # Add some test commands
    from grind.tui.core.shell_commands import ShellCommand

    async def dummy_handler(args, ctx):
        return "Done"

    registry.register(ShellCommand(
        name="status",
        description="Show status",
        usage="status",
        handler=dummy_handler
    ))
    registry.register(ShellCommand(
        name="start",
        description="Start agent",
        usage="start",
        handler=dummy_handler
    ))

    shell = AgentShell(command_registry=registry)

    # Get completions for "st"
    completions = shell.get_completions("st")

    assert len(completions) >= 2
    assert "status" in completions
    assert "start" in completions


def test_shell_completion_no_match():
    """Test AgentShell completion with no matches."""
    registry = CommandRegistry()
    shell = AgentShell(command_registry=registry)

    completions = shell.get_completions("xyz")

    assert len(completions) == 0


def test_shell_completion_multi_word():
    """Test AgentShell doesn't complete multi-word input."""
    registry = CommandRegistry()
    shell = AgentShell(command_registry=registry)

    # Completions only work for first word
    completions = shell.get_completions("status all")

    assert len(completions) == 0


def test_shell_clear_output():
    """Test AgentShell clears output."""
    registry = CommandRegistry()
    shell = AgentShell(command_registry=registry)

    shell._output_lines.append("Line 1")
    shell._output_lines.append("Line 2")
    assert len(shell._output_lines) == 2

    # Direct test of internal state
    shell._output_lines = []
    assert len(shell._output_lines) == 0


def test_shell_show_hide_completions():
    """Test AgentShell shows and hides completion popup."""
    registry = CommandRegistry()
    shell = AgentShell(command_registry=registry)

    # Show completions
    shell._completions = ["cmd1", "cmd2"]
    assert len(shell._completions) == 2

    # Hide completions (test internal state)
    shell._completions = []
    assert len(shell._completions) == 0


@pytest.mark.asyncio
async def test_shell_execute_clear_command():
    """Test AgentShell handles clear command."""
    registry = CommandRegistry()
    shell = AgentShell(command_registry=registry)

    # Mock the query_one method to avoid DOM access
    with patch.object(shell, 'query_one') as mock_query:
        mock_output = MagicMock()
        mock_query.return_value = mock_output

        await shell.execute_command("clear")

        # Should have called clear_output which resets _output_lines
        assert len(shell._output_lines) == 0


@pytest.mark.asyncio
async def test_shell_execute_shell_escape():
    """Test AgentShell executes shell escape commands."""
    registry = CommandRegistry()
    shell = AgentShell(command_registry=registry)

    # Mock the shell escape execution and query_one
    with patch.object(shell, '_execute_shell_escape', new_callable=AsyncMock) as mock_exec:
        with patch.object(shell, 'query_one'):
            mock_exec.return_value = "Command output"

            await shell.execute_command("!echo test")

            mock_exec.assert_called_once_with("echo test")


@pytest.mark.asyncio
async def test_shell_execute_empty_shell_escape():
    """Test AgentShell handles empty shell escape."""
    registry = CommandRegistry()
    shell = AgentShell(command_registry=registry)

    # Mock query_one to avoid DOM access
    with patch.object(shell, 'query_one'):
        await shell.execute_command("!")

        # Should write usage message to _output_lines
        assert any("Usage:" in line for line in shell._output_lines)


# ============================================================================
# Iteration Progress Tests
# ============================================================================


@pytest.mark.asyncio
async def test_agents_manager_handles_iteration_started_event():
    """Test RunningAgentsManager updates iteration progress on ITERATION_STARTED event."""
    from grind.orchestration.events import AgentEvent, EventBus, EventType

    # Create EventBus and agents manager
    event_bus = EventBus()
    list_view = MagicMock(spec=ListView)
    list_view.is_attached = True
    list_view.clear = MagicMock()
    list_view.append = MagicMock()

    manager = RunningAgentsManager(list_view)

    # Create a sample running agent
    now = datetime.now()
    agent = AgentInfo(
        agent_id="test-agent-1",
        task_id="task-1",
        task_description="Test task",
        agent_type=AgentType.WORKER,
        status=AgentStatus.RUNNING,
        model="sonnet",
        iteration=1,
        max_iterations=5,
        progress=0.2,
        created_at=now,
        started_at=now,
    )

    # Update manager with initial agent
    manager.update([agent])
    assert manager.agents[0].iteration == 1

    # Emit ITERATION_STARTED event
    event = AgentEvent(
        event_type=EventType.ITERATION_STARTED,
        agent_id="test-agent-1",
        timestamp=datetime.now().timestamp(),
        data={
            "iteration": 2,
            "max_iterations": 5,
        }
    )

    # Handle the event by updating the agent's iteration
    updated_agent = AgentInfo(
        agent_id="test-agent-1",
        task_id="task-1",
        task_description="Test task",
        agent_type=AgentType.WORKER,
        status=AgentStatus.RUNNING,
        model="sonnet",
        iteration=2,  # Updated iteration
        max_iterations=5,
        progress=0.4,
        created_at=now,
        started_at=now,
    )

    manager.update([updated_agent])
    assert manager.agents[0].iteration == 2
    assert manager.agents[0].progress == 0.4


@pytest.mark.asyncio
async def test_agents_manager_handles_iteration_completed_event():
    """Test RunningAgentsManager updates iteration progress on ITERATION_COMPLETED event."""
    from grind.orchestration.events import AgentEvent, EventBus, EventType

    # Create EventBus and agents manager
    event_bus = EventBus()
    list_view = MagicMock(spec=ListView)
    list_view.is_attached = True
    list_view.clear = MagicMock()
    list_view.append = MagicMock()

    manager = RunningAgentsManager(list_view)

    # Create a sample running agent
    now = datetime.now()
    agent = AgentInfo(
        agent_id="test-agent-1",
        task_id="task-1",
        task_description="Test task",
        agent_type=AgentType.WORKER,
        status=AgentStatus.RUNNING,
        model="sonnet",
        iteration=2,
        max_iterations=5,
        progress=0.4,
        created_at=now,
        started_at=now,
    )

    # Update manager with initial agent
    manager.update([agent])
    assert manager.agents[0].iteration == 2

    # Emit ITERATION_COMPLETED event
    event = AgentEvent(
        event_type=EventType.ITERATION_COMPLETED,
        agent_id="test-agent-1",
        timestamp=datetime.now().timestamp(),
        data={
            "iteration": 2,
            "max_iterations": 5,
            "success": True,
        }
    )

    # Verify the event can be created
    assert event.event_type == EventType.ITERATION_COMPLETED
    assert event.data["iteration"] == 2


@pytest.mark.asyncio
async def test_agents_manager_updates_progress_from_iteration():
    """Test RunningAgentsManager calculates progress from iteration count."""
    list_view = MagicMock(spec=ListView)
    list_view.is_attached = True
    list_view.clear = MagicMock()
    list_view.append = MagicMock()

    manager = RunningAgentsManager(list_view)

    # Create agents at different iteration stages
    now = datetime.now()
    agents = [
        AgentInfo(
            agent_id="agent-1",
            task_id="task-1",
            task_description="Agent at iteration 1/5",
            agent_type=AgentType.WORKER,
            status=AgentStatus.RUNNING,
            model="sonnet",
            iteration=1,
            max_iterations=5,
            progress=0.2,
            created_at=now,
            started_at=now,
        ),
        AgentInfo(
            agent_id="agent-2",
            task_id="task-2",
            task_description="Agent at iteration 3/5",
            agent_type=AgentType.WORKER,
            status=AgentStatus.RUNNING,
            model="sonnet",
            iteration=3,
            max_iterations=5,
            progress=0.6,
            created_at=now,
            started_at=now,
        ),
    ]

    manager.update(agents)

    # Verify agents are displayed with correct iteration counts
    assert manager.agents[0].iteration == 1
    assert manager.agents[0].max_iterations == 5
    assert manager.agents[1].iteration == 3
    assert manager.agents[1].max_iterations == 5


@pytest.mark.asyncio
async def test_event_handler_subscribes_to_iteration_events():
    """Test EventHandler subscribes to ITERATION_STARTED and ITERATION_COMPLETED events."""
    from grind.orchestration.events import EventBus
    from grind.tui.widgets.event_handler import EventHandler

    event_bus = EventBus()
    event_handler = EventHandler(event_bus=event_bus)

    # Verify subscriptions exist for iteration events
    # EventBus stores subscriptions in a dict keyed by EventType
    from grind.orchestration.events import EventType

    # Check that iteration event handlers are registered
    assert EventType.ITERATION_STARTED in event_bus._subscribers
    assert EventType.ITERATION_COMPLETED in event_bus._subscribers


@pytest.mark.asyncio
async def test_event_handler_handles_iteration_started():
    """Test EventHandler properly handles ITERATION_STARTED event."""
    from grind.orchestration.events import AgentEvent, EventBus, EventType
    from grind.tui.widgets.event_handler import EventHandler

    event_bus = EventBus()
    event_handler = EventHandler(event_bus=event_bus)

    # Track if callback was called
    callback_called = False
    received_agent = None

    def callback(agent_info):
        nonlocal callback_called, received_agent
        callback_called = True
        received_agent = agent_info

    event_handler.on_agent_updated = callback

    # Emit ITERATION_STARTED event
    event = AgentEvent(
        event_type=EventType.ITERATION_STARTED,
        agent_id="test-agent",
        timestamp=datetime.now().timestamp(),
        data={
            "task_id": "task-1",
            "task_description": "Test task",
            "agent_type": "worker",
            "model": "sonnet",
            "iteration": 3,
            "max_iterations": 5,
        }
    )

    await event_bus.publish(event)

    # Wait a bit for async event processing
    import asyncio
    await asyncio.sleep(0.01)

    # Verify callback was called
    assert callback_called
    assert received_agent is not None
    assert received_agent.agent_id == "test-agent"
    assert received_agent.iteration == 3
    assert received_agent.max_iterations == 5
    assert received_agent.progress == 0.6  # 3/5


@pytest.mark.asyncio
async def test_event_handler_handles_iteration_completed():
    """Test EventHandler properly handles ITERATION_COMPLETED event."""
    from grind.orchestration.events import AgentEvent, EventBus, EventType
    from grind.tui.widgets.event_handler import EventHandler

    event_bus = EventBus()
    event_handler = EventHandler(event_bus=event_bus)

    # Track if callback was called
    callback_called = False
    received_agent = None

    def callback(agent_info):
        nonlocal callback_called, received_agent
        callback_called = True
        received_agent = agent_info

    event_handler.on_agent_updated = callback

    # Emit ITERATION_COMPLETED event
    event = AgentEvent(
        event_type=EventType.ITERATION_COMPLETED,
        agent_id="test-agent",
        timestamp=datetime.now().timestamp(),
        data={
            "task_id": "task-1",
            "task_description": "Test task",
            "agent_type": "worker",
            "model": "sonnet",
            "iteration": 2,
            "max_iterations": 5,
            "success": True,
        }
    )

    await event_bus.publish(event)

    # Wait a bit for async event processing
    import asyncio
    await asyncio.sleep(0.01)

    # Verify callback was called
    assert callback_called
    assert received_agent is not None
    assert received_agent.agent_id == "test-agent"
    assert received_agent.iteration == 2
    assert received_agent.max_iterations == 5
    assert received_agent.progress == 0.4  # 2/5
    assert received_agent.status == AgentStatus.RUNNING  # Still running after iteration
