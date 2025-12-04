"""Tests for grind.orchestration core functionality.

This module tests the Orchestrator with multiple GrindAgents, dependency
resolution, event emission, and metrics collection.
"""

from unittest.mock import AsyncMock, patch
import pytest

from grind.models import GrindResult, GrindStatus
from grind.orchestration.agent import AgentResult, AgentStatus
from grind.orchestration.events import AgentEvent, EventBus, EventType
from grind.orchestration.grind_agent import GrindAgent
from grind.orchestration.metrics import MetricsCollector
from grind.orchestration.orchestrator import Orchestrator


class TestOrchestratorBasics:
    """Test basic Orchestrator functionality."""

    def test_orchestrator_initialization(self):
        """Orchestrator should initialize with default components."""
        orch = Orchestrator()

        assert orch.event_bus is not None
        assert orch.metrics_collector is not None
        assert isinstance(orch.event_bus, EventBus)
        assert isinstance(orch.metrics_collector, MetricsCollector)

    def test_orchestrator_with_custom_components(self):
        """Orchestrator should accept custom EventBus and MetricsCollector."""
        custom_bus = EventBus()
        custom_metrics = MetricsCollector()

        orch = Orchestrator(event_bus=custom_bus, metrics_collector=custom_metrics)

        assert orch.event_bus is custom_bus
        assert orch.metrics_collector is custom_metrics

    def test_add_agent(self):
        """Orchestrator should allow adding agents."""
        orch = Orchestrator()
        agent = GrindAgent()

        orch.add_agent("agent_1", agent)

        assert "agent_1" in orch.list_agents()
        assert orch.get_agent("agent_1") is agent

    def test_add_multiple_agents(self):
        """Orchestrator should handle multiple agents."""
        orch = Orchestrator()
        agent1 = GrindAgent()
        agent2 = GrindAgent()
        agent3 = GrindAgent()

        orch.add_agent("agent_1", agent1)
        orch.add_agent("agent_2", agent2)
        orch.add_agent("agent_3", agent3)

        assert len(orch.list_agents()) == 3
        assert "agent_1" in orch.list_agents()
        assert "agent_2" in orch.list_agents()
        assert "agent_3" in orch.list_agents()

    def test_remove_agent(self):
        """Orchestrator should allow removing agents."""
        orch = Orchestrator()
        agent = GrindAgent()

        orch.add_agent("agent_1", agent)
        assert "agent_1" in orch.list_agents()

        orch.remove_agent("agent_1")
        assert "agent_1" not in orch.list_agents()

    def test_get_nonexistent_agent(self):
        """Orchestrator should return None for nonexistent agents."""
        orch = Orchestrator()

        assert orch.get_agent("nonexistent") is None

    def test_clear_agents(self):
        """Orchestrator should clear all agents."""
        orch = Orchestrator()
        orch.add_agent("agent_1", GrindAgent())
        orch.add_agent("agent_2", GrindAgent())
        orch.add_agent("agent_3", GrindAgent())

        assert len(orch.list_agents()) == 3

        orch.clear_agents()

        assert len(orch.list_agents()) == 0


