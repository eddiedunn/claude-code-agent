"""Tests for grind/batch.py run_batch() function."""

import pytest
from unittest.mock import patch, AsyncMock

from grind.batch import run_batch
from grind.models import TaskDefinition, GrindResult, GrindStatus


@pytest.mark.asyncio
async def test_batch_runs_all_tasks_sequentially():
    """Test that all tasks are run sequentially and tracked correctly."""
    tasks = [
        TaskDefinition(task="Task 1", verify="echo ok"),
        TaskDefinition(task="Task 2", verify="echo ok"),
        TaskDefinition(task="Task 3", verify="echo ok"),
    ]

    mock_result = GrindResult(
        status=GrindStatus.COMPLETE,
        iterations=1,
        message="Done",
        tools_used=[],
        hooks_executed=[],
        duration_seconds=1.0
    )

    with patch('grind.batch.grind', new_callable=AsyncMock) as mock_grind:
        mock_grind.return_value = mock_result
        result = await run_batch(tasks)

    assert mock_grind.call_count == 3
    assert len(result.results) == 3
    assert result.completed == 3
    assert result.stuck == 0
    assert result.failed == 0


@pytest.mark.asyncio
async def test_batch_stops_on_stuck_when_flag_set():
    """Test that batch stops on stuck task when stop_on_stuck is True."""
    tasks = [
        TaskDefinition(task="Task 1", verify="echo ok"),
        TaskDefinition(task="Task 2", verify="echo ok"),
        TaskDefinition(task="Task 3", verify="echo ok"),
    ]

    # First task completes, second task gets stuck
    complete_result = GrindResult(
        status=GrindStatus.COMPLETE,
        iterations=1,
        message="Done",
        tools_used=[],
        hooks_executed=[],
        duration_seconds=1.0
    )
    stuck_result = GrindResult(
        status=GrindStatus.STUCK,
        iterations=5,
        message="Stuck",
        tools_used=[],
        hooks_executed=[],
        duration_seconds=2.0
    )

    with patch('grind.batch.grind', new_callable=AsyncMock) as mock_grind:
        mock_grind.side_effect = [complete_result, stuck_result]
        result = await run_batch(tasks, stop_on_stuck=True)

    # Should only run 2 tasks before stopping
    assert mock_grind.call_count == 2
    assert len(result.results) == 2
    assert result.completed == 1
    assert result.stuck == 1
    assert result.failed == 0


@pytest.mark.asyncio
async def test_batch_continues_on_stuck_when_flag_false():
    """Test that batch continues when stuck and stop_on_stuck is False."""
    tasks = [
        TaskDefinition(task="Task 1", verify="echo ok"),
        TaskDefinition(task="Task 2", verify="echo ok"),
        TaskDefinition(task="Task 3", verify="echo ok"),
    ]

    # Second task gets stuck, but continues to third task
    complete_result = GrindResult(
        status=GrindStatus.COMPLETE,
        iterations=1,
        message="Done",
        tools_used=[],
        hooks_executed=[],
        duration_seconds=1.0
    )
    stuck_result = GrindResult(
        status=GrindStatus.STUCK,
        iterations=5,
        message="Stuck",
        tools_used=[],
        hooks_executed=[],
        duration_seconds=2.0
    )

    with patch('grind.batch.grind', new_callable=AsyncMock) as mock_grind:
        mock_grind.side_effect = [complete_result, stuck_result, complete_result]
        result = await run_batch(tasks, stop_on_stuck=False)

    # Should run all 3 tasks
    assert mock_grind.call_count == 3
    assert len(result.results) == 3
    assert result.completed == 2
    assert result.stuck == 1
    assert result.failed == 0


@pytest.mark.asyncio
async def test_batch_tracks_duration():
    """Test that batch tracks total duration."""
    tasks = [
        TaskDefinition(task="Task 1", verify="echo ok"),
    ]

    mock_result = GrindResult(
        status=GrindStatus.COMPLETE,
        iterations=1,
        message="Done",
        tools_used=[],
        hooks_executed=[],
        duration_seconds=1.0
    )

    with patch('grind.batch.grind', new_callable=AsyncMock) as mock_grind:
        mock_grind.return_value = mock_result
        result = await run_batch(tasks)

    # Duration should be tracked and be greater than 0
    assert result.duration_seconds > 0


@pytest.mark.asyncio
async def test_batch_handles_error_status():
    """Test that batch correctly tracks ERROR status."""
    tasks = [
        TaskDefinition(task="Task 1", verify="echo ok"),
    ]

    error_result = GrindResult(
        status=GrindStatus.ERROR,
        iterations=1,
        message="Error occurred",
        tools_used=[],
        hooks_executed=[],
        duration_seconds=1.0
    )

    with patch('grind.batch.grind', new_callable=AsyncMock) as mock_grind:
        mock_grind.return_value = error_result
        result = await run_batch(tasks)

    assert result.failed == 1
    assert result.completed == 0
    assert result.stuck == 0


@pytest.mark.asyncio
async def test_batch_empty_task_list():
    """Test that batch handles empty task list correctly."""
    tasks = []

    result = await run_batch(tasks)

    # Should return empty results with zero counts
    assert len(result.results) == 0
    assert result.completed == 0
    assert result.stuck == 0
    assert result.failed == 0
    assert result.total == 0
