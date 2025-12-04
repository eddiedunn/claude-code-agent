import argparse
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from grind.cli import main_async
from grind.models import BatchResult, GrindResult, GrindStatus, TaskDefinition


def run_grind(*args) -> subprocess.CompletedProcess:
    """Run grind CLI and return result."""
    return subprocess.run(
        ["uv", "run", "grind"] + list(args),
        capture_output=True,
        text=True,
    )


@pytest.mark.asyncio
async def test_run_command_returns_zero_on_success():
    """Test that run command returns 0 on successful completion."""
    args = argparse.Namespace(
        command="run",
        task="Test task",
        verify="echo ok",
        model="sonnet",
        max_iter=10,
        verbose=False,
        interactive=False,
        cwd=".",
        quiet=False,
    )

    with patch('grind.cli.grind', new_callable=AsyncMock) as mock_grind:
        mock_grind.return_value = GrindResult(
            status=GrindStatus.COMPLETE,
            iterations=1,
            message="Success"
        )
        exit_code = await main_async(args)

    assert exit_code == 0


@pytest.mark.asyncio
async def test_run_command_returns_two_on_stuck():
    """Test that run command returns 2 when stuck."""
    args = argparse.Namespace(
        command="run",
        task="Test task",
        verify="echo ok",
        model="sonnet",
        max_iter=10,
        verbose=False,
        interactive=False,
        cwd=".",
        quiet=False,
    )

    with patch('grind.cli.grind', new_callable=AsyncMock) as mock_grind:
        mock_grind.return_value = GrindResult(
            status=GrindStatus.STUCK,
            iterations=5,
            message="Stuck"
        )
        exit_code = await main_async(args)

    assert exit_code == 2


@pytest.mark.asyncio
async def test_run_command_returns_one_on_error():
    """Test that run command returns 1 on error."""
    args = argparse.Namespace(
        command="run",
        task="Test task",
        verify="echo ok",
        model="sonnet",
        max_iter=10,
        verbose=False,
        interactive=False,
        cwd=".",
        quiet=False,
    )

    with patch('grind.cli.grind', new_callable=AsyncMock) as mock_grind:
        mock_grind.return_value = GrindResult(
            status=GrindStatus.ERROR,
            iterations=1,
            message="Error occurred"
        )
        exit_code = await main_async(args)

    assert exit_code == 1


@pytest.mark.asyncio
async def test_run_command_returns_one_on_max_iterations():
    """Test that run command returns 1 when max iterations reached."""
    args = argparse.Namespace(
        command="run",
        task="Test task",
        verify="echo ok",
        model="sonnet",
        max_iter=10,
        verbose=False,
        interactive=False,
        cwd=".",
        quiet=False,
    )

    with patch('grind.cli.grind', new_callable=AsyncMock) as mock_grind:
        mock_grind.return_value = GrindResult(
            status=GrindStatus.MAX_ITERATIONS,
            iterations=10,
            message="Max iterations reached"
        )
        exit_code = await main_async(args)

    assert exit_code == 1


@pytest.mark.asyncio
async def test_batch_command_loads_tasks_from_file():
    """Test that batch command loads tasks from YAML file."""
    # Create a temporary YAML file with tasks
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml_content = {
            "tasks": [
                {"task": "Task 1", "verify": "echo test1"},
                {"task": "Task 2", "verify": "echo test2"}
            ]
        }
        yaml.dump(yaml_content, f)
        temp_file = f.name

    try:
        args = argparse.Namespace(
            command="batch",
            file=temp_file,
            cwd=None,
            verbose=False,
            interactive=False,
            stop_on_stuck=False,
        )

        with patch('grind.cli.load_tasks') as mock_load_tasks, \
             patch('grind.cli.run_batch', new_callable=AsyncMock) as mock_run_batch:

            # Mock load_tasks to return some task definitions
            mock_load_tasks.return_value = [
                TaskDefinition(task="Task 1", verify="echo test1"),
                TaskDefinition(task="Task 2", verify="echo test2"),
            ]

            # Mock run_batch to return a successful result
            mock_run_batch.return_value = BatchResult(
                total=2,
                completed=2,
                stuck=0,
                max_iterations=0,
                failed=0,
                results=[],
                duration_seconds=1.5
            )

            await main_async(args)

            # Verify load_tasks was called with the correct file path
            mock_load_tasks.assert_called_once_with(temp_file, None)
    finally:
        # Clean up the temporary file
        Path(temp_file).unlink()