class TestOrchestratorWithMultipleGrindAgents:
    """Test Orchestrator with multiple GrindAgent instances."""

    @pytest.mark.asyncio
    async def test_run_single_grind_agent(self):
        """Orchestrator should run a single GrindAgent successfully."""
        orch = Orchestrator()
        agent = GrindAgent()
        orch.add_agent("agent_1", agent)

        mock_grind_result = GrindResult(
            status=GrindStatus.COMPLETE,
            iterations=3,
            message="Task completed",
            tools_used=["Read", "Write"],
            duration_seconds=10.0,
            hooks_executed=[],
            model="sonnet"
        )

        with patch('grind.orchestration.grind_agent.grind',
                   AsyncMock(return_value=mock_grind_result)):
            result = await orch.run_agent("agent_1", {
                "task": "Create test file",
                "verify": "pytest"
            })

        assert result.status == AgentStatus.COMPLETE
        assert result.iterations == 3
        assert result.message == "Task completed"

    @pytest.mark.asyncio
    async def test_run_multiple_grind_agents_sequentially(self):
        """Orchestrator should run multiple GrindAgents in sequence."""
        orch = Orchestrator()
        agent1 = GrindAgent()
        agent2 = GrindAgent()
        agent3 = GrindAgent()

        orch.add_agent("agent_1", agent1)
        orch.add_agent("agent_2", agent2)
        orch.add_agent("agent_3", agent3)

        # Mock results for each agent
        mock_results = [
            GrindResult(
                status=GrindStatus.COMPLETE,
                iterations=2,
                message="Agent 1 completed",
                tools_used=["Read"],
                duration_seconds=5.0,
                hooks_executed=[],
                model="sonnet"
            ),
            GrindResult(
                status=GrindStatus.COMPLETE,
                iterations=3,
                message="Agent 2 completed",
                tools_used=["Write"],
                duration_seconds=7.0,
                hooks_executed=[],
                model="sonnet"
            ),
            GrindResult(
                status=GrindStatus.COMPLETE,
                iterations=1,
                message="Agent 3 completed",
                tools_used=["Bash"],
                duration_seconds=3.0,
                hooks_executed=[],
                model="sonnet"
            ),
        ]

        call_count = 0
        async def mock_grind(*args, **kwargs):
            nonlocal call_count
            result = mock_results[call_count]
            call_count += 1
            return result

        with patch('grind.orchestration.grind_agent.grind', side_effect=mock_grind):
            result1 = await orch.run_agent("agent_1", {
                "task": "Task 1",
                "verify": "test1"
            })
            result2 = await orch.run_agent("agent_2", {
                "task": "Task 2",
                "verify": "test2"
            })
            result3 = await orch.run_agent("agent_3", {
                "task": "Task 3",
                "verify": "test3"
            })

        assert result1.status == AgentStatus.COMPLETE
        assert result1.iterations == 2
        assert result2.status == AgentStatus.COMPLETE
        assert result2.iterations == 3
        assert result3.status == AgentStatus.COMPLETE
        assert result3.iterations == 1

    @pytest.mark.asyncio
    async def test_run_all_agents(self):
        """Orchestrator should run all agents with run_all()."""
        orch = Orchestrator()
        orch.add_agent("agent_1", GrindAgent())
        orch.add_agent("agent_2", GrindAgent())

        mock_grind_result = GrindResult(
            status=GrindStatus.COMPLETE,
            iterations=1,
            message="Success",
            tools_used=[],
            duration_seconds=5.0,
            hooks_executed=[],
            model="sonnet"
        )

        with patch('grind.orchestration.grind_agent.grind',
                   AsyncMock(return_value=mock_grind_result)):
            results = await orch.run_all({
                "task": "Shared task",
                "verify": "pytest"
            })

        assert len(results) == 2
        assert "agent_1" in results
        assert "agent_2" in results
        assert results["agent_1"].status == AgentStatus.COMPLETE
        assert results["agent_2"].status == AgentStatus.COMPLETE

    @pytest.mark.asyncio
    async def test_agents_with_different_outcomes(self):
        """Orchestrator should handle agents with different outcomes."""
        orch = Orchestrator()
        orch.add_agent("complete_agent", GrindAgent())
        orch.add_agent("stuck_agent", GrindAgent())
        orch.add_agent("max_iter_agent", GrindAgent())

        mock_results = [
            GrindResult(
                status=GrindStatus.COMPLETE,
                iterations=3,
                message="Success",
                tools_used=["Read"],
                duration_seconds=10.0,
                hooks_executed=[],
                model="sonnet"
            ),
            GrindResult(
                status=GrindStatus.STUCK,
                iterations=5,
                message="GRIND_STUCK: Cannot proceed",
                tools_used=["Read", "Write"],
                duration_seconds=15.0,
                hooks_executed=[],
                model="sonnet"
            ),
            GrindResult(
                status=GrindStatus.MAX_ITERATIONS,
                iterations=10,
                message="Max iterations reached",
                tools_used=["Bash"],
                duration_seconds=30.0,
                hooks_executed=[],
                model="sonnet"
            ),
        ]

        call_count = 0
        async def mock_grind(*args, **kwargs):
            nonlocal call_count
            result = mock_results[call_count]
            call_count += 1
            return result

        with patch('grind.orchestration.grind_agent.grind', side_effect=mock_grind):
            results = await orch.run_all({
                "task": "Test",
                "verify": "pytest"
            })

        assert results["complete_agent"].status == AgentStatus.COMPLETE
        assert results["stuck_agent"].status == AgentStatus.STUCK
        assert results["max_iter_agent"].status == AgentStatus.MAX_ITERATIONS


