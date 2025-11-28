#!/usr/bin/env python3
"""
Command-line interface for grind loop.
"""

import argparse
import asyncio
import sys
from pathlib import Path

import yaml

from grind_loop.core import GrindResult, GrindStatus, grind
from grind_loop.batch import load_tasks, run_batch, print_batch_summary, TaskDefinition
from grind_loop.decompose import decompose


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


async def run_single(args: argparse.Namespace) -> int:
    """Run a single grind task."""
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
    return 1


async def run_batch_cmd(args: argparse.Namespace) -> int:
    """Run batch of tasks from file."""
    print("=" * 60)
    print("GRIND LOOP - BATCH MODE")
    print("=" * 60)
    print(f"Tasks file: {args.file}")
    print("=" * 60)

    tasks = load_tasks(args.file)
    print(f"Loaded {len(tasks)} tasks")

    result = await run_batch(
        tasks=tasks,
        verbose=args.verbose,
        stop_on_stuck=args.stop_on_stuck,
    )

    print_batch_summary(result)

    if result.completed == result.total:
        return 0
    elif result.stuck > 0:
        return 2
    return 1


async def run_decompose(args: argparse.Namespace) -> int:
    """Decompose a problem into subtasks."""
    print("=" * 60)
    print("GRIND LOOP - DECOMPOSE MODE")
    print("=" * 60)
    print(f"Problem: {args.problem}")
    print(f"Verify:  {args.verify}")
    print("=" * 60)
    print("\nAnalyzing problem...")

    tasks = await decompose(
        problem=args.problem,
        verify_cmd=args.verify,
        cwd=args.cwd if args.cwd != "." else None,
        verbose=args.verbose,
    )

    print(f"\nFound {len(tasks)} subtasks:\n")

    # Output as YAML
    task_list = {
        "tasks": [
            {"task": t.task, "verify": t.verify, "max_iterations": t.max_iterations}
            for t in tasks
        ]
    }

    yaml_output = yaml.dump(task_list, default_flow_style=False, sort_keys=False)
    print(yaml_output)

    # Save to file if requested
    if args.output:
        Path(args.output).write_text(yaml_output)
        print(f"\nSaved to {args.output}")
        print(f"Run with: uv run grind batch {args.output}")

    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Automated fix-verify loops using Claude Agent SDK",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Single task (default, also works without subcommand)
    single = subparsers.add_parser("run", help="Run a single grind task")
    single.add_argument("--task", "-t", required=True, help="What to fix")
    single.add_argument("--verify", "-v", required=True, help="Verification command")
    single.add_argument("--max-iter", "-n", type=int, default=10, help="Max iterations")
    single.add_argument("--cwd", "-c", default=".", help="Working directory")
    single.add_argument("--verbose", action="store_true", help="Show full output")
    single.add_argument("--quiet", "-q", action="store_true", help="Minimal output")

    # Batch mode
    batch = subparsers.add_parser("batch", help="Run batch of tasks from file")
    batch.add_argument("file", help="YAML/JSON file with task list")
    batch.add_argument("--verbose", action="store_true", help="Show full output")
    batch.add_argument("--stop-on-stuck", action="store_true", help="Stop if any task gets stuck")

    # Decompose mode
    decomp = subparsers.add_parser("decompose", help="Analyze problem and create task list")
    decomp.add_argument("--problem", "-p", required=True, help="Problem to decompose")
    decomp.add_argument("--verify", "-v", required=True, help="Verification command")
    decomp.add_argument("--output", "-o", help="Save task list to file")
    decomp.add_argument("--cwd", "-c", default=".", help="Working directory")
    decomp.add_argument("--verbose", action="store_true", help="Show analysis")

    # Also support direct args without subcommand for backwards compat
    parser.add_argument("--task", "-t", help="What to fix (direct mode)")
    parser.add_argument("--verify", "-v", help="Verification command (direct mode)")
    parser.add_argument("--max-iter", "-n", type=int, default=10, help="Max iterations")
    parser.add_argument("--cwd", "-c", default=".", help="Working directory")
    parser.add_argument("--verbose", action="store_true", help="Show full output")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")

    args = parser.parse_args(argv)

    # Handle direct mode (no subcommand)
    if args.command is None and args.task and args.verify:
        args.command = "run"

    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.command is None:
        print("Usage: grind <command> [options]")
        print("")
        print("Commands:")
        print("  run        Run a single grind task")
        print("  batch      Run batch of tasks from file")
        print("  decompose  Analyze problem and create task list")
        print("")
        print("Examples:")
        print("  grind run --task 'Fix tests' --verify 'pytest'")
        print("  grind batch tasks.yaml")
        print("  grind decompose --problem 'Fix all test failures' --verify 'pytest' -o tasks.yaml")
        print("")
        print("For direct mode: grind --task 'Fix tests' --verify 'pytest'")
        return 1

    try:
        if args.command == "run":
            return asyncio.run(run_single(args))
        elif args.command == "batch":
            return asyncio.run(run_batch_cmd(args))
        elif args.command == "decompose":
            return asyncio.run(run_decompose(args))
        else:
            print(f"Unknown command: {args.command}")
            return 1
    except KeyboardInterrupt:
        print("\nInterrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
