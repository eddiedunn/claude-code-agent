"""Tests for cleanup and resource management."""

import asyncio
import pytest
from pathlib import Path

from grind.models import TaskDefinition
from grind.tui.core.session import AgentSession
from grind.tui.core.agent_executor import AgentExecutor


@pytest.fixture
def temp_session():
    """Create a temporary AgentSession for testing."""
    session = AgentSession()
    yield session
    # Cleanup in case test didn't
    if not session._cleanup_done:
        session.cleanup()


@pytest.fixture
def sample_task_def():
    """Sample TaskDefinition for testing."""
    return TaskDefinition(
        task="Test task",
        verify="echo test",
        max_iterations=5,
        model="sonnet"
    )


def test_session_cleanup_deletes_temp_files(temp_session):
    """Test that session cleanup deletes temporary files."""
    # Create AgentSession
    session = temp_session

    # Store session_dir path
    session_dir = session.session_dir

    # Assert session_dir exists
    assert session_dir.exists()
    assert session_dir.is_dir()

    # Call session.cleanup()
    session.cleanup()

    # Assert session_dir no longer exists
    assert not session_dir.exists()


def test_session_cleanup_idempotent(temp_session):
    """Test that cleanup can be called multiple times without error."""
    session = temp_session

    # Call cleanup() twice
    session.cleanup()
    session.cleanup()

    # Assert no error on second call
    # Assert _cleanup_done flag works
    assert session._cleanup_done is True


def test_session_context_manager():
    """Test that AgentSession context manager cleans up properly."""
    # Use AgentSession in 'with' statement
    with AgentSession() as session:
        # Store session_dir inside context
        session_dir = session.session_dir
        assert session_dir.exists()

    # After context exits, assert session_dir deleted
    assert not session_dir.exists()


@pytest.mark.asyncio
async def test_agent_executor_cleanup_cancels_all_tasks(temp_session, sample_task_def):
    """Test that executor cleanup cancels all active tasks."""
    # Create AgentExecutor
    executor = AgentExecutor(temp_session, max_parallel=3)

    # Create multiple agents but don't await them (simulate running agents)
    agent1 = executor.create_agent(sample_task_def)
    agent2 = executor.create_agent(sample_task_def)

    # Add tasks to active_tasks (simulate running agents)
    task1 = asyncio.create_task(asyncio.sleep(10))
    task2 = asyncio.create_task(asyncio.sleep(10))
    executor.active_tasks[agent1.agent_id] = task1
    executor.active_tasks[agent2.agent_id] = task2

    # Verify tasks are active
    assert len(executor.active_tasks) == 2
    assert not task1.done()
    assert not task2.done()

    # Call executor.cleanup()
    await executor.cleanup()

    # Assert all active_tasks cancelled
    assert task1.cancelled() or task1.done()
    assert task2.cancelled() or task2.done()

    # Assert active_tasks dict cleared
    assert len(executor.active_tasks) == 0


@pytest.mark.asyncio
async def test_agent_executor_cleanup_clears_paused_agents(temp_session, sample_task_def):
    """Test that cleanup clears paused agents."""
    # Create AgentExecutor
    executor = AgentExecutor(temp_session, max_parallel=3)

    # Create agents
    agent1 = executor.create_agent(sample_task_def)
    agent2 = executor.create_agent(sample_task_def)

    # Manually add to paused agents (simulate paused state)
    executor._paused_agents[agent1.agent_id] = asyncio.Event()
    executor._paused_agents[agent2.agent_id] = asyncio.Event()

    # Verify paused agents exist
    assert len(executor._paused_agents) == 2

    # Call cleanup()
    await executor.cleanup()

    # Assert _paused_agents dict cleared
    assert len(executor._paused_agents) == 0


@pytest.mark.asyncio
async def test_cleanup_during_active_agent_execution(temp_session, sample_task_def):
    """Test cleanup while agent is running."""
    # Create AgentExecutor
    executor = AgentExecutor(temp_session, max_parallel=3)

    # Create a long-running task
    async def long_running_task():
        await asyncio.sleep(10)

    # Create agent and add a long-running task
    agent = executor.create_agent(sample_task_def)
    task = asyncio.create_task(long_running_task())
    executor.active_tasks[agent.agent_id] = task

    # Verify task is running
    assert not task.done()
    assert len(executor.active_tasks) == 1

    # Call cleanup while agent running
    await executor.cleanup()

    # Assert agent gets cancelled
    assert task.cancelled() or task.done()

    # Assert cleanup completes successfully
    assert len(executor.active_tasks) == 0


@pytest.mark.asyncio
async def test_agent_executor_task_storage(temp_session):
    """Test that AgentExecutor stores and retrieves TaskDefinitions correctly."""
    # Create AgentExecutor
    executor = AgentExecutor(temp_session, max_parallel=3)

    # Test 1: _task_definitions is initialized
    assert hasattr(executor, '_task_definitions')
    assert isinstance(executor._task_definitions, dict)
    assert len(executor._task_definitions) == 0

    # Test 2: create_agent stores TaskDefinition
    task_def1 = TaskDefinition(
        task="First task",
        verify="echo verify1",
        max_iterations=5,
        model="haiku"
    )
    agent1 = executor.create_agent(task_def1)

    assert agent1.agent_id in executor._task_definitions
    assert executor._task_definitions[agent1.agent_id] == task_def1

    # Test 3: _get_task_def_for_agent retrieves correctly
    retrieved1 = executor._get_task_def_for_agent(agent1)
    assert retrieved1 == task_def1
    assert retrieved1.task == "First task"
    assert retrieved1.verify == "echo verify1"
    assert retrieved1.max_iterations == 5
    assert retrieved1.model == "haiku"

    # Test 4: Multiple agents
    task_def2 = TaskDefinition(task="Second task", verify="echo 2", max_iterations=3, model="sonnet")
    task_def3 = TaskDefinition(task="Third task", verify="echo 3", max_iterations=7, model="opus")

    agent2 = executor.create_agent(task_def2)
    agent3 = executor.create_agent(task_def3)

    assert len(executor._task_definitions) == 3
    assert executor._get_task_def_for_agent(agent2) == task_def2
    assert executor._get_task_def_for_agent(agent3) == task_def3

    # Test 5: KeyError for non-existent agent
    from grind.tui.core.models import AgentInfo, AgentStatus, AgentType
    from datetime import datetime

    fake_agent = AgentInfo(
        agent_id="nonexistent-id",
        task_id="fake-task",
        task_description="fake",
        agent_type=AgentType.WORKER,
        status=AgentStatus.PENDING,
        model="haiku",
        iteration=0,
        max_iterations=5,
        progress=0.0,
        created_at=datetime.now(),
    )

    with pytest.raises(KeyError, match="No task definition found for agent nonexistent-id"):
        executor._get_task_def_for_agent(fake_agent)

    # Test 6: Cleanup clears task_definitions
    await executor.cleanup()
    assert len(executor._task_definitions) == 0
