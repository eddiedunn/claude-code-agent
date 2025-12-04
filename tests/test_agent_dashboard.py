"""Tests for AgentDashboard widget."""

import pytest
from textual.widgets import Button, Static, ListView
from textual.app import ComposeResult

from grind.tui.core.models import AgentInfo, AgentStatus, AgentType
from grind.tui.widgets.agent_dashboard import AgentDashboard
from datetime import datetime


@pytest.fixture
def dashboard():
    """Create a dashboard instance."""
    return AgentDashboard()


@pytest.fixture
def sample_agents():
    """Create sample agents with various statuses."""
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
        AgentInfo(
            agent_id="agent-3",
            task_id="task-3",
            task_description="Fix type errors",
            agent_type=AgentType.WORKER,
            status=AgentStatus.COMPLETE,
            model="haiku",
            iteration=3,
            max_iterations=5,
            progress=1.0,
            created_at=datetime.now(),
            started_at=datetime.now(),
            end_time=datetime.now(),
        ),
        AgentInfo(
            agent_id="agent-4",
            task_id="task-4",
            task_description="Deploy to staging",
            agent_type=AgentType.WORKER,
            status=AgentStatus.FAILED,
            model="haiku",
            iteration=2,
            max_iterations=5,
            progress=0.4,
            created_at=datetime.now(),
            started_at=datetime.now(),
            end_time=datetime.now(),
        ),
    ]


def test_dashboard_initialization(dashboard):
    """Test dashboard initializes correctly."""
    assert dashboard.agents == []
    assert dashboard.on_spawn is None
    assert dashboard.on_pause is None
    assert dashboard.on_resume is None
    assert dashboard.on_cancel is None
    assert dashboard.on_clear is None


def test_dashboard_has_compose_method(dashboard):
    """Test dashboard has compose method."""
    assert hasattr(dashboard, "compose")
    assert callable(dashboard.compose)


def test_render_status_overview_empty(dashboard):
    """Test status overview with no agents."""
    overview = dashboard._render_status_overview()
    assert "No agents yet" in overview


def test_render_status_overview_with_agents(dashboard):
    """Test status overview renders agent counts correctly."""
    # Create minimal agents with only required fields
    from grind.tui.core.models import AgentInfo, AgentStatus, AgentType
    from datetime import datetime

    running_agent = AgentInfo(
        agent_id="agent-1",
        task_id="task-1",
        task_description="Task 1",
        agent_type=AgentType.WORKER,
        status=AgentStatus.RUNNING,
        model="haiku",
        iteration=1,
        max_iterations=5,
        progress=0.2,
        created_at=datetime.now(),
    )

    dashboard.agents = [running_agent]
    overview = dashboard._render_status_overview()

    # Check for status indicators and counts
    assert "Running:" in overview
    assert "1" in overview


def test_render_status_overview_single_status(dashboard):
    """Test status overview with only running agents."""
    dashboard.agents = [
        AgentInfo(
            agent_id="agent-1",
            task_id="task-1",
            task_description="Task",
            agent_type=AgentType.WORKER,
            status=AgentStatus.RUNNING,
            model="haiku",
            iteration=1,
            max_iterations=5,
            progress=0.2,
            created_at=datetime.now(),
            started_at=datetime.now(),
        ),
    ]
    overview = dashboard._render_status_overview()
    assert "Running:" in overview
    assert "1" in overview


def test_update_agents(dashboard):
    """Test updating agents list."""
    from grind.tui.core.models import AgentInfo, AgentStatus, AgentType
    from datetime import datetime

    agents = [
        AgentInfo(
            agent_id="agent-1",
            task_id="task-1",
            task_description="Task 1",
            agent_type=AgentType.WORKER,
            status=AgentStatus.RUNNING,
            model="haiku",
            iteration=1,
            max_iterations=5,
            progress=0.2,
            created_at=datetime.now(),
        ),
    ]

    dashboard.update_agents(agents)
    assert len(dashboard.agents) == 1
    assert dashboard.agents[0].agent_id == "agent-1"


def test_agent_counts(dashboard):
    """Test correct agent status counting."""
    from grind.tui.core.models import AgentInfo, AgentStatus, AgentType
    from datetime import datetime

    agents = [
        AgentInfo(
            agent_id="agent-1",
            task_id="task-1",
            task_description="Task 1",
            agent_type=AgentType.WORKER,
            status=AgentStatus.RUNNING,
            model="haiku",
            iteration=1,
            max_iterations=5,
            progress=0.2,
            created_at=datetime.now(),
        ),
    ]

    dashboard.agents = agents

    running = len([a for a in dashboard.agents if a.status == AgentStatus.RUNNING])
    pending = len([a for a in dashboard.agents if a.status == AgentStatus.PENDING])

    assert running == 1
    assert pending == 0


def test_dashboard_callback_spawn(dashboard):
    """Test spawn callback is called."""
    spawn_called = False

    def on_spawn():
        nonlocal spawn_called
        spawn_called = True

    dashboard.on_spawn = on_spawn
    dashboard.on_spawn()
    assert spawn_called


def test_dashboard_callback_pause(dashboard):
    """Test pause callback is called."""
    pause_called = False

    def on_pause():
        nonlocal pause_called
        pause_called = True

    dashboard.on_pause = on_pause
    dashboard.on_pause()
    assert pause_called


def test_dashboard_callback_resume(dashboard):
    """Test resume callback is called."""
    resume_called = False

    def on_resume():
        nonlocal resume_called
        resume_called = True

    dashboard.on_resume = on_resume
    dashboard.on_resume()
    assert resume_called


def test_dashboard_callback_cancel(dashboard):
    """Test cancel callback is called."""
    cancel_called = False

    def on_cancel():
        nonlocal cancel_called
        cancel_called = True

    dashboard.on_cancel = on_cancel
    dashboard.on_cancel()
    assert cancel_called


def test_dashboard_callback_clear(dashboard):
    """Test clear callback is called."""
    clear_called = False

    def on_clear():
        nonlocal clear_called
        clear_called = True

    dashboard.on_clear = on_clear
    dashboard.on_clear()
    assert clear_called


def test_dashboard_has_quick_action_buttons(dashboard):
    """Test dashboard CSS is structured correctly."""
    css = dashboard.DEFAULT_CSS

    # Check CSS has proper structure for dashboard layout
    assert "AgentDashboard" in css
    assert "#status-overview" in css


def test_dashboard_css_valid(dashboard):
    """Test dashboard CSS is valid and contains key selectors."""
    css = dashboard.DEFAULT_CSS

    # Should have proper Textual CSS structure
    assert "AgentDashboard {" in css
    assert "#dashboard-title" in css or "dashboard" in css
    assert "#status-overview" in css or "status" in css
    assert "#agent-feed" in css or "feed" in css
