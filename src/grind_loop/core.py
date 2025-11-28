"""
Core grind loop implementation.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)


class GrindStatus(Enum):
    """Status of a grind loop execution."""

    COMPLETE = "complete"
    STUCK = "stuck"
    MAX_ITERATIONS = "max_iterations"
    ERROR = "error"


@dataclass
class GrindResult:
    """Result of a grind loop execution."""

    status: GrindStatus
    iterations: int
    message: str = ""
    tools_used: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


GRIND_PROMPT_TEMPLATE = """
You are in an automated fix-verify loop. Your mission:

## TASK
{task}

## VERIFICATION
Run this command to check success: `{verify_cmd}`

## PROCESS
1. First, run the verification command to see current state
2. Analyze the failures/errors carefully
3. Make targeted fixes (prefer minimal, focused changes)
4. Run verification again
5. Repeat until verification passes

## SIGNALS (use these exact strings in your response)
- When verification passes completely: say "GRIND_COMPLETE"
- If you're stuck and need human help: say "GRIND_STUCK: <reason>"
- To report progress between iterations: say "GRIND_PROGRESS: <summary>"

## RULES
- Focus on ONE issue at a time when possible
- After each fix, re-run verification to confirm
- Don't make speculative changes - verify each step
- If the same fix fails twice, try a different approach
- Read error messages carefully - they often tell you exactly what's wrong
- Check file paths and imports when you see "not found" errors

Begin by running the verification command to see the current state.
"""

CONTINUE_PROMPT = (
    "Continue. Check verification status and fix any remaining issues. "
    "Remember to signal GRIND_COMPLETE when done, or GRIND_STUCK if you need help."
)


async def grind(
    task: str,
    verify_cmd: str,
    max_iterations: int = 10,
    cwd: str | None = None,
    allowed_tools: list[str] | None = None,
    verbose: bool = False,
    on_iteration: Callable[[int, str], None] | None = None,
) -> GrindResult:
    """
    Run an automated fix-verify loop.

    Args:
        task: Description of what needs to be fixed
        verify_cmd: Command to run to verify success (exit 0 = success)
        max_iterations: Maximum number of fix-verify cycles
        cwd: Working directory for the agent
        allowed_tools: List of tools the agent can use (defaults to common set)
        verbose: Print full agent output
        on_iteration: Callback called at start of each iteration(iteration_num, status)

    Returns:
        GrindResult with status, iteration count, and details

    Example:
        result = await grind(
            task="Fix failing unit tests",
            verify_cmd="pytest tests/ -v",
            max_iterations=5
        )
        if result.status == GrindStatus.COMPLETE:
            print("All tests passing!")
    """
    if allowed_tools is None:
        allowed_tools = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]

    options = ClaudeAgentOptions(
        allowed_tools=allowed_tools,
        permission_mode="acceptEdits",
        cwd=cwd,
        max_turns=50,
    )

    start_time = datetime.now()
    all_tools_used: list[str] = []

    try:
        async with ClaudeSDKClient(options=options) as client:
            initial_prompt = GRIND_PROMPT_TEMPLATE.format(task=task, verify_cmd=verify_cmd)
            await client.query(initial_prompt)

            iteration = 0
            while iteration < max_iterations:
                iteration += 1

                if on_iteration:
                    on_iteration(iteration, "running")

                if verbose:
                    print(f"\n{'='*60}")
                    print(f"ITERATION {iteration}/{max_iterations}")
                    print("=" * 60)

                collected_text = ""
                iteration_tools: list[str] = []

                async for message in client.receive_response():
                    if isinstance(message, AssistantMessage):
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                if verbose:
                                    print(block.text)
                                collected_text += block.text
                            elif isinstance(block, ToolUseBlock):
                                iteration_tools.append(block.name)
                                if verbose:
                                    print(f"  -> {block.name}")

                    elif isinstance(message, ResultMessage):
                        all_tools_used.extend(iteration_tools)
                        duration = (datetime.now() - start_time).total_seconds()

                        if "GRIND_COMPLETE" in collected_text:
                            msg = ""
                            if "GRIND_COMPLETE:" in collected_text:
                                msg = collected_text.split("GRIND_COMPLETE:")[1].split("\n")[0].strip()
                            return GrindResult(
                                status=GrindStatus.COMPLETE,
                                iterations=iteration,
                                message=msg,
                                tools_used=list(set(all_tools_used)),
                                duration_seconds=duration,
                            )

                        if "GRIND_STUCK" in collected_text:
                            reason = "Unknown reason"
                            if "GRIND_STUCK:" in collected_text:
                                reason = collected_text.split("GRIND_STUCK:")[1].split("\n")[0].strip()
                            return GrindResult(
                                status=GrindStatus.STUCK,
                                iterations=iteration,
                                message=reason,
                                tools_used=list(set(all_tools_used)),
                                duration_seconds=duration,
                            )

                        if verbose and "GRIND_PROGRESS:" in collected_text:
                            progress = collected_text.split("GRIND_PROGRESS:")[1].split("\n")[0].strip()
                            print(f"Progress: {progress}")

                if iteration < max_iterations:
                    await client.query(CONTINUE_PROMPT)

            duration = (datetime.now() - start_time).total_seconds()
            return GrindResult(
                status=GrindStatus.MAX_ITERATIONS,
                iterations=iteration,
                message=f"Reached maximum iterations ({max_iterations})",
                tools_used=list(set(all_tools_used)),
                duration_seconds=duration,
            )

    except Exception as e:
        duration = (datetime.now() - start_time).total_seconds()
        return GrindResult(
            status=GrindStatus.ERROR,
            iterations=0,
            message=str(e),
            tools_used=list(set(all_tools_used)),
            duration_seconds=duration,
        )
