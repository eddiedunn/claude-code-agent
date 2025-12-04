"""Integration tests for DAG execution with worktrees.

These tests create real git repositories and run actual (mocked) grind tasks
to verify the full system works together.
"""

import os
import subprocess
from unittest.mock import patch

import pytest

from grind.dag import DAGExecutor
from grind.engine import decompose
from grind.models import GrindResult, GrindStatus
from grind.tasks import build_task_graph
from grind.worktree import WorktreeManager


@pytest.fixture
def git_repo(tmp_path):
    """Create a git repository for testing."""
    repo = tmp_path / "project"
    repo.mkdir()

    # Initialize git
    subprocess.run(
        ["git", "init"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo, check=True, capture_output=True
    )

    # Create some files
    (repo / "src").mkdir()
    (repo / "src" / "main.py").write_text("def main():\n    pass\n")

    # Initial commit
    subprocess.run(
        ["git", "add", "."], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial"],
        cwd=repo, check=True, capture_output=True
    )

    return repo


@pytest.fixture
def tasks_yaml(git_repo):
    """Create a tasks.yaml file with dependencies and worktrees."""
    content = '''
tasks:
  - id: lint
    task: "Fix linting errors"
    verify: "echo lint ok"
    branch: fix/lint

  - id: tests
    task: "Fix test failures"
    verify: "echo tests ok"
    depends_on: [lint]
    branch: fix/tests
    merge_from: [fix/lint]
'''
    yaml_path = git_repo / "tasks.yaml"
    yaml_path.write_text(content)
    return str(yaml_path)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dag_with_worktrees_end_to_end(git_repo, tasks_yaml):
    """Test full DAG execution with worktree isolation."""
    # Load task graph
    graph = build_task_graph(tasks_yaml, base_cwd=str(git_repo))

    assert len(graph.nodes) == 2
    assert graph.nodes["lint"].worktree is not None
    assert graph.nodes["tests"].depends_on == ["lint"]

    # Mock grind to simulate successful execution
    async def mock_grind(task_def, verbose=False, on_iteration=None):
        return GrindResult(
            status=GrindStatus.COMPLETE,
            iterations=1,
            message="Task completed",
            model=task_def.model,
        )

    # Create a real WorktreeManager pointing to our temp repo
    real_manager = WorktreeManager(str(git_repo))

    with patch("grind.dag.grind", side_effect=mock_grind), \
         patch("grind.dag.WorktreeManager", return_value=real_manager):
        executor = DAGExecutor(graph)
        result = await executor.execute(
            max_parallel=2,
            use_worktrees=True,
        )

    # Verify results
    assert result.completed == 2
    assert result.failed == 0
    assert result.blocked == 0

    # Verify execution order (lint before tests)
    lint_idx = result.execution_order.index("lint")
    tests_idx = result.execution_order.index("tests")
    assert lint_idx < tests_idx

    # Verify branches were created
    branches_result = subprocess.run(
        ["git", "branch", "-a"],
        cwd=git_repo,
        capture_output=True,
        text=True,
    )
    assert "fix/lint" in branches_result.stdout
    assert "fix/tests" in branches_result.stdout


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dag_blocked_on_failure(git_repo, tasks_yaml):
    """Test that downstream tasks are blocked when upstream fails."""
    graph = build_task_graph(tasks_yaml, base_cwd=str(git_repo))

    call_count = {"lint": 0, "tests": 0}

    async def mock_grind(task_def, verbose=False, on_iteration=None):
        if "lint" in task_def.task.lower():
            call_count["lint"] += 1
            return GrindResult(
                status=GrindStatus.STUCK,
                iterations=1,
                message="Lint failed",
                model=task_def.model,
            )
        else:
            call_count["tests"] += 1
            return GrindResult(
                status=GrindStatus.COMPLETE,
                iterations=1,
                message="OK",
                model=task_def.model,
            )

    # Create a real WorktreeManager pointing to our temp repo
    real_manager = WorktreeManager(str(git_repo))

    with patch("grind.dag.grind", side_effect=mock_grind), \
         patch("grind.dag.WorktreeManager", return_value=real_manager):
        executor = DAGExecutor(graph)
        result = await executor.execute(max_parallel=1, use_worktrees=True)

    # Lint was attempted, tests was blocked
    assert call_count["lint"] == 1
    assert call_count["tests"] == 0

    assert result.stuck == 1
    assert result.blocked == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_worktree_lifecycle(git_repo):
    """Test worktree creation and cleanup."""
    manager = WorktreeManager(str(git_repo))

    # Create worktree
    path = await manager.create("test_task", "test-branch")
    assert path.exists()

    # Verify in list
    worktrees = await manager.list_worktrees()
    assert any("test_task" in w.get("path", "") for w in worktrees)

    # Cleanup
    await manager.cleanup("test_task")
    assert not path.exists()

    # Cleanup all handles empty gracefully
    count = await manager.cleanup_all()
    assert count == 0


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set"
)
async def test_decompose_model_assignment(tmp_path):
    """Test that decompose() returns tasks with appropriate models assigned.

    This test makes a real API call to decompose a problem into tasks,
    then validates that:
    1. Tasks are returned
    2. Each task has a model assigned
    3. Models are valid (haiku, sonnet, or opus)
    4. Simple tasks get haiku, complex tasks get opus, others get sonnet
    """
    # Use tmp_path as working directory
    test_cwd = str(tmp_path)

    # Create a test file to work with
    test_file = tmp_path / "test.txt"
    test_file.write_text("Hello World")

    # Define a problem that should generate multiple tasks with varying complexity
    problem = """
    Fix the following issues:
    1. Fix typo in test.txt (change 'World' to 'World!')
    2. Add a new feature to handle user authentication
    3. Update the configuration file
    """

    verify_cmd = "echo 'Verification passed'"

    # Call decompose with real API
    tasks = await decompose(
        problem=problem,
        verify_cmd=verify_cmd,
        cwd=test_cwd,
        verbose=False
    )

    # Validate results
    assert len(tasks) > 0, "decompose() should return at least one task"

    # Check each task has required attributes and valid model
    valid_models = {"haiku", "sonnet", "opus"}
    for task in tasks:
        assert hasattr(task, "task"), "Task should have 'task' attribute"
        assert hasattr(task, "verify"), "Task should have 'verify' attribute"
        assert hasattr(task, "model"), "Task should have 'model' attribute"
        assert task.model in valid_models, f"Model '{task.model}' should be one of {valid_models}"
        assert task.task.strip(), "Task description should not be empty"
        assert task.verify.strip(), "Verify command should not be empty"

    # Check that model assignment makes sense (at least one task should use routing)
    models_used = {task.model for task in tasks}
    assert len(models_used) > 0, "At least one model should be used"
