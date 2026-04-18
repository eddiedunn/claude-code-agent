"""Real Claude CLI executor for the self-evolution loop (Phase A)."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from grind.team import AgentTask


async def claude_executor(
    task: AgentTask,
    worktree_path: Path,
    attempt: int,
    model: str = "sonnet",
    timeout_seconds: int = 600,
) -> None:
    if shutil.which("claude") is None:
        raise RuntimeError(
            "'claude' binary not found on PATH — install Claude Code CLI"
        )

    proc = await asyncio.create_subprocess_exec(
        "claude", "-p", task.prompt, "--model", model,
        cwd=worktree_path,
    )

    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()
        raise
