import argparse
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml

from grind.cli import main_async
from grind.models import BatchResult, GrindResult, GrindStatus, InteractiveConfig, TaskDefinition


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
                TaskDefinition(task="Fix test 1", verify="pytest test1.py", max_iterations=5, model="sonnet"),
                TaskDefinition(task="Fix test 2", verify="pytest test2.py", max_iterations=5, model="sonnet"),
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