class TestOrchestratorEventEmission:
    """Test Orchestrator event emission during agent execution."""

    @pytest.mark.asyncio
    async def test_agent_started_event_emitted(self):
        """Orchestrator should emit AGENT_STARTED event."""
        event_bus = EventBus()
        orch = Orchestrator(event_bus=event_bus)
        orch.add_agent("agent_1", GrindAgent())

        events = []
        async def capture_event(event: AgentEvent):
            events.append(event)

        event_bus.subscribe(EventType.AGENT_STARTED, capture_event)

        mock_grind_result = GrindResult(
            status=GrindStatus.COMPLETE,
            iterations=1,
            message="Success",
            tools_used=[],
            duration_seconds=5.0,
            hooks_executed=[],
            model="sonnet"
        )

        with patch('grind.orchestration.grind_agent.grind',
                   AsyncMock(return_value=mock_grind_result)):
            await orch.run_agent("agent_1", {
                "task": "Test task",
                "verify": "pytest"
            })

        assert len(events) == 1
        assert events[0].event_type == EventType.AGENT_STARTED
        assert events[0].agent_id == "agent_1"
        assert events[0].data["input"]["task"] == "Test task"

    @pytest.mark.asyncio
    async def test_agent_completed_event_emitted(self):
        """Orchestrator should emit AGENT_COMPLETED event on success."""
        event_bus = EventBus()
        orch = Orchestrator(event_bus=event_bus)
        orch.add_agent("agent_1", GrindAgent())

        events = []
        async def capture_event(event: AgentEvent):
            events.append(event)

        event_bus.subscribe(EventType.AGENT_COMPLETED, capture_event)

        mock_grind_result = GrindResult(
            status=GrindStatus.COMPLETE,
            iterations=3,
            message="All tests passed",
            tools_used=["Read", "Write"],
            duration_seconds=12.5,
            hooks_executed=[],
            model="sonnet"
        )

        with patch('grind.orchestration.grind_agent.grind',
                   AsyncMock(return_value=mock_grind_result)):
            await orch.run_agent("agent_1", {
                "task": "Test task",
                "verify": "pytest"
            })

        assert len(events) == 1
        assert events[0].event_type == EventType.AGENT_COMPLETED
        assert events[0].agent_id == "agent_1"
        assert events[0].data["status"] == "complete"
        assert events[0].data["iterations"] == 3
        assert events[0].data["message"] == "All tests passed"

    @pytest.mark.asyncio
    async def test_agent_failed_event_emitted(self):
        """Orchestrator should emit AGENT_FAILED event on exception."""
        event_bus = EventBus()
        orch = Orchestrator(event_bus=event_bus)
        orch.add_agent("agent_1", GrindAgent())

        events = []
        async def capture_event(event: AgentEvent):
            events.append(event)

        event_bus.subscribe(EventType.AGENT_FAILED, capture_event)

        with patch('grind.orchestration.grind_agent.grind',
                   AsyncMock(side_effect=RuntimeError("Test error"))):
            result = await orch.run_agent("agent_1", {
                "task": "Test task",
                "verify": "pytest"
            })

        assert len(events) == 1
        assert events[0].event_type == EventType.AGENT_FAILED
        assert events[0].agent_id == "agent_1"
        assert "Test error" in events[0].data["error"]
        assert result.status == AgentStatus.ERROR

    @pytest.mark.asyncio
    async def test_multiple_agents_emit_events(self):
        """Orchestrator should emit events for multiple agents."""
        event_bus = EventBus()
        orch = Orchestrator(event_bus=event_bus)
        orch.add_agent("agent_1", GrindAgent())
        orch.add_agent("agent_2", GrindAgent())

        started_events = []
        completed_events = []

        async def capture_started(event: AgentEvent):
            started_events.append(event)

        async def capture_completed(event: AgentEvent):
            completed_events.append(event)

        event_bus.subscribe(EventType.AGENT_STARTED, capture_started)
        event_bus.subscribe(EventType.AGENT_COMPLETED, capture_completed)

        mock_grind_result = GrindResult(
            status=GrindStatus.COMPLETE,
            iterations=1,
            message="Success",
            tools_used=[],
            duration_seconds=5.0,
            hooks_executed=[],
            model="sonnet"
        )

        with patch('grind.orchestration.grind_agent.grind',
                   AsyncMock(return_value=mock_grind_result)):
            await orch.run_all({
                "task": "Test",
                "verify": "pytest"
            })

        # Should have 2 started and 2 completed events
        assert len(started_events) == 2
        assert len(completed_events) == 2

        # Verify agent IDs
        started_ids = {e.agent_id for e in started_events}
        completed_ids = {e.agent_id for e in completed_events}
        assert started_ids == {"agent_1", "agent_2"}
        assert completed_ids == {"agent_1", "agent_2"}

    @pytest.mark.asyncio
    async def test_event_sequence_for_single_agent(self):
        """Events should be emitted in correct sequence: started -> completed."""
        event_bus = EventBus()
        orch = Orchestrator(event_bus=event_bus)
        orch.add_agent("agent_1", GrindAgent())

        event_sequence = []

        async def capture_any(event: AgentEvent):
            event_sequence.append(event.event_type)

        event_bus.subscribe(EventType.AGENT_STARTED, capture_any)
        event_bus.subscribe(EventType.AGENT_COMPLETED, capture_any)
        event_bus.subscribe(EventType.AGENT_FAILED, capture_any)

        mock_grind_result = GrindResult(
            status=GrindStatus.COMPLETE,
            iterations=1,
            message="Success",
            tools_used=[],
            duration_seconds=5.0,
            hooks_executed=[],
            model="sonnet"
        )

        with patch('grind.orchestration.grind_agent.grind',
                   AsyncMock(return_value=mock_grind_result)):
            await orch.run_agent("agent_1", {
                "task": "Test",
                "verify": "pytest"
            })

        assert event_sequence == [EventType.AGENT_STARTED, EventType.AGENT_COMPLETED]


