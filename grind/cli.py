import argparse
import asyncio
from pathlib import Path

import yaml

from grind.batch import run_batch
from grind.engine import decompose, grind
from grind.models import GrindStatus, InteractiveConfig, TaskDefinition
from grind.tasks import load_tasks
from grind.utils import Color, print_batch_summary, print_result


async def main_async(args: argparse.Namespace) -> int:
    if args.command == "run" or (args.command is None and args.task):
        print(Color.header("=" * 60))
        print(Color.header("GRIND LOOP"))
        print(Color.header("=" * 60))
        print(Color.info(f"Task: {args.task}"))
        print(Color.info(f"Verify: {args.verify}"))
        print(Color.info(f"Model: {args.model}"))
        print(Color.header("=" * 60))

        interactive_config = InteractiveConfig(
            enabled=getattr(args, 'interactive', False),
        )

        task_def = TaskDefinition(
            task=args.task,
            verify=args.verify,
            max_iterations=args.max_iter,
            cwd=args.cwd if args.cwd != "." else None,
            model=args.model,
            interactive=interactive_config,
        )

        iteration_callback = (
            (lambda n, s: print(f"\n[Iteration {n}]"))
            if not getattr(args, 'quiet', False)
            else None
        )
        result = await grind(task_def, args.verbose, iteration_callback)
        print_result(result)
        if result.status == GrindStatus.COMPLETE:
            return 0
        elif result.status == GrindStatus.STUCK:
            return 2
        else:
            return 1

    elif args.command == "batch":
        # Determine working directory: explicit --cwd overrides, else infer from tasks file
        base_cwd = args.cwd if args.cwd else None
        tasks = load_tasks(args.file, base_cwd)

        # Apply interactive config from CLI to all tasks (unless task specifies its own)
        if getattr(args, 'interactive', False):
            interactive_config = InteractiveConfig(enabled=True)
            for task in tasks:
                if not task.interactive.enabled:
                    task.interactive = interactive_config

        # Resolve and display the effective working directory
        effective_cwd = base_cwd if base_cwd else str(Path(args.file).resolve().parent)

        print(Color.header("=" * 60))
        print(Color.header(f"GRIND BATCH - {len(tasks)} tasks"))
        print(Color.header("=" * 60))
        print(Color.info(f"Working directory: {effective_cwd}"))
        if getattr(args, 'interactive', False):
            print(Color.info("Interactive mode: enabled"))

        result = await run_batch(tasks, args.verbose, getattr(args, 'stop_on_stuck', False))
        print_batch_summary(result)
        return 0 if result.completed == result.total else 1

    elif args.command == "decompose":
        print(Color.header("=" * 60))
        print(Color.header("DECOMPOSE"))
        print(Color.header("=" * 60))
        print(Color.info(f"Analyzing: {args.problem}\n"))

        tasks = await decompose(
            args.problem, args.verify,
            args.cwd if args.cwd != "." else None, args.verbose
        )
        output = {
            "tasks": [
                {
                    "task": t.task,
                    "verify": t.verify,
                    "max_iterations": t.max_iterations,
                    "model": t.model,
                }
                for t in tasks
            ]
        }
        yaml_out = yaml.dump(output, default_flow_style=False, sort_keys=False)
        print(Color.success(f"\nFound {len(tasks)} subtasks:\n\n{yaml_out}"))
        if args.output:
            Path(args.output).write_text(yaml_out)
            print(Color.success(f"Saved to {args.output}"))
            print(Color.info(f"Run: uv run grind.py batch {args.output}"))
        return 0

    print(Color.error("Usage: grind.py [run|batch|decompose] [options]"))
    print(Color.dim("  grind.py run -t 'Fix tests' -v 'pytest' -m sonnet"))
    print(Color.dim("  grind.py batch tasks.yaml"))
    print(Color.dim("  grind.py decompose -p 'Fix failures' -v 'pytest' -o tasks.yaml"))
    return 1


def main():
    p = argparse.ArgumentParser(description="Grind Loop - Automated fix-verify loops")
    sub = p.add_subparsers(dest="command")

    run = sub.add_parser("run", help="Run single task")
    run.add_argument("--task", "-t", required=True)
    run.add_argument("--verify", "-v", required=True)
    run.add_argument("--max-iter", "-n", type=int, default=10)
    run.add_argument("--cwd", "-c", default=".")
    run.add_argument("--model", "-m", default="sonnet", choices=["sonnet", "opus", "haiku"])
    run.add_argument("--verbose", action="store_true")
    run.add_argument("--quiet", "-q", action="store_true")
    run.add_argument("--interactive", "-i", action="store_true",
                     help="Enable interactive mode (press 'i' to interject)")

    batch = sub.add_parser("batch", help="Run batch from file")
    batch.add_argument("file")
    batch.add_argument("--cwd", "-c", help="Working directory (default: tasks file's directory)")
    batch.add_argument("--verbose", action="store_true")
    batch.add_argument("--stop-on-stuck", action="store_true")
    batch.add_argument("--interactive", "-i", action="store_true",
                       help="Enable interactive mode (press 'i' to interject)")

    dec = sub.add_parser("decompose", help="Decompose problem into tasks")
    dec.add_argument("--problem", "-p", required=True)
    dec.add_argument("--verify", "-v", required=True)
    dec.add_argument("--output", "-o")
    dec.add_argument("--cwd", "-c", default=".")
    dec.add_argument("--verbose", action="store_true")

    p.add_argument("--task", "-t")
    p.add_argument("--verify", "-v")
    p.add_argument("--max-iter", "-n", type=int, default=10)
    p.add_argument("--cwd", "-c", default=".")
    p.add_argument("--model", "-m", default="sonnet", choices=["sonnet", "opus", "haiku"])
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--quiet", "-q", action="store_true")

    args = p.parse_args()
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print(Color.warning("\nInterrupted"))
        return 130
