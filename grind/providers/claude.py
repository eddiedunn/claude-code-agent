"""Claude provider adapter.

Wraps the existing Claude Agent SDK execution path in grind.engine so that
the rest of the codebase can treat Claude as just another Provider.

The ClaudeProvider delegates entirely to ``grind.engine.grind()`` — all
iteration logic, hook execution, interactive checkpoints, and contract
validation remain in engine.py.  This adapter translates the ``GrindResult``
returned by the engine into a stream of ``Event`` objects so callers that
use the Provider protocol get a consistent interface.

NOTE: Because the Claude path relies on the stateful ``ClaudeSDKClient``
context manager (which maintains conversation history across iterations),
the full loop *must* run inside engine.py.  The Provider protocol here is
therefore a run-level wrapper, not an iteration-level one.
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

from grind.models import GrindStatus, TaskDefinition
from grind.providers import Event, EventKind, RunConfig


class ClaudeProvider:
    """Provider adapter that executes tasks via the Claude Agent SDK.

    Delegates to ``grind.engine.grind()`` which owns the full iteration loop,
    hooks, checkpoints, and contract validation.
    """

    async def run(
        self,
        prompt: str,
        tools: list[str],
        config: RunConfig,
    ) -> AsyncIterator[Event]:
        """Run a task via the Claude Agent SDK and yield result Events.

        The prompt is treated as the task description.  A ``TaskDefinition``
        is constructed from *config* so the existing engine path is used
        without modification.

        Yields a single terminal Event (COMPLETE, STUCK, or ERROR) after the
        engine finishes.  Future work can add finer-grained events by wiring
        the engine's ``on_iteration`` callback.
        """
        # Import here to avoid circular imports at module load time.
        from grind.engine import grind as _engine_grind
        from grind.models import GrindHooks, InteractiveConfig, PromptConfig

        task_def = TaskDefinition(
            task=prompt,
            verify="true",          # caller is responsible for verify logic
            model=config.model,
            max_iterations=config.max_iterations,
            max_turns=config.max_turns,
            cwd=config.cwd,
            allowed_tools=tools if tools else None,
            permission_mode=config.permission_mode,
            query_timeout=config.query_timeout,
            hooks=GrindHooks(),
            prompt_config=PromptConfig(),
            interactive=InteractiveConfig(enabled=False),
        )

        result = await _engine_grind(task_def, verbose=config.verbose)

        # Translate GrindResult → Event
        if result.status == GrindStatus.COMPLETE:
            yield Event(
                kind=EventKind.COMPLETE,
                message=result.message,
                raw=result,
            )
        elif result.status == GrindStatus.STUCK:
            yield Event(
                kind=EventKind.STUCK,
                message=result.message,
                raw=result,
            )
        else:
            # MAX_ITERATIONS or ERROR
            yield Event(
                kind=EventKind.ERROR,
                message=result.message,
                raw=result,
            )

    # ------------------------------------------------------------------
    # Convenience: run with a full TaskDefinition (used by engine.py
    # when routing an existing task through the provider abstraction).
    # ------------------------------------------------------------------

    async def run_task(
        self,
        task_def: TaskDefinition,
        verbose: bool = False,
    ) -> AsyncIterator[Event]:
        """Run an already-constructed TaskDefinition and yield result Events."""
        from grind.engine import grind as _engine_grind

        result = await _engine_grind(task_def, verbose=verbose)

        if result.status == GrindStatus.COMPLETE:
            yield Event(kind=EventKind.COMPLETE, message=result.message, raw=result)
        elif result.status == GrindStatus.STUCK:
            yield Event(kind=EventKind.STUCK, message=result.message, raw=result)
        else:
            yield Event(kind=EventKind.ERROR, message=result.message, raw=result)
