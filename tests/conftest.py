"""Pytest configuration and fixtures."""

import pytest
from pathlib import Path


@pytest.fixture
def temp_task_file(tmp_path):
    """Create a temporary task file."""
    task_file = tmp_path / "test_tasks.yaml"
    content = """
tasks:
  - task: "Test task"
    verify: "echo test"
    model: haiku
    max_iterations: 3
"""
    task_file.write_text(content)
    return task_file


@pytest.fixture
def sample_task_definition():
    """Sample task definition for testing."""
    from grind.models import TaskDefinition
    return TaskDefinition(
        task="Fix tests",
        verify="pytest",
        model="sonnet",
        max_iterations=5
    )


@pytest.fixture
def sample_grind_result():
    """Sample grind result for testing."""
    from grind.models import GrindResult, GrindStatus
    return GrindResult(
        status=GrindStatus.COMPLETE,
        iterations=3,
        message="All tests passed",
        tools_used=["Read", "Write", "Bash"],
        duration_seconds=45.2,
        hooks_executed=[],
        model="sonnet"
    )
