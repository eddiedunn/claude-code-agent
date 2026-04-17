"""End-to-end tests for Phase 5: SDK custom agents via subtraction.

Run with: uv run python -m pytest tests/test_phase5_e2e.py -v
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
# Helpers (mirror Phase 4 style)
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
    """Start the observer server on port 18427 for the test module."""
    base = "http://127.0.0.1:18427"
    db = "/tmp/test_phase5_e2e.db"

    for f in [db, db + "-journal", db + "-wal"]:
        if os.path.exists(f):
            os.unlink(f)

    grind_bin = os.path.join(os.path.dirname(sys.executable), "grind")
    proc = subprocess.Popen(
        [grind_bin, "observe",
         "--port", "18427", "--db", db, "--host", "127.0.0.1"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    if not _wait_for_server(f"{base}/health"):
        proc.terminate()
        proc.wait(timeout=5)
        pytest.fail("Observer server failed to start on port 18427")

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


def test_frontend_agent_tool_ratio() -> None:
    """frontend_agent() allowed_tools is ≤21% of CLAUDE_CODE_TOOLS."""
    from grind.agents import CLAUDE_CODE_TOOLS, frontend_agent

    spec = frontend_agent()
    ratio = len(spec.allowed_tools) / len(CLAUDE_CODE_TOOLS)
    assert ratio <= 0.21, (
        f"frontend_agent tool ratio {ratio:.2%} exceeds 21% "
        f"({len(spec.allowed_tools)}/{len(CLAUDE_CODE_TOOLS)} tools)"
    )


def test_data_migration_agent_tool_ratio() -> None:
    """data_migration_agent() allowed_tools is ≤21% of CLAUDE_CODE_TOOLS."""
    from grind.agents import CLAUDE_CODE_TOOLS, data_migration_agent

    spec = data_migration_agent()
    ratio = len(spec.allowed_tools) / len(CLAUDE_CODE_TOOLS)
    assert ratio <= 0.21, (
        f"data_migration_agent tool ratio {ratio:.2%} exceeds 21% "
        f"({len(spec.allowed_tools)}/{len(CLAUDE_CODE_TOOLS)} tools)"
    )


def test_subtract_removes_tools() -> None:
    """subtract(CLAUDE_CODE_TOOLS, {'Bash', 'Write'}) removes both and shrinks by 2."""
    from grind.agents import CLAUDE_CODE_TOOLS, subtract

    result = subtract(CLAUDE_CODE_TOOLS, {"Bash", "Write"})
    assert "Bash" not in result
    assert "Write" not in result
    assert len(result) == len(CLAUDE_CODE_TOOLS) - 2


def test_spec_contract_permits_listed_tool(
    git_repo: Path, observer_server: str
) -> None:
    """validate() with a tool in spec.allowed_tools → FULFILLED."""
    from grind.agents import frontend_agent, spec_to_contract
    from grind.contract import ContractStatus, validate

    spec = frontend_agent()
    contract = spec_to_contract(spec)

    # "Read" is in frontend_agent's allowed_tools
    assert "Read" in spec.allowed_tools
    result = validate(
        contract,
        git_repo,
        observer_url=observer_server,
        session_id="p5-permit-tool",
        tool_used="Read",
    )

    assert result.status == ContractStatus.FULFILLED
    assert result.violations == []


def test_spec_contract_denies_unlisted_tool(
    git_repo: Path, observer_server: str
) -> None:
    """validate() with a tool not in spec.allowed_tools → VIOLATED, observer records violation."""
    from grind.agents import frontend_agent, spec_to_contract
    from grind.contract import ContractStatus, validate

    spec = frontend_agent()
    contract = spec_to_contract(spec)

    # "Bash" is NOT in frontend_agent's allowed_tools
    assert "Bash" not in spec.allowed_tools
    result = validate(
        contract,
        git_repo,
        observer_url=observer_server,
        session_id="p5-denied-tool",
        tool_used="Bash",
    )

    assert result.status == ContractStatus.VIOLATED
    assert any("Bash" in v for v in result.violations)

    violation_events = _get_json(
        f"{observer_server}/events?event_type=contract_violation"
    )
    session_ids = [e["session_id"] for e in violation_events["events"]]
    assert "p5-denied-tool" in session_ids, (
        f"No contract_violation event for p5-denied-tool: {session_ids}"
    )


def test_spec_integrates_with_loop(git_repo: Path, observer_server: str) -> None:
    """AgentTask built from spec_to_contract(frontend_agent()) → accepted on first attempt."""
    from grind.agents import frontend_agent, spec_to_contract
    from grind.team import AgentTask, SelfEvolutionLoop

    contract = spec_to_contract(frontend_agent(), required_outputs=["result.json"])

    async def executor(task: AgentTask, path: Path, attempt: int) -> None:
        (path / "state" / "result.json").write_text('{"done": true}', encoding="utf-8")

    loop = SelfEvolutionLoop(repo_root=str(git_repo), observer_url=observer_server)
    task = AgentTask(
        task_id="p5-spec-loop",
        prompt="write result.json",
        contract=contract,
        max_retries=3,
    )
    result = asyncio.run(loop.run(task, executor))

    assert result.status == "accepted"
    assert result.attempts == 1
    assert result.task_id == "p5-spec-loop"


def test_spec_composition() -> None:
    """Intersection of two specs' allowed_tools is a subset of both."""
    from grind.agents import data_migration_agent, frontend_agent

    fe = frontend_agent()
    dm = data_migration_agent()

    intersection = fe.allowed_tools & dm.allowed_tools

    assert intersection <= fe.allowed_tools, (
        f"Intersection {intersection} not a subset of frontend {fe.allowed_tools}"
    )
    assert intersection <= dm.allowed_tools, (
        f"Intersection {intersection} not a subset of data_migration {dm.allowed_tools}"
    )


