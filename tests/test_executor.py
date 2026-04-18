"""Tests for grind.executor — real Claude CLI executor (Phase A)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from grind.contract import ExecutionContract
from grind.executor import claude_executor
from grind.team import AgentTask


def _task(prompt: str = "test") -> AgentTask:
    return AgentTask(
        task_id="test-task",
        prompt=prompt,
        contract=ExecutionContract(),
    )


@pytest.mark.asyncio
async def test_command_cwd_model_wired(tmp_path: Path) -> None:
    """Verify claude is invoked with the correct command, cwd, and model."""
    call_args: list = []

    async def fake_wait() -> int:
        return 0

    mock_proc = MagicMock()
    mock_proc.wait = fake_wait

    async def fake_exec(*args, **kwargs):
        call_args.extend(args)
        call_args.append(kwargs)
        return mock_proc

    with patch("shutil.which", return_value="/usr/bin/claude"), \
         patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
        await claude_executor(_task("hello world"), tmp_path, 1, model="opus", timeout_seconds=30)

    assert call_args[0] == "claude"
    assert call_args[1] == "-p"
    assert call_args[2] == "hello world"
    assert call_args[3] == "--model"
    assert call_args[4] == "opus"
    assert call_args[-1].get("cwd") == tmp_path


@pytest.mark.asyncio
async def test_timeout_terminates_process(tmp_path: Path) -> None:
    """Timeout fires → proc.terminate() is called, TimeoutError propagates."""
    terminated: list[bool] = []
    call_count = [0]

    def make_wait():
        call_count[0] += 1
        if call_count[0] == 1:
            async def _hang():
                await asyncio.sleep(10)
            return _hang()
        else:
            async def _fast():
                return 0
            return _fast()

    mock_proc = MagicMock()
    mock_proc.wait = make_wait
    mock_proc.terminate = lambda: terminated.append(True)
    mock_proc.kill = MagicMock()

    with patch("shutil.which", return_value="/usr/bin/claude"), \
         patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        with pytest.raises(asyncio.TimeoutError):
            await claude_executor(_task(), tmp_path, 1, timeout_seconds=0.05)

    assert terminated, "proc.terminate() was not called on timeout"


@pytest.mark.asyncio
async def test_missing_binary_raises_clear_error(tmp_path: Path) -> None:
    """If 'claude' is not on PATH, raise RuntimeError with 'claude' in message."""
    with patch("shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="claude"):
            await claude_executor(_task(), tmp_path, 1)
