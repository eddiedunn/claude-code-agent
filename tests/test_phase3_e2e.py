"""End-to-end tests for Phase 3: Execution contracts primitive.

Run with: uv run python -m pytest tests/test_phase3_e2e.py -v
"""

import asyncio
import json
import os
import subprocess
import sys
import time
import urllib.request
from collections.abc import Generator
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers (mirror Phase 2 style)
# ---------------------------------------------------------------------------


def _wait_for_server(url: str, timeout: int = 15) -> bool:
    """Wait for server to be ready."""
    for _ in range(timeout):
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(1)
    return False


def _get_json(url: str) -> dict:  # type: ignore[type-arg]
    """GET a JSON endpoint."""
    return json.loads(urllib.request.urlopen(url).read())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def observer_server() -> Generator[str, None, None]:
    """Start the observer server on port 18425 for the test module."""
    base = "http://127.0.0.1:18425"
    db = "/tmp/test_phase3_e2e.db"

    for f in [db, db + "-journal", db + "-wal"]:
        if os.path.exists(f):
            os.unlink(f)

    grind_bin = os.path.join(os.path.dirname(sys.executable), "grind")
    proc = subprocess.Popen(
        [grind_bin, "observe",
         "--port", "18425", "--db", db, "--host", "127.0.0.1"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    if not _wait_for_server(f"{base}/health"):
        proc.terminate()
        proc.wait(timeout=5)
        pytest.fail("Observer server failed to start on port 18425")

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


def test_contract_fulfilled(git_repo: Path, observer_server: str) -> None:
    """Create a worktree, write required outputs to state/, validate → fulfilled."""
    from grind.contract import Budget, ContractStatus, ExecutionContract, validate
    from grind.worktree import WorktreeManager

    mgr = WorktreeManager(repo_root=str(git_repo), observer_url=observer_server)
    worktree_path = asyncio.run(
        mgr.create("fulfilled-test", "grind/fulfilled-test")
    )
    try:
        (worktree_path / "state" / "result.txt").write_text(
            "done\n", encoding="utf-8"
        )
        contract = ExecutionContract(
            required_outputs=["result.txt"],
            budget=Budget(max_tool_calls=10),
        )
        result = validate(
            contract,
            worktree_path,
            observer_url=observer_server,
            session_id="fulfilled-test",
            actual_tool_calls=3,
        )
        assert result.status == ContractStatus.FULFILLED
        assert result.violations == []
        assert "result.txt" in result.actual_outputs
    finally:
        asyncio.run(mgr.cleanup("fulfilled-test", force=True))


def test_contract_violated_missing_output(
    git_repo: Path, observer_server: str
) -> None:
    """Validate with a missing required output → violated, observer has CONTRACT_VIOLATION."""
    from grind.contract import ContractStatus, ExecutionContract, validate
    from grind.worktree import WorktreeManager

    mgr = WorktreeManager(repo_root=str(git_repo), observer_url=observer_server)
    worktree_path = asyncio.run(
        mgr.create("missing-output-test", "grind/missing-output-test")
    )
    try:
        # Do NOT write the required output
        contract = ExecutionContract(required_outputs=["missing.txt"])
        result = validate(
            contract,
            worktree_path,
            observer_url=observer_server,
            session_id="missing-output-test",
        )
        assert result.status == ContractStatus.VIOLATED
        assert any("missing.txt" in v for v in result.violations)

        # Observer must have recorded a CONTRACT_VIOLATION event
        events = _get_json(
            f"{observer_server}/events?event_type=contract_violation"
        )
        session_ids = [e["session_id"] for e in events["events"]]
        assert "missing-output-test" in session_ids, (
            f"No contract_violation event for session 'missing-output-test': {session_ids}"
        )
    finally:
        asyncio.run(mgr.cleanup("missing-output-test", force=True))


def test_contract_violated_budget(git_repo: Path, observer_server: str) -> None:
    """A contract with max_tool_calls=0 is violated when actual_tool_calls > 0."""
    from grind.contract import Budget, ContractStatus, ExecutionContract, validate
    from grind.worktree import WorktreeManager

    mgr = WorktreeManager(repo_root=str(git_repo), observer_url=observer_server)
    worktree_path = asyncio.run(
        mgr.create("budget-test", "grind/budget-test")
    )
    try:
        contract = ExecutionContract(budget=Budget(max_tool_calls=0))
        result = validate(
            contract,
            worktree_path,
            observer_url=observer_server,
            session_id="budget-test",
            actual_tool_calls=1,
        )
        assert result.status == ContractStatus.VIOLATED
        assert any("max_tool_calls" in v for v in result.violations)
    finally:
        asyncio.run(mgr.cleanup("budget-test", force=True))


def test_contract_denied_tool(git_repo: Path, observer_server: str) -> None:
    """permissions.denied_tools blocks a named tool → violated."""
    from grind.contract import ContractStatus, ExecutionContract, Permissions, validate
    from grind.worktree import WorktreeManager

    mgr = WorktreeManager(repo_root=str(git_repo), observer_url=observer_server)
    worktree_path = asyncio.run(
        mgr.create("denied-tool-test", "grind/denied-tool-test")
    )
    try:
        contract = ExecutionContract(
            permissions=Permissions(denied_tools=["Bash"]),
        )
        result = validate(
            contract,
            worktree_path,
            observer_url=observer_server,
            session_id="denied-tool-test",
            tool_used="Bash",
        )
        assert result.status == ContractStatus.VIOLATED
        assert any("denied_tools" in v for v in result.violations)
    finally:
        asyncio.run(mgr.cleanup("denied-tool-test", force=True))


def test_contract_composes(git_repo: Path, observer_server: str) -> None:
    """A parent contract constrains a child: child budget cannot exceed parent."""
    from grind.contract import Budget, ContractStatus, ExecutionContract, validate
    from grind.worktree import WorktreeManager

    mgr = WorktreeManager(repo_root=str(git_repo), observer_url=observer_server)
    worktree_path = asyncio.run(
        mgr.create("compose-test", "grind/compose-test")
    )
    try:
        parent = ExecutionContract(budget=Budget(max_tool_calls=5))
        # Child declares 10, but parent only allows 5 → violated
        child = ExecutionContract(
            budget=Budget(max_tool_calls=10),
            parent=parent,
        )
        result = validate(
            child,
            worktree_path,
            observer_url=observer_server,
            session_id="compose-test",
        )
        assert result.status == ContractStatus.VIOLATED
        assert any("max_tool_calls" in v and "parent" in v for v in result.violations)
    finally:
        asyncio.run(mgr.cleanup("compose-test", force=True))


def test_contract_module_imports() -> None:
    """contract module exports expected symbols."""
    from grind.contract import (  # noqa: F401
        Budget,
        ContractResult,
        ContractStatus,
        ContractViolationError,
        ExecutionContract,
        Permissions,
        validate,
    )

    assert callable(validate)
    assert issubclass(ContractViolationError, Exception)
    assert ContractStatus.FULFILLED == "fulfilled"
    assert ContractStatus.VIOLATED == "violated"
    assert ContractStatus.TIMEOUT == "timeout"


def test_contract_allowed_tool_pass(git_repo: Path, observer_server: str) -> None:
    """allowed_tools permits the named tool → fulfilled, no violations."""
    from grind.contract import ContractStatus, ExecutionContract, Permissions, validate
    from grind.worktree import WorktreeManager

    mgr = WorktreeManager(repo_root=str(git_repo), observer_url=observer_server)
    worktree_path = asyncio.run(
        mgr.create("allowed-tool-pass-test", "grind/allowed-tool-pass-test")
    )
    try:
        contract = ExecutionContract(
            permissions=Permissions(allowed_tools=["Read"]),
        )
        result = validate(
            contract,
            worktree_path,
            observer_url=observer_server,
            session_id="allowed-tool-pass-test",
            tool_used="Read",
        )
        assert result.status == ContractStatus.FULFILLED
        assert result.violations == []
    finally:
        asyncio.run(mgr.cleanup("allowed-tool-pass-test", force=True))


def test_contract_allowed_tool_blocked(git_repo: Path, observer_server: str) -> None:
    """allowed_tools blocks a tool not in the list → violated, observer event emitted."""
    from grind.contract import ContractStatus, ExecutionContract, Permissions, validate
    from grind.worktree import WorktreeManager

    mgr = WorktreeManager(repo_root=str(git_repo), observer_url=observer_server)
    worktree_path = asyncio.run(
        mgr.create("allowed-tool-blocked-test", "grind/allowed-tool-blocked-test")
    )
    try:
        contract = ExecutionContract(
            permissions=Permissions(allowed_tools=["Read"]),
        )
        result = validate(
            contract,
            worktree_path,
            observer_url=observer_server,
            session_id="allowed-tool-blocked-test",
            tool_used="Bash",
        )
        assert result.status == ContractStatus.VIOLATED
        assert any("allowed_tools" in v for v in result.violations)

        events = _get_json(
            f"{observer_server}/events?event_type=contract_violation"
        )
        session_ids = [e["session_id"] for e in events["events"]]
        assert "allowed-tool-blocked-test" in session_ids, (
            f"No contract_violation event for session 'allowed-tool-blocked-test': {session_ids}"
        )
    finally:
        asyncio.run(mgr.cleanup("allowed-tool-blocked-test", force=True))


def test_contract_violated_budget_tokens(git_repo: Path, observer_server: str) -> None:
    """Budget.max_tokens exceeded → violated with max_tokens in violation message."""
    from grind.contract import Budget, ContractStatus, ExecutionContract, validate
    from grind.worktree import WorktreeManager

    mgr = WorktreeManager(repo_root=str(git_repo), observer_url=observer_server)
    worktree_path = asyncio.run(
        mgr.create("budget-tokens-test", "grind/budget-tokens-test")
    )
    try:
        contract = ExecutionContract(budget=Budget(max_tokens=100))
        result = validate(
            contract,
            worktree_path,
            observer_url=observer_server,
            session_id="budget-tokens-test",
            actual_tokens=500,
        )
        assert result.status == ContractStatus.VIOLATED
        assert any("max_tokens" in v for v in result.violations)
    finally:
        asyncio.run(mgr.cleanup("budget-tokens-test", force=True))


def test_contract_violated_budget_wall_time(
    git_repo: Path, observer_server: str
) -> None:
    """Budget.max_wall_time_s exceeded → violated with max_wall_time_s in violation message."""
    from grind.contract import Budget, ContractStatus, ExecutionContract, validate
    from grind.worktree import WorktreeManager

    mgr = WorktreeManager(repo_root=str(git_repo), observer_url=observer_server)
    worktree_path = asyncio.run(
        mgr.create("budget-wall-time-test", "grind/budget-wall-time-test")
    )
    try:
        contract = ExecutionContract(budget=Budget(max_wall_time_s=1.0))
        result = validate(
            contract,
            worktree_path,
            observer_url=observer_server,
            session_id="budget-wall-time-test",
            actual_wall_time_s=5.5,
        )
        assert result.status == ContractStatus.VIOLATED
        assert any("max_wall_time_s" in v for v in result.violations)
    finally:
        asyncio.run(mgr.cleanup("budget-wall-time-test", force=True))


def test_contract_composes_tokens(git_repo: Path, observer_server: str) -> None:
    """Child max_tokens cannot exceed parent max_tokens → violated with parent in message."""
    from grind.contract import Budget, ContractStatus, ExecutionContract, validate
    from grind.worktree import WorktreeManager

    mgr = WorktreeManager(repo_root=str(git_repo), observer_url=observer_server)
    worktree_path = asyncio.run(
        mgr.create("compose-tokens-test", "grind/compose-tokens-test")
    )
    try:
        parent = ExecutionContract(budget=Budget(max_tokens=1000))
        child = ExecutionContract(
            budget=Budget(max_tokens=2000),
            parent=parent,
        )
        result = validate(
            child,
            worktree_path,
            observer_url=observer_server,
            session_id="compose-tokens-test",
        )
        assert result.status == ContractStatus.VIOLATED
        assert any("max_tokens" in v and "parent" in v for v in result.violations)
    finally:
        asyncio.run(mgr.cleanup("compose-tokens-test", force=True))


def test_contract_composes_wall_time(git_repo: Path, observer_server: str) -> None:
    """Child max_wall_time_s cannot exceed parent max_wall_time_s → violated with parent in message."""
    from grind.contract import Budget, ContractStatus, ExecutionContract, validate
    from grind.worktree import WorktreeManager

    mgr = WorktreeManager(repo_root=str(git_repo), observer_url=observer_server)
    worktree_path = asyncio.run(
        mgr.create("compose-wall-time-test", "grind/compose-wall-time-test")
    )
    try:
        parent = ExecutionContract(budget=Budget(max_wall_time_s=30.0))
        child = ExecutionContract(
            budget=Budget(max_wall_time_s=60.0),
            parent=parent,
        )
        result = validate(
            child,
            worktree_path,
            observer_url=observer_server,
            session_id="compose-wall-time-test",
        )
        assert result.status == ContractStatus.VIOLATED
        assert any("max_wall_time_s" in v and "parent" in v for v in result.violations)
    finally:
        asyncio.run(mgr.cleanup("compose-wall-time-test", force=True))


def test_contract_timeout(git_repo: Path, observer_server: str) -> None:
    """timed_out=True → TIMEOUT status, observer has contract_violation event."""
    from grind.contract import ContractStatus, ExecutionContract, validate
    from grind.worktree import WorktreeManager

    mgr = WorktreeManager(repo_root=str(git_repo), observer_url=observer_server)
    worktree_path = asyncio.run(
        mgr.create("timeout-test", "grind/timeout-test")
    )
    try:
        contract = ExecutionContract()
        result = validate(
            contract,
            worktree_path,
            observer_url=observer_server,
            session_id="timeout-test",
            timed_out=True,
        )
        assert result.status == ContractStatus.TIMEOUT

        events = _get_json(
            f"{observer_server}/events?event_type=contract_violation"
        )
        session_ids = [e["session_id"] for e in events["events"]]
        assert "timeout-test" in session_ids, (
            f"No contract_violation event for session 'timeout-test': {session_ids}"
        )
    finally:
        asyncio.run(mgr.cleanup("timeout-test", force=True))


def test_contract_violated_budget_emits_observer_event(
    git_repo: Path, observer_server: str
) -> None:
    """Budget.max_tool_calls=0 with actual_tool_calls=1 → VIOLATED, observer event emitted."""
    from grind.contract import Budget, ContractStatus, ExecutionContract, validate
    from grind.worktree import WorktreeManager

    mgr = WorktreeManager(repo_root=str(git_repo), observer_url=observer_server)
    worktree_path = asyncio.run(
        mgr.create("budget-emit-test", "grind/budget-emit-test")
    )
    try:
        contract = ExecutionContract(budget=Budget(max_tool_calls=0))
        result = validate(
            contract,
            worktree_path,
            observer_url=observer_server,
            session_id="budget-emit-test",
            actual_tool_calls=1,
        )
        assert result.status == ContractStatus.VIOLATED

        events = _get_json(
            f"{observer_server}/events?event_type=contract_violation"
        )
        session_ids = [e["session_id"] for e in events["events"]]
        assert "budget-emit-test" in session_ids, (
            f"No contract_violation event for session 'budget-emit-test': {session_ids}"
        )
    finally:
        asyncio.run(mgr.cleanup("budget-emit-test", force=True))


def test_contract_denied_tool_emits_observer_event(
    git_repo: Path, observer_server: str
) -> None:
    """Permissions.denied_tools blocks tool → VIOLATED, observer event emitted."""
    from grind.contract import ContractStatus, ExecutionContract, Permissions, validate
    from grind.worktree import WorktreeManager

    mgr = WorktreeManager(repo_root=str(git_repo), observer_url=observer_server)
    worktree_path = asyncio.run(
        mgr.create("denied-emit-test", "grind/denied-emit-test")
    )
    try:
        contract = ExecutionContract(
            permissions=Permissions(denied_tools=["Bash"]),
        )
        result = validate(
            contract,
            worktree_path,
            observer_url=observer_server,
            session_id="denied-emit-test",
            tool_used="Bash",
        )
        assert result.status == ContractStatus.VIOLATED

        events = _get_json(
            f"{observer_server}/events?event_type=contract_violation"
        )
        session_ids = [e["session_id"] for e in events["events"]]
        assert "denied-emit-test" in session_ids, (
            f"No contract_violation event for session 'denied-emit-test': {session_ids}"
        )
    finally:
        asyncio.run(mgr.cleanup("denied-emit-test", force=True))
