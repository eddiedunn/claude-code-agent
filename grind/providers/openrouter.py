"""OpenRouter provider adapter.

Sends requests to the OpenRouter API (https://openrouter.ai/api/v1) using
``httpx`` for async HTTP.  Authentication is via the ``OPENROUTER_API_KEY``
environment variable.

## Current state: text-only skeleton

This adapter supports basic chat completions (single-turn: prompt → text
response).  The grind loop (multiple iterations, GRIND_COMPLETE / GRIND_STUCK
signals) is implemented via a simple retry loop that re-sends the full
conversation history on each iteration.

### What is stubbed / not yet implemented

- **Tool use**: OpenRouter proxies OpenAI-compatible tool-use semantics, but
  different upstream models handle function-calling differently.  A translation
  layer that maps grind's tool list (Read, Write, Bash, …) to OpenAI-style
  function schemas is a future task.  For now, ``tools`` is accepted but
  ignored, and a note is prepended to the prompt informing the model it has
  no tools available.  TODO: implement tool-use translation for OpenRouter.

- **Streaming**: Responses are collected non-streaming for simplicity.
  TODO: switch to streaming for better UX on long completions.

- **Hooks / checkpoints**: The Claude adapter delegates to engine.py which
  owns hooks and interactive checkpoints.  The OpenRouter adapter cannot reuse
  engine.py (it's SDK-specific), so hooks are not executed.
  TODO: extract hook execution from engine.py into a provider-agnostic layer.

- **Cost tracking / token counting**: Not yet surfaced in Event payloads.
"""
from __future__ import annotations

import asyncio
import os
from typing import AsyncIterator

import httpx

from grind.providers import Event, EventKind, RunConfig

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_CHAT_ENDPOINT = f"{OPENROUTER_BASE_URL}/chat/completions"

# Grind completion signals — same patterns engine.py looks for
_COMPLETE_SIGNAL = "GRIND_COMPLETE"
_STUCK_SIGNAL = "GRIND_STUCK"

_NO_TOOLS_NOTICE = (
    "[Note: You are running in text-only mode. "
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
        async for event in provider.run(prompt, tools=[], config=config):
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

        Implements a simple iteration loop:
        1. Send system prompt + task description.
        2. Check response for GRIND_COMPLETE / GRIND_STUCK signals.
        3. If neither found and iterations remain, send continue prompt.
        4. Yield a terminal Event (COMPLETE / STUCK / ERROR).
        """
        api_key = self._api_key or os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            yield Event(
                kind=EventKind.ERROR,
                message="OPENROUTER_API_KEY environment variable is not set.",
            )
            return

        # Build system message
        system_parts = [
            "You are an AI assistant executing an automated task.",
            "When you complete the task successfully, output GRIND_COMPLETE on its own line.",
            "If you cannot proceed, output GRIND_STUCK on its own line.",
        ]
        if tools:
            # TODO: translate grind tools to OpenAI function schemas
            system_parts.append(
                f"[Note: Tool use ({', '.join(tools)}) is not yet implemented "
                "for OpenRouter. Describe changes rather than executing them.]"
            )
        else:
            system_parts.append(_NO_TOOLS_NOTICE)

        system_content = "  ".join(system_parts)

        # Conversation history (grows across iterations)
        messages: list[dict] = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt},
        ]

        async with httpx.AsyncClient(timeout=config.query_timeout) as client:
            for iteration in range(1, config.max_iterations + 1):
                # Emit iteration boundary event
                yield Event(
                    kind=EventKind.ITERATION,
                    iteration=iteration,
                    max_iterations=config.max_iterations,
                )

                try:
                    response_text = await self._chat(
                        client, api_key, config.model, messages
                    )
                except httpx.HTTPStatusError as exc:
                    yield Event(
                        kind=EventKind.ERROR,
                        message=f"OpenRouter HTTP {exc.response.status_code}: {exc.response.text}",
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

                # Emit text event
                yield Event(kind=EventKind.TEXT, text=response_text)

                # Check for completion signals
                if _COMPLETE_SIGNAL in response_text:
                    yield Event(kind=EventKind.COMPLETE, message="Task completed")
                    return

                if _STUCK_SIGNAL in response_text:
                    yield Event(kind=EventKind.STUCK, message="Model declared stuck")
                    return

                # Append assistant response and continue prompt to history
                messages.append({"role": "assistant", "content": response_text})
                if iteration < config.max_iterations:
                    messages.append({"role": "user", "content": _CONTINUE_PROMPT})

        # Exhausted iterations without a terminal signal
        yield Event(
            kind=EventKind.ERROR,
            message=f"Reached max iterations ({config.max_iterations}) without completion signal",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _chat(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        model: str,
        messages: list[dict],
    ) -> str:
        """Send a chat completion request and return the assistant text."""
        payload = {
            "model": model,
            "messages": messages,
        }
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
        data = response.json()
        # OpenAI-compatible response shape
        return data["choices"][0]["message"]["content"]
