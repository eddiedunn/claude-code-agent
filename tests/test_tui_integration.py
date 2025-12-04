'''End-to-end integration tests for TUI workflow.'''

import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from grind.tui.app import AgentTUI
from grind.tui.core.models import AgentStatus, AgentInfo, AgentType
from grind.orchestration.events import EventBus, EventType, AgentEvent
from grind.orchestration.metrics import MetricsCollector


@pytest.mark.asyncio
async def test_full_tui_workflow(tmp_path):
    '''Test complete TUI workflow from task file to execution.'''
    # Create test task file
    task_file = tmp_path / "integration_tasks.yaml"
    task_file.write_text("""
tasks:
  - task: "Integration test task"
    verify: "true"
    model: haiku
    max_iterations: 3
""")

    # Initialize TUI (don't run, just test setup)
    app = AgentTUI()
    app.startup_task_file = str(task_file)
    app.default_model = "sonnet"

    # Verify attributes are set
    assert app.startup_task_file == str(task_file)
    assert app.default_model == "sonnet"
    assert app.session is not None
    assert app.executor is not None
    assert app.command_registry is not None

    # Test that we can create an agent manually
    from grind.models import TaskDefinition
    task_def = TaskDefinition(
        task="Test task",
        verify="true",
        model="haiku",
        max_iterations=5,
    )

    agent = app.executor.create_agent(task_def)
    assert agent.agent_id is not None
    assert agent.status == AgentStatus.PENDING

    # Verify agent is tracked in session
    assert len(app.session.agents) == 1
    assert app.session.agents[0] == agent

    # Cleanup
    app.session.cleanup()


@pytest.mark.asyncio
async def test_shell_command_execution(tmp_path):
    '''Test executing shell commands programmatically.'''
    from grind.tui.core.shell_commands import parse_and_execute, CommandRegistry, ShellContext

    app = AgentTUI()

    # Create shell context
    context = ShellContext(
        session=app.session,
        agents=app.session.agents,
        current_agent_id=None,
        history=[],
        variables={},
        executor=app.executor,
    )

    registry = CommandRegistry()

    # Test help command
    result = await parse_and_execute("help", registry, context)
    assert "Available commands" in result

    # Test status command with no agents
    result = await parse_and_execute("status", registry, context)
    assert "No agents" in result

    # Create an agent
    from grind.models import TaskDefinition
    task_def = TaskDefinition(
        task="Test",
        verify="true",
        model="haiku",
        max_iterations=3,
    )
    agent = app.executor.create_agent(task_def)

    # Update context agents list
    context.agents = app.session.agents

    # Test agents command
    result = await parse_and_execute("agents", registry, context)
    assert agent.agent_id in result

    # Test agent detail command
    result = await parse_and_execute(f"agent {agent.agent_id}", registry, context)
    assert agent.agent_id in result
    assert "Test" in result

    # Cleanup
    app.session.cleanup()


def test_tui_initialization():
    '''Test TUI initializes all components correctly.'''
    app = AgentTUI()

    # Check core components exist
    assert app.session is not None
    assert app.executor is not None
    assert app.tab_registry is not None
    assert app.log_streamer is not None

    # Check tab registry has all 5 tabs (shell is now a footer overlay, not a tab)
    assert app.tab_registry.count_tabs() == 5

    enabled_tabs = app.tab_registry.get_enabled_tabs()
    assert len(enabled_tabs) == 5

    tab_ids = [t.id for t in enabled_tabs]
    assert "tab-dag" in tab_ids
    assert "tab-running" in tab_ids
    assert "tab-completed" in tab_ids
    assert "tab-logs" in tab_ids
    assert "tab-metrics" in tab_ids

    # Cleanup
    app.session.cleanup()


@pytest.mark.asyncio
async def test_orchestrator_integration():
    '''Test that TUI integrates with Orchestrator for agent execution.'''
    app = AgentTUI()

    # Verify executor exists and has event_bus configured
    assert app.executor is not None
    assert app.executor.event_bus is not None

    # Create a task definition
    from grind.models import TaskDefinition
    task_def = TaskDefinition(
        task="Test orchestrator integration",
        verify="echo 'test'",
        model="haiku",
        max_iterations=2,
    )

    # Create an agent (this should use the orchestrator internally)
    agent = app.executor.create_agent(task_def)
    assert agent is not None
    assert agent.agent_id is not None

    # Verify the agent is tracked
    assert len(app.session.agents) == 1

    # Cleanup
    app.session.cleanup()