def test_agents_module_imports() -> None:
    """Smoke: all public names import cleanly from grind.agents."""
    from grind.agents import (  # noqa: F401
        CLAUDE_CODE_TOOLS,
        AgentSpec,
        data_migration_agent,
        frontend_agent,
        spec_to_contract,
        subtract,
    )

    assert isinstance(CLAUDE_CODE_TOOLS, frozenset)
    assert len(CLAUDE_CODE_TOOLS) == 14
    assert callable(subtract)
    assert callable(spec_to_contract)
    assert callable(frontend_agent)
    assert callable(data_migration_agent)


def test_agent_spec_system_prompt_suffix_default() -> None:
    """AgentSpec.system_prompt_suffix defaults to empty string when not supplied."""
    from grind.agents import AgentSpec

    spec = AgentSpec(name="minimal", allowed_tools=frozenset({"Read"}))
    assert spec.system_prompt_suffix == "", (
        f"Expected system_prompt_suffix='' by default, got {spec.system_prompt_suffix!r}"
    )


def test_agent_spec_custom_system_prompt_suffix() -> None:
    """AgentSpec.system_prompt_suffix is preserved exactly as supplied."""
    from grind.agents import AgentSpec

    suffix = "Always respond in JSON.\nNo prose."
    spec = AgentSpec(
        name="json-only",
        allowed_tools=frozenset({"Read", "Write"}),
        system_prompt_suffix=suffix,
    )
    assert spec.system_prompt_suffix == suffix, (
        f"system_prompt_suffix not preserved: got {spec.system_prompt_suffix!r}"
    )


def test_agent_spec_suffix_not_lost_after_spec_to_contract() -> None:
    """spec_to_contract() does not mutate or drop system_prompt_suffix on the spec."""
    from grind.agents import AgentSpec, spec_to_contract

    suffix = "Custom instructions here."
    spec = AgentSpec(
        name="custom",
        allowed_tools=frozenset({"Glob"}),
        system_prompt_suffix=suffix,
    )
    _ = spec_to_contract(spec)
    assert spec.system_prompt_suffix == suffix, (
        "spec_to_contract() mutated system_prompt_suffix on the AgentSpec"
    )


def test_subtract_empty_remove_returns_full() -> None:
    """subtract(full, frozenset()) returns full set unchanged."""
    from grind.agents import CLAUDE_CODE_TOOLS, subtract

    result = subtract(CLAUDE_CODE_TOOLS, frozenset())
    assert result == CLAUDE_CODE_TOOLS, (
        f"subtract with empty remove should return the full set; got {result}"
    )


