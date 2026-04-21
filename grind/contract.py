"""Execution contract primitives for agent call enforcement.

Every agent call must declare a contract before it executes. The contract
is enforced by the harness, not the prompt. Contract violations are
first-class trace events emitted to the observer.

Contracts compose: a parent contract constrains child contracts. A child
budget cannot exceed its parent's budget on any axis.
"""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from grind.observer.models import EventType


@dataclass
class Budget:
    """Resource budget for an agent call."""

    max_tokens: int | None = None
    max_wall_time_s: float | None = None
    max_tool_calls: int | None = None


@dataclass
class Permissions:
    """Tool permissions for an agent call."""

    allowed_tools: list[str] = field(default_factory=list)
    denied_tools: list[str] = field(default_factory=list)


@dataclass
class ExecutionContract:
    """Contract every agent invocation must declare before execution.

    Fields map directly to the Phase 3 specification:
    - required_outputs: artifact paths the call must produce in state/
    - budget: resource limits enforced by the harness
    - permissions: tool allow/deny list
    - completion_conditions: declarative success criteria
    - output_paths: canonical landing locations in worktree state/
    - parent: optional parent contract; child budget cannot exceed parent
    """

    required_outputs: list[str] = field(default_factory=list)
    budget: Budget = field(default_factory=Budget)
    permissions: Permissions = field(default_factory=Permissions)
    completion_conditions: list[str] = field(default_factory=list)
    output_paths: list[str] = field(default_factory=list)
    parent: ExecutionContract | None = None


class ContractViolationError(Exception):
    """Raised when a contract is violated programmatically."""

    pass


class ContractStatus(str, Enum):
    """Outcome of a contract validation."""

    FULFILLED = "fulfilled"
    VIOLATED = "violated"
    TIMEOUT = "timeout"


@dataclass
class ContractResult:
    """Result of validating an execution contract."""

    status: ContractStatus
    actual_outputs: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)


def _emit_violation(
    observer_url: str,
    session_id: str,
    violations: list[str],
    agent_name: str = "",
) -> None:
    """Fire-and-forget CONTRACT_VIOLATION event to the observer."""
    payload: dict[str, object] = {
        "event_type": EventType.CONTRACT_VIOLATION.value,
        "session_id": session_id,
        "agent_name": agent_name,
        "timestamp": time.time(),
        "tool_name": "contract_validate",
        "payload": {"violations": violations},
    }
    try:
        req = urllib.request.Request(
            f"{observer_url}/events",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        pass  # observer is optional — never block contract validation


def validate(
    contract: ExecutionContract,
    worktree_path: Path,
    observer_url: str | None = None,
    session_id: str = "",
    actual_tool_calls: int | None = None,
    actual_tokens: int | None = None,
    actual_wall_time_s: float | None = None,
    tool_used: str | None = None,
    agent_name: str = "",
    timed_out: bool = False,
) -> ContractResult:
    """Validate an execution contract against a worktree's state.

    Checks are applied in this order (earlier checks are "immediate"):
    0. Timeout: if timed_out is True, return TIMEOUT immediately.
    1. Parent composition: child budget must not exceed parent on any axis.
    2. Budget: actual usage must not exceed declared limits.
    3. Permissions: tool_used must not appear in denied_tools or must be in allowed_tools.
    4. Required outputs: each path must exist under worktree state/.

    A CONTRACT_VIOLATION event is emitted to observer_url if any check fails.

    Args:
        contract: The contract to validate.
        worktree_path: Path to the worktree root.
        observer_url: Optional observer server URL for event emission.
        session_id: Session ID used in emitted events.
        actual_tool_calls: Actual tool calls made (compared against budget).
        actual_tokens: Actual tokens used (compared against budget).
        actual_wall_time_s: Actual wall time in seconds (compared against budget).
        tool_used: Name of a tool that was used (checked against denied_tools/allowed_tools).
        agent_name: Agent name used in emitted events.
        timed_out: If True, return TIMEOUT immediately before all other checks.

    Returns:
        ContractResult with status, actual_outputs list, and violations list.
    """
    if timed_out:
        if observer_url:
            _emit_violation(
                observer_url, session_id, ["execution timed out"], agent_name=agent_name
            )
        return ContractResult(
            status=ContractStatus.TIMEOUT,
            violations=["execution timed out"],
        )

    violations: list[str] = []
    state_dir = worktree_path / "state"

    # 1. Parent composition: child budget cannot exceed parent
    if contract.parent is not None:
        pb = contract.parent.budget
        cb = contract.budget
        if pb.max_tokens is not None and cb.max_tokens is not None:
            if cb.max_tokens > pb.max_tokens:
                violations.append(
                    f"child max_tokens={cb.max_tokens} exceeds "
                    f"parent max_tokens={pb.max_tokens}"
                )
        if pb.max_wall_time_s is not None and cb.max_wall_time_s is not None:
            if cb.max_wall_time_s > pb.max_wall_time_s:
                violations.append(
                    f"child max_wall_time_s={cb.max_wall_time_s} exceeds "
                    f"parent max_wall_time_s={pb.max_wall_time_s}"
                )
        if pb.max_tool_calls is not None and cb.max_tool_calls is not None:
            if cb.max_tool_calls > pb.max_tool_calls:
                violations.append(
                    f"child max_tool_calls={cb.max_tool_calls} exceeds "
                    f"parent max_tool_calls={pb.max_tool_calls}"
                )

    # 2. Budget checks
    b = contract.budget
    if b.max_tool_calls is not None and actual_tool_calls is not None:
        if actual_tool_calls > b.max_tool_calls:
            violations.append(
                f"actual_tool_calls={actual_tool_calls} exceeds "
                f"budget max_tool_calls={b.max_tool_calls}"
            )
    if b.max_tokens is not None and actual_tokens is not None:
        if actual_tokens > b.max_tokens:
            violations.append(
                f"actual_tokens={actual_tokens} exceeds "
                f"budget max_tokens={b.max_tokens}"
            )
    if b.max_wall_time_s is not None and actual_wall_time_s is not None:
        if actual_wall_time_s > b.max_wall_time_s:
            violations.append(
                f"actual_wall_time_s={actual_wall_time_s} exceeds "
                f"budget max_wall_time_s={b.max_wall_time_s}"
            )

    # 3. Permission checks
    if tool_used is not None and tool_used in contract.permissions.denied_tools:
        violations.append(f"tool '{tool_used}' is in denied_tools")
    if (
        tool_used is not None
        and contract.permissions.allowed_tools
        and tool_used not in contract.permissions.allowed_tools
    ):
        violations.append(f"tool '{tool_used}' is not in allowed_tools")

    # 4. Required outputs: must exist under state/
    actual_outputs: list[str] = []
    for output_key in contract.required_outputs:
        output_path = state_dir / output_key
        if output_path.exists():
            actual_outputs.append(output_key)
        else:
            violations.append(f"required output missing: {output_key}")

    if violations and observer_url:
        _emit_violation(observer_url, session_id, violations, agent_name=agent_name)

    status = ContractStatus.FULFILLED if not violations else ContractStatus.VIOLATED
    return ContractResult(
        status=status,
        actual_outputs=actual_outputs,
        violations=violations,
    )
