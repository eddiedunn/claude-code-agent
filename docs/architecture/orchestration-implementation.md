# Agent Orchestration Implementation - Phase 2-3

This document provides practical examples and implementation details for Phase 2 (Agent Abstraction) and Phase 3 (Orchestrator Build) of the [orchestration vision](orchestration-vision.md).

**Status**: ✅ Phase 2 Complete, ✅ Phase 3 Complete

---

## Table of Contents

1. [Overview](#overview)
2. [Phase 2: Agent Abstraction](#phase-2-agent-abstraction)
3. [Phase 3: Orchestrator Build](#phase-3-orchestrator-build)
4. [Complete Examples](#complete-examples)
5. [Testing](#testing)
6. [Next Steps](#next-steps)

---

## Overview

### What We've Built

Phase 2-3 introduced a complete orchestration foundation:

```
grind/orchestration/
├── agent.py           # Agent protocol and AgentResult
├── grind_agent.py     # GrindAgent wraps grind() function
├── orchestrator.py    # Orchestrator for multi-agent coordination
├── events.py          # EventBus for pub-sub communication
├── metrics.py         # MetricsCollector for performance tracking
└── __init__.py        # Public API exports
```

**Key Design Decision**: Simple dict-based input/output instead of complex generics. This maintains flexibility while keeping the API clean.

### Architecture at a Glance

```
┌─────────────────────────────────────────────────────┐
│                  Orchestrator                       │
│  ┌─────────────────────────────────────────────────┤
│  │  - Agent registry                                │
│  │  - Sequential execution                          │
│  │  - Event emission via EventBus                   │
│  │  - Metrics collection via MetricsCollector       │
│  └─────────────────────────────────────────────────┤
│                         │                            │
│    ┌────────────────────┼────────────────────┐      │
│    │                    │                    │      │
│    ▼                    ▼                    ▼      │
│ ┌──────────┐     ┌──────────┐         ┌──────────┐ │
│ │ Agent 1  │     │ Agent 2  │         │ Agent 3  │ │
│ │(GrindAgt)│     │(GrindAgt)│         │(GrindAgt)│ │
│ └──────────┘     └──────────┘         └──────────┘ │
│       │                │                     │      │
│       ▼                ▼                     ▼      │
│   grind()          grind()               grind()    │
└─────────────────────────────────────────────────────┘
```

---

## Phase 2: Agent Abstraction

### Agent Protocol

The Agent protocol defines a simple interface all agents must implement:

```python
from grind.orchestration.agent import Agent, AgentResult, AgentStatus

class Agent(Protocol):
    """Protocol for agents that can be orchestrated."""

    async def run(self, input: dict[str, object]) -> AgentResult:
        """Execute the agent with given input.

        Args:
            input: Dict containing agent input parameters

        Returns:
            AgentResult with status, iterations, and output dict
        """
        ...
```

**Why dict-based?** Flexibility. Agents can accept any input structure without complex type constraints.

### AgentResult

Standard result type for all agents:

```python
from dataclasses import dataclass

@dataclass
class AgentResult:
    """Result of agent execution."""
    status: AgentStatus           # COMPLETE, STUCK, MAX_ITERATIONS, ERROR
    iterations: int               # Number of iterations performed
    output: dict[str, object]     # Output data (flexible structure)
    message: str = ""             # Human-readable message
    duration_seconds: float = 0.0 # Execution time
```

### AgentStatus

Standard status enum:

```python
from enum import Enum

class AgentStatus(Enum):
    """Status of agent execution."""
    COMPLETE = "complete"
    STUCK = "stuck"
    MAX_ITERATIONS = "max_iterations"
    ERROR = "error"
```

### GrindAgent Implementation

GrindAgent wraps the existing `grind()` function to conform to the Agent protocol:

```python
from grind.orchestration import GrindAgent

# Create a GrindAgent
agent = GrindAgent()

# Run with dict input
result = await agent.run({
    "task": "Create a hello world function in hello.py",
    "verify": "python -c 'from hello import hello; hello()'",
    "max_iterations": 5,
    "model": "sonnet"
})

# Check result
if result.status == AgentStatus.COMPLETE:
    print(f"✅ Success in {result.iterations} iterations")
    print(f"Duration: {result.duration_seconds:.2f}s")
    print(f"Tools used: {result.output['tools_used']}")
else:
    print(f"❌ Failed: {result.message}")
```

**Input Parameters** for GrindAgent:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task` | str | ✅ | Task description |
| `verify` | str | ✅ | Verification command |
| `max_iterations` | int | ❌ | Max iterations (default: 5) |
| `model` | str | ❌ | Model name (haiku, sonnet, opus) |
| `cwd` | str | ❌ | Working directory |
| `allowed_tools` | list[str] | ❌ | Allowed tools |
| `permission_mode` | str | ❌ | Permission mode |
| `verbose` | bool | ❌ | Verbose output (default: False) |

**Output Dictionary** from GrindAgent:

```python
{
    "message": "Task completed successfully",
    "tools_used": ["Read", "Write", "Bash"],
    "duration_seconds": 12.5,
    "model": "sonnet",
    "hooks_executed": ["/compact"]
}
```

### Creating Custom Agents

You can create custom agents by implementing the Agent protocol:

```python
from grind.orchestration.agent import Agent, AgentResult, AgentStatus

class MyCustomAgent:
    """Custom agent example."""

    async def run(self, input: dict[str, object]) -> AgentResult:
        # Extract input
        data = input.get("data", "")

        # Process
        try:
            result = self._process(data)

            return AgentResult(
                status=AgentStatus.COMPLETE,
                iterations=1,
                output={"result": result},
                message="Processing complete"
            )
        except Exception as e:
            return AgentResult(
                status=AgentStatus.ERROR,
                iterations=0,
                output={},
                message=str(e)
            )

    def _process(self, data: str) -> str:
        # Your processing logic
        return data.upper()
```

---

## Phase 3: Orchestrator Build

### Basic Orchestrator Usage

The Orchestrator manages multiple agents:

```python
from grind.orchestration import Orchestrator, GrindAgent

# Create orchestrator
orchestrator = Orchestrator()

# Add agents
orchestrator.add_agent("fix_linting", GrindAgent())
orchestrator.add_agent("fix_types", GrindAgent())
orchestrator.add_agent("fix_tests", GrindAgent())

# Run all agents sequentially
results = await orchestrator.run_all({
    "task": "Fix all errors",
    "verify": "make check",
    "max_iterations": 3
})

# Check results
for agent_id, result in results.items():
    print(f"{agent_id}: {result.status.value}")
```

### Running Individual Agents

```python
# Run a specific agent
result = await orchestrator.run_agent("fix_linting", {
    "task": "Fix linting errors",
    "verify": "ruff check .",
    "max_iterations": 5
})

if result.status == AgentStatus.COMPLETE:
    print(f"✅ Linting fixed in {result.iterations} iterations")
```

### EventBus - Pub/Sub Communication

The EventBus enables reactive programming with agents:

```python
from grind.orchestration import Orchestrator, EventBus, GrindAgent
from grind.orchestration.events import AgentEvent, EventType

# Create custom event bus
event_bus = EventBus()

# Subscribe to events
async def on_agent_started(event: AgentEvent):
    print(f"🚀 {event.agent_id} started")
    print(f"   Input: {event.data['input']}")

async def on_agent_completed(event: AgentEvent):
    print(f"✅ {event.agent_id} completed")
    print(f"   Status: {event.data['status']}")
    print(f"   Iterations: {event.data['iterations']}")

async def on_agent_failed(event: AgentEvent):
    print(f"❌ {event.agent_id} failed")
    print(f"   Error: {event.data['error']}")

# Register handlers
event_bus.subscribe(EventType.AGENT_STARTED, on_agent_started)
event_bus.subscribe(EventType.AGENT_COMPLETED, on_agent_completed)
event_bus.subscribe(EventType.AGENT_FAILED, on_agent_failed)

# Create orchestrator with custom event bus
orchestrator = Orchestrator(event_bus=event_bus)

# Now all agent executions will emit events
orchestrator.add_agent("my_agent", GrindAgent())
result = await orchestrator.run_agent("my_agent", {
    "task": "Create test file",
    "verify": "test -f test.py"
})
```

**Event Types**:

| EventType | When Emitted | Data Fields |
|-----------|--------------|-------------|
| `AGENT_STARTED` | Agent begins execution | `input` |
| `AGENT_COMPLETED` | Agent completes successfully | `status`, `iterations`, `output`, `message` |
| `AGENT_FAILED` | Agent raises exception | `error`, `duration` |
| `TASK_STARTED` | Task begins (reserved for future use) | TBD |
| `TASK_COMPLETED` | Task completes (reserved for future use) | TBD |
| `TASK_FAILED` | Task fails (reserved for future use) | TBD |
| `ITERATION_STARTED` | Iteration begins (reserved for future use) | TBD |
| `ITERATION_COMPLETED` | Iteration completes (reserved for future use) | TBD |

### MetricsCollector - Performance Tracking

The MetricsCollector tracks agent performance:

```python
from grind.orchestration import Orchestrator, MetricsCollector, GrindAgent

# Create custom metrics collector
metrics_collector = MetricsCollector()

# Create orchestrator with custom metrics
orchestrator = Orchestrator(metrics_collector=metrics_collector)

# Add and run agents
orchestrator.add_agent("agent_1", GrindAgent())
orchestrator.add_agent("agent_2", GrindAgent())

await orchestrator.run_all({
    "task": "Fix errors",
    "verify": "make test"
})

# Query metrics
metrics_1 = metrics_collector.get_metrics("agent_1")
print(f"Agent 1 Stats:")
print(f"  Total runs: {metrics_1.total_runs}")
print(f"  Successful: {metrics_1.successful_runs}")
print(f"  Success rate: {metrics_1.success_rate:.2%}")
print(f"  Avg duration: {metrics_1.average_duration:.2f}s")
print(f"  Avg cost: ${metrics_1.average_cost:.4f}")

# Get all metrics
all_metrics = metrics_collector.get_all_metrics()
for agent_id, metrics in all_metrics.items():
    print(f"{agent_id}: {metrics.success_rate:.2%} success rate")
```

**AgentMetrics Properties**:

```python
@dataclass
class AgentMetrics:
    total_duration: float       # Sum of all execution times
    total_cost: float          # Sum of all costs (currently 0.0)
    total_runs: int            # Number of executions
    successful_runs: int       # Number of successful executions

    @property
    def success_rate(self) -> float:
        """Success rate from 0.0 to 1.0"""

    @property
    def average_duration(self) -> float:
        """Average duration per run in seconds"""

    @property
    def average_cost(self) -> float:
        """Average cost per run"""
```

### Orchestrator API Reference

```python
class Orchestrator:
    """Stateless orchestrator for managing multiple agents."""

    def __init__(
        self,
        event_bus: EventBus | None = None,
        metrics_collector: MetricsCollector | None = None
    ):
        """Initialize with optional custom components."""

    def add_agent(self, agent_id: str, agent: Agent) -> None:
        """Register an agent."""

    def remove_agent(self, agent_id: str) -> None:
        """Unregister an agent."""

    def get_agent(self, agent_id: str) -> Agent | None:
        """Get agent by ID."""

    def list_agents(self) -> list[str]:
        """Get all agent IDs."""

    async def run_agent(
        self,
        agent_id: str,
        input_data: dict[str, object]
    ) -> AgentResult:
        """Run single agent, emits events and records metrics."""

    async def run_all(
        self,
        input_data: dict[str, object]
    ) -> dict[str, AgentResult]:
        """Run all agents sequentially with same input."""

    def clear_agents(self) -> None:
        """Remove all agents."""

    def reset_metrics(self) -> None:
        """Reset all metrics."""
```

---

## Complete Examples

### Example 1: Multiple Independent Fixes

Fix multiple issues in parallel (logically - executed sequentially):

```python
from grind.orchestration import Orchestrator, GrindAgent

async def fix_multiple_issues():
    orchestrator = Orchestrator()

    # Add agents for different fixes
    orchestrator.add_agent("linting", GrindAgent())
    orchestrator.add_agent("types", GrindAgent())
    orchestrator.add_agent("tests", GrindAgent())

    # Define tasks
    tasks = {
        "linting": {
            "task": "Fix all linting errors",
            "verify": "ruff check .",
            "max_iterations": 5
        },
        "types": {
            "task": "Fix all type errors",
            "verify": "mypy .",
            "max_iterations": 5
        },
        "tests": {
            "task": "Fix all test failures",
            "verify": "pytest",
            "max_iterations": 10
        }
    }

    # Run each agent with its specific task
    results = {}
    for agent_id, task_input in tasks.items():
        result = await orchestrator.run_agent(agent_id, task_input)
        results[agent_id] = result

    # Report results
    for agent_id, result in results.items():
        status_emoji = "✅" if result.status == AgentStatus.COMPLETE else "❌"
        print(f"{status_emoji} {agent_id}: {result.message}")
        print(f"   Iterations: {result.iterations}")
        print(f"   Duration: {result.duration_seconds:.2f}s")

    return results
```

### Example 2: Sequential Pipeline with Data Flow

Execute agents in sequence, passing data between them:

```python
from grind.orchestration import Orchestrator, GrindAgent, AgentStatus

async def sequential_pipeline():
    orchestrator = Orchestrator()

    # Stage 1: Analyze codebase
    orchestrator.add_agent("analyze", GrindAgent())
    analyze_result = await orchestrator.run_agent("analyze", {
        "task": "Analyze the codebase and create a report in analysis.md",
        "verify": "test -f analysis.md && grep -q 'Issues Found' analysis.md",
        "max_iterations": 3
    })

    if analyze_result.status != AgentStatus.COMPLETE:
        print("❌ Analysis failed, aborting pipeline")
        return

    print("✅ Analysis complete")

    # Stage 2: Fix critical issues identified
    orchestrator.add_agent("fix", GrindAgent())
    fix_result = await orchestrator.run_agent("fix", {
        "task": "Fix the critical issues identified in analysis.md",
        "verify": "pytest tests/critical/",
        "max_iterations": 10
    })

    if fix_result.status != AgentStatus.COMPLETE:
        print("❌ Fixes failed, aborting pipeline")
        return

    print("✅ Critical fixes complete")

    # Stage 3: Update documentation
    orchestrator.add_agent("docs", GrindAgent())
    docs_result = await orchestrator.run_agent("docs", {
        "task": "Update documentation to reflect the fixes made",
        "verify": "mkdocs build",
        "max_iterations": 3
    })

    if docs_result.status == AgentStatus.COMPLETE:
        print("✅ Documentation updated")
    else:
        print("⚠️  Documentation update failed (non-critical)")

    # Summary
    total_iterations = (
        analyze_result.iterations +
        fix_result.iterations +
        docs_result.iterations
    )
    print(f"\n📊 Pipeline complete: {total_iterations} total iterations")
```

### Example 3: Event-Driven Progress Tracking

Track progress in real-time using events:

```python
from grind.orchestration import Orchestrator, GrindAgent, EventBus
from grind.orchestration.events import AgentEvent, EventType
import asyncio

async def event_driven_execution():
    # Setup event tracking
    event_bus = EventBus()
    events_log = []

    async def log_event(event: AgentEvent):
        timestamp = event.timestamp
        events_log.append((timestamp, event.event_type, event.agent_id))
        print(f"[{event.event_type.value}] {event.agent_id}")

    # Subscribe to all event types
    event_bus.subscribe(EventType.AGENT_STARTED, log_event)
    event_bus.subscribe(EventType.AGENT_COMPLETED, log_event)
    event_bus.subscribe(EventType.AGENT_FAILED, log_event)

    # Create orchestrator with event bus
    orchestrator = Orchestrator(event_bus=event_bus)

    # Add multiple agents
    orchestrator.add_agent("agent_1", GrindAgent())
    orchestrator.add_agent("agent_2", GrindAgent())
    orchestrator.add_agent("agent_3", GrindAgent())

    # Run all agents
    results = await orchestrator.run_all({
        "task": "Create a hello world function in hello.py",
        "verify": "python hello.py",
        "max_iterations": 3
    })

    # Analyze event log
    print("\n📊 Event Timeline:")
    for timestamp, event_type, agent_id in events_log:
        print(f"  {timestamp:.2f}s: {event_type.value} - {agent_id}")

    return results
```

### Example 4: Metrics-Based Analysis

Collect and analyze performance metrics:

```python
from grind.orchestration import Orchestrator, GrindAgent, MetricsCollector

async def metrics_analysis():
    metrics_collector = MetricsCollector()
    orchestrator = Orchestrator(metrics_collector=metrics_collector)

    # Add agents
    orchestrator.add_agent("fast_agent", GrindAgent())
    orchestrator.add_agent("slow_agent", GrindAgent())

    # Run fast agent multiple times
    for i in range(3):
        await orchestrator.run_agent("fast_agent", {
            "task": f"Quick task {i}",
            "verify": "echo 'done'",
            "max_iterations": 1
        })

    # Run slow agent once
    await orchestrator.run_agent("slow_agent", {
        "task": "Complex task",
        "verify": "pytest",
        "max_iterations": 10
    })

    # Compare metrics
    fast_metrics = metrics_collector.get_metrics("fast_agent")
    slow_metrics = metrics_collector.get_metrics("slow_agent")

    print("Performance Comparison:")
    print(f"\nFast Agent:")
    print(f"  Runs: {fast_metrics.total_runs}")
    print(f"  Success Rate: {fast_metrics.success_rate:.2%}")
    print(f"  Avg Duration: {fast_metrics.average_duration:.2f}s")

    print(f"\nSlow Agent:")
    print(f"  Runs: {slow_metrics.total_runs}")
    print(f"  Success Rate: {slow_metrics.success_rate:.2%}")
    print(f"  Avg Duration: {slow_metrics.average_duration:.2f}s")

    # Get all metrics summary
    all_metrics = metrics_collector.get_all_metrics()
    total_runs = sum(m.total_runs for m in all_metrics.values())
    print(f"\n📊 Total agent runs across system: {total_runs}")
```

### Example 5: Custom Agent Integration

Integrate custom agents with GrindAgent:

```python
from grind.orchestration import (
    Orchestrator,
    GrindAgent,
    Agent,
    AgentResult,
    AgentStatus
)

class ValidationAgent:
    """Custom agent that validates results."""

    async def run(self, input: dict[str, object]) -> AgentResult:
        """Validate that previous agent succeeded."""
        previous_result = input.get("previous_result")

        if not previous_result:
            return AgentResult(
                status=AgentStatus.ERROR,
                iterations=0,
                message="No previous result to validate"
            )

        # Validation logic
        if previous_result.get("status") == "complete":
            return AgentResult(
                status=AgentStatus.COMPLETE,
                iterations=1,
                output={"validated": True},
                message="Validation passed"
            )
        else:
            return AgentResult(
                status=AgentStatus.ERROR,
                iterations=1,
                output={"validated": False},
                message="Validation failed"
            )

async def hybrid_agents():
    orchestrator = Orchestrator()

    # Mix GrindAgent and custom agent
    orchestrator.add_agent("fix", GrindAgent())
    orchestrator.add_agent("validate", ValidationAgent())

    # Run fix
    fix_result = await orchestrator.run_agent("fix", {
        "task": "Fix the bug",
        "verify": "pytest test_bug.py"
    })

    # Validate the fix
    validate_result = await orchestrator.run_agent("validate", {
        "previous_result": {
            "status": fix_result.status.value
        }
    })

    if validate_result.status == AgentStatus.COMPLETE:
        print("✅ Fix validated successfully")
    else:
        print("❌ Fix validation failed")
```

---

## Testing

### Test Structure

The orchestration module has comprehensive test coverage:

```
tests/
├── test_orchestration_agent.py   # Agent protocol and GrindAgent tests
├── test_orchestration_events.py  # EventBus tests
├── test_orchestration_core.py    # Orchestrator integration tests
└── test_orchestration_metrics.py # MetricsCollector tests (if exists)
```

### Running Tests

```bash
# Run all orchestration tests
pytest tests/test_orchestration*.py -v

# Run specific test file
pytest tests/test_orchestration_core.py -v

# Run with coverage
pytest tests/test_orchestration*.py --cov=grind.orchestration --cov-report=term-missing
```

### Key Test Scenarios

The test suite covers:

1. **Agent Basics**
   - GrindAgent wraps grind() correctly
   - Status mapping (GrindStatus → AgentStatus)
   - Error handling

2. **Orchestrator Basics**
   - Agent registration/removal
   - Single agent execution
   - Multiple agent execution
   - Sequential ordering

3. **Event Emission**
   - AGENT_STARTED events
   - AGENT_COMPLETED events
   - AGENT_FAILED events
   - Event sequencing
   - Multiple subscribers

4. **Metrics Collection**
   - Success/failure tracking
   - Duration tracking
   - Per-agent metrics
   - Aggregated metrics

5. **Error Handling**
   - Agent exceptions caught
   - Failed agents don't stop others
   - Nonexistent agent errors

---

## Next Steps

### Phase 4: Rebuild TUI on Orchestrator

The next phase will integrate the Orchestrator into the TUI:

1. **TUI Integration**
   - TUI creates Orchestrator instance
   - TUI subscribes to EventBus for progress updates
   - TUI renders agent execution state from events

2. **Multi-Agent Visibility**
   - Display multiple agents simultaneously
   - Show per-agent status and progress
   - Real-time event streaming to UI

3. **User Controls**
   - Start/stop individual agents
   - Restart failed agents
   - View agent metrics

### Future Enhancements

1. **PromptAgent** (Phase 4)
   - Single-shot Claude calls without grind loop
   - Useful for analysis, planning, reporting

2. **CompositeAgent** (Phase 4)
   - Workflow composition
   - Define pipelines declaratively

3. **Agent Memory** (Phase 4)
   - Store execution history
   - Learn from past runs
   - Semantic search for similar tasks

4. **Parallel Execution** (Phase 5)
   - True concurrent agent execution
   - Resource pooling
   - Dependency-aware scheduling

5. **Advanced Routing** (Phase 5)
   - Cost-aware agent selection
   - Model routing (haiku/sonnet/opus)
   - Quality vs. speed tradeoffs

---

## Design Notes

### Why No Generics?

The vision document proposed `Agent[Input, Output]` with generics, but we chose simple dict-based input/output instead:

**Benefits:**
- Simpler API surface
- More flexible - agents can evolve input/output without breaking protocol
- Easier testing and mocking
- Aligns with industry patterns (LangChain, etc.)
- No runtime overhead

**Tradeoff:**
- Less type safety (but runtime validation compensates)

### Why Stateless Orchestrator?

The Orchestrator maintains agent registry but creates ephemeral execution contexts:

**Benefits:**
- No state corruption between runs
- Thread-safe by design
- Easy to test
- Clear lifecycle

**Pattern:**
```python
# Registry state (persistent)
self._agents: dict[str, Agent]

# Execution is stateless
async def run_agent(agent_id, input) -> AgentResult:
    # No persistent state modified
```

### Event-Driven Architecture

Events enable loose coupling between orchestration layers:

```
Orchestrator → EventBus → [TUI, Metrics, Logs, ...]
```

Any component can subscribe to agent events without tight coupling.

---

## Appendix: API Quick Reference

### Imports

```python
from grind.orchestration import (
    Agent,              # Protocol
    AgentResult,        # Result type
    AgentStatus,        # Status enum
    GrindAgent,         # grind() wrapper
    Orchestrator,       # Multi-agent coordinator
    EventBus,           # Pub/sub events
    MetricsCollector,   # Performance tracking
)

from grind.orchestration.events import (
    AgentEvent,         # Event data structure
    EventType,          # Event type enum
)

from grind.orchestration.metrics import (
    AgentMetrics,       # Metrics data structure
)
```

### Status Values

```python
AgentStatus.COMPLETE        # Success
AgentStatus.STUCK           # Agent reported stuck
AgentStatus.MAX_ITERATIONS  # Hit iteration limit
AgentStatus.ERROR           # Exception occurred
```

### Event Types

```python
EventType.AGENT_STARTED     # Agent began execution
EventType.AGENT_COMPLETED   # Agent finished successfully
EventType.AGENT_FAILED      # Agent raised exception
```

---

**Document Version**: 1.0
**Last Updated**: December 2025
**Status**: Complete (Phase 2-3)
**Next Review**: After Phase 4 TUI integration
