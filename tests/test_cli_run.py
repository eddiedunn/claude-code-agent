"""Tests for Phase A grind run (self-evolution) and grind show CLI subcommands."""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest

from grind.cli import handle_evolve_command, handle_show_command


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def git_repo(tmp_path_factory: pytest.TempPathFactory) -> Generator[Path, None, None]:
    repo: Path = tmp_path_factory.mktemp("run_repo")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "README.md").write_text("# test\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True)
    yield repo


# ---------------------------------------------------------------------------
# Argparse smoke tests
# ---------------------------------------------------------------------------


def _run_grind(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "grind.py", *args],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )


def test_run_help_exits_zero() -> None:
    result = _run_grind("run", "--help")
    assert result.returncode == 0
    assert "--repo" in result.stdout
    assert "--contract-file" in result.stdout
    assert "--contract-cmd" in result.stdout


def test_show_help_exits_zero() -> None:
    result = _run_grind("show", "--help")
    assert result.returncode == 0
    assert "task_id" in result.stdout


def test_run_evolve_no_contract_exits_nonzero() -> None:
    """--repo + --prompt without contract flag should error."""
    args = argparse.Namespace(
        command="run",
        repo="/tmp/fake",
        prompt="do something",
        task_id=None,
        model="sonnet",
        max_retries=3,
        timeout=600,
        observer_url=None,
        contract_file=None,
        contract_cmd=None,
    )
    code = asyncio.run(handle_evolve_command(args))
    assert code == 1


def test_run_evolve_both_contracts_exits_nonzero() -> None:
    """Providing both --contract-file and --contract-cmd should error."""
    args = argparse.Namespace(
        command="run",
        repo="/tmp/fake",
        prompt="do something",
        task_id=None,
        model="sonnet",
        max_retries=3,
        timeout=600,
        observer_url=None,
        contract_file="hello.py",
        contract_cmd="pytest",
    )
    code = asyncio.run(handle_evolve_command(args))
    assert code == 1


# ---------------------------------------------------------------------------
# End-to-end: stub executor writes file, --contract-file passes
# ---------------------------------------------------------------------------


def test_evolve_contract_file_accepted(git_repo: Path) -> None:
    """Stub executor creates hello.py in worktree → contract passes, exit 0."""

    async def stub_claude(task, worktree_path, attempt, model, timeout_seconds):
        (worktree_path / "hello.py").write_text("print('hello')", encoding="utf-8")

    args = argparse.Namespace(
        command="run",
        repo=str(git_repo),
        prompt="Create hello.py",
        task_id="test-e2e-file",
        model="sonnet",
        max_retries=3,
        timeout=600,
        observer_url=None,
        contract_file="hello.py",
        contract_cmd=None,
    )

    with patch("grind.executor.claude_executor", side_effect=stub_claude):
        code = asyncio.run(handle_evolve_command(args))

    assert code == 0


def test_evolve_contract_file_rejected_on_missing_file(git_repo: Path) -> None:
    """Stub executor creates wrong file → contract fails, exit 1 after max_retries."""

    async def stub_claude(task, worktree_path, attempt, model, timeout_seconds):
        (worktree_path / "wrong.py").write_text("oops", encoding="utf-8")

    args = argparse.Namespace(
        command="run",
        repo=str(git_repo),
        prompt="Create hello.py",
        task_id="test-e2e-miss",
        model="sonnet",
        max_retries=2,
        timeout=600,
        observer_url=None,
        contract_file="hello.py",
        contract_cmd=None,
    )

    with patch("grind.executor.claude_executor", side_effect=stub_claude):
        code = asyncio.run(handle_evolve_command(args))

    assert code == 1


def test_show_no_db_exits_nonzero(tmp_path: Path) -> None:
    """Missing DB returns exit 1."""
    args = argparse.Namespace(
        task_id="nonexistent-job",
        db=str(tmp_path / "nofile.db"),
    )
    code = asyncio.run(handle_show_command(args))
    assert code == 1