def test_subtract_superset_remove_returns_empty() -> None:
    """subtract(full, superset_of_full) returns empty frozenset."""
    from grind.agents import CLAUDE_CODE_TOOLS, subtract

    bigger = CLAUDE_CODE_TOOLS | frozenset({"ExtraToolA", "ExtraToolB"})
    result = subtract(CLAUDE_CODE_TOOLS, bigger)
    assert result == frozenset(), (
        f"subtract with superset remove should return empty frozenset; got {result}"
    )


def test_spec_to_contract_explicit_budget() -> None:
    """spec_to_contract() with an explicit Budget wires it through to the contract."""
    from grind.agents import AgentSpec, spec_to_contract
    from grind.contract import Budget

    budget = Budget(max_tokens=5000, max_wall_time_s=30.0, max_tool_calls=10)
    spec = AgentSpec(name="budget-test", allowed_tools=frozenset({"Read"}))
    contract = spec_to_contract(spec, budget=budget)

    assert contract.budget is budget, (
        "spec_to_contract() did not wire the supplied Budget onto the contract"
    )
    assert contract.budget.max_tokens == 5000, (
        f"Expected max_tokens=5000, got {contract.budget.max_tokens}"
    )
    assert contract.budget.max_wall_time_s == 30.0, (
        f"Expected max_wall_time_s=30.0, got {contract.budget.max_wall_time_s}"
    )
    assert contract.budget.max_tool_calls == 10, (
        f"Expected max_tool_calls=10, got {contract.budget.max_tool_calls}"
    )


def test_spec_to_contract_default_budget_is_empty() -> None:
    """spec_to_contract() with no budget arg produces a default Budget() with all None limits."""
    from grind.agents import AgentSpec, spec_to_contract
    from grind.contract import Budget

    spec = AgentSpec(name="no-budget", allowed_tools=frozenset({"Read"}))
    contract = spec_to_contract(spec)

    assert isinstance(contract.budget, Budget), (
        f"Expected Budget instance, got {type(contract.budget)}"
    )
    assert contract.budget.max_tokens is None
    assert contract.budget.max_wall_time_s is None
    assert contract.budget.max_tool_calls is None


def test_spec_to_contract_explicit_required_outputs() -> None:
    """spec_to_contract() with required_outputs list passes them through to the contract."""
    from grind.agents import AgentSpec, spec_to_contract

    outputs = ["report.json", "summary.txt"]
    spec = AgentSpec(name="output-test", allowed_tools=frozenset({"Read", "Write"}))
    contract = spec_to_contract(spec, required_outputs=outputs)

    assert contract.required_outputs == outputs, (
        f"required_outputs not wired through: got {contract.required_outputs}"
    )


def test_spec_to_contract_no_required_outputs_defaults_to_empty() -> None:
    """spec_to_contract() with no required_outputs produces an empty list."""
    from grind.agents import AgentSpec, spec_to_contract

    spec = AgentSpec(name="no-outputs", allowed_tools=frozenset({"Read"}))
    contract = spec_to_contract(spec)

    assert contract.required_outputs == [], (
        f"Expected [] for required_outputs, got {contract.required_outputs}"
    )


def test_spec_to_contract_denied_tools_count() -> None:
    """denied_tools count equals len(CLAUDE_CODE_TOOLS) - len(allowed_tools)."""
    from grind.agents import CLAUDE_CODE_TOOLS, AgentSpec, spec_to_contract

    allowed = frozenset({"Read", "Write", "Edit"})
    spec = AgentSpec(name="count-test", allowed_tools=allowed)
    contract = spec_to_contract(spec)

    expected_denied_count = len(CLAUDE_CODE_TOOLS) - len(allowed)
    actual_denied_count = len(contract.permissions.denied_tools)
    assert actual_denied_count == expected_denied_count, (
        f"Expected {expected_denied_count} denied tools, "
        f"got {actual_denied_count}: {contract.permissions.denied_tools}"
    )