@pytest.mark.asyncio
async def test_batch_command_returns_zero_on_all_complete():
    """Test batch command returns 0 when all tasks complete."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write("tasks:\n  - task: Test\n    verify: echo ok\n")
        temp_file = f.name

    try:
        args = argparse.Namespace(
            command="batch",
            file=temp_file,
            cwd=None,
            verbose=False,
            interactive=False,
            stop_on_stuck=False,
        )

        with patch('grind.cli.load_tasks') as mock_load_tasks, \
             patch('grind.cli.run_batch', new_callable=AsyncMock) as mock_run_batch:
            mock_load_tasks.return_value = [TaskDefinition(task="T1", verify="echo ok")]
            mock_run_batch.return_value = BatchResult(
                total=1, completed=1, stuck=0, max_iterations=0, failed=0, results=[], duration_seconds=1.0
            )

            exit_code = await main_async(args)
            assert exit_code == 0
    finally:
        Path(temp_file).unlink()


@pytest.mark.asyncio
async def test_batch_command_returns_two_on_stuck():
    """Test batch command returns 2 when tasks get stuck."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write("tasks:\n  - task: Test\n    verify: echo ok\n")
        temp_file = f.name

    try:
        args = argparse.Namespace(
            command="batch",
            file=temp_file,
            cwd=None,
            verbose=False,
            interactive=False,
            stop_on_stuck=False,
        )

        with patch('grind.cli.load_tasks') as mock_load_tasks, \
             patch('grind.cli.run_batch', new_callable=AsyncMock) as mock_run_batch:
            mock_load_tasks.return_value = [TaskDefinition(task="T1", verify="echo ok")]
            mock_run_batch.return_value = BatchResult(
                total=1, completed=0, stuck=1, max_iterations=0, failed=0, results=[], duration_seconds=1.0
            )

            exit_code = await main_async(args)
            assert exit_code == 2
    finally:
        Path(temp_file).unlink()


@pytest.mark.asyncio
async def test_batch_command_returns_three_on_max_iterations():
    """Test batch command returns 3 when tasks hit max iterations."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write("tasks:\n  - task: Test\n    verify: echo ok\n")
        temp_file = f.name

    try:
        args = argparse.Namespace(
            command="batch",
            file=temp_file,
            cwd=None,
            verbose=False,
            interactive=False,
            stop_on_stuck=False,
        )

        with patch('grind.cli.load_tasks') as mock_load_tasks, \
             patch('grind.cli.run_batch', new_callable=AsyncMock) as mock_run_batch:
            mock_load_tasks.return_value = [TaskDefinition(task="T1", verify="echo ok")]
            mock_run_batch.return_value = BatchResult(
                total=1, completed=0, stuck=0, max_iterations=1, failed=0, results=[], duration_seconds=1.0
            )

            exit_code = await main_async(args)
            assert exit_code == 3
    finally:
        Path(temp_file).unlink()


@pytest.mark.asyncio
async def test_batch_command_returns_one_on_error():
    """Test batch command returns 1 when tasks fail with errors."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write("tasks:\n  - task: Test\n    verify: echo ok\n")
        temp_file = f.name

    try:
        args = argparse.Namespace(
            command="batch",
            file=temp_file,
            cwd=None,
            verbose=False,
            interactive=False,
            stop_on_stuck=False,
        )

        with patch('grind.cli.load_tasks') as mock_load_tasks, \
             patch('grind.cli.run_batch', new_callable=AsyncMock) as mock_run_batch:
            mock_load_tasks.return_value = [TaskDefinition(task="T1", verify="echo ok")]
            mock_run_batch.return_value = BatchResult(
                total=1, completed=0, stuck=0, max_iterations=0, failed=1, results=[], duration_seconds=1.0
            )

            exit_code = await main_async(args)
            assert exit_code == 1
    finally:
        Path(temp_file).unlink()


