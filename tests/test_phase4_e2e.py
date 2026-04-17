"""End-to-end tests for Phase 4: Agent teams — single self-evolution loop.

Run with: uv run python -m pytest tests/test_phase4_e2e.py -v
"""

import asyncio
import json
import os
import subprocess
import sys
import time
import unittest.mock
import urllib.request
from collections.abc import Generator
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers (mirror Phase 3 style)
# ---------------------------------------------------------------------------


def _wait_for_server(url: str, timeout: int = 15) -> bool:
    for _ in range(timeout):
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(1)
    return False


def _get_json(url: str) -> dict:  # type: ignore[type-arg]
    return json.loads(urllib.request.urlopen(url).read())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def observer_server() -> Generator[str, None, None]:
    """Start the observer server on port 18426 for the test module."""
    base = "http://127.0.0.1:18426"
    db = "/tmp/test_phase4_e2e.db"

    for f in [db, db + "-journal", db + "-wal"]:
        if os.path.exists(f):
            os.unlink(f)

    grind_bin = os.path.join(os.path.dirname(sys.executable), "grind")
    proc = subprocess.Popen(
        [grind_bin, "observe",
         "--port", "18426", "--db", db, "--host", "127.0.0.1"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    if not _wait_for_server(f"{base}/health"):
        proc.terminate()
        proc.wait(timeout=5)
        pytest.fail("Observer server failed to start on port 18426")

    yield base

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    for f in [db, db + "-journal", db + "-wal"]:
        if os.path.exists(f):
            os.unlink(f)


@pytest.fixture(scope="module")
def git_repo(tmp_path_factory: pytest.TempPathFactory) -> Generator[Path, None, None]:
    """Create a temporary git repo with an initial commit on main."""
    repo: Path = tmp_path_factory.mktemp("repo")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo, check=True,
    )
    (repo / "README.md").write_text("# test\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True)
    yield repo


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_loop_accepts_on_first_attempt(git_repo: Path, observer_server: str) -> None:
    """Executor writes required output on attempt 1 → accepted, attempts == 1."""
    from grind.contract import ExecutionContract
    from grind.team import AgentTask, SelfEvolutionLoop

    async def executor(task: AgentTask, path: Path, attempt: int) -> None:
        (path / "state" / "result.json").write_text('{"done": true}', encoding="utf-8")

    loop = SelfEvolutionLoop(
        repo_root=str(git_repo), observer_url=observer_server
    )
    task = AgentTask(
        task_id="p4-accept-first",
        prompt="write result.json",
        contract=ExecutionContract(required_outputs=["result.json"]),
        max_retries=3,
    )
    result = asyncio.run(loop.run(task, executor))

    assert result.status == "accepted"
    assert result.attempts == 1
    assert result.task_id == "p4-accept-first"


def test_loop_retries_on_violation(git_repo: Path, observer_server: str) -> None:
    """Attempt 1 violates contract (no output), attempt 2 fulfills → accepted, 2 attempts."""
    from grind.contract import ExecutionContract
    from grind.team import AgentTask, SelfEvolutionLoop

    async def executor(task: AgentTask, path: Path, attempt: int) -> None:
        if attempt >= 2:
            (path / "state" / "result.json").write_text(
                '{"done": true}', encoding="utf-8"
            )

    loop = SelfEvolutionLoop(
        repo_root=str(git_repo), observer_url=observer_server
    )
    task = AgentTask(
        task_id="p4-retry-once",
        prompt="write result.json",
        contract=ExecutionContract(required_outputs=["result.json"]),
        max_retries=3,
    )
    result = asyncio.run(loop.run(task, executor))

    assert result.status == "accepted"
    assert result.attempts == 2


def test_loop_fails_after_max_retries(git_repo: Path, observer_server: str) -> None:
    """Executor never writes required output → failed after max_retries attempts."""
    from grind.contract import ExecutionContract
    from grind.team import AgentTask, SelfEvolutionLoop

    async def executor(task: AgentTask, path: Path, attempt: int) -> None:
        pass  # never write the required output

    loop = SelfEvolutionLoop(
        repo_root=str(git_repo), observer_url=observer_server
    )
    task = AgentTask(
        task_id="p4-fail-all",
        prompt="write result.json",
        contract=ExecutionContract(required_outputs=["result.json"]),
        max_retries=3,
    )
    result = asyncio.run(loop.run(task, executor))

    assert result.status == "failed"
    assert result.attempts == 3
    assert result.final_worktree_path is None


def test_loop_emits_agent_spawn_and_complete(
    git_repo: Path, observer_server: str
) -> None:
    """Observer records AGENT_SPAWN and AGENT_COMPLETE events for the task."""
    from grind.contract import ExecutionContract
    from grind.team import AgentTask, SelfEvolutionLoop

    async def executor(task: AgentTask, path: Path, attempt: int) -> None:
        (path / "state" / "out.txt").write_text("done", encoding="utf-8")

    loop = SelfEvolutionLoop(
        repo_root=str(git_repo), observer_url=observer_server
    )
    task = AgentTask(
        task_id="p4-emit-spawn",
        prompt="write out.txt",
        contract=ExecutionContract(required_outputs=["out.txt"]),
        max_retries=3,
    )
    asyncio.run(loop.run(task, executor))

    spawn_events = _get_json(f"{observer_server}/events?event_type=agent_spawn")
    spawn_ids = [e["session_id"] for e in spawn_events["events"]]
    assert "p4-emit-spawn" in spawn_ids, (
        f"No agent_spawn event for p4-emit-spawn: {spawn_ids}"
    )

    complete_events = _get_json(f"{observer_server}/events?event_type=agent_complete")
    complete_ids = [e["session_id"] for e in complete_events["events"]]
    assert "p4-emit-spawn" in complete_ids, (
        f"No agent_complete event for p4-emit-spawn: {complete_ids}"
    )


def test_loop_emits_retry_events(git_repo: Path, observer_server: str) -> None:
    """Observer records an AGENT_RETRY event when the second attempt begins."""
    from grind.contract import ExecutionContract
    from grind.team import AgentTask, SelfEvolutionLoop

    async def executor(task: AgentTask, path: Path, attempt: int) -> None:
        if attempt >= 2:
            (path / "state" / "out.txt").write_text("done", encoding="utf-8")

    loop = SelfEvolutionLoop(
        repo_root=str(git_repo), observer_url=observer_server
    )
    task = AgentTask(
        task_id="p4-emit-retry",
        prompt="write out.txt",
        contract=ExecutionContract(required_outputs=["out.txt"]),
        max_retries=3,
    )
    asyncio.run(loop.run(task, executor))

    retry_events = _get_json(f"{observer_server}/events?event_type=agent_retry")
    retry_ids = [e["session_id"] for e in retry_events["events"]]
    assert "p4-emit-retry" in retry_ids, (
        f"No agent_retry event for p4-emit-retry: {retry_ids}"
    )


def test_loop_worktrees_cleaned_up(git_repo: Path, observer_server: str) -> None:
    """After run() completes (any outcome), no .worktrees/ entries remain."""
    from grind.contract import ExecutionContract
    from grind.team import AgentTask, SelfEvolutionLoop

    async def executor(task: AgentTask, path: Path, attempt: int) -> None:
        pass  # intentional failure to test cleanup on failed paths too

    loop = SelfEvolutionLoop(
        repo_root=str(git_repo), observer_url=observer_server
    )
    task = AgentTask(
        task_id="p4-cleanup",
        prompt="nothing",
        contract=ExecutionContract(required_outputs=["missing.txt"]),
        max_retries=2,
    )
    result = asyncio.run(loop.run(task, executor))
    assert result.status == "failed"

    wt_dir = git_repo / ".worktrees"
    assert not wt_dir.exists() or not any(p.is_dir() for p in wt_dir.iterdir()), (
        f"Worktree entries remain after run(): {list(wt_dir.iterdir()) if wt_dir.exists() else []}"
    )


def test_loop_contract_result_attached(git_repo: Path, observer_server: str) -> None:
    """Accepted AgentResult carries a non-None ContractResult with FULFILLED status."""
    from grind.contract import ContractResult, ContractStatus, ExecutionContract
    from grind.team import AgentTask, SelfEvolutionLoop

    async def executor(task: AgentTask, path: Path, attempt: int) -> None:
        (path / "state" / "artifact.txt").write_text("ok", encoding="utf-8")

    loop = SelfEvolutionLoop(
        repo_root=str(git_repo), observer_url=observer_server
    )
    task = AgentTask(
        task_id="p4-result-attach",
        prompt="write artifact.txt",
        contract=ExecutionContract(required_outputs=["artifact.txt"]),
        max_retries=3,
    )
    result = asyncio.run(loop.run(task, executor))

    assert result.status == "accepted"
    assert result.contract_result is not None
    assert isinstance(result.contract_result, ContractResult)
    assert result.contract_result.status == ContractStatus.FULFILLED
    assert "artifact.txt" in result.contract_result.actual_outputs


def test_team_module_imports() -> None:
    """grind.team exports AgentTask, AgentResult, SelfEvolutionLoop."""
    from grind.team import AgentResult, AgentTask, SelfEvolutionLoop  # noqa: F401

    assert AgentTask.__dataclass_fields__["task_id"] is not None
    assert AgentResult.__dataclass_fields__["status"] is not None
    assert callable(SelfEvolutionLoop)


def test_loop_timeout_path(git_repo: Path, observer_server: str) -> None:
    """validate patched to return TIMEOUT → loop retries and fails after max_retries."""
    from grind.contract import ContractResult, ContractStatus, ExecutionContract
    from grind.team import AgentTask, SelfEvolutionLoop

    async def executor(task: AgentTask, path: Path, attempt: int) -> None:
        pass

    loop = SelfEvolutionLoop(repo_root=str(git_repo), observer_url=observer_server)
    task = AgentTask(
        task_id="p4-timeout-path",
        prompt="nothing",
        contract=ExecutionContract(),
        max_retries=2,
    )

    timeout_result = ContractResult(
        status=ContractStatus.TIMEOUT,
        violations=["execution timed out"],
    )
    with unittest.mock.patch("grind.team.validate", return_value=timeout_result):
        result = asyncio.run(loop.run(task, executor))

    assert result.status == "failed"
    assert result.attempts == task.max_retries


def test_loop_no_observer(git_repo: Path) -> None:
    """observer_url=None → loop completes with status 'accepted' without crashing."""
    from grind.contract import ExecutionContract
    from grind.team import AgentTask, SelfEvolutionLoop

    async def executor(task: AgentTask, path: Path, attempt: int) -> None:
        (path / "state" / "out.txt").write_text("ok", encoding="utf-8")

    loop = SelfEvolutionLoop(repo_root=str(git_repo), observer_url=None)
    task = AgentTask(
        task_id="p4-no-observer",
        prompt="write out.txt",
        contract=ExecutionContract(required_outputs=["out.txt"]),
        max_retries=3,
    )
    result = asyncio.run(loop.run(task, executor))

    assert result.status == "accepted"
    assert result.attempts == 1


def test_loop_no_executor(git_repo: Path) -> None:
    """No executor + empty contract → auto-fulfilled on attempt 1."""
    from grind.contract import ExecutionContract
    from grind.team import AgentTask, SelfEvolutionLoop

    loop = SelfEvolutionLoop(repo_root=str(git_repo), observer_url=None)
    task = AgentTask(
        task_id="p4-no-executor",
        prompt="nothing",
        contract=ExecutionContract(),
        max_retries=3,
    )
    result = asyncio.run(loop.run(task))

    assert result.status == "accepted"
    assert result.attempts == 1


def test_loop_executor_raises(git_repo: Path) -> None:
    """Executor that raises RuntimeError → exception propagates, no worktrees remain."""
    from grind.contract import ExecutionContract
    from grind.team import AgentTask, SelfEvolutionLoop

    async def executor(task: AgentTask, path: Path, attempt: int) -> None:
        raise RuntimeError("boom")

    loop = SelfEvolutionLoop(repo_root=str(git_repo), observer_url=None)
    task = AgentTask(
        task_id="p4-executor-raises",
        prompt="crash",
        contract=ExecutionContract(),
        max_retries=3,
    )

    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(loop.run(task, executor))

    wt_dir = git_repo / ".worktrees"
    assert not wt_dir.exists() or not any(p.is_dir() for p in wt_dir.iterdir()), (
        f"Worktree entries remain after exception: "
        f"{list(wt_dir.iterdir()) if wt_dir.exists() else []}"
    )
