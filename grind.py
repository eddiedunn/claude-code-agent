#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "claude-agent-sdk>=0.1.0",
#     "pyyaml>=6.0",
# ]
# ///
"""
Standalone grind loop script - run directly with uv:

    uv run grind.py --task "Fix tests" --verify "pytest"
    uv run grind.py decompose -p "Fix all failures" -v "pytest" -o tasks.yaml
    uv run grind.py batch tasks.yaml

For installed usage: uv run grind --task "..." --verify "..."
"""

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable

import yaml
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


@dataclass
class TaskDefinition:
    task: str
    verify: str
    max_iterations: int = 10
    cwd: str | None = None


@dataclass
class BatchResult:
    total: int
    completed: int
    stuck: int
    failed: int
    results: list[tuple[str, GrindResult]]
    duration_seconds: float


GRIND_PROMPT = """
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
- To report progress: say "GRIND_PROGRESS: <summary>"

## RULES
- Focus on ONE issue at a time when possible
- After each fix, re-run verification to confirm
- Don't make speculative changes - verify each step
- If the same fix fails twice, try a different approach

Begin by running the verification command.
"""

CONTINUE_PROMPT = (
    "Continue. Check verification status and fix remaining issues. "
    "Signal GRIND_COMPLETE when done, or GRIND_STUCK if you need help."
)

DECOMPOSE_PROMPT = """
Analyze this problem and break it into independent subtasks.

## PROBLEM
{problem}

## VERIFICATION COMMAND
{verify_cmd}

## YOUR TASK
1. Run the verification command to see failures
2. Group related issues that should be fixed together
3. Output a JSON task list

## OUTPUT FORMAT (JSON only, no markdown):
{{
  "tasks": [
    {{"task": "Description of what to fix", "verify": "verification command", "max_iterations": 5}}
  ]
}}

Group by file or issue type. Order by dependency.
"""


async def grind(
    task: str,
    verify_cmd: str,
    max_iterations: int = 10,
    cwd: str | None = None,
    verbose: bool = False,
    on_iteration: Callable[[int, str], None] | None = None,
) -> GrindResult:
    options = ClaudeAgentOptions(
        allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
        permission_mode="acceptEdits",
        cwd=cwd,
        max_turns=50,
    )

    start_time = datetime.now()
    all_tools: list[str] = []

    try:
        async with ClaudeSDKClient(options=options) as client:
            await client.query(GRIND_PROMPT.format(task=task, verify_cmd=verify_cmd))

            iteration = 0
            while iteration < max_iterations:
                iteration += 1
                if on_iteration:
                    on_iteration(iteration, "running")
                if verbose:
                    print(f"\n{'='*60}\nITERATION {iteration}/{max_iterations}\n{'='*60}")

                collected = ""
                tools: list[str] = []

                async for msg in client.receive_response():
                    if isinstance(msg, AssistantMessage):
                        for block in msg.content:
                            if isinstance(block, TextBlock):
                                if verbose:
                                    print(block.text)
                                collected += block.text
                            elif isinstance(block, ToolUseBlock):
                                tools.append(block.name)
                                if verbose:
                                    print(f"  -> {block.name}")
                    elif isinstance(msg, ResultMessage):
                        all_tools.extend(tools)
                        duration = (datetime.now() - start_time).total_seconds()

                        if "GRIND_COMPLETE" in collected:
                            m = ""
                            if "GRIND_COMPLETE:" in collected:
                                m = collected.split("GRIND_COMPLETE:")[1].split("\n")[0].strip()
                            return GrindResult(GrindStatus.COMPLETE, iteration, m, list(set(all_tools)), duration)

                        if "GRIND_STUCK" in collected:
                            r = "Unknown"
                            if "GRIND_STUCK:" in collected:
                                r = collected.split("GRIND_STUCK:")[1].split("\n")[0].strip()
                            return GrindResult(GrindStatus.STUCK, iteration, r, list(set(all_tools)), duration)

                if iteration < max_iterations:
                    await client.query(CONTINUE_PROMPT)

            return GrindResult(
                GrindStatus.MAX_ITERATIONS, iteration,
                f"Reached max iterations ({max_iterations})",
                list(set(all_tools)),
                (datetime.now() - start_time).total_seconds()
            )
    except Exception as e:
        return GrindResult(GrindStatus.ERROR, 0, str(e), [], (datetime.now() - start_time).total_seconds())


async def decompose(problem: str, verify_cmd: str, cwd: str | None = None, verbose: bool = False) -> list[TaskDefinition]:
    options = ClaudeAgentOptions(
        allowed_tools=["Bash", "Read", "Glob", "Grep"],
        permission_mode="acceptEdits",
        cwd=cwd,
        max_turns=10,
    )

    collected = ""
    async with ClaudeSDKClient(options=options) as client:
        await client.query(DECOMPOSE_PROMPT.format(problem=problem, verify_cmd=verify_cmd))
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        if verbose:
                            print(block.text)
                        collected += block.text

    start = collected.find("{")
    end = collected.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("No JSON found in response")

    data = json.loads(collected[start:end])
    return [
        TaskDefinition(t["task"], t["verify"], t.get("max_iterations", 5))
        for t in data.get("tasks", [])
    ]


def load_tasks(path: str) -> list[TaskDefinition]:
    p = Path(path)
    content = p.read_text()
    data = yaml.safe_load(content) if p.suffix in (".yaml", ".yml") else json.loads(content)
    return [
        TaskDefinition(t["task"], t["verify"], t.get("max_iterations", 10), t.get("cwd"))
        for t in data.get("tasks", [])
    ]