@pytest.mark.asyncio
async def test_decompose_command_writes_output_file():
    """Test that decompose command writes tasks to output file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "output.yaml"

        args = argparse.Namespace(
            command="decompose",
            problem="Fix the broken tests",
            verify="pytest",
            output=str(output_file),
            cwd=".",
            verbose=False,
        )

        with patch('grind.cli.decompose', new_callable=AsyncMock) as mock_decompose:
            # Mock decompose to return list of TaskDefinitions
            mock_decompose.return_value = [
                TaskDefinition(
                    task="Fix test 1", verify="pytest test1.py",
                    max_iterations=5, model="sonnet"
                ),
                TaskDefinition(
                    task="Fix test 2", verify="pytest test2.py",
                    max_iterations=5, model="sonnet"
                ),
            ]

            exit_code = await main_async(args)

            # Verify the output file was written
            assert output_file.exists()

            # Verify the content is valid YAML with expected structure
            with open(output_file) as f:
                content = yaml.safe_load(f)
                assert "tasks" in content
                assert len(content["tasks"]) == 2
                assert content["tasks"][0]["task"] == "Fix test 1"
                assert content["tasks"][0]["verify"] == "pytest test1.py"
                assert content["tasks"][1]["task"] == "Fix test 2"

            # Verify exit code is 0
            assert exit_code == 0


class TestDagCommand:
    def test_dag_help(self):
        """dag --help shows usage information."""
        result = run_grind("dag", "--help")

        assert result.returncode == 0
        assert "dependency" in result.stdout.lower() or "dag" in result.stdout.lower()
        assert "--dry-run" in result.stdout

    def test_dag_dry_run(self, tmp_path):
        """dag --dry-run shows execution plan without running."""
        yaml_content = """
tasks:
  - id: first
    task: "First task"
    verify: "echo 1"
  - id: second
    task: "Second task"
    verify: "echo 2"
    depends_on: [first]
"""
        tasks_file = tmp_path / "tasks.yaml"
        tasks_file.write_text(yaml_content)

        result = run_grind("dag", str(tasks_file), "--dry-run")

        assert result.returncode == 0
        assert "first" in result.stdout
        assert "second" in result.stdout
        assert "after: first" in result.stdout

    def test_dag_invalid_cycle(self, tmp_path):
        """dag with cycle returns error exit code."""
        yaml_content = """
tasks:
  - id: a
    task: "A"
    verify: "echo a"
    depends_on: [b]
  - id: b
    task: "B"
    verify: "echo b"
    depends_on: [a]
"""
        tasks_file = tmp_path / "tasks.yaml"
        tasks_file.write_text(yaml_content)

        result = run_grind("dag", str(tasks_file))

        assert result.returncode == 2  # Invalid graph exit code
        assert "cycle" in result.stdout.lower() or "cycle" in result.stderr.lower()

    def test_dag_missing_file(self):
        """dag with nonexistent file returns error."""
        result = run_grind("dag", "nonexistent.yaml")

        assert result.returncode != 0

    @pytest.mark.asyncio
    async def test_dag_returns_zero_on_all_complete(self, tmp_path):
        """Test DAG command returns 0 when all tasks complete."""
        yaml_content = """
tasks:
  - id: task1
    task: "Task 1"
    verify: "echo ok"
"""
        tasks_file = tmp_path / "tasks.yaml"
        tasks_file.write_text(yaml_content)

        args = argparse.Namespace(
            command="dag",
            tasks_file=str(tasks_file),
            verbose=False,
            dry_run=False,
            parallel=1,
            worktrees=False,
            cleanup_worktrees=False,
        )

        from grind.models import DAGResult, GrindResult, GrindStatus

        with patch('grind.tasks.build_task_graph') as mock_build, \
             patch('grind.dag.DAGExecutor') as mock_executor_class:

            mock_graph = MagicMock()
            mock_build.return_value = mock_graph

            mock_executor = MagicMock()
            mock_executor_class.return_value = mock_executor

            mock_executor.execute = AsyncMock(return_value=DAGResult(
                total=1, completed=1, stuck=0, max_iterations=0, failed=0, blocked=0,
                execution_order=["task1"], duration_seconds=1.0
            ))

            exit_code = await main_async(args)
            assert exit_code == 0

    @pytest.mark.asyncio
    async def test_dag_returns_two_on_stuck(self, tmp_path):
        """Test DAG command returns 2 when tasks get stuck."""
        yaml_content = """
tasks:
  - id: task1
    task: "Task 1"
    verify: "echo ok"