@pytest.mark.asyncio
async def test_eventbus_subscription():
    '''Test that EventHandler subscribes to EventBus events.'''
    app = AgentTUI()

    # Verify event_bus exists
    assert app.event_bus is not None

    # Track if callback was called
    callback_called = {"called": False, "agent_info": None}

    def mock_callback(agent_info: AgentInfo):
        callback_called["called"] = True
        callback_called["agent_info"] = agent_info

    # Create and mount event handler
    from grind.tui.widgets.event_handler import EventHandler
    event_handler = EventHandler(event_bus=app.event_bus)
    event_handler.on_agent_updated = mock_callback

    # Simulate an AGENT_STARTED event
    event = AgentEvent(
        event_type=EventType.AGENT_STARTED,
        agent_id="test-agent-123",
        timestamp=0.0,
        data={
            "task_id": "test-task-1",
            "task_description": "Test task description",
            "agent_type": "worker",
            "model": "haiku",
            "iteration": 0,
            "max_iterations": 3,
        }
    )

    # Publish the event
    await app.event_bus.publish(event)

    # Give event handlers time to process
    await asyncio.sleep(0.1)

    # Verify callback was called
    assert callback_called["called"]
    assert callback_called["agent_info"] is not None
    assert callback_called["agent_info"].agent_id == "test-agent-123"
    assert callback_called["agent_info"].status == AgentStatus.RUNNING

    # Cleanup
    app.session.cleanup()


@pytest.mark.asyncio
async def test_metrics_display():
    '''Test that MetricsView displays metrics from MetricsCollector.'''
    from grind.tui.widgets.metrics_view import MetricsView

    # Create a metrics collector and add some test data
    collector = MetricsCollector()

    # Record some metrics for a test agent (2 successful runs)
    collector.record_run(
        agent_id="test-agent-1",
        duration=1.5,
        cost=0.001,
        success=True
    )
    collector.record_run(
        agent_id="test-agent-1",
        duration=2.0,
        cost=0.002,
        success=True
    )

    # Create metrics view with the collector
    metrics_view = MetricsView(metrics_collector=collector)

    # Test rendering all metrics
    all_metrics_output = metrics_view.render()
    assert "All Agent Metrics" in all_metrics_output
    assert "test-agent-1" in all_metrics_output
    assert "100.0%" in all_metrics_output  # Success rate should be 100%
    assert "2" in all_metrics_output  # Total runs should be 2

    # Test rendering specific agent metrics
    metrics_view.show_agent("test-agent-1")
    agent_metrics_output = metrics_view.render()
    assert "Agent Metrics" in agent_metrics_output
    assert "test-agent-1" in agent_metrics_output
    assert "100.0%" in agent_metrics_output  # Success rate
    assert "Total Runs:[/bold] 2" in agent_metrics_output  # Check with markup

    # Test with no metrics collector
    empty_view = MetricsView()
    empty_output = empty_view.render()
    assert "No metrics collector configured" in empty_output


@pytest.mark.asyncio
async def test_dashboard_integration_with_grind_spawn():
    '''Test TUI dashboard integration with grind spawn workflow.'''
    from grind.models import TaskDefinition
    from grind.tui.widgets.agent_dashboard import AgentDashboard
    from grind.tui.widgets.footer_shell import FooterShell
    from grind.tui.core.shell_commands import ShellContext

    # Create TUI app
    app = AgentTUI()

    # Test dashboard initializes cleanly without buttons
    dashboard = AgentDashboard()
    assert dashboard is not None
    assert dashboard.agents == []
    assert hasattr(dashboard, "compose")
    assert callable(dashboard.compose)

    # Create a task and spawn an agent via grind spawn
    task_def = TaskDefinition(
        task="Integration test with dashboard",
        verify="echo 'test'",
        model="haiku",
        max_iterations=3,
    )

    # Spawn agent using executor
    agent = app.executor.create_agent(task_def)
    assert agent is not None
    assert agent.agent_id is not None

    # Update dashboard with spawned agents
    dashboard.update_agents(app.session.agents)
    assert len(dashboard.agents) == 1
    assert dashboard.agents[0].agent_id == agent.agent_id

    # Test footer shell overlay (Ctrl+`)
    shell = FooterShell()
    assert shell is not None
    assert hasattr(shell, "expand")
    assert hasattr(shell, "collapse")
    assert hasattr(shell, "toggle")

    # Create shell context for command testing
    context = ShellContext(
        session=app.session,
        agents=app.session.agents,
        current_agent_id=agent.agent_id,
        history=[],
        variables={},
        executor=app.executor,
    )

    # Test shell commands: help
    from grind.tui.core.shell_commands import parse_and_execute, CommandRegistry
    registry = CommandRegistry()
    result = await parse_and_execute("help", registry, context)
    assert "Available commands" in result

    # Test shell commands: agents
    result = await parse_and_execute("agents", registry, context)
    assert agent.agent_id in result

    # Test shell commands: spawn (create another agent)
    result = await parse_and_execute("spawn", registry, context)
    assert "spawn" in result.lower() or "created" in result.lower() or "usage" in result.lower()

    # Verify agents display in dashboard when spawned
    dashboard.agents = app.session.agents
    assert len(dashboard.agents) >= 1

    # Verify dashboard renders status correctly
    status_overview = dashboard._render_status_overview()
    assert status_overview is not None

    # Test keyboard binding for shell toggle
    bindings = app.BINDINGS
    binding_keys = [b[0] for b in bindings]
    assert "ctrl+grave_accent" in binding_keys

    # Find the shell toggle binding and verify it maps to toggle_shell action
    bindings_dict = {b[0]: b[1] for b in bindings}
    assert bindings_dict["ctrl+grave_accent"] == "toggle_shell"

    # Verify app has required shell toggle method
    assert hasattr(app, "action_toggle_shell")

    # Cleanup
    app.session.cleanup()
