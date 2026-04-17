"""End-to-end tests for Phase 6: Orchestrator (planner + generator + using-evaluator).

Run with: uv run python -m pytest tests/test_phase6_e2e.py -v
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
# Helpers (mirror Phase 5 style)
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
    """Start the observer server on port 18428 for the test module."""
    base = "http://127.0.0.1:18428"
    db = "/tmp/test_phase6_e2e.db"

    for f in [db, db + "-journal", db + "-wal"]:
        if os.path.exists(f):
            os.unlink(f)

    grind_bin = os.path.join(os.path.dirname(sys.executable), "grind")
    proc = subprocess.Popen(
        [grind_bin, "observe",
         "--port", "18428", "--db", db, "--host", "127.0.0.1"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    if not _wait_for_server(f"{base}/health"):
        proc.terminate()
        proc.wait(timeout=5)
        pytest.fail("Observer server failed to start on port 18428")

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


def test_orchestrator_module_imports() -> None:
    """Smoke: imports OrchestratorStep, OrchestratorResult, Orchestrator."""
    from grind.orchestrator import (  # noqa: F401
        Orchestrator,
        OrchestratorResult,
        OrchestratorStep,
    )

    assert callable(Orchestrator)
    assert callable(OrchestratorResult)
    assert callable(OrchestratorStep)


def test_orchestrator_accepts_all_steps_fulfilled(
    git_repo: Path, observer_server: str
) -> None:
    """All steps write required outputs → accepted, plan_attempts == 1."""
    from grind.agents import AgentSpec, spec_to_contract
    from grind.orchestrator import Orchestrator, OrchestratorStep
    from grind.team import AgentTask

    spec = AgentSpec(name="p6-all-fulfilled", allowed_tools=frozenset({"Read", "Write"}))
    contract = spec_to_contract(spec, required_outputs=["out.json"])

    steps = [
        OrchestratorStep(
            step_id="p6-af-step1",
            prompt="write out.json",
            contract=contract,
            max_retries=2,
        ),
        OrchestratorStep(
            step_id="p6-af-step2",
            prompt="write out.json",
            contract=contract,
            max_retries=2,
        ),
    ]

    async def executor(task: AgentTask, path: Path, attempt: int) -> None:
        (path / "state" / "out.json").write_text('{"done": true}', encoding="utf-8")

    orch = Orchestrator(repo_root=str(git_repo), observer_url=observer_server)
    result = asyncio.run(orch.run("p6-all-fulfilled", steps, executor=executor))

    assert result.status == "accepted"
    assert result.plan_attempts == 1
    assert len(result.step_results) == 2
    assert all(r.status == "accepted" for r in result.step_results)


def test_orchestrator_failed_step_triggers_evaluator(
    git_repo: Path, observer_server: str
) -> None:
    """One step fails, evaluator sees partial results, evaluator returns True → accepted."""
    from grind.agents import AgentSpec, spec_to_contract
    from grind.orchestrator import Orchestrator, OrchestratorStep
    from grind.team import AgentResult, AgentTask

    spec_ok = spec_to_contract(
        AgentSpec(name="p6-fe-ok", allowed_tools=frozenset({"Read"})),
        required_outputs=["ok.json"],
    )
    spec_fail = spec_to_contract(
        AgentSpec(name="p6-fe-fail", allowed_tools=frozenset({"Read"})),
        required_outputs=["missing.json"],  # executor never writes this
    )

    steps = [
        OrchestratorStep(step_id="p6-fe-step1", prompt="write ok.json", contract=spec_ok),
        OrchestratorStep(
            step_id="p6-fe-step2",
            prompt="write missing.json",
            contract=spec_fail,
            max_retries=1,
        ),
    ]

    async def executor(task: AgentTask, path: Path, attempt: int) -> None:
        if task.task_id == "p6-fe-step1":
            (path / "state" / "ok.json").write_text('{"done": true}', encoding="utf-8")
        # p6-fe-step2 never writes missing.json → step fails

    evaluator_results: list[list[AgentResult]] = []

    async def evaluator(results: list[AgentResult]) -> bool:
        evaluator_results.append(results)
        return True  # accept even with partial completion

    orch = Orchestrator(repo_root=str(git_repo), observer_url=observer_server)
    result = asyncio.run(
        orch.run("p6-failed-step-evaluator", steps, executor=executor, evaluator=evaluator)
    )

    assert result.status == "accepted"
    assert result.plan_attempts == 1
    assert len(evaluator_results) == 1
    statuses = [r.status for r in evaluator_results[0]]
    assert "accepted" in statuses
    assert "failed" in statuses


def test_orchestrator_evaluator_rejection_retries_plan(
    git_repo: Path, observer_server: str
) -> None:
    """Evaluator returns False on attempt 1, True on attempt 2 → accepted, plan_attempts == 2."""
    from grind.agents import AgentSpec, spec_to_contract
    from grind.orchestrator import Orchestrator, OrchestratorStep
    from grind.team import AgentResult, AgentTask

    contract = spec_to_contract(
        AgentSpec(name="p6-retry", allowed_tools=frozenset({"Read"})),
        required_outputs=["result.json"],
    )
    steps = [
        OrchestratorStep(step_id="p6-retry-step1", prompt="write result.json", contract=contract),
    ]

    async def executor(task: AgentTask, path: Path, attempt: int) -> None:
        (path / "state" / "result.json").write_text('{"ok": true}', encoding="utf-8")

    call_count = 0

    async def evaluator(results: list[AgentResult]) -> bool:
        nonlocal call_count
        call_count += 1
        return call_count >= 2

    orch = Orchestrator(repo_root=str(git_repo), observer_url=observer_server)
    result = asyncio.run(
        orch.run(
            "p6-eval-rejection-retry",
            steps,
            executor=executor,
            evaluator=evaluator,
            max_plan_retries=3,
        )
    )

    assert result.status == "accepted"
    assert result.plan_attempts == 2


def test_orchestrator_exhausts_plan_retries(
    git_repo: Path, observer_server: str
) -> None:
    """Evaluator always returns False → failed, plan_attempts == max_plan_retries."""
    from grind.agents import AgentSpec, spec_to_contract
    from grind.orchestrator import Orchestrator, OrchestratorStep
    from grind.team import AgentResult, AgentTask

    contract = spec_to_contract(
        AgentSpec(name="p6-exhaust", allowed_tools=frozenset({"Read"})),
        required_outputs=["out.json"],
    )
    steps = [
        OrchestratorStep(step_id="p6-exhaust-step1", prompt="write out.json", contract=contract),
    ]

    async def executor(task: AgentTask, path: Path, attempt: int) -> None:
        (path / "state" / "out.json").write_text('{"ok": true}', encoding="utf-8")

    async def evaluator(results: list[AgentResult]) -> bool:
        return False

    orch = Orchestrator(repo_root=str(git_repo), observer_url=observer_server)
    result = asyncio.run(
        orch.run(
            "p6-exhaust-retries",
            steps,
            executor=executor,
            evaluator=evaluator,
            max_plan_retries=2,
        )
    )

    assert result.status == "failed"
    assert result.plan_attempts == 2


def test_orchestrator_emits_spawn_and_complete(
    git_repo: Path, observer_server: str
) -> None:
    """Observer has agent_spawn and agent_complete events for the run."""
    from grind.agents import AgentSpec, spec_to_contract
    from grind.orchestrator import Orchestrator, OrchestratorStep
    from grind.team import AgentTask

    goal = "p6-spawn-complete-events"
    contract = spec_to_contract(
        AgentSpec(name="p6-sc", allowed_tools=frozenset({"Read"})),
        required_outputs=["sc.json"],
    )
    steps = [
        OrchestratorStep(step_id="p6-sc-step1", prompt="write sc.json", contract=contract),
    ]

    async def executor(task: AgentTask, path: Path, attempt: int) -> None:
        (path / "state" / "sc.json").write_text('{"ok": true}', encoding="utf-8")

    orch = Orchestrator(repo_root=str(git_repo), observer_url=observer_server)
    asyncio.run(orch.run(goal, steps, executor=executor))

    spawn_events = _get_json(f"{observer_server}/events?event_type=agent_spawn")
    complete_events = _get_json(f"{observer_server}/events?event_type=agent_complete")

    spawn_ids = [e["session_id"] for e in spawn_events["events"]]
    complete_ids = [e["session_id"] for e in complete_events["events"]]

    assert goal in spawn_ids, f"No agent_spawn for {goal!r}: {spawn_ids}"
    assert goal in complete_ids, f"No agent_complete for {goal!r}: {complete_ids}"


def test_orchestrator_emits_retry_on_plan_retry(
    git_repo: Path, observer_server: str
) -> None:
    """Observer has agent_retry event when plan is retried."""
    from grind.agents import AgentSpec, spec_to_contract
    from grind.orchestrator import Orchestrator, OrchestratorStep
    from grind.team import AgentResult, AgentTask

    goal = "p6-retry-event-check"
    contract = spec_to_contract(
        AgentSpec(name="p6-re", allowed_tools=frozenset({"Read"})),
        required_outputs=["re.json"],
    )
    steps = [
        OrchestratorStep(step_id="p6-re-step1", prompt="write re.json", contract=contract),
    ]

    async def executor(task: AgentTask, path: Path, attempt: int) -> None:
        (path / "state" / "re.json").write_text('{"ok": true}', encoding="utf-8")

    call_count = 0

    async def evaluator(results: list[AgentResult]) -> bool:
        nonlocal call_count
        call_count += 1
        return call_count >= 2

    orch = Orchestrator(repo_root=str(git_repo), observer_url=observer_server)
    asyncio.run(orch.run(goal, steps, executor=executor, evaluator=evaluator, max_plan_retries=3))

    retry_events = _get_json(f"{observer_server}/events?event_type=agent_retry")
    retry_ids = [e["session_id"] for e in retry_events["events"]]

    assert goal in retry_ids, f"No agent_retry for {goal!r}: {retry_ids}"


def test_orchestrator_no_evaluator_all_accepted(
    git_repo: Path, observer_server: str
) -> None:
    """No evaluator, all steps succeed → accepted."""
    from grind.agents import AgentSpec, spec_to_contract
    from grind.orchestrator import Orchestrator, OrchestratorStep
    from grind.team import AgentTask

    contract = spec_to_contract(
        AgentSpec(name="p6-no-eval", allowed_tools=frozenset({"Read"})),
        required_outputs=["noeval.json"],
    )
    steps = [
        OrchestratorStep(step_id="p6-ne-step1", prompt="write noeval.json", contract=contract),
        OrchestratorStep(step_id="p6-ne-step2", prompt="write noeval.json", contract=contract),
    ]

    async def executor(task: AgentTask, path: Path, attempt: int) -> None:
        (path / "state" / "noeval.json").write_text('{"done": true}', encoding="utf-8")

    orch = Orchestrator(repo_root=str(git_repo), observer_url=observer_server)
    result = asyncio.run(orch.run("p6-no-evaluator", steps, executor=executor))

    assert result.status == "accepted"
    assert result.plan_attempts == 1
    assert all(r.status == "accepted" for r in result.step_results)


# ---------------------------------------------------------------------------
# Coverage gap tests
# ---------------------------------------------------------------------------


def test_emit_no_observer_url_early_return(git_repo: Path) -> None:
    """_emit() with observer_url=None hits the early-return branch (line 68)."""
    from grind.orchestrator import Orchestrator, OrchestratorResult, OrchestratorStep

    # observer_url intentionally omitted → defaults to None
    orch = Orchestrator(repo_root=str(git_repo))
    assert orch.observer_url is None

    # _emit should return immediately without raising
    orch._emit("agent_spawn", "p6-cov-no-url")

    # run() with no steps: vacuous all() → accepted, no HTTP calls attempted
    result = asyncio.run(orch.run("p6-cov-no-url-run", steps=[]))
    assert isinstance(result, OrchestratorResult)
    assert result.status == "accepted"
    assert result.step_results == []

    # Confirm default field values on the dataclasses
    assert OrchestratorStep.__dataclass_fields__["max_retries"].default == 3
    assert OrchestratorResult.__dataclass_fields__["step_results"].default_factory is not None


def test_emit_http_exception_silenced(git_repo: Path) -> None:
    """_emit() swallows any HTTP error so orchestration is never blocked (lines 83-84)."""
    from grind.orchestrator import Orchestrator

    # Point at a port where nothing is listening → urlopen raises → silenced
    dead_url = "http://127.0.0.1:19999"
    orch = Orchestrator(repo_root=str(git_repo), observer_url=dead_url)

    # Should not raise despite the broken URL
    orch._emit("agent_spawn", "p6-cov-dead-url", {"attempt": 1, "goal": "probe"})


def test_emit_http_exception_during_run(git_repo: Path) -> None:
    """run() with a dead observer_url completes normally — HTTP errors are silenced."""
    from grind.agents import AgentSpec, spec_to_contract
    from grind.orchestrator import Orchestrator, OrchestratorStep
    from grind.team import AgentTask

    contract = spec_to_contract(
        AgentSpec(name="p6-cov-dead", allowed_tools=frozenset({"Read"})),
        required_outputs=["cov.json"],
    )
    steps = [
        OrchestratorStep(
            step_id="p6-cov-dead-step1",
            prompt="write cov.json",
            contract=contract,
            max_retries=1,
        ),
    ]

    async def executor(task: AgentTask, path: Path, attempt: int) -> None:
        (path / "state" / "cov.json").write_text('{"ok": true}', encoding="utf-8")

    dead_url = "http://127.0.0.1:19999"
    orch = Orchestrator(repo_root=str(git_repo), observer_url=dead_url)
    result = asyncio.run(orch.run("p6-cov-dead-run", steps, executor=executor))

    assert result.status == "accepted"
    assert result.plan_attempts == 1


def test_no_evaluator_failed_step_exhausts_plan(git_repo: Path) -> None:
    """No evaluator + step exhausts retries → default evaluator (all accepted) returns
    False → plan exhausts max_plan_retries → OrchestratorResult status='failed'."""
    from grind.agents import AgentSpec, spec_to_contract
    from grind.orchestrator import Orchestrator, OrchestratorStep
    from grind.team import AgentTask

    # required_outputs never written → SelfEvolutionLoop marks step failed
    contract = spec_to_contract(
        AgentSpec(name="p6-cov-fail-default", allowed_tools=frozenset({"Read"})),
        required_outputs=["never.json"],
    )
    steps = [
        OrchestratorStep(
            step_id="p6-cov-fail-default-step1",
            prompt="write never.json",
            contract=contract,
            max_retries=1,
        ),
    ]

    async def executor(task: AgentTask, path: Path, attempt: int) -> None:
        pass  # deliberately writes nothing → contract check fails

    orch = Orchestrator(repo_root=str(git_repo))  # no observer_url → also covers line 68
    result = asyncio.run(
        orch.run("p6-cov-fail-default-goal", steps, executor=executor, max_plan_retries=2)
    )

    assert result.status == "failed"
    assert result.plan_attempts == 2
    assert all(r.status == "failed" for r in result.step_results)