"""
        tasks_file = tmp_path / "tasks.yaml"
        tasks_file.write_text(yaml_content)

        args = argparse.Namespace(
            command="dag",
            tasks_file=str(tasks_file),
            verbose=False,
            dry_run=False,
            parallel=1,
            worktrees=False,
            cleanup_worktrees=False,
        )

        from grind.models import DAGResult, GrindResult, GrindStatus

        with patch('grind.tasks.build_task_graph') as mock_build, \
             patch('grind.dag.DAGExecutor') as mock_executor_class:

            mock_graph = MagicMock()
            mock_build.return_value = mock_graph

            mock_executor = MagicMock()
            mock_executor_class.return_value = mock_executor

            mock_executor.execute = AsyncMock(return_value=DAGResult(
                total=1, completed=0, stuck=1, max_iterations=0, failed=0, blocked=0,
                execution_order=["task1"], duration_seconds=1.0
            ))

            exit_code = await main_async(args)
            assert exit_code == 2

    @pytest.mark.asyncio
    async def test_dag_returns_three_on_max_iterations(self, tmp_path):
        """Test DAG command returns 3 when tasks hit max iterations."""
        yaml_content = """
tasks:
  - id: task1
    task: "Task 1"
    verify: "echo ok"
"""
        tasks_file = tmp_path / "tasks.yaml"
        tasks_file.write_text(yaml_content)

        args = argparse.Namespace(
            command="dag",
            tasks_file=str(tasks_file),
            verbose=False,
            dry_run=False,
            parallel=1,
            worktrees=False,
            cleanup_worktrees=False,
        )

        from grind.models import DAGResult, GrindResult, GrindStatus

        with patch('grind.tasks.build_task_graph') as mock_build, \
             patch('grind.dag.DAGExecutor') as mock_executor_class:

            mock_graph = MagicMock()
            mock_build.return_value = mock_graph

            mock_executor = MagicMock()
            mock_executor_class.return_value = mock_executor

            mock_executor.execute = AsyncMock(return_value=DAGResult(
                total=1, completed=0, stuck=0, max_iterations=1, failed=0, blocked=0,
                execution_order=["task1"], duration_seconds=1.0
            ))

            exit_code = await main_async(args)
            assert exit_code == 3

    @pytest.mark.asyncio
    async def test_dag_returns_one_on_error(self, tmp_path):
        """Test DAG command returns 1 when tasks fail with errors."""
        yaml_content = """
tasks:
  - id: task1
    task: "Task 1"
    verify: "echo ok"
"""
        tasks_file = tmp_path / "tasks.yaml"
        tasks_file.write_text(yaml_content)

        args = argparse.Namespace(
            command="dag",
            tasks_file=str(tasks_file),
            verbose=False,
            dry_run=False,
            parallel=1,
            worktrees=False,
            cleanup_worktrees=False,
        )

        from grind.models import DAGResult, GrindResult, GrindStatus

        with patch('grind.tasks.build_task_graph') as mock_build, \
             patch('grind.dag.DAGExecutor') as mock_executor_class:

            mock_graph = MagicMock()
            mock_build.return_value = mock_graph

            mock_executor = MagicMock()
            mock_executor_class.return_value = mock_executor

            mock_executor.execute = AsyncMock(return_value=DAGResult(
                total=1, completed=0, stuck=0, max_iterations=0, failed=1, blocked=0,
                execution_order=["task1"], duration_seconds=1.0
            ))

            exit_code = await main_async(args)
            assert exit_code == 1

    @pytest.mark.asyncio
    async def test_dag_returns_one_on_blocked(self, tmp_path):
        """Test DAG command returns 1 when tasks are blocked."""
        yaml_content = """
tasks:
  - id: task1
    task: "Task 1"
    verify: "echo ok"
  - id: task2
    task: "Task 2"
    verify: "echo ok"
    depends_on: [task1]
"""
        tasks_file = tmp_path / "tasks.yaml"
        tasks_file.write_text(yaml_content)

        args = argparse.Namespace(
            command="dag",
            tasks_file=str(tasks_file),
            verbose=False,
            dry_run=False,
            parallel=1,
            worktrees=False,
            cleanup_worktrees=False,
        )

        from grind.models import DAGResult, GrindResult, GrindStatus

        with patch('grind.tasks.build_task_graph') as mock_build, \
             patch('grind.dag.DAGExecutor') as mock_executor_class:

            mock_graph = MagicMock()
            mock_build.return_value = mock_graph

            mock_executor = MagicMock()
            mock_executor_class.return_value = mock_executor

            # Task 1 fails, task 2 gets blocked
            mock_executor.execute = AsyncMock(return_value=DAGResult(
                total=2, completed=0, stuck=0, max_iterations=0, failed=1, blocked=1,
                execution_order=["task1"], duration_seconds=1.0
            ))

            exit_code = await main_async(args)
            assert exit_code == 1
