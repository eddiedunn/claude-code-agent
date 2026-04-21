"""Tests for the OpenRouter provider adapter.

Uses ``httpx.MockTransport`` to intercept HTTP requests without a live API key.
Each test injects a mock handler that returns pre-baked OpenAI-compatible
responses.

Coverage:
- Text-only path (no tools) still works end-to-end.
- Single tool call: model returns tool_calls, provider executes Write,
  appends tool result, then model returns GRIND_COMPLETE.
- Multi-round tools: Bash then Read then COMPLETE.
- Tool error (Read of nonexistent file) fed back as tool-role message, no ERROR.
- Path traversal rejection: returned as tool error, provider keeps running.
- Missing API key → EventKind.ERROR immediately.
- max_turns limit stops the run.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from grind.providers import Event, EventKind, RunConfig
from grind.providers.openrouter import OpenRouterProvider

# ---------------------------------------------------------------------------
# Helpers: mock response factories
# ---------------------------------------------------------------------------

def _openai_text_response(content: str, finish_reason: str = "stop") -> dict:
    """Build a minimal OpenAI-compatible chat completion response with text."""
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def _openai_tool_response(tool_calls: list[dict], content: str = "") -> dict:
    """Build a response with tool_calls (and optional narration text)."""
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": tool_calls,
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 20, "completion_tokens": 15, "total_tokens": 35},
    }


def _tool_call(name: str, arguments: dict, call_id: str = "call_1") -> dict:
    """Build a single tool_call entry."""
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(arguments),
        },
    }


class _MockHandler:
    """Stateful mock handler: pops responses from a queue on each request."""

    def __init__(self, responses: list[dict | Exception]) -> None:
        self._queue = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self._queue:
            raise RuntimeError("No more mock responses queued")
        resp = self._queue.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return httpx.Response(200, json=resp)


def _make_provider(api_key: str = "test-key") -> OpenRouterProvider:
    return OpenRouterProvider(api_key=api_key)


def _make_config(
    tmp_path: Path,
    tools: list[str] | None = None,
    max_iterations: int = 5,
    max_turns: int = 20,
) -> tuple[RunConfig, list[str]]:
    cfg = RunConfig(
        model="openai/gpt-4o",
        max_iterations=max_iterations,
        max_turns=max_turns,
        cwd=str(tmp_path),
        query_timeout=30,
    )
    tool_list = tools if tools is not None else []
    return cfg, tool_list


async def _collect(provider, prompt, tools, config) -> list[Event]:
    events = []
    async for ev in provider.run(prompt, tools, config):
        events.append(ev)
    return events


def _inject_transport(mock_handler: _MockHandler) -> AsyncMock:
    """Return a patch context for httpx.AsyncClient that uses mock_handler."""
    transport = httpx.MockTransport(mock_handler)
    # We need to patch AsyncClient so it uses our transport
    original_init = httpx.AsyncClient.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = transport
        original_init(self, *args, **kwargs)

    return patched_init


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def provider():
    return _make_provider()


# ---------------------------------------------------------------------------
# Test: missing API key → ERROR event
# ---------------------------------------------------------------------------

class TestMissingApiKey:
    @pytest.mark.asyncio
    async def test_no_key_yields_error(self, tmp_path):
        provider = OpenRouterProvider(api_key=None)
        config, tools = _make_config(tmp_path)

        # Ensure env var is not set
        import os
        env_backup = os.environ.pop("OPENROUTER_API_KEY", None)
        try:
            events = await _collect(provider, "do something", tools, config)
        finally:
            if env_backup is not None:
                os.environ["OPENROUTER_API_KEY"] = env_backup

        assert len(events) == 1
        assert events[0].kind == EventKind.ERROR
        assert "OPENROUTER_API_KEY" in events[0].message


# ---------------------------------------------------------------------------
# Test: text-only path (no tools)
# ---------------------------------------------------------------------------

class TestTextOnlyPath:
    @pytest.mark.asyncio
    async def test_complete_signal_in_first_response(self, tmp_path):
        response = _openai_text_response("All done!\nGRIND_COMPLETE")
        handler = _MockHandler([response])

        config, tools = _make_config(tmp_path, tools=[])

        with patch.object(httpx.AsyncClient, "__init__", _inject_transport(handler)):
            events = await _collect(_make_provider(), "do task", tools, config)

        kinds = [e.kind for e in events]
        assert EventKind.ITERATION in kinds
        assert EventKind.TEXT in kinds
        assert EventKind.COMPLETE in kinds

        text_events = [e for e in events if e.kind == EventKind.TEXT]
        assert any("All done" in e.text for e in text_events)

    @pytest.mark.asyncio
    async def test_stuck_signal_detected(self, tmp_path):
        response = _openai_text_response("I cannot proceed.\nGRIND_STUCK")
        handler = _MockHandler([response])
        config, tools = _make_config(tmp_path, tools=[])

        with patch.object(httpx.AsyncClient, "__init__", _inject_transport(handler)):
            events = await _collect(_make_provider(), "do task", tools, config)

        kinds = [e.kind for e in events]
        assert EventKind.STUCK in kinds
        assert EventKind.COMPLETE not in kinds

    @pytest.mark.asyncio
    async def test_no_tools_sent_in_request(self, tmp_path):
        response = _openai_text_response("Done.\nGRIND_COMPLETE")
        handler = _MockHandler([response])
        config, tools = _make_config(tmp_path, tools=[])

        with patch.object(httpx.AsyncClient, "__init__", _inject_transport(handler)):
            await _collect(_make_provider(), "do task", tools, config)

        # Verify the HTTP request did NOT include a "tools" field
        assert len(handler.requests) == 1
        body = json.loads(handler.requests[0].content)
        assert "tools" not in body

    @pytest.mark.asyncio
    async def test_text_only_system_message_mentions_no_tools(self, tmp_path):
        response = _openai_text_response("GRIND_COMPLETE")
        handler = _MockHandler([response])
        config, tools = _make_config(tmp_path, tools=[])

        with patch.object(httpx.AsyncClient, "__init__", _inject_transport(handler)):
            await _collect(_make_provider(), "task", tools, config)

        body = json.loads(handler.requests[0].content)
        system_content = body["messages"][0]["content"]
        assert "text-only" in system_content.lower() or "no" in system_content.lower()

    @pytest.mark.asyncio
    async def test_max_iterations_exhausted_yields_error(self, tmp_path):
        # Model never signals completion — should exhaust iterations
        responses = [_openai_text_response("still working...")] * 3
        handler = _MockHandler(responses)
        config, tools = _make_config(tmp_path, tools=[], max_iterations=3)

        with patch.object(httpx.AsyncClient, "__init__", _inject_transport(handler)):
            events = await _collect(_make_provider(), "task", tools, config)

        kinds = [e.kind for e in events]
        assert EventKind.ERROR in kinds
        assert EventKind.COMPLETE not in kinds


# ---------------------------------------------------------------------------
# Test: single tool call
# ---------------------------------------------------------------------------

class TestSingleToolCall:
    @pytest.mark.asyncio
    async def test_model_calls_write_then_complete(self, tmp_path):
        """Model returns Write tool call; provider executes it; model then completes."""
        write_call = _tool_call(
            "Write",
            {"file_path": "result.txt", "content": "hello from gpt\n"},
            call_id="call_write_1",
        )
        tool_response = _openai_tool_response([write_call])
        complete_response = _openai_text_response(
            "I wrote the file.\nGRIND_COMPLETE"
        )
        handler = _MockHandler([tool_response, complete_response])

        config, tools = _make_config(tmp_path, tools=["Read", "Write", "Bash"])

        with patch.object(httpx.AsyncClient, "__init__", _inject_transport(handler)):
            events = await _collect(_make_provider(), "write a file", tools, config)

        # File should actually exist
        assert (tmp_path / "result.txt").exists()
        assert (tmp_path / "result.txt").read_text() == "hello from gpt\n"

        # TOOL_USE event was emitted
        tool_events = [e for e in events if e.kind == EventKind.TOOL_USE]
        assert len(tool_events) == 1
        assert tool_events[0].tool_name == "Write"
        assert tool_events[0].tool_id == "call_write_1"
        assert tool_events[0].tool_input["file_path"] == "result.txt"

        # COMPLETE event was emitted
        kinds = [e.kind for e in events]
        assert EventKind.COMPLETE in kinds

    @pytest.mark.asyncio
    async def test_tools_sent_in_request(self, tmp_path):
        """Verify the HTTP request includes the tools schemas."""
        write_call = _tool_call("Write", {"file_path": "f.txt", "content": "x"})
        handler = _MockHandler([
            _openai_tool_response([write_call]),
            _openai_text_response("GRIND_COMPLETE"),
        ])
        config, tools = _make_config(tmp_path, tools=["Write"])

        with patch.object(httpx.AsyncClient, "__init__", _inject_transport(handler)):
            await _collect(_make_provider(), "task", tools, config)

        first_body = json.loads(handler.requests[0].content)
        assert "tools" in first_body
        tool_names = [t["function"]["name"] for t in first_body["tools"]]
        assert "Write" in tool_names

    @pytest.mark.asyncio
    async def test_tool_result_fed_back_to_model(self, tmp_path):
        """The second request should include a tool-role message."""
        write_call = _tool_call("Write", {"file_path": "f.txt", "content": "data"})
        handler = _MockHandler([
            _openai_tool_response([write_call]),
            _openai_text_response("GRIND_COMPLETE"),
        ])
        config, tools = _make_config(tmp_path, tools=["Write"])

        with patch.object(httpx.AsyncClient, "__init__", _inject_transport(handler)):
            await _collect(_make_provider(), "write", tools, config)

        # Second request should include the tool result
        second_body = json.loads(handler.requests[1].content)
        roles = [m["role"] for m in second_body["messages"]]
        assert "tool" in roles


# ---------------------------------------------------------------------------
# Test: multi-round tools
# ---------------------------------------------------------------------------

class TestMultiRoundTools:
    @pytest.mark.asyncio
    async def test_bash_then_read_then_complete(self, tmp_path):
        """Two tool calls in separate rounds before GRIND_COMPLETE."""
        bash_call = _tool_call(
            "Bash",
            {"command": "echo 'generated' > gen.txt"},
            call_id="call_bash",
        )
        read_call = _tool_call(
            "Read",
            {"file_path": "gen.txt"},
            call_id="call_read",
        )
        handler = _MockHandler([
            _openai_tool_response([bash_call]),
            _openai_tool_response([read_call]),
            _openai_text_response("File contains 'generated'. GRIND_COMPLETE"),
        ])
        config, tools = _make_config(tmp_path, tools=["Bash", "Read"])

        with patch.object(httpx.AsyncClient, "__init__", _inject_transport(handler)):
            events = await _collect(_make_provider(), "generate and read", tools, config)

        tool_events = [e for e in events if e.kind == EventKind.TOOL_USE]
        assert len(tool_events) == 2
        tool_names = [e.tool_name for e in tool_events]
        assert "Bash" in tool_names
        assert "Read" in tool_names

        kinds = [e.kind for e in events]
        assert EventKind.COMPLETE in kinds

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_in_single_response(self, tmp_path):
        """A single response can have multiple tool_calls entries."""
        calls = [
            _tool_call("Write", {"file_path": "a.txt", "content": "A"}, call_id="c1"),
            _tool_call("Write", {"file_path": "b.txt", "content": "B"}, call_id="c2"),
        ]
        handler = _MockHandler([
            _openai_tool_response(calls),
            _openai_text_response("Both written. GRIND_COMPLETE"),
        ])
        config, tools = _make_config(tmp_path, tools=["Write"])

        with patch.object(httpx.AsyncClient, "__init__", _inject_transport(handler)):
            events = await _collect(_make_provider(), "write two files", tools, config)

        assert (tmp_path / "a.txt").exists()
        assert (tmp_path / "b.txt").exists()
        tool_events = [e for e in events if e.kind == EventKind.TOOL_USE]
        assert len(tool_events) == 2


# ---------------------------------------------------------------------------
# Test: tool errors fed back as tool-role messages (not provider ERROR)
# ---------------------------------------------------------------------------

class TestToolErrors:
    @pytest.mark.asyncio
    async def test_read_nonexistent_file_fed_back_as_tool_result(self, tmp_path):
        """Read of missing file → error text in tool-role message, NOT ERROR event."""
        read_call = _tool_call(
            "Read",
            {"file_path": "nonexistent.txt"},
            call_id="call_r",
        )
        handler = _MockHandler([
            _openai_tool_response([read_call]),
            _openai_text_response("File was missing, can't proceed. GRIND_STUCK"),
        ])
        config, tools = _make_config(tmp_path, tools=["Read"])

        with patch.object(httpx.AsyncClient, "__init__", _inject_transport(handler)):
            events = await _collect(_make_provider(), "read file", tools, config)

        # No provider-level ERROR
        error_events = [e for e in events if e.kind == EventKind.ERROR]
        assert len(error_events) == 0

        # Should have STUCK
        kinds = [e.kind for e in events]
        assert EventKind.STUCK in kinds

        # Tool result was fed back (second request should have tool role message)
        second_body = json.loads(handler.requests[1].content)
        tool_messages = [m for m in second_body["messages"] if m["role"] == "tool"]
        assert len(tool_messages) == 1
        # The error text should be in the tool message content
        assert "not found" in tool_messages[0]["content"].lower() or \
               "nonexistent" in tool_messages[0]["content"].lower() or \
               "missing" in tool_messages[0]["content"].lower()

    @pytest.mark.asyncio
    async def test_bash_nonzero_exit_not_provider_error(self, tmp_path):
        """Bash with exit code 1 is a tool result, not a provider ERROR."""
        bash_call = _tool_call(
            "Bash",
            {"command": "exit 1"},
            call_id="call_b",
        )
        handler = _MockHandler([
            _openai_tool_response([bash_call]),
            _openai_text_response("Command failed. GRIND_STUCK"),
        ])
        config, tools = _make_config(tmp_path, tools=["Bash"])

        with patch.object(httpx.AsyncClient, "__init__", _inject_transport(handler)):
            events = await _collect(_make_provider(), "run command", tools, config)

        error_events = [e for e in events if e.kind == EventKind.ERROR]
        assert len(error_events) == 0


# ---------------------------------------------------------------------------
# Test: path traversal rejection
# ---------------------------------------------------------------------------

class TestPathTraversal:
    @pytest.mark.asyncio
    async def test_dotdot_path_in_read_rejected(self, tmp_path):
        """../../etc/passwd → error result fed back, not ERROR event."""
        read_call = _tool_call(
            "Read",
            {"file_path": "../../etc/passwd"},
            call_id="call_traverse",
        )
        handler = _MockHandler([
            _openai_tool_response([read_call]),
            _openai_text_response("Could not read that file. GRIND_STUCK"),
        ])
        config, tools = _make_config(tmp_path, tools=["Read"])

        with patch.object(httpx.AsyncClient, "__init__", _inject_transport(handler)):
            events = await _collect(_make_provider(), "try to read", tools, config)

        # No provider ERROR
        error_events = [e for e in events if e.kind == EventKind.ERROR]
        assert len(error_events) == 0

        # Tool result message should mention the rejection
        second_body = json.loads(handler.requests[1].content)
        tool_messages = [m for m in second_body["messages"] if m["role"] == "tool"]
        assert len(tool_messages) == 1
        msg_content = tool_messages[0]["content"].lower()
        assert "outside" in msg_content or "traversal" in msg_content or \
               "escape" in msg_content or "working directory" in msg_content

    @pytest.mark.asyncio
    async def test_dotdot_path_in_write_rejected(self, tmp_path):
        """Write to ../../evil.txt rejected and file NOT created."""
        write_call = _tool_call(
            "Write",
            {"file_path": "../../evil.txt", "content": "pwned"},
            call_id="call_w",
        )
        handler = _MockHandler([
            _openai_tool_response([write_call]),
            _openai_text_response("GRIND_STUCK"),
        ])
        config, tools = _make_config(tmp_path, tools=["Write"])

        with patch.object(httpx.AsyncClient, "__init__", _inject_transport(handler)):
            await _collect(_make_provider(), "write evil", tools, config)

        # The evil file must NOT exist two levels up
        evil = tmp_path.parent.parent / "evil.txt"
        assert not evil.exists()


# ---------------------------------------------------------------------------
# Test: max_turns limit
# ---------------------------------------------------------------------------

class TestMaxTurns:
    @pytest.mark.asyncio
    async def test_max_turns_stops_run(self, tmp_path):
        """When max_turns is exhausted the provider yields ERROR."""
        # Each response is a tool call → model never completes
        def _write_call(n):
            return _tool_call(
                "Write",
                {"file_path": f"f{n}.txt", "content": "x"},
                call_id=f"call_{n}",
            )

        responses = [_openai_tool_response([_write_call(i)]) for i in range(10)]
        handler = _MockHandler(responses)

        config, tools = _make_config(
            tmp_path, tools=["Write"], max_iterations=5, max_turns=2
        )

        with patch.object(httpx.AsyncClient, "__init__", _inject_transport(handler)):
            events = await _collect(_make_provider(), "keep writing", tools, config)

        kinds = [e.kind for e in events]
        assert EventKind.ERROR in kinds
        # Only max_turns requests should have been made
        assert len(handler.requests) <= 2


# ---------------------------------------------------------------------------
# Test: HTTP error
# ---------------------------------------------------------------------------

class TestHttpErrors:
    @pytest.mark.asyncio
    async def test_http_error_yields_provider_error(self, tmp_path):
        """A 401 from the API → EventKind.ERROR."""

        def error_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "Unauthorized"})

        transport = httpx.MockTransport(error_handler)
        original_init = httpx.AsyncClient.__init__

        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = transport
            original_init(self, *args, **kwargs)

        config, tools = _make_config(tmp_path, tools=[])

        with patch.object(httpx.AsyncClient, "__init__", patched_init):
            events = await _collect(_make_provider(), "task", tools, config)

        error_events = [e for e in events if e.kind == EventKind.ERROR]
        assert len(error_events) == 1
        assert "401" in error_events[0].message

    @pytest.mark.asyncio
    async def test_network_error_yields_provider_error(self, tmp_path):
        """A network-level exception → EventKind.ERROR."""

        def fail_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        transport = httpx.MockTransport(fail_handler)
        original_init = httpx.AsyncClient.__init__

        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = transport
            original_init(self, *args, **kwargs)

        config, tools = _make_config(tmp_path, tools=[])

        with patch.object(httpx.AsyncClient, "__init__", patched_init):
            events = await _collect(_make_provider(), "task", tools, config)

        error_events = [e for e in events if e.kind == EventKind.ERROR]
        assert len(error_events) == 1


# ---------------------------------------------------------------------------
# Test: ITERATION events
# ---------------------------------------------------------------------------

class TestIterationEvents:
    @pytest.mark.asyncio
    async def test_iteration_event_emitted_each_iteration(self, tmp_path):
        """ITERATION events should be emitted with correct iteration numbers."""
        responses = [
            _openai_text_response("still working..."),
            _openai_text_response("GRIND_COMPLETE"),
        ]
        handler = _MockHandler(responses)
        config, tools = _make_config(tmp_path, tools=[], max_iterations=5)

        with patch.object(httpx.AsyncClient, "__init__", _inject_transport(handler)):
            events = await _collect(_make_provider(), "task", tools, config)

        iter_events = [e for e in events if e.kind == EventKind.ITERATION]
        assert len(iter_events) == 2
        assert iter_events[0].iteration == 1
        assert iter_events[1].iteration == 2
        for ie in iter_events:
            assert ie.max_iterations == 5
