#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "claude-agent-sdk>=0.1.0",
# ]
# ///
"""
Standalone grind loop script - run directly with uv:

    uv run grind.py --task "Fix tests" --verify "pytest"

For installed usage, use: uv run grind --task "..." --verify "..."
"""

import argparse
import asyncio
import sys
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
    COMPLETE = "complete"
    STUCK = "stuck"
    MAX_ITERATIONS = "max_iterations"
    ERROR = "error"


@dataclass
class GrindResult:
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


def print_banner(task: str, verify_cmd: str, max_iter: int, cwd: str) -> None:
    print("=" * 60)
    print("GRIND LOOP")
    print("=" * 60)
    print(f"Task:       {task}")
    print(f"Verify:     {verify_cmd}")
    print(f"Max iter:   {max_iter}")
    print(f"Directory:  {cwd}")
    print("=" * 60)


def print_result(result: GrindResult) -> None:
    print("\n" + "=" * 60)
    status_display = {
        GrindStatus.COMPLETE: ("COMPLETE", "Verification passed!"),
        GrindStatus.STUCK: ("STUCK", "Human intervention needed"),
        GrindStatus.MAX_ITERATIONS: ("MAX ITERATIONS", "Limit reached"),
        GrindStatus.ERROR: ("ERROR", "Execution failed"),
    }
    label, desc = status_display.get(result.status, ("UNKNOWN", "Unknown status"))
    print(f"{label} - {desc}")
    print("=" * 60)
    if result.message:
        print(f"Message: {result.message}")
    print(f"Iterations: {result.iterations}")
    print(f"Duration: {result.duration_seconds:.1f}s")
    if result.tools_used:
        print(f"Tools used: {', '.join(result.tools_used)}")


def on_iteration(iteration: int, status: str) -> None:
    print(f"\n[Iteration {iteration}] {status}...")


async def run_grind(args: argparse.Namespace) -> int:
    print_banner(args.task, args.verify, args.max_iter, args.cwd)

    result = await grind(
        task=args.task,
        verify_cmd=args.verify,
        max_iterations=args.max_iter,
        cwd=args.cwd if args.cwd != "." else None,
        verbose=args.verbose,
        on_iteration=on_iteration if not args.quiet else None,
    )

    print_result(result)

    if result.status == GrindStatus.COMPLETE:
        return 0
    elif result.status == GrindStatus.STUCK:
        return 2
    elif result.status == GrindStatus.MAX_ITERATIONS:
        return 3
    else:
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Automated fix-verify loop using Claude Agent SDK",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run grind.py --task "Fix failing tests" --verify "pytest tests/ -v"
  uv run grind.py -t "Fix SonarQube issues" -v "./sonar-check.sh" -n 8
        """,
    )
    parser.add_argument("--task", "-t", required=True, help="What needs to be fixed")
    parser.add_argument("--verify", "-v", required=True, help="Command to verify success")
    parser.add_argument("--max-iter", "-n", type=int, default=10, help="Max iterations (default: 10)")
    parser.add_argument("--cwd", "-c", default=".", help="Working directory")
    parser.add_argument("--verbose", action="store_true", help="Show full Claude output")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")

    args = parser.parse_args()

    try:
        return asyncio.run(run_grind(args))
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        return 130


if __name__ == "__main__":
    sys.exit(main())