def test_spec_to_contract_denied_tools_are_complement() -> None:
    """denied_tools is exactly CLAUDE_CODE_TOOLS minus allowed_tools (no extras, no missing)."""
    from grind.agents import CLAUDE_CODE_TOOLS, AgentSpec, spec_to_contract

    allowed = frozenset({"Read", "Glob", "Grep"})
    spec = AgentSpec(name="complement-test", allowed_tools=allowed)
    contract = spec_to_contract(spec)

    expected_denied = sorted(CLAUDE_CODE_TOOLS - allowed)
    assert contract.permissions.denied_tools == expected_denied, (
        f"denied_tools mismatch.\n"
        f"  expected: {expected_denied}\n"
        f"  got:      {contract.permissions.denied_tools}"
    )


def test_spec_to_contract_allowed_tools_is_list() -> None:
    """permissions.allowed_tools on the contract is a list, not a frozenset."""
    from grind.agents import AgentSpec, spec_to_contract

    spec = AgentSpec(name="type-check", allowed_tools=frozenset({"Read", "Glob"}))
    contract = spec_to_contract(spec)

    assert isinstance(contract.permissions.allowed_tools, list), (
        f"allowed_tools must be list; got {type(contract.permissions.allowed_tools)}"
    )


def test_spec_to_contract_denied_tools_is_list() -> None:
    """permissions.denied_tools on the contract is a list, not a frozenset."""
    from grind.agents import AgentSpec, spec_to_contract

    spec = AgentSpec(name="type-check-denied", allowed_tools=frozenset({"Read"}))
    contract = spec_to_contract(spec)

    assert isinstance(contract.permissions.denied_tools, list), (
        f"denied_tools must be list; got {type(contract.permissions.denied_tools)}"
    )


def test_frontend_agent_name() -> None:
    """frontend_agent() name field equals 'frontend'."""
    from grind.agents import frontend_agent

    spec = frontend_agent()
    assert spec.name == "frontend", (
        f"Expected frontend_agent().name == 'frontend', got {spec.name!r}"
    )


def test_data_migration_agent_name() -> None:
    """data_migration_agent() name field equals 'data_migration'."""
    from grind.agents import data_migration_agent

    spec = data_migration_agent()
    assert spec.name == "data_migration", (
        f"Expected data_migration_agent().name == 'data_migration', got {spec.name!r}"
    )


def test_frontend_agent_allowed_tools_are_sorted_on_contract() -> None:
    """spec_to_contract(frontend_agent()) allowed_tools is sorted alphabetically."""
    from grind.agents import frontend_agent, spec_to_contract

    contract = spec_to_contract(frontend_agent())
    allowed = contract.permissions.allowed_tools

    assert allowed == sorted(allowed), (
        f"allowed_tools is not sorted: {allowed}"
    )


def test_data_migration_agent_allowed_tools_are_sorted_on_contract() -> None:
    """spec_to_contract(data_migration_agent()) allowed_tools is sorted alphabetically."""
    from grind.agents import data_migration_agent, spec_to_contract

    contract = spec_to_contract(data_migration_agent())
    allowed = contract.permissions.allowed_tools

    assert allowed == sorted(allowed), (
        f"allowed_tools is not sorted: {allowed}"
    )


def test_spec_to_contract_allowed_tools_matches_spec() -> None:
    """permissions.allowed_tools on the contract contains exactly the tools in the spec."""
    from grind.agents import AgentSpec, spec_to_contract

    allowed = frozenset({"Read", "Write", "Bash"})
    spec = AgentSpec(name="exact-match", allowed_tools=allowed)
    contract = spec_to_contract(spec)

    assert set(contract.permissions.allowed_tools) == allowed, (
        f"allowed_tools mismatch.\n"
        f"  expected (set): {allowed}\n"
        f"  got (set):      {set(contract.permissions.allowed_tools)}"
    )


def test_subtract_identity_on_disjoint_sets() -> None:
    """subtract(full, disjoint_set) returns full unchanged when remove shares no elements."""
    from grind.agents import subtract

    full: frozenset[str] = frozenset({"A", "B", "C"})
    remove: frozenset[str] = frozenset({"X", "Y", "Z"})
    result = subtract(full, remove)
    assert result == full, (
        f"subtract with disjoint remove should return full; got {result}"
    )