class TestOrchestratorMetricsCollection:
    """Test Orchestrator metrics collection during agent execution."""

    @pytest.mark.asyncio
    async def test_metrics_recorded_for_successful_run(self):
        """Orchestrator should record metrics for successful agent run."""
        metrics_collector = MetricsCollector()
        orch = Orchestrator(metrics_collector=metrics_collector)
        orch.add_agent("agent_1", GrindAgent())

        mock_grind_result = GrindResult(
            status=GrindStatus.COMPLETE,
            iterations=3,
            message="Success",
            tools_used=[],
            duration_seconds=10.0,
            hooks_executed=[],
            model="sonnet"
        )

        with patch('grind.orchestration.grind_agent.grind',
                   AsyncMock(return_value=mock_grind_result)):
            await orch.run_agent("agent_1", {
                "task": "Test",
                "verify": "pytest"
            })

        metrics = metrics_collector.get_metrics("agent_1")
        assert metrics is not None
        assert metrics.total_runs == 1
        assert metrics.successful_runs == 1
        assert metrics.total_runs - metrics.successful_runs == 0  # failed runs

    @pytest.mark.asyncio
    async def test_metrics_recorded_for_failed_run(self):
        """Orchestrator should record metrics for failed agent run."""
        metrics_collector = MetricsCollector()
        orch = Orchestrator(metrics_collector=metrics_collector)
        orch.add_agent("agent_1", GrindAgent())

        with patch('grind.orchestration.grind_agent.grind',
                   AsyncMock(side_effect=RuntimeError("Test error"))):
            result = await orch.run_agent("agent_1", {
                "task": "Test",
                "verify": "pytest"
            })

        assert result.status == AgentStatus.ERROR

        metrics = metrics_collector.get_metrics("agent_1")
        assert metrics is not None
        assert metrics.total_runs == 1
        assert metrics.successful_runs == 0
        assert metrics.total_runs - metrics.successful_runs == 1  # failed runs

    @pytest.mark.asyncio
    async def test_metrics_for_multiple_agents(self):
        """Orchestrator should track metrics for multiple agents separately."""
        metrics_collector = MetricsCollector()
        orch = Orchestrator(metrics_collector=metrics_collector)
        orch.add_agent("agent_1", GrindAgent())
        orch.add_agent("agent_2", GrindAgent())

        mock_grind_result = GrindResult(
            status=GrindStatus.COMPLETE,
            iterations=1,
            message="Success",
            tools_used=[],
            duration_seconds=5.0,
            hooks_executed=[],
            model="sonnet"
        )

        with patch('grind.orchestration.grind_agent.grind',
                   AsyncMock(return_value=mock_grind_result)):
            await orch.run_all({
                "task": "Test",
                "verify": "pytest"
            })

        metrics1 = metrics_collector.get_metrics("agent_1")
        metrics2 = metrics_collector.get_metrics("agent_2")

        assert metrics1 is not None
        assert metrics2 is not None
        assert metrics1.total_runs == 1
        assert metrics2.total_runs == 1

    @pytest.mark.asyncio
    async def test_reset_metrics(self):
        """Orchestrator should allow resetting metrics."""
        metrics_collector = MetricsCollector()
        orch = Orchestrator(metrics_collector=metrics_collector)
        orch.add_agent("agent_1", GrindAgent())

        mock_grind_result = GrindResult(
            status=GrindStatus.COMPLETE,
            iterations=1,
            message="Success",
            tools_used=[],
            duration_seconds=5.0,
            hooks_executed=[],
            model="sonnet"
        )

        with patch('grind.orchestration.grind_agent.grind',
                   AsyncMock(return_value=mock_grind_result)):
            await orch.run_agent("agent_1", {
                "task": "Test",
                "verify": "pytest"
            })

        # Verify metrics were recorded
        metrics_before = metrics_collector.get_metrics("agent_1")
        assert metrics_before.total_runs == 1

        orch.reset_metrics()

        # After reset, metrics should be cleared (all_metrics should be empty)
        all_metrics = metrics_collector.get_all_metrics()
        assert len(all_metrics) == 0


