#!/usr/bin/env python3
"""
Command-line interface for grind loop.

Usage:
    uv run grind --task "Fix failing tests" --verify "pytest tests/ -v"
    uv run grind -t "Fix SonarQube issues" -v "sonar-check.sh" -n 8
"""

import argparse
import asyncio
import sys

from grind_loop.core import GrindResult, GrindStatus, grind


def print_banner(task: str, verify_cmd: str, max_iter: int, cwd: str) -> None:
    """Print startup banner."""
    print("=" * 60)
    print("GRIND LOOP")
    print("=" * 60)
    print(f"Task:       {task}")
    print(f"Verify:     {verify_cmd}")
    print(f"Max iter:   {max_iter}")
    print(f"Directory:  {cwd}")
    print("=" * 60)


def print_result(result: GrindResult) -> None:
    """Print final result."""
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
    """Callback for iteration progress."""
    print(f"\n[Iteration {iteration}] {status}...")


async def run_grind(args: argparse.Namespace) -> int:
    """Run the grind loop with parsed arguments."""
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Automated fix-verify loop using Claude Agent SDK",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fix failing unit tests
  grind --task "Fix failing unit tests" --verify "pytest tests/ -v"

  # Fix SonarQube issues
  grind -t "Fix code smells in auth module" -v "./sonar-check.sh" -n 8

  # Fix Ansible playbook
  grind -t "Fix the webserver playbook" -v "ansible-playbook site.yml --check"

  # Fix Jenkins pipeline
  grind -t "Get deploy job working" -v "jenkins-cli build deploy -s"

Exit codes:
  0 - Success (GRIND_COMPLETE)
  1 - Error during execution
  2 - Agent got stuck (GRIND_STUCK)
  3 - Max iterations reached
        """,
    )

    parser.add_argument(
        "--task",
        "-t",
        required=True,
        help="Description of what needs to be fixed",
    )

    parser.add_argument(
        "--verify",
        "-v",
        required=True,
        help="Command to verify success (exit 0 = success)",
    )

    parser.add_argument(
        "--max-iter",
        "-n",
        type=int,
        default=10,
        help="Maximum iterations (default: 10)",
    )

    parser.add_argument(
        "--cwd",
        "-c",
        default=".",
        help="Working directory (default: current)",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show full Claude output",
    )

    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Minimal output (no iteration updates)",
    )

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    args = parse_args(argv)

    try:
        return asyncio.run(run_grind(args))
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        return 130


if __name__ == "__main__":
    sys.exit(main())
