"""Tests for _grind_via_provider parity with the Claude path.

Uses a fake Provider that yields scripted Event objects, injected by
monkeypatching grind.providers.resolve_provider.
"""
from __future__ import annotations

from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from grind.contract import Budget, ContractStatus, ExecutionContract
from grind.engine import grind
from grind.models import GrindStatus, TaskDefinition
from grind.orchestration.events import AgentEvent, EventBus, EventType
from grind.providers import Event, EventKind


# ---------------------------------------------------------------------------
# Fake provider helpers
# ---------------------------------------------------------------------------

class FakeProvider:
    """Provider that yields a pre-scripted list of Event objects."""

    def __init__(self, events: list[Event]) -> None:
        self._events = events

    async def run(
        self,
        prompt: str,
        tools: list[str],
        config,
    ) -> AsyncIterator[Event]:
        for event in self._events:
            yield event


def _task_def(**kwargs) -> TaskDefinition:
    """Build a minimal openrouter TaskDefinition for provider-path tests."""
    defaults = dict(
        task="test task",
        verify="echo ok",
        model="openrouter/openai/gpt-4o",
        max_iterations=10,
    )
    defaults.update(kwargs)
    return TaskDefinition(**defaults)


def _iteration_event(n: int = 1) -> Event:
    return Event(kind=EventKind.ITERATION, iteration=n, max_iterations=10)


def _tool_event(name: str) -> Event:
    return Event(kind=EventKind.TOOL_USE, tool_name=name)


def _complete_event(msg: str = "done") -> Event:
    return Event(kind=EventKind.COMPLETE, message=msg)


def _stuck_event(msg: str = "stuck") -> Event:
    return Event(kind=EventKind.STUCK, message=msg)


def _error_event(msg: str = "error") -> Event:
    return Event(kind=EventKind.ERROR, message=msg)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def patch_provider():
    """Context-manager helper: patch resolve_provider with a FakeProvider."""
    def _patch(events: list[Event]):
        fake = FakeProvider(events)
        return patch("grind.providers.resolve_provider", return_value=fake)
    return _patch


# ---------------------------------------------------------------------------
# Iteration count
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_iteration_count(patch_provider):
    """3 ITERATION events → result.iterations == 3."""
    events = [
        _iteration_event(1),
        _iteration_event(2),
        _iteration_event(3),
        _complete_event("all done"),
    ]
    with patch_provider(events):
        result = await grind(_task_def())

    assert result.iterations == 3
    assert result.status == GrindStatus.COMPLETE


# ---------------------------------------------------------------------------
# Tools used (dedup)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tools_used_dedup(patch_provider):
    """TOOL_USE events for Write, Bash, Write → tools_used contains both, deduplicated."""
    events = [
        _tool_event("Write"),
        _tool_event("Bash"),
        _tool_event("Write"),   # duplicate
        _complete_event(),
    ]
    with patch_provider(events):
        result = await grind(_task_def())

    assert result.status == GrindStatus.COMPLETE
    assert set(result.tools_used) == {"Write", "Bash"}
    # No duplicates
    assert len(result.tools_used) == len(set(result.tools_used))


# ---------------------------------------------------------------------------
# on_iteration callback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_on_iteration_callback(patch_provider):
    """on_iteration invoked once per ITERATION event with (iteration, 'running')."""
    events = [
        _iteration_event(1),
        _iteration_event(2),
        _iteration_event(3),
        _complete_event(),
    ]
    calls = []
    def _on_iter(n: int, state: str) -> None:
        calls.append((n, state))

    with patch_provider(events):
        result = await grind(_task_def(), on_iteration=_on_iter)

    assert result.status == GrindStatus.COMPLETE
    assert calls == [(1, "running"), (2, "running"), (3, "running")]


# ---------------------------------------------------------------------------
# event_bus.publish
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_event_bus_publish(patch_provider):
    """event_bus.publish called for ITERATION, TOOL_USE, and COMPLETE events."""
    events = [
        _iteration_event(1),
        _tool_event("Read"),
        _complete_event("finished"),
    ]

    published: list[AgentEvent] = []

    async def _capture(event: AgentEvent) -> None:
        published.append(event)

    bus = EventBus()
    for et in EventType:
        bus.subscribe(et, _capture)

    with patch_provider(events):
        result = await grind(_task_def(), event_bus=bus)

    assert result.status == GrindStatus.COMPLETE
    # Should have: ITERATION_STARTED (iteration), ITERATION_COMPLETED (tool_use), AGENT_COMPLETED (complete)
    event_types = [e.event_type for e in published]
    assert EventType.ITERATION_STARTED in event_types
    assert EventType.AGENT_COMPLETED in event_types
    # All published events have agent_id "grind"
    assert all(e.agent_id == "grind" for e in published)


# ---------------------------------------------------------------------------
# Contract FULFILLED path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_contract_fulfilled(patch_provider, tmp_path):
    """Contract with no constraints is FULFILLED → COMPLETE returned unchanged."""
    contract = ExecutionContract(budget=Budget())  # no limits
    td = _task_def(cwd=str(tmp_path), contract=contract)

    events = [
        _tool_event("Write"),
        _complete_event("all ok"),
    ]
    with patch_provider(events):
        result = await grind(td)

    assert result.status == GrindStatus.COMPLETE
    assert result.message == "all ok"


# ---------------------------------------------------------------------------
# Contract VIOLATED path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_contract_violated(patch_provider, tmp_path):
    """Contract with max_tool_calls=0 violated → STUCK with 'Contract' in message."""
    contract = ExecutionContract(budget=Budget(max_tool_calls=0))
    td = _task_def(cwd=str(tmp_path), contract=contract)

    events = [
        _tool_event("Write"),   # 1 tool call, exceeds limit of 0
        _complete_event("done"),
    ]
    with patch_provider(events):
        result = await grind(td)

    assert result.status == GrindStatus.STUCK
    assert "Contract" in result.message


# ---------------------------------------------------------------------------
# ERROR terminal event
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_error_terminal_event(patch_provider):
    """ERROR terminal event → GrindResult with ERROR status."""
    events = [
        _iteration_event(1),
        _error_event("provider blew up"),
    ]
    with patch_provider(events):
        result = await grind(_task_def())

    assert result.status == GrindStatus.ERROR
    assert "provider blew up" in result.message
    assert result.iterations == 1


# ---------------------------------------------------------------------------
# No terminal event (provider yields nothing useful)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_terminal_event(patch_provider):
    """Provider yields no terminal event → ERROR GrindResult."""
    events: list[Event] = []   # provider immediately stops
    with patch_provider(events):
        result = await grind(_task_def())

    assert result.status == GrindStatus.ERROR


# ---------------------------------------------------------------------------
# STUCK terminal event
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stuck_terminal_event(patch_provider):
    """STUCK terminal event → GrindResult with STUCK status."""
    events = [
        _iteration_event(1),
        _iteration_event(2),
        _stuck_event("cannot proceed"),
    ]
    with patch_provider(events):
        result = await grind(_task_def())

    assert result.status == GrindStatus.STUCK
    assert "cannot proceed" in result.message
    assert result.iterations == 2
