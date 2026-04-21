"""OpenRouter provider adapter.

Sends requests to the OpenRouter API (https://openrouter.ai/api/v1) using
``httpx`` for async HTTP.  Authentication is via the ``OPENROUTER_API_KEY``
environment variable.

## Tool use

When ``tools`` is non-empty, this adapter translates grind's tool list to
OpenAI-compatible function schemas (via ``openrouter_tools.build_tool_schemas``),
sends them with each chat completion request, and executes any returned
``tool_calls`` locally inside ``config.cwd``.

Tool execution is purely in-process (no SDK dependency):
- Read / Write / Edit operate on the filesystem relative to ``config.cwd``.
- Bash runs via ``subprocess`` with a 60-second timeout.
- Glob / Grep search the worktree.
- Paths that escape ``config.cwd`` are rejected and returned as tool errors.

Each tool invocation emits a ``TOOL_USE`` event before execution so the
caller's UI/logger sees real-time progress.

## Message loop (per iteration)

Within a single grind iteration the provider runs an inner tool loop:
1. Send messages (including accumulated tool results) to the model.
2. If the response has ``tool_calls`` → execute each, emit TOOL_USE events,
   append tool-result messages, go to 1.
3. If the response has text → emit TEXT event, check for GRIND_COMPLETE /
   GRIND_STUCK, handle accordingly.

``config.max_turns`` caps the total number of model calls across all
iterations combined.

## Backwards compat

If ``tools`` is empty, the adapter falls back to the original text-only
behaviour and does NOT send a ``tools`` field in the request payload.
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from typing import AsyncIterator

import httpx

from grind.providers import Event, EventKind, RunConfig

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_CHAT_ENDPOINT = f"{OPENROUTER_BASE_URL}/chat/completions"

# Grind completion signals — same patterns engine.py looks for
_COMPLETE_SIGNAL = "GRIND_COMPLETE"
_STUCK_SIGNAL = "GRIND_STUCK"

_SYSTEM_BASE = (
    "You are an AI assistant executing an automated task.\n"
    "When you have finished the task successfully, output GRIND_COMPLETE on its own line.\n"
    "If you cannot proceed and need to give up, output GRIND_STUCK on its own line.\n"
)

_SYSTEM_WITH_TOOLS = (
    _SYSTEM_BASE
    + "\nYou have access to file system tools (Read, Write, Edit, Bash, Glob, Grep). "
    "Use them to complete the task. Do NOT just describe what you would do — "
    "actually execute the tools. When the task is done, output GRIND_COMPLETE."
)

_SYSTEM_NO_TOOLS = (
    _SYSTEM_BASE
    + "\n[Note: You are running in text-only mode. "
    "No file system tools are available. "
    "Describe what you would do rather than executing commands.]"
)

_CONTINUE_PROMPT = (
    "Continue working on the task. "
    "When you have finished, output GRIND_COMPLETE on its own line. "
    "If you are stuck and cannot proceed, output GRIND_STUCK on its own line."
)


class OpenRouterProvider:
    """Provider adapter that executes tasks via the OpenRouter API.

    Authentication: set ``OPENROUTER_API_KEY`` in the environment.

    Usage::

        provider = OpenRouterProvider()
        async for event in provider.run(prompt, tools=["Read","Write","Bash"], config=config):
            ...
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key  # if None, read from env at call time

    # ------------------------------------------------------------------
    # Provider protocol implementation
    # ------------------------------------------------------------------

    async def run(
        self,
        prompt: str,
        tools: list[str],
        config: RunConfig,
    ) -> AsyncIterator[Event]:
        """Run a task against an OpenRouter model and yield Events.

        Drives the complete grind iteration loop.  Each iteration may involve
        multiple model calls (tool-call rounds) before the model signals
        completion or the iteration budget is exhausted.

        Yields:
            ITERATION events at each iteration boundary.
            TEXT events for assistant narration.
            TOOL_USE events before each tool execution.
            COMPLETE / STUCK / ERROR terminal events.
        """
        api_key = self._api_key or os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            yield Event(
                kind=EventKind.ERROR,
                message="OPENROUTER_API_KEY environment variable is not set.",
            )
            return

        # Build tool schemas (empty list → text-only mode)
        from grind.providers.openrouter_tools import build_tool_schemas, execute_tool

        use_tools = bool(tools)
        tool_schemas = build_tool_schemas(tools) if use_tools else []
        cwd = config.cwd or os.getcwd()

        system_content = _SYSTEM_WITH_TOOLS if use_tools else _SYSTEM_NO_TOOLS

        # Conversation history — grows across all iterations and tool rounds
        messages: list[dict] = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt},
        ]

        turns_used = 0  # total model calls across all iterations

        async with httpx.AsyncClient(timeout=config.query_timeout) as client:
            for iteration in range(1, config.max_iterations + 1):
                yield Event(
                    kind=EventKind.ITERATION,
                    iteration=iteration,
                    max_iterations=config.max_iterations,
                )

                # ---- inner tool loop for this iteration ----
                completed_this_iter = False

                while True:
                    if turns_used >= config.max_turns:
                        yield Event(
                            kind=EventKind.ERROR,
                            message=(
                                f"Reached max_turns ({config.max_turns}) "
                                "without a completion signal"
                            ),
                        )
                        return

                    # --- call the model ---
                    try:
                        response_data = await self._chat_raw(
                            client, api_key, config.model, messages, tool_schemas
                        )
                    except httpx.HTTPStatusError as exc:
                        yield Event(
                            kind=EventKind.ERROR,
                            message=(
                                f"OpenRouter HTTP {exc.response.status_code}: "
                                f"{exc.response.text}"
                            ),
                            raw=exc,
                        )
                        return
                    except Exception as exc:  # noqa: BLE001
                        yield Event(
                            kind=EventKind.ERROR,
                            message=f"OpenRouter request failed: {exc}",
                            raw=exc,
                        )
                        return

                    turns_used += 1
                    choice = response_data["choices"][0]
                    message = choice["message"]
                    finish_reason = choice.get("finish_reason", "")

                    # --- handle tool_calls ---
                    tool_calls = message.get("tool_calls") or []
                    if tool_calls:
                        # Add assistant message with tool_calls to history
                        messages.append(
                            {
                                "role": "assistant",
                                "content": message.get("content") or "",
                                "tool_calls": tool_calls,
                            }
                        )

                        # If there's accompanying assistant text, emit it
                        if message.get("content"):
                            yield Event(
                                kind=EventKind.TEXT,
                                text=message["content"],
                            )

                        # Execute each tool call and collect results
                        for tc in tool_calls:
                            tool_id = tc.get("id") or str(uuid.uuid4())
                            fn = tc.get("function", {})
                            tool_name = fn.get("name", "")
                            raw_args = fn.get("arguments", "{}")
                            try:
                                tool_input = json.loads(raw_args) if raw_args else {}
                            except json.JSONDecodeError:
                                tool_input = {"_raw": raw_args}

                            # Emit TOOL_USE event before execution
                            yield Event(
                                kind=EventKind.TOOL_USE,
                                tool_name=tool_name,
                                tool_id=tool_id,
                                tool_input=tool_input,
                            )

                            # Execute locally
                            result_text, is_error = execute_tool(
                                tool_name, tool_input, cwd
                            )

                            # Append tool result to conversation
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tool_id,
                                    "content": result_text,
                                }
                            )

                        # Continue inner loop — ask model to proceed
                        continue

                    # --- no tool_calls: pure text response ---
                    response_text = message.get("content") or ""
                    messages.append({"role": "assistant", "content": response_text})

                    # Emit text event
                    if response_text:
                        yield Event(kind=EventKind.TEXT, text=response_text)

                    # Check completion signals
                    if _COMPLETE_SIGNAL in response_text:
                        yield Event(kind=EventKind.COMPLETE, message="Task completed")
                        return

                    if _STUCK_SIGNAL in response_text:
                        yield Event(kind=EventKind.STUCK, message="Model declared stuck")
                        return

                    # No completion signal — iteration done, break to outer loop
                    completed_this_iter = True
                    break

                # If we exited cleanly from this iteration, inject continue prompt
                if completed_this_iter and iteration < config.max_iterations:
                    messages.append({"role": "user", "content": _CONTINUE_PROMPT})

        # Exhausted iterations without a terminal signal
        yield Event(
            kind=EventKind.ERROR,
            message=(
                f"Reached max iterations ({config.max_iterations}) "
                "without a completion signal"
            ),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _chat_raw(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        model: str,
        messages: list[dict],
        tool_schemas: list[dict],
    ) -> dict:
        """Send a chat completion request and return the raw response dict.

        Args:
            client: Shared httpx async client.
            api_key: OpenRouter API key.
            model: Bare model name (provider prefix already stripped).
            messages: Full conversation history.
            tool_schemas: OpenAI function schemas; empty list → no tools sent.

        Returns:
            Parsed JSON response dict from the API.
        """
        payload: dict = {
            "model": model,
            "messages": messages,
        }
        if tool_schemas:
            payload["tools"] = tool_schemas
            # Let the model decide when to call tools
            payload["tool_choice"] = "auto"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/grind-loop/grind",
            "X-Title": "grind",
        }
        response = await client.post(
            OPENROUTER_CHAT_ENDPOINT,
            json=payload,
            headers=headers,
        )
        response.raise_for_status()
        return response.json()

    async def _chat(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        model: str,
        messages: list[dict],
    ) -> str:
        """Send a chat completion request and return the assistant text.

        Convenience wrapper used by legacy callers and tests that don't need
        the full response dict.
        """
        data = await self._chat_raw(client, api_key, model, messages, [])
        return data["choices"][0]["message"]["content"]