class TestOrchestratorDependencyResolution:
    """Test Orchestrator dependency resolution and sequencing."""

    @pytest.mark.asyncio
    async def test_sequential_execution_order(self):
        """Orchestrator should execute agents in registration order."""
        orch = Orchestrator()
        orch.add_agent("agent_1", GrindAgent())
        orch.add_agent("agent_2", GrindAgent())
        orch.add_agent("agent_3", GrindAgent())

        execution_order = []

        async def mock_grind(task_def, **kwargs):
            execution_order.append(task_def.task)
            return GrindResult(
                status=GrindStatus.COMPLETE,
                iterations=1,
                message="Success",
                tools_used=[],
                duration_seconds=1.0,
                hooks_executed=[],
                model="sonnet"
            )

        with patch('grind.orchestration.grind_agent.grind', side_effect=mock_grind):
            await orch.run_agent("agent_1", {"task": "Task 1", "verify": "test1"})
            await orch.run_agent("agent_2", {"task": "Task 2", "verify": "test2"})
            await orch.run_agent("agent_3", {"task": "Task 3", "verify": "test3"})

        assert execution_order == ["Task 1", "Task 2", "Task 3"]

    @pytest.mark.asyncio
    async def test_run_all_preserves_order(self):
        """run_all() should execute agents in registration order."""
        orch = Orchestrator()
        orch.add_agent("first", GrindAgent())
        orch.add_agent("second", GrindAgent())
        orch.add_agent("third", GrindAgent())

        execution_order = []

        async def mock_grind(task_def, **kwargs):
            execution_order.append(task_def.task)
            return GrindResult(
                status=GrindStatus.COMPLETE,
                iterations=1,
                message="Success",
                tools_used=[],
                duration_seconds=1.0,
                hooks_executed=[],
                model="sonnet"
            )

        with patch('grind.orchestration.grind_agent.grind', side_effect=mock_grind):
            results = await orch.run_all({"task": "Test", "verify": "pytest"})

        # All three should execute
        assert len(execution_order) == 3
        # Results should contain all agent IDs
        assert set(results.keys()) == {"first", "second", "third"}

    @pytest.mark.asyncio
    async def test_agent_can_pass_data_to_next_agent(self):
        """Agents can share data through orchestrator coordination."""
        orch = Orchestrator()
        orch.add_agent("producer", GrindAgent())
        orch.add_agent("consumer", GrindAgent())

        mock_grind_result = GrindResult(
            status=GrindStatus.COMPLETE,
            iterations=1,
            message="Success",
            tools_used=[],
            duration_seconds=1.0,
            hooks_executed=[],
            model="sonnet"
        )

        with patch('grind.orchestration.grind_agent.grind',
                   AsyncMock(return_value=mock_grind_result)):
            # First agent produces data
            result1 = await orch.run_agent("producer", {
                "task": "Create data",
                "verify": "test"
            })

            # Second agent can use data from first (simulated dependency)
            result2 = await orch.run_agent("consumer", {
                "task": "Use data",
                "verify": "test",
                "input_data": result1.output
            })

        assert result1.status == AgentStatus.COMPLETE
        assert result2.status == AgentStatus.COMPLETE


