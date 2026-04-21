"""Provider abstraction for grind.

A Provider encapsulates a full task execution loop for a specific model/API.
The engine calls ``resolve_provider(model_id)`` to get the right provider,
then calls ``provider.run(prompt, tools, config)`` which yields ``Event``
objects for each notable occurrence in the run.

Model ID format:  ``<provider>/<model>``
  - ``claude/sonnet``             → ClaudeProvider (default)
  - ``openrouter/openai/gpt-4o``  → OpenRouterProvider

The prefix before the first ``/`` names the provider.  If no prefix is
present the whole string is treated as a bare Claude model name.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, AsyncIterator, Protocol, runtime_checkable

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# RunConfig — provider-agnostic task configuration
# ---------------------------------------------------------------------------

@dataclass
class RunConfig:
    """Provider-agnostic configuration for a single task run."""
    model: str                          # bare model name after provider prefix is stripped
    max_iterations: int = 10
    max_turns: int = 50
    cwd: str | None = None
    allowed_tools: list[str] | None = None
    permission_mode: str = "acceptEdits"
    query_timeout: int = 300
    verbose: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------

class EventKind(Enum):
    TEXT = "text"            # assistant produced text
    TOOL_USE = "tool_use"    # assistant invoked a tool
    COMPLETE = "complete"    # task finished successfully (GRIND_COMPLETE)
    STUCK = "stuck"          # task declared stuck (GRIND_STUCK)
    ERROR = "error"          # provider-level error
    ITERATION = "iteration"  # iteration boundary (for progress tracking)


@dataclass
class Event:
    """A single event emitted by a Provider during a run.

    Only the fields relevant to each *kind* will be populated:

    - TEXT:       text
    - TOOL_USE:   tool_name, tool_id, tool_input
    - COMPLETE:   message
    - STUCK:      message
    - ERROR:      message
    - ITERATION:  iteration (int), max_iterations (int)
    """
    kind: EventKind
    # TEXT / COMPLETE / STUCK / ERROR
    text: str = ""
    message: str = ""
    # TOOL_USE
    tool_name: str = ""
    tool_id: str = ""
    tool_input: dict[str, Any] = field(default_factory=dict)
    # ITERATION
    iteration: int = 0
    max_iterations: int = 0
    # raw provider payload for debugging
    raw: Any = None


# ---------------------------------------------------------------------------
# Provider protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class Provider(Protocol):
    """Protocol that all provider adapters must satisfy.

    ``run`` drives the *entire* task loop (system-prompt → iterations →
    completion signal) and yields ``Event`` objects as execution proceeds.
    It is the caller's responsibility to stop iterating after an event whose
    kind is COMPLETE, STUCK, or ERROR.
    """

    async def run(
        self,
        prompt: str,
        tools: list[str],
        config: RunConfig,
    ) -> AsyncIterator[Event]:
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def resolve_provider(model_id: str) -> "Provider":
    """Return the Provider instance for *model_id*.

    Parses the ``<provider>/<model>`` prefix.  Defaults to ``claude`` when no
    provider prefix is present (e.g. ``"sonnet"`` → ClaudeProvider).

    Raises ``ValueError`` for unknown provider prefixes.
    """
    provider_name, _ = _split_model_id(model_id)

    if provider_name == "claude":
        from grind.providers.claude import ClaudeProvider
        return ClaudeProvider()

    if provider_name == "openrouter":
        from grind.providers.openrouter import OpenRouterProvider
        return OpenRouterProvider()

    raise ValueError(
        f"Unknown provider '{provider_name}' in model ID '{model_id}'. "
        "Known providers: claude, openrouter"
    )


def _split_model_id(model_id: str) -> tuple[str, str]:
    """Return (provider_name, bare_model).

    Examples:
        "claude/sonnet"              → ("claude", "sonnet")
        "openrouter/openai/gpt-4o"   → ("openrouter", "openai/gpt-4o")
        "sonnet"                     → ("claude", "sonnet")
        "haiku"                      → ("claude", "haiku")
    """
    _KNOWN_PROVIDERS = ("claude", "openrouter")
    if "/" in model_id:
        prefix, rest = model_id.split("/", 1)
        if prefix in _KNOWN_PROVIDERS:
            return prefix, rest
    # No recognised prefix — treat as bare Claude model name
    return "claude", model_id
