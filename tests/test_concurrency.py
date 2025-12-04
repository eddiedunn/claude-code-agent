"""Tests for agent executor concurrency."""

import asyncio
from datetime import datetime

import pytest

from grind.models import TaskDefinition
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
async def test_concurrent_agents_do_not_interfere(temp_session, sample_task_def):
    """Test that concurrent agents execute without interference."""
    # Create AgentExecutor with max_parallel=2
    executor = AgentExecutor(temp_session, max_parallel=2)

    # Create 3 task_defs with different verify commands
    task_def1 = TaskDefinition(
        task="Task 1",
        verify="echo 'test1'",
        model="haiku",
        max_iterations=2
    )
    task_def2 = TaskDefinition(
        task="Task 2",
        verify="echo 'test2'",
        model="haiku",
        max_iterations=2
    )
    task_def3 = TaskDefinition(
        task="Task 3",
        verify="echo 'test3'",
        model="haiku",
        max_iterations=2
    )

    # Track execution order to verify parallelism
    execution_times = {}
    original_execute = executor.execute_agent

    async def tracked_execute(agent):
        """Track when agents start executing."""
        execution_times[agent.agent_id] = datetime.now()
        return await original_execute(agent)

    executor.execute_agent = tracked_execute

    # Run execute_batch() with all 3 tasks
    results = await executor.execute_batch([task_def1, task_def2, task_def3])

    # Assert all complete without interference
    assert len(results) == 3
    assert all(agent.status in [AgentStatus.COMPLETE, AgentStatus.FAILED, AgentStatus.STUCK] for agent in results)

    # Verify that agents ran (at least started)
    assert len(execution_times) == 3

    # Check that at least 2 agents ran concurrently (within small time window)
    times = sorted(execution_times.values())
    if len(times) >= 2:
        # First two should start within a reasonable window
        time_diff = (times[1] - times[0]).total_seconds()
        # They should start very close together (both in first batch)
        assert time_diff < 1.0, "First two agents should start nearly simultaneously"


@pytest.mark.asyncio
async def test_semaphore_limits_parallelism(temp_session):
    """Test that semaphore properly limits parallel execution."""
    # Create AgentExecutor with max_parallel=2
    executor = AgentExecutor(temp_session, max_parallel=2)

    # Track concurrent execution count with callback
    current_running = 0
    max_concurrent = 0
    lock = asyncio.Lock()

    original_execute = executor.execute_agent

    async def tracked_execute(agent):
        """Track concurrent execution count."""
        nonlocal current_running, max_concurrent

        async with lock:
            current_running += 1
            max_concurrent = max(max_concurrent, current_running)

        try:
            # Add small delay to ensure overlap
            await asyncio.sleep(0.1)
            return await original_execute(agent)
        finally:
            async with lock:
                current_running -= 1

    executor.execute_agent = tracked_execute

    # Create 4 tasks to test parallelism limit
    task_defs = [
        TaskDefinition(
            task=f"Task {i}",
            verify="echo 'test'",
            model="haiku",
            max_iterations=1
        )
        for i in range(4)
    ]

    # Execute all tasks
    await executor.execute_batch(task_defs)

    # Assert never more than 2 agents running simultaneously
    assert max_concurrent <= 2, f"Expected max 2 concurrent agents, got {max_concurrent}"
    assert max_concurrent >= 1, "At least 1 agent should have run"


@pytest.mark.asyncio
async def test_agent_cancellation_during_execution(temp_session):
    """Test cancelling an agent mid-execution."""
    executor = AgentExecutor(temp_session, max_parallel=1)

    # Create a task that will run long enough to cancel
    task_def = TaskDefinition(
        task="Long running task",
        verify="sleep 10",  # This will fail but take time
        model="haiku",
        max_iterations=5
    )

    # Create agent
    agent = executor.create_agent(task_def)
    executor._task_defs = {agent.agent_id: task_def}

    # Start agent execution in background task
    execution_task = asyncio.create_task(executor.execute_agent(agent))
    executor.active_tasks[agent.agent_id] = execution_task

    # Wait a bit for execution to start
    await asyncio.sleep(0.2)

    # Cancel agent mid-execution using cancel_agent()
    cancelled = await executor.cancel_agent(agent.agent_id)

    # Assert cancellation succeeded
    assert cancelled is True

    # Assert agent status becomes CANCELLED
    assert agent.status == AgentStatus.CANCELLED

    # Assert task cleanup completes (task removed from active_tasks)
    assert agent.agent_id not in executor.active_tasks


@pytest.mark.asyncio
async def test_status_callback_thread_safety(temp_session):
    """Test that status callbacks are called safely without race conditions."""
    executor = AgentExecutor(temp_session, max_parallel=3)

    # Track callback invocations
    callback_counts = {}
    callback_lock = asyncio.Lock()

    async def status_callback(agent):
        """Thread-safe callback that tracks invocations."""
        async with callback_lock:
            if agent.agent_id not in callback_counts:
                callback_counts[agent.agent_id] = []
            callback_counts[agent.agent_id].append(agent.status)

    # Add multiple status callbacks
    executor.add_status_callback(lambda agent: asyncio.create_task(status_callback(agent)))
    executor.add_status_callback(lambda agent: asyncio.create_task(status_callback(agent)))

    # Run concurrent agents
    task_defs = [
        TaskDefinition(
            task=f"Task {i}",
            verify="echo 'test'",
            model="haiku",
            max_iterations=2
        )
        for i in range(3)
    ]

    results = await executor.execute_batch(task_defs)

    # Wait a bit for async callbacks to complete
    await asyncio.sleep(0.5)

    # Assert callbacks called without race conditions
    # Each agent should have callback invocations
    assert len(callback_counts) == 3, f"Expected 3 agents tracked, got {len(callback_counts)}"

    # Each agent should have status changes recorded
    for agent_id, statuses in callback_counts.items():
        assert len(statuses) > 0, f"Agent {agent_id} should have status callbacks"
        # Should include at least RUNNING and a terminal status
        assert any(s == AgentStatus.RUNNING for s in statuses), f"Agent {agent_id} should have RUNNING status"
