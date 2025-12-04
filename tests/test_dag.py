"""Tests for DAGExecutor."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from grind.dag import DAGExecutor
from grind.models import (
    GrindResult,
    GrindStatus,
    TaskDefinition,
    TaskGraph,
    TaskNode,
)


def make_node(node_id: str, depends_on: list[str] | None = None) -> TaskNode:
    """Create a TaskNode for testing."""
    return TaskNode(
        id=node_id,
        task_def=TaskDefinition(task=f"Task {node_id}", verify=f"echo {node_id}"),
        depends_on=depends_on or [],
    )


def make_graph(*nodes: TaskNode) -> TaskGraph:
    """Create a TaskGraph from nodes."""
    return TaskGraph(nodes={n.id: n for n in nodes})


def make_result(status: GrindStatus = GrindStatus.COMPLETE) -> GrindResult:
    """Create a GrindResult for testing."""
    return GrindResult(
        status=status,
        iterations=1,
        message="Test result",
        model="sonnet",
    )


class TestDAGExecutor:
    @pytest.mark.asyncio
    async def test_linear_chain(self):
        """Linear chain A -> B -> C executes in order."""
        graph = make_graph(
            make_node("A"),
            make_node("B", depends_on=["A"]),
            make_node("C", depends_on=["B"]),
        )

        with patch("grind.dag.grind", new_callable=AsyncMock) as mock_grind:
            mock_grind.return_value = make_result()

            executor = DAGExecutor(graph)
            result = await executor.execute()

        assert result.completed == 3
        assert result.failed == 0
        assert result.blocked == 0
        assert result.execution_order == ["A", "B", "C"]

    @pytest.mark.asyncio
    async def test_parallel_ready(self):
        """Tasks B and C both ready after A completes."""
        graph = make_graph(
            make_node("A"),
            make_node("B", depends_on=["A"]),
            make_node("C", depends_on=["A"]),
        )

        with patch("grind.dag.grind", new_callable=AsyncMock) as mock_grind:
            mock_grind.return_value = make_result()

            executor = DAGExecutor(graph)
            result = await executor.execute()

        assert result.completed == 3
        assert result.execution_order[0] == "A"

    @pytest.mark.asyncio
    async def test_blocked_on_failure(self):
        """Downstream tasks blocked when upstream fails."""
        graph = make_graph(
            make_node("A"),
            make_node("B", depends_on=["A"]),
            make_node("C", depends_on=["B"]),
        )

        with patch("grind.dag.grind", new_callable=AsyncMock) as mock_grind:
            mock_grind.return_value = make_result(GrindStatus.STUCK)

            executor = DAGExecutor(graph)
            result = await executor.execute()

        # A stuck, B and C blocked
        assert result.stuck == 1
        assert result.blocked == 2
        assert result.completed == 0
        assert "Blocked" in result.results["B"].message
        assert "Blocked" in result.results["C"].message

    @pytest.mark.asyncio
    async def test_partial_failure_diamond(self):
        """In diamond pattern, failure of B blocks D but not C."""
        # A -> B -> D
        # A -> C -> D
        graph = make_graph(
            make_node("A"),
            make_node("B", depends_on=["A"]),
            make_node("C", depends_on=["A"]),
            make_node("D", depends_on=["B", "C"]),
        )

        call_order = []

        async def mock_grind(task_def, **kwargs):
            task_id = task_def.task.split()[-1]  # "Task X" -> "X"
            call_order.append(task_id)
            if task_id == "B":
                return make_result(GrindStatus.STUCK)
            return make_result()

        with patch("grind.dag.grind", side_effect=mock_grind):
            executor = DAGExecutor(graph)
            result = await executor.execute()

        # A and C completed, B stuck, D blocked
        assert result.completed == 2
        assert result.stuck == 1
        assert result.blocked == 1
        assert "A" in call_order
        assert "B" in call_order
        assert "C" in call_order
        assert "D" not in call_order  # Never called, was blocked

    @pytest.mark.asyncio
    async def test_callbacks(self):
        """Callbacks are called for each task."""
        graph = make_graph(
            make_node("A"),
            make_node("B", depends_on=["A"]),
        )

        starts = []
        completes = []

        with patch("grind.dag.grind", new_callable=AsyncMock) as mock_grind:
            mock_grind.return_value = make_result()

            executor = DAGExecutor(graph)
            await executor.execute(
                on_task_start=lambda n: starts.append(n.id),
                on_task_complete=lambda n, r: completes.append(n.id),
            )

        assert starts == ["A", "B"]
        assert completes == ["A", "B"]

    @pytest.mark.asyncio
    async def test_empty_graph(self):
        """Empty graph returns zero counts."""
        graph = TaskGraph(nodes={})

        executor = DAGExecutor(graph)
        result = await executor.execute()

        assert result.total == 0
        assert result.completed == 0
        assert result.failed == 0
        assert result.blocked == 0


class TestDAGExecutorParallel:
    @pytest.mark.asyncio
    async def test_parallel_independent_tasks(self):
        """Independent tasks can run in parallel."""
        graph = make_graph(
            make_node("A"),
            make_node("B"),
            make_node("C"),
        )

        call_times = {}

        async def mock_grind(task_def, **kwargs):
            task_id = task_def.task.split()[-1]
            call_times[task_id] = asyncio.get_event_loop().time()
            await asyncio.sleep(0.05)  # Simulate work
            return make_result()

        with patch("grind.dag.grind", side_effect=mock_grind):
            executor = DAGExecutor(graph)
            result = await executor.execute(max_parallel=3)

        assert result.completed == 3
        # All should start at roughly the same time (within 0.02s)
        times = list(call_times.values())
        assert max(times) - min(times) < 0.02

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrency(self):
        """Semaphore limits concurrent tasks."""
        graph = make_graph(
            make_node("A"),
            make_node("B"),
            make_node("C"),
            make_node("D"),
        )

        max_concurrent = 0
        current_concurrent = 0
        lock = asyncio.Lock()

        async def mock_grind(task_def, **kwargs):
            nonlocal max_concurrent, current_concurrent
            async with lock:
                current_concurrent += 1
                max_concurrent = max(max_concurrent, current_concurrent)
            await asyncio.sleep(0.05)
            async with lock:
                current_concurrent -= 1
            return make_result()

        with patch("grind.dag.grind", side_effect=mock_grind):
            executor = DAGExecutor(graph)
            await executor.execute(max_parallel=2)

        assert max_concurrent <= 2

    @pytest.mark.asyncio
    async def test_parallel_respects_dependencies(self):
        """Parallel execution still respects dependencies."""
        # A -> C, B -> C (C depends on both A and B)
        graph = make_graph(
            make_node("A"),
            make_node("B"),
            make_node("C", depends_on=["A", "B"]),
        )

        call_order = []

        async def mock_grind(task_def, **kwargs):
            task_id = task_def.task.split()[-1]
            call_order.append(task_id)
            await asyncio.sleep(0.01)
            return make_result()

        with patch("grind.dag.grind", side_effect=mock_grind):
            executor = DAGExecutor(graph)
            await executor.execute(max_parallel=3)

        # C must come after both A and B
        c_idx = call_order.index("C")
        a_idx = call_order.index("A")
        b_idx = call_order.index("B")
        assert c_idx > a_idx
        assert c_idx > b_idx