async def run_batch(tasks: list[TaskDefinition], verbose: bool = False, stop_on_stuck: bool = False) -> BatchResult:
    start = datetime.now()
    results: list[tuple[str, GrindResult]] = []
    completed = stuck = failed = 0

    for i, t in enumerate(tasks, 1):
        print(f"\n{'#'*60}\n# TASK {i}/{len(tasks)}: {t.task[:50]}...\n{'#'*60}")
        result = await grind(t.task, t.verify, t.max_iterations, t.cwd, verbose,
                            lambda n, s: print(f"  [Iteration {n}]") if not verbose else None)
        results.append((t.task, result))

        if result.status == GrindStatus.COMPLETE:
            completed += 1
            print(f"  -> COMPLETE in {result.iterations} iterations")
        elif result.status == GrindStatus.STUCK:
            stuck += 1
            print(f"  -> STUCK: {result.message}")
            if stop_on_stuck:
                break
        else:
            failed += 1
            print(f"  -> FAILED: {result.status.value}")

    return BatchResult(len(tasks), completed, stuck, failed, results, (datetime.now() - start).total_seconds())


def print_result(r: GrindResult) -> None:
    labels = {
        GrindStatus.COMPLETE: ("COMPLETE", "Verification passed!"),
        GrindStatus.STUCK: ("STUCK", "Human intervention needed"),
        GrindStatus.MAX_ITERATIONS: ("MAX ITERATIONS", "Limit reached"),
        GrindStatus.ERROR: ("ERROR", "Execution failed"),
    }
    label, desc = labels.get(r.status, ("UNKNOWN", ""))
    print(f"\n{'='*60}\n{label} - {desc}\n{'='*60}")
    if r.message:
        print(f"Message: {r.message}")
    print(f"Iterations: {r.iterations}\nDuration: {r.duration_seconds:.1f}s")
    if r.tools_used:
        print(f"Tools: {', '.join(r.tools_used)}")


def print_batch_summary(r: BatchResult) -> None:
    print(f"\n{'='*60}\nBATCH SUMMARY\n{'='*60}")
    print(f"Total: {r.total}  Completed: {r.completed}  Stuck: {r.stuck}  Failed: {r.failed}")
    print(f"Duration: {r.duration_seconds:.1f}s")
    if r.stuck or r.failed:
        print("\nNeeds attention:")
        for task, res in r.results:
            if res.status != GrindStatus.COMPLETE:
                print(f"  [{res.status.value}] {task[:50]}")


async def main_async(args):
    if args.command == "run" or (args.command is None and args.task):
        print(f"{'='*60}\nGRIND LOOP\n{'='*60}")
        print(f"Task: {args.task}\nVerify: {args.verify}\n{'='*60}")
        result = await grind(args.task, args.verify, args.max_iter,
                            args.cwd if args.cwd != "." else None, args.verbose,
                            (lambda n, s: print(f"\n[Iteration {n}]")) if not getattr(args, 'quiet', False) else None)
        print_result(result)
        return 0 if result.status == GrindStatus.COMPLETE else (2 if result.status == GrindStatus.STUCK else 1)

    elif args.command == "batch":
        tasks = load_tasks(args.file)
        print(f"{'='*60}\nGRIND BATCH - {len(tasks)} tasks\n{'='*60}")
        result = await run_batch(tasks, args.verbose, getattr(args, 'stop_on_stuck', False))
        print_batch_summary(result)
        return 0 if result.completed == result.total else 1

    elif args.command == "decompose":
        print(f"{'='*60}\nDECOMPOSE\n{'='*60}\nAnalyzing: {args.problem}\n")
        tasks = await decompose(args.problem, args.verify, args.cwd if args.cwd != "." else None, args.verbose)
        output = {"tasks": [{"task": t.task, "verify": t.verify, "max_iterations": t.max_iterations} for t in tasks]}
        yaml_out = yaml.dump(output, default_flow_style=False, sort_keys=False)
        print(f"\nFound {len(tasks)} subtasks:\n\n{yaml_out}")
        if args.output:
            Path(args.output).write_text(yaml_out)
            print(f"Saved to {args.output}\nRun: uv run grind.py batch {args.output}")
        return 0

    print("Usage: grind.py [run|batch|decompose] [options]\n  grind.py run -t 'Fix tests' -v 'pytest'\n  grind.py batch tasks.yaml\n  grind.py decompose -p 'Fix failures' -v 'pytest' -o tasks.yaml")
    return 1


def main():
    p = argparse.ArgumentParser(description="Grind Loop - Automated fix-verify loops")
    sub = p.add_subparsers(dest="command")

    run = sub.add_parser("run", help="Run single task")
    run.add_argument("--task", "-t", required=True)
    run.add_argument("--verify", "-v", required=True)
    run.add_argument("--max-iter", "-n", type=int, default=10)
    run.add_argument("--cwd", "-c", default=".")
    run.add_argument("--verbose", action="store_true")
    run.add_argument("--quiet", "-q", action="store_true")

    batch = sub.add_parser("batch", help="Run batch from file")
    batch.add_argument("file")
    batch.add_argument("--verbose", action="store_true")
    batch.add_argument("--stop-on-stuck", action="store_true")

    dec = sub.add_parser("decompose", help="Decompose problem into tasks")
    dec.add_argument("--problem", "-p", required=True)
    dec.add_argument("--verify", "-v", required=True)
    dec.add_argument("--output", "-o")
    dec.add_argument("--cwd", "-c", default=".")
    dec.add_argument("--verbose", action="store_true")

    # Direct mode support
    p.add_argument("--task", "-t")
    p.add_argument("--verify", "-v")
    p.add_argument("--max-iter", "-n", type=int, default=10)
    p.add_argument("--cwd", "-c", default=".")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--quiet", "-q", action="store_true")

    args = p.parse_args()
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("\nInterrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
