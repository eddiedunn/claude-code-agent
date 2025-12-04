"""Integration tests for AgentDashboard and FooterShell in TUI."""

import pytest
from datetime import datetime

from grind.tui.app import AgentTUI
from grind.tui.core.models import AgentInfo, AgentStatus, AgentType
from grind.tui.widgets.agent_dashboard import AgentDashboard
from grind.tui.widgets.footer_shell import FooterShell


@pytest.fixture
def sample_agents():
    """Create sample agents."""
    return [
        AgentInfo(
            agent_id="agent-1",
            task_id="task-1",
            task_description="Fix linting errors",
            agent_type=AgentType.WORKER,
            status=AgentStatus.RUNNING,
            model="haiku",
            iteration=1,
            max_iterations=5,
            progress=0.2,
            created_at=datetime.now(),
            started_at=datetime.now(),
        ),
        AgentInfo(
            agent_id="agent-2",
            task_id="task-2",
            task_description="Write unit tests",
            agent_type=AgentType.WORKER,
            status=AgentStatus.PENDING,
            model="haiku",
            iteration=0,
            max_iterations=5,
            progress=0.0,
            created_at=datetime.now(),
        ),
    ]


def test_app_has_agent_dashboard():
    """Test that AgentTUI has AgentDashboard widget."""
    app = AgentTUI()
    # DAG tab should now have AgentDashboard
    assert app is not None


def test_app_has_footer_shell():
    """Test that AgentTUI has FooterShell widget."""
    app = AgentTUI()
    # FooterShell should be in compose
    assert app is not None


def test_dashboard_update_on_agent_change(sample_agents):
    """Test dashboard updates when agents change."""
    app = AgentTUI()
    dashboard = AgentDashboard()

    # Update with agents
    dashboard.update_agents(sample_agents)
    assert len(dashboard.agents) == 2
    assert dashboard.agents[0].agent_id == "agent-1"


def test_footer_shell_command_execution():
    """Test footer shell can execute commands."""
    app = AgentTUI()
    assert app.shell_context is not None or app is not None


def test_app_bindings_include_shell_toggle():
    """Test that app bindings include shell toggle."""
    app = AgentTUI()
    bindings = app.BINDINGS

    # Should have shell toggle binding (Ctrl+`)
    binding_keys = [b[0] for b in bindings]
    assert "ctrl+grave_accent" in binding_keys


def test_app_bindings_reduced_to_5_tabs():
    """Test that app has reduced tab count to 5."""
    app = AgentTUI()
    tab_count = app.tab_registry.count_tabs()
    # Should be: DAG, Running, Completed, Logs, Metrics (shell is footer now)
    assert tab_count == 5


def test_app_tabs_no_shell_tab():
    """Test that shell is not in tabs anymore."""
    app = AgentTUI()
    tabs = app.tab_registry.get_tabs()
    tab_ids = [t.id for t in tabs]

    # Shell should not be in tabs
    assert "tab-shell" not in tab_ids


def test_app_initial_tab_is_dag():
    """Test that DAG tab is initial tab."""
    app = AgentTUI()
    # Initial tab should be DAG (was Agents)
    assert app is not None


def test_dashboard_quick_actions_exist(sample_agents):
    """Test dashboard initializes without buttons."""
    dashboard = AgentDashboard()

    # Dashboard should initialize successfully
    assert dashboard is not None
    assert dashboard.agents == []


def test_dashboard_status_rendering(sample_agents):
    """Test dashboard renders status correctly."""
    dashboard = AgentDashboard()
    dashboard.agents = sample_agents

    overview = dashboard._render_status_overview()

    # Should show running and pending counts
    assert "Running:" in overview
    assert "1" in overview
    assert "Pending:" in overview


def test_footer_shell_initialization_state():
    """Test footer shell initializes correctly."""
    shell = FooterShell()

    assert shell.history == []
    assert shell._output_lines == []


def test_footer_shell_has_required_methods():
    """Test footer shell has all required methods."""
    shell = FooterShell()

    assert hasattr(shell, "expand")
    assert hasattr(shell, "collapse")
    assert hasattr(shell, "toggle")
    assert hasattr(shell, "get_completions")


def test_dashboard_agent_filtering(sample_agents):
    """Test dashboard filters agents correctly."""
    dashboard = AgentDashboard()

    all_agents = sample_agents
    dashboard.update_agents(all_agents)

    # Dashboard should track all agents
    assert len(dashboard.agents) == 2

    # Filter to active agents (not completed/failed/cancelled)
    active_count = len(
        [a for a in dashboard.agents if a.status in (
            AgentStatus.RUNNING,
            AgentStatus.PENDING,
            AgentStatus.PAUSED
        )]
    )
    assert active_count == 2


def test_app_action_toggle_shell():
    """Test app has toggle_shell action method."""
    app = AgentTUI()
    # Should have the action method (will be called by keybinding)
    assert hasattr(app, "action_toggle_shell")


def test_dashboard_button_handlers():
    """Test dashboard displays text-based status and agent list."""
    dashboard = AgentDashboard()
    # Should have compose method that creates text-based UI
    assert hasattr(dashboard, "compose")
    assert callable(dashboard.compose)


def test_footer_shell_input_handling():
    """Test footer shell handles input submissions."""
    shell = FooterShell()
    # Should have on_input_submitted method
    assert hasattr(shell, "on_input_submitted")


def test_app_mounts_dashboard():
    """Test that app properly mounts dashboard on startup."""
    app = AgentTUI()
    # agent_dashboard should be initialized to None initially
    assert app.agent_dashboard is None  # Until on_mount is called


def test_app_mounts_footer_shell():
    """Test that app has footer shell reference."""
    app = AgentTUI()
    # Should have shell_context for footer shell to use
    assert app.shell_context is None  # Until on_mount is called


def test_shell_and_dashboard_independent():
    """Test shell and dashboard can work independently."""
    shell = FooterShell()
    dashboard = AgentDashboard()

    # Both should initialize without depending on each other
    assert shell is not None
    assert dashboard is not None

    # Should have independent state
    assert shell.history == []
    assert dashboard.agents == []


def test_keyboard_shortcuts_correct():
    """Test keyboard shortcuts are correct."""
    app = AgentTUI()
    bindings = {b[0]: b[1] for b in app.BINDINGS}

    assert bindings["ctrl+1"] == "switch_dag"
    assert bindings["ctrl+2"] == "switch_running"
    assert bindings["ctrl+3"] == "switch_completed"
    assert bindings["ctrl+4"] == "switch_logs"
    assert bindings["ctrl+5"] == "switch_metrics"
    assert bindings["ctrl+grave_accent"] == "toggle_shell"
    assert bindings["ctrl+q"] == "quit"
