# TUI-Orchestrator Integration - Phase 4

This document details the implementation of Phase 4 of the agent orchestration system, which integrates the TUI (Terminal User Interface) with the Orchestrator framework built in Phases 2-3.

**Status**: ✅ Phase 4 Complete (100%)

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [EventBus Integration](#eventbus-integration)
4. [Metrics Display](#metrics-display)
5. [Agent Controls](#agent-controls)
6. [Real-Time Updates](#real-time-updates)
7. [Complete Examples](#complete-examples)
8. [Testing](#testing)
9. [Next Steps](#next-steps)

---

## Overview

### What We Built

Phase 4 transformed the TUI from polling-based updates to an event-driven architecture powered by the Orchestrator's EventBus. This enables real-time agent status updates, metrics visualization, and interactive agent control.

**Key Components Added:**

```
grind/tui/
├── core/
│   └── agent_executor.py      # Updated to use Orchestrator
├── widgets/
│   ├── event_handler.py       # EventBus subscriber widget
│   ├── metrics_view.py        # Metrics visualization widget
│   └── agent_controls.py      # Agent start/stop/restart controls
└── app.py                     # Updated with EventBus integration
```

### Design Philosophy

1. **Event-Driven**: Replace polling with reactive event subscriptions
2. **Real-Time**: Instant UI updates via EventBus pub-sub
3. **Composable**: Modular widgets that can be independently updated
4. **Observable**: MetricsCollector provides performance insights

---

## Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         AgentTUI (App)                          │
│  ┌─────────────────────────────────────────────────────────────┤
│  │  - EventBus (shared event bus)                              │
│  │  - AgentSession (state management)                          │
│  │  - AgentExecutor (orchestrator bridge)                      │
│  │  - TabRegistry (tab management)                             │
│  └─────────────────────────────────────────────────────────────┤
│                              │                                  │
│         ┌────────────────────┼────────────────────┐            │
│         │                    │                    │            │
│         ▼                    ▼                    ▼            │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐      │
│  │EventHandler │     │ MetricsView │     │AgentControls│      │
│  │  Widget     │     │   Widget    │     │   Panel     │      │
│  └─────────────┘     └─────────────┘     └─────────────┘      │
│         │                    │                    │            │
│         ▼                    ▼                    ▼            │
│  ┌──────────────────────────────────────────────────────┐      │
│  │              EventBus (pub-sub)                      │      │
│  └──────────────────────────────────────────────────────┘      │
│                              │                                  │
│         ┌────────────────────┼────────────────────┐            │
│         │                    │                    │            │
│         ▼                    ▼                    ▼            │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐      │
│  │ Orchestrator│────▶│MetricsCollec│     │ GrindAgent  │      │
│  │             │     │    tor      │     │   (Agent)   │      │
│  └─────────────┘     └─────────────┘     └─────────────┘      │
│         │                                         │            │
│         └─────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility |
|-----------|---------------|
| **AgentTUI** | Main application, creates EventBus and wires components |
| **EventBus** | Pub-sub event distribution for orchestration events |
| **EventHandler** | Subscribes to events, updates TUI state |
| **AgentExecutor** | Bridges TUI with Orchestrator, manages agent lifecycle |
| **MetricsView** | Displays metrics from MetricsCollector |
| **AgentControlPanel** | Provides UI controls for agent start/stop/restart |
| **Orchestrator** | Manages agent execution, publishes events |
| **MetricsCollector** | Tracks agent performance metrics |

---

## EventBus Integration

### EventBus Creation and Sharing

The EventBus is created in `AgentTUI` and shared across all components:

```python
from grind.orchestration.events import EventBus
from grind.tui.core.agent_executor import AgentExecutor

class AgentTUI(App):
    def __init__(self):
        super().__init__()

        # Create shared EventBus
        self.event_bus = EventBus()

        # Pass to AgentExecutor
        self.executor = AgentExecutor(
            self.session,
            event_bus=self.event_bus
        )

        # EventHandler will subscribe to events
        self.event_handler = EventHandler(event_bus=self.event_bus)
```

### EventHandler Widget

The `EventHandler` widget acts as a bridge between EventBus and TUI state:

```python
from grind.orchestration.events import EventBus, EventType, AgentEvent
from grind.tui.widgets.event_handler import EventHandler

# Create event handler
event_handler = EventHandler(event_bus=event_bus)

# Register callback for agent updates
event_handler.on_agent_updated = self._handle_agent_update

# EventHandler automatically subscribes to:
# - AGENT_STARTED
# - AGENT_COMPLETED
# - AGENT_FAILED
# - ITERATION_STARTED
# - ITERATION_COMPLETED
```

### Event Flow Diagram

```
Agent Execution
      │
      ▼
┌─────────────┐
│Orchestrator │
│  run_agent()│
└─────────────┘
      │
      ├─────────────────────────────────────────┐
      │                                         │
      ▼                                         ▼
┌─────────────────┐                    ┌────────────────┐
│ EventBus.publish│                    │ GrindAgent.run │
│ AGENT_STARTED   │                    │                │
└─────────────────┘                    └────────────────┘
      │                                         │
      ▼                                         │
┌─────────────────┐                             │
│  EventHandler   │                             │
│  _handle_agent_ │                             │
│    started()    │                             │
└─────────────────┘                             │
      │                                         │
      ▼                                         │
┌─────────────────┐                             │
│ on_agent_updated│                             │
│   callback      │                             │
└─────────────────┘                             │
      │                                         │
      ▼                                         ▼
┌─────────────────┐                    ┌────────────────┐
│   TUI Update    │                    │ Agent executes │
│  (reactive UI)  │                    │  iterations    │
└─────────────────┘                    └────────────────┘
                                                │
                                                ▼
                                       ┌────────────────┐
                                       │ EventBus.publish│
                                       │ITERATION_STARTED│
                                       └────────────────┘
                                                │
                                                ▼
                                       ┌────────────────┐
                                       │  EventHandler  │
                                       │  updates iter  │
                                       └────────────────┘
```

### Event Types and Payloads

#### AGENT_STARTED

Published when agent execution begins.

```python
event = AgentEvent(
    event_type=EventType.AGENT_STARTED,
    agent_id="agent-abc123",
    timestamp=time.time(),
    data={
        "task_id": "agent-abc123",
        "task_description": "Implement feature X",
        "agent_type": "worker",
        "model": "sonnet",
        "max_iterations": 5,
    }
)
```

#### AGENT_COMPLETED

Published when agent successfully completes.

```python
event = AgentEvent(
    event_type=EventType.AGENT_COMPLETED,
    agent_id="agent-abc123",
    timestamp=time.time(),
    data={
        "task_id": "agent-abc123",
        "status": "success",
        "iterations": 3,
        "duration": 45.2,
        "output": {"result": "success"}
    }
)
```

#### AGENT_FAILED

Published when agent execution fails.

```python
event = AgentEvent(
    event_type=EventType.AGENT_FAILED,
    agent_id="agent-abc123",
    timestamp=time.time(),
    data={
        "task_id": "agent-abc123",
        "error_message": "Task verification failed",
        "iteration": 5,
    }
)
```

#### ITERATION_STARTED / ITERATION_COMPLETED

Published at the start and end of each iteration.

```python
event = AgentEvent(
    event_type=EventType.ITERATION_STARTED,
    agent_id="agent-abc123",
    timestamp=time.time(),
    data={
        "iteration": 2,
        "max_iterations": 5,
    }
)
```

---

## Metrics Display

### MetricsView Widget

The `MetricsView` widget displays real-time metrics from the `MetricsCollector`:

```python
from grind.tui.widgets.metrics_view import MetricsView

# Create metrics view
metrics_view = MetricsView(
    metrics_collector=orchestrator.metrics_collector
)

# Display all metrics
metrics_view.show_all()

# Display specific agent metrics
metrics_view.show_agent("agent-abc123")
```

### Metrics Tab Integration

Added to `AgentTUI` as tab "7":

```python
class AgentTUI(App):
    BINDINGS = [
        ("1", "switch_agents", "Agents"),
        ("2", "switch_dag", "DAG"),
        ("3", "switch_running", "Running"),
        ("4", "switch_completed", "Completed"),
        ("5", "switch_logs", "Logs"),
        ("6", "switch_shell", "Shell"),
        ("7", "switch_metrics", "Metrics"),  # ← New metrics tab
        ("q", "quit", "Quit"),
    ]

    def _compose_metrics_tab(self) -> Iterator[Widget]:
        """Compose the metrics tab."""
        yield MetricsView(
            metrics_collector=self.executor.orchestrator.metrics_collector
        )
```

### Metrics Displayed

| Metric | Description |
|--------|-------------|
| **Success Rate** | Percentage of successful agent runs |
| **Average Duration** | Mean execution time per agent run |
| **Total Runs** | Total number of agent executions |
| **Average Cost** | Mean cost per agent run (if available) |

### Visual Example

```
Agent Metrics
─────────────────────────────────────────
All Agents Summary
Success Rate: 85.7%
Avg Duration: 12.34s
Total Runs: 42
Avg Cost: $0.156

agent-abc123
  Success Rate: 100%
  Avg Duration: 10.2s
  Total Runs: 5
  Avg Cost: $0.120

agent-def456
  Success Rate: 66.7%
  Avg Duration: 15.8s
  Total Runs: 6
  Avg Cost: $0.189
```

---

## Agent Controls

### AgentControlPanel Widget

Provides interactive buttons for agent management:

```python
from grind.tui.widgets.agent_controls import AgentControlPanel

# Create control panel for specific agent
control_panel = AgentControlPanel(agent=agent_info)

# Register callbacks
control_panel.on_start = lambda agent_id: self._start_agent(agent_id)
control_panel.on_stop = lambda agent_id: self._stop_agent(agent_id)
control_panel.on_restart = lambda agent_id: self._restart_agent(agent_id)
```

### Button States

Buttons are dynamically enabled/disabled based on agent status:

| Button | Enabled When | Action |
|--------|-------------|--------|
| **Start** | `status == PENDING` | Begin agent execution |
| **Stop** | `status == RUNNING` | Cancel running agent |
| **Restart** | `status in [COMPLETE, FAILED, STUCK, CANCELLED]` | Re-run agent from beginning |

### Integration in Running Agents Tab

```python
def _compose_running_tab(self) -> Iterator[Widget]:
    """Compose the running agents tab."""
    # Agent list
    yield RunningAgentsManager(session=self.session)

    # Control panel for selected agent
    control_panel = AgentControlPanel()
    control_panel.on_start = self._handle_start_agent
    control_panel.on_stop = self._handle_stop_agent
    control_panel.on_restart = self._handle_restart_agent
    yield control_panel
```

---

## Real-Time Updates

### Event-Driven Status Updates

Before Phase 4, agent status was updated via polling. Now it's event-driven:

**Before (Polling):**
```python
# Update every 1 second
async def _update_loop(self):
    while True:
        await asyncio.sleep(1)
        self._refresh_agent_status()
```

**After (Event-Driven):**
```python
# Update immediately on event
async def _handle_agent_updated(self, agent_info: AgentInfo):
    # Update UI immediately when event is received
    self.running_agents_manager.update_agent(agent_info)
```

### Iteration Progress Display

Real-time iteration updates from `ITERATION_STARTED` and `ITERATION_COMPLETED` events:

```python
async def _handle_iteration_started(self, event: AgentEvent):
    iteration = event.data.get("iteration", 0)
    max_iterations = event.data.get("max_iterations", 5)
    progress = iteration / max_iterations

    # Update progress bar in real-time
    self.progress_bar.update(progress=progress)
    self.iteration_label.update(f"Iteration {iteration}/{max_iterations}")
```

### Visual Feedback

```
Running Agents
─────────────────────────────────────────
agent-abc123 | RUNNING | Iteration 3/5
[████████████░░░░░░░░] 60%
Task: Implement authentication feature

agent-def456 | RUNNING | Iteration 1/5
[████░░░░░░░░░░░░░░░░] 20%
Task: Fix database query optimization
```

---

## Complete Examples

### Example 1: Creating TUI with Orchestrator

```python
from grind.tui.app import AgentTUI
from grind.models import TaskDefinition

# Create TUI app (EventBus automatically created)
app = AgentTUI()

# Create task definition
task_def = TaskDefinition(
    id="task-1",
    task="Implement user authentication",
    verify="pytest tests/test_auth.py",
    max_iterations=5,
    model="sonnet"
)

# Create and execute agent
agent = app.executor.create_agent(task_def)
await app.executor.execute_agent(agent)

# Events are automatically published via EventBus:
# 1. AGENT_STARTED → EventHandler updates UI
# 2. ITERATION_STARTED (x5) → Progress updates
# 3. ITERATION_COMPLETED (x5) → Progress updates
# 4. AGENT_COMPLETED → Final status update

# Metrics are automatically collected
metrics = app.executor.orchestrator.metrics_collector.get_agent_metrics(agent.agent_id)
print(f"Success rate: {metrics.success_rate}%")
```

### Example 2: Subscribing to Custom Events

```python
from grind.orchestration.events import EventType, AgentEvent

async def on_agent_completed(event: AgentEvent):
    """Custom handler for agent completion."""
    print(f"Agent {event.agent_id} completed!")
    print(f"Iterations: {event.data.get('iterations')}")
    print(f"Duration: {event.data.get('duration')}s")

# Subscribe to events
app.event_bus.subscribe(EventType.AGENT_COMPLETED, on_agent_completed)

# Run agent
await app.executor.execute_agent(agent)

# on_agent_completed() will be called automatically
```

### Example 3: Using MetricsView Programmatically

```python
from grind.tui.widgets.metrics_view import MetricsView

# Create metrics view
metrics_view = MetricsView(
    metrics_collector=app.executor.orchestrator.metrics_collector
)

# Render metrics for display
metrics_text = metrics_view.render()
print(metrics_text)

# Show specific agent
metrics_view.selected_agent_id = "agent-abc123"
agent_metrics = metrics_view.render()
print(agent_metrics)
```

### Example 4: Controlling Agents Programmatically

```python
from grind.tui.widgets.agent_controls import AgentControlPanel

# Create control panel
control_panel = AgentControlPanel(agent=agent_info)

# Define control handlers
async def start_agent(agent_id: str):
    await app.executor.execute_agent(
        app.session.get_agent(agent_id)
    )

async def stop_agent(agent_id: str):
    await app.executor.cancel_agent(agent_id)

async def restart_agent(agent_id: str):
    # Create new agent with same task
    task_def = app.executor._task_definitions[agent_id]
    new_agent = app.executor.create_agent(task_def)
    await app.executor.execute_agent(new_agent)

# Register handlers
control_panel.on_start = start_agent
control_panel.on_stop = stop_agent
control_panel.on_restart = restart_agent
```

---

## Testing

### TUI Integration Tests

Updated `tests/test_tui_integration.py` to test Orchestrator integration:

```python
import pytest
from grind.tui.app import AgentTUI
from grind.orchestration.events import EventType

@pytest.mark.asyncio
async def test_eventbus_integration():
    """Test that TUI creates and uses EventBus."""
    app = AgentTUI()

    # Verify EventBus exists
    assert app.event_bus is not None

    # Verify AgentExecutor has EventBus
    assert app.executor.event_bus is app.event_bus

    # Verify EventHandler is subscribed
    assert app.event_handler is not None
    assert app.event_handler.event_bus is app.event_bus

@pytest.mark.asyncio
async def test_metrics_display():
    """Test that MetricsView displays metrics."""
    app = AgentTUI()

    # Create and run agent
    task_def = TaskDefinition(
        id="test-task",
        task="echo 'test'",
        verify="true",
        max_iterations=1
    )
    agent = app.executor.create_agent(task_def)
    await app.executor.execute_agent(agent)

    # Verify metrics were collected
    metrics = app.executor.orchestrator.metrics_collector.get_agent_metrics(
        agent.agent_id
    )
    assert metrics is not None
    assert metrics.total_runs > 0

@pytest.mark.asyncio
async def test_event_handler_updates():
    """Test that EventHandler updates TUI state."""
    app = AgentTUI()

    # Track updates
    updates = []

    def track_update(agent_info):
        updates.append(agent_info)

    app.event_handler.on_agent_updated = track_update

    # Run agent
    task_def = TaskDefinition(
        id="test-task",
        task="echo 'test'",
        verify="true",
        max_iterations=1
    )
    agent = app.executor.create_agent(task_def)
    await app.executor.execute_agent(agent)

    # Verify updates were received
    assert len(updates) > 0
```

### Widget Unit Tests

Test individual widgets in isolation:

```python
@pytest.mark.asyncio
async def test_event_handler_agent_started():
    """Test EventHandler handles AGENT_STARTED event."""
    from grind.orchestration.events import EventBus, EventType, AgentEvent
    from grind.tui.widgets.event_handler import EventHandler

    event_bus = EventBus()
    handler = EventHandler(event_bus=event_bus)

    # Track callback
    received = []
    handler.on_agent_updated = lambda agent: received.append(agent)

    # Publish event
    await event_bus.publish(AgentEvent(
        event_type=EventType.AGENT_STARTED,
        agent_id="test-agent",
        timestamp=time.time(),
        data={
            "task_description": "Test task",
            "model": "sonnet",
            "max_iterations": 5
        }
    ))

    # Verify callback was called
    assert len(received) == 1
    assert received[0].agent_id == "test-agent"
    assert received[0].status == AgentStatus.RUNNING
```

### Manual Testing

See `tests/manual/tui_smoke_test.md` for step-by-step manual testing guide.

---

## Next Steps

### Phase 5: Multi-Agent DAG Execution (Planned)

1. **DAG Visualization**: Interactive DAG view showing dependencies
2. **Parallel Execution**: Run independent agents in parallel
3. **Dependency Management**: Ensure agents run in correct order
4. **Visual Task Graph**: Real-time updates to DAG as agents execute

### Potential Enhancements

1. **Custom Event Types**: Allow users to define custom orchestration events
2. **Event Replay**: Record and replay event streams for debugging
3. **Metrics Export**: Export metrics to JSON/CSV for analysis
4. **Agent Templates**: Pre-configured agent types for common tasks
5. **Live Log Filtering**: Filter logs by event type in real-time

### Performance Improvements

1. **Event Batching**: Batch multiple events for reduced overhead
2. **Lazy Rendering**: Only render visible widgets
3. **Metric Aggregation**: Pre-compute aggregate metrics for faster display

---

## Appendix

### Key Files Reference

| File | Purpose |
|------|---------|
| `grind/tui/app.py` | Main TUI application with EventBus |
| `grind/tui/core/agent_executor.py` | Bridges TUI with Orchestrator |
| `grind/tui/widgets/event_handler.py` | EventBus subscriber widget |
| `grind/tui/widgets/metrics_view.py` | Metrics visualization |
| `grind/tui/widgets/agent_controls.py` | Agent control buttons |
| `grind/orchestration/events.py` | EventBus and event types |
| `grind/orchestration/orchestrator.py` | Agent orchestrator |
| `grind/orchestration/metrics.py` | Metrics collector |
| `tests/test_tui_integration.py` | TUI integration tests |

### Related Documentation

- [Phase 2-3: Orchestration Implementation](orchestration-implementation.md)
- [Orchestration Vision](orchestration-vision.md)
- [Architecture Overview](overview.md)
