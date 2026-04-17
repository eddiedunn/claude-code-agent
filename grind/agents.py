"""SDK custom agents via subtraction (Phase 5).

The core insight: start from the full Claude Code tool set, subtract everything
the domain doesn't need, produce a scoped ExecutionContract. The subtraction
is the agent definition.

Vercel removed 80% of an agent's tools and got better results — treat that
as the target ratio, not a ceiling. System prompt is secondary to tool restriction.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from grind.contract import Budget, ExecutionContract, Permissions

CLAUDE_CODE_TOOLS: frozenset[str] = frozenset({
    "Read",
    "Write",
    "Edit",
    "Bash",
    "Glob",
    "Grep",
    "Agent",
    "WebFetch",
    "WebSearch",
    "LSP",
    "NotebookEdit",
    "TodoWrite",
    "Task",
    "Monitor",
})


def subtract(full: frozenset[str], remove: frozenset[str]) -> frozenset[str]:
    """Return full minus remove — the core subtraction operation."""
    return full - remove


@dataclass
class AgentSpec:
    """Declarative specification for a domain-specialized agent.

    The allowed_tools set IS the agent definition. Everything else follows.
    """

    name: str
    allowed_tools: frozenset[str]
    system_prompt_suffix: str = field(default="")


def spec_to_contract(
    spec: AgentSpec,
    required_outputs: list[str] | None = None,
    budget: Budget | None = None,
) -> ExecutionContract:
    """Build an ExecutionContract from an AgentSpec.

    permissions.allowed_tools ← spec.allowed_tools
    permissions.denied_tools  ← CLAUDE_CODE_TOOLS - spec.allowed_tools
    """
    denied: frozenset[str] = CLAUDE_CODE_TOOLS - spec.allowed_tools
    return ExecutionContract(
        required_outputs=required_outputs or [],
        budget=budget or Budget(),
        permissions=Permissions(
            allowed_tools=sorted(spec.allowed_tools),
            denied_tools=sorted(denied),
        ),
    )


def frontend_agent() -> AgentSpec:
    """Frontend-only agent: read files and find components.

    2/14 tools = 14.3% of the full set. Bash, Write, and network tools
    are all removed — a frontend reader has no need for them.
    """
    return AgentSpec(
        name="frontend",
        allowed_tools=frozenset({"Read", "Glob"}),
    )


def data_migration_agent() -> AgentSpec:
    """Data migration agent: read schemas and run migration scripts.

    2/14 tools = 14.3% of the full set. Network access, IDE tools, and
    file editing are removed — migrations read and execute, nothing else.
    """
    return AgentSpec(
        name="data_migration",
        allowed_tools=frozenset({"Read", "Bash"}),
    )
