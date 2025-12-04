"""Tests for DAG orchestration logic."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from grind.models import TaskDefinition, TaskGraph, TaskNode
from grind.tui.core.agent_executor import AgentExecutor
from grind.tui.core.models import AgentStatus
from grind.tui.core.session import AgentSession


@pytest.fixture
def temp_session():
    """Create a temporary AgentSession for testing."""
    session = AgentSession()
    yield session
    session.cleanup()


@pytest.mark.asyncio
async def test_dag_execution_order_topological_sort(dag_graph_linear):
    """Test that DAG execution order is topologically sorted."""
    # dag_graph_linear is A -> B -> C
    order = dag_graph_linear.get_execution_order()
    assert order == ["A", "B", "C"]


@pytest.mark.asyncio
async def test_dag_parallel_execution_respects_semaphore(dag_graph_diamond, temp_session):
    """Test that DAG parallel execution respects the semaphore limit."""
    # dag_graph_diamond is: A -> B,C -> D
    # B and C should run in parallel after A completes
    # D should wait for both B and C

    concurrent_tasks = []
    max_concurrent = 0
    current_concurrent = 0
    lock = asyncio.Lock()
    execution_log = []

    async def mock_grind(task_def, **kwargs):
        nonlocal max_concurrent, current_concurrent
        task_id = task_def.task  # Task description is just the node ID

        async with lock:
            current_concurrent += 1
            max_concurrent = max(max_concurrent, current_concurrent)
            execution_log.append(("start", task_id))

        await asyncio.sleep(0.05)  # Simulate work

        async with lock:
            current_concurrent -= 1
            execution_log.append(("end", task_id))

        from grind.models import GrindResult, GrindStatus
        return GrindResult(status=GrindStatus.COMPLETE, iterations=1, model="sonnet")

    with patch("grind.orchestration.grind_agent.grind", side_effect=mock_grind):
        executor = AgentExecutor(temp_session, max_parallel=2)
        results = await executor.execute_dag(dag_graph_diamond)

    # Check max concurrency is respected
    assert max_concurrent <= 2

    # Check B and C run after A
    a_end_idx = next(i for i, (action, task) in enumerate(execution_log) if action == "end" and task == "A")
    b_start_idx = next(i for i, (action, task) in enumerate(execution_log) if action == "start" and task == "B")
    c_start_idx = next(i for i, (action, task) in enumerate(execution_log) if action == "start" and task == "C")
    assert b_start_idx > a_end_idx
    assert c_start_idx > a_end_idx

    # Check D starts after both B and C end
    b_end_idx = next(i for i, (action, task) in enumerate(execution_log) if action == "end" and task == "B")
    c_end_idx = next(i for i, (action, task) in enumerate(execution_log) if action == "end" and task == "C")
    d_start_idx = next(i for i, (action, task) in enumerate(execution_log) if action == "start" and task == "D")
    assert d_start_idx > b_end_idx
    assert d_start_idx > c_end_idx


@pytest.mark.asyncio
async def test_dag_dependency_wait_blocks_until_complete(temp_session):
    """Test that dependent tasks wait until dependencies complete."""
    # Create graph where B depends on A
    graph = TaskGraph()
    graph.nodes["A"] = TaskNode(id="A", task_def=TaskDefinition(task="A", verify="echo A"))
    graph.nodes["B"] = TaskNode(id="B", task_def=TaskDefinition(task="B", verify="echo B"), depends_on=["A"])

    a_started = asyncio.Event()
    a_completed = asyncio.Event()
    b_started = asyncio.Event()
    b_started_before_a_complete = False

    async def mock_grind(task_def, **kwargs):
        nonlocal b_started_before_a_complete
        task_id = task_def.task

        if task_id == "A":
            a_started.set()
            await asyncio.sleep(0.1)  # Simulate work
            a_completed.set()
        elif task_id == "B":
            b_started.set()
            # Check if B started before A completed
            b_started_before_a_complete = not a_completed.is_set()

        from grind.models import GrindResult, GrindStatus
        return GrindResult(status=GrindStatus.COMPLETE, iterations=1, model="sonnet")

    with patch("grind.orchestration.grind_agent.grind", side_effect=mock_grind):
        executor = AgentExecutor(temp_session, max_parallel=2)
        await executor.execute_dag(graph)

    # Assert B doesn't start until A completes
    assert not b_started_before_a_complete


@pytest.mark.asyncio
async def test_dag_failed_dependency_blocks_dependent(temp_session):
    """Test that failed dependencies block dependent tasks."""
    # Create graph: A -> B
    graph = TaskGraph()
    graph.nodes["A"] = TaskNode(id="A", task_def=TaskDefinition(task="A", verify="echo A"))
    graph.nodes["B"] = TaskNode(id="B", task_def=TaskDefinition(task="B", verify="echo B"), depends_on=["A"])

    b_executed = False

    async def mock_grind(task_def, **kwargs):
        nonlocal b_executed
        task_id = task_def.task

        if task_id == "A":
            # A fails
            from grind.models import GrindResult, GrindStatus
            return GrindResult(status=GrindStatus.STUCK, iterations=1, model="sonnet", message="A failed")
        elif task_id == "B":
            b_executed = True
            from grind.models import GrindResult, GrindStatus
            return GrindResult(status=GrindStatus.COMPLETE, iterations=1, model="sonnet")

    with patch("grind.orchestration.grind_agent.grind", side_effect=mock_grind):
        executor = AgentExecutor(temp_session, max_parallel=2)
        results = await executor.execute_dag(graph)

    # B should not have executed
    assert not b_executed
    # B should be blocked (not in results since it was blocked)
    # Results contains only agents that were actually created and executed
    assert "A" in results
    assert results["A"].status in (AgentStatus.STUCK, AgentStatus.FAILED)


@pytest.mark.asyncio
async def test_dag_diamond_dependency_pattern(dag_graph_diamond, temp_session):
    """Test complete diamond dependency pattern execution."""
    # dag_graph_diamond is: A -> B,C -> D
    execution_order = []

    async def mock_grind(task_def, **kwargs):
        task_id = task_def.task
        execution_order.append(task_id)
        await asyncio.sleep(0.01)  # Small delay

        from grind.models import GrindResult, GrindStatus
        return GrindResult(status=GrindStatus.COMPLETE, iterations=1, model="sonnet")

    with patch("grind.orchestration.grind_agent.grind", side_effect=mock_grind):
        executor = AgentExecutor(temp_session, max_parallel=2)
        results = await executor.execute_dag(dag_graph_diamond)

    # All tasks completed
    assert len(results) == 4
    for agent_info in results.values():
        assert agent_info.status == AgentStatus.COMPLETE

    # Check correct order: A must be first, D must be last
    assert execution_order[0] == "A"
    assert execution_order[-1] == "D"

    # B and C must both come before D
    assert "B" in execution_order[:3]
    assert "C" in execution_order[:3]


@pytest.mark.asyncio
async def test_dag_cycle_detection_validation():
    """Test that cycle detection validation works."""
    # Create graph with cycle: A -> B -> C -> A
    graph = TaskGraph()
    graph.nodes["A"] = TaskNode(id="A", task_def=TaskDefinition(task="A", verify="echo A"), depends_on=["C"])
    graph.nodes["B"] = TaskNode(id="B", task_def=TaskDefinition(task="B", verify="echo B"), depends_on=["A"])
    graph.nodes["C"] = TaskNode(id="C", task_def=TaskDefinition(task="C", verify="echo C"), depends_on=["B"])

    errors = graph.validate()

    # Should have error about cycle
    assert len(errors) > 0
    assert any("cycle" in error.lower() for error in errors)