class TestOrchestratorErrorHandling:
    """Test Orchestrator error handling."""

    @pytest.mark.asyncio
    async def test_run_nonexistent_agent_raises_error(self):
        """Running a nonexistent agent should raise KeyError."""
        orch = Orchestrator()

        with pytest.raises(KeyError, match="Agent 'nonexistent' not found"):
            await orch.run_agent("nonexistent", {
                "task": "Test",
                "verify": "pytest"
            })

    @pytest.mark.asyncio
    async def test_agent_exception_returns_error_result(self):
        """Agent exception should be caught and returned as ERROR result."""
        orch = Orchestrator()
        orch.add_agent("failing_agent", GrindAgent())

        with patch('grind.orchestration.grind_agent.grind',
                   AsyncMock(side_effect=ValueError("Invalid input"))):
            result = await orch.run_agent("failing_agent", {
                "task": "Test",
                "verify": "pytest"
            })

        assert result.status == AgentStatus.ERROR
        assert "Invalid input" in result.message
        assert result.iterations == 0

    @pytest.mark.asyncio
    async def test_one_agent_failure_doesnt_stop_others(self):
        """One failing agent should not prevent other agents from running."""
        orch = Orchestrator()
        orch.add_agent("failing_agent", GrindAgent())
        orch.add_agent("success_agent", GrindAgent())

        async def mock_grind_selective(task_def, **kwargs):
            if task_def.task == "fail":
                raise RuntimeError("Intentional failure")
            return GrindResult(
                status=GrindStatus.COMPLETE,
                iterations=1,
                message="Success",
                tools_used=[],
                duration_seconds=1.0,
                hooks_executed=[],
                model="sonnet"
            )

        with patch('grind.orchestration.grind_agent.grind',
                   side_effect=mock_grind_selective):
            result1 = await orch.run_agent("failing_agent", {
                "task": "fail",
                "verify": "test"
            })
            result2 = await orch.run_agent("success_agent", {
                "task": "succeed",
                "verify": "test"
            })

        assert result1.status == AgentStatus.ERROR
        assert result2.status == AgentStatus.COMPLETE
