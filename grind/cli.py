import argparse
import asyncio
from pathlib import Path

import yaml

from grind.batch import run_batch
from grind.engine import decompose, grind
from grind.models import GrindStatus, InteractiveConfig, TaskDefinition
from grind.tasks import load_tasks
from grind.tui.main import run_tui
from grind.utils import Color, print_batch_summary, print_result


async def handle_run_command(args: argparse.Namespace) -> int:
    """Handle the 'run' command - execute a single task."""
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


async def handle_batch_command(args: argparse.Namespace) -> int:
    """Handle the 'batch' command - execute multiple tasks from a file."""
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

    # Return semantic exit codes per documentation
    # 0: Success, 1: Error, 2: Stuck, 3: Max iterations
    if result.completed == result.total:
        return 0
    elif result.failed > 0:
        return 1  # Error takes priority
    elif result.max_iterations > 0:
        return 3  # Max iterations
    elif result.stuck > 0:
        return 2  # Stuck
    else:
        return 1  # Fallback to error


async def handle_decompose_command(args: argparse.Namespace) -> int:
    """Handle the 'decompose' command - break down a problem into subtasks."""
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


async def handle_tui_command(args: argparse.Namespace) -> int:
    """Handle the 'tui' command - launch the TUI interface."""
    return await run_tui(
        task_file=args.task_file,
        model=args.model,
        verbose=args.verbose
    )


def _print_dag_dry_run(graph):
    """Print the DAG execution plan without running tasks."""
    order = graph.get_execution_order()
    print(Color.header("=" * 60))
    print(Color.bold("DAG Execution Plan"))
    print(Color.header("=" * 60))
    for i, task_id in enumerate(order, 1):
        node = graph.nodes[task_id]
        deps = node.depends_on
        dep_str = f" (after: {', '.join(deps)})" if deps else ""
        task_preview = node.task_def.task[:50]
        if len(node.task_def.task) > 50:
            task_preview += "..."
        print(f"  {i}. {task_id}{dep_str}")
        print(Color.dim(f"     {task_preview}"))
    print(Color.header("=" * 60))
    print(f"Total: {len(order)} tasks")


def _print_dag_summary(result):
    """Print the DAG execution summary."""
    print(Color.header("\n" + "=" * 60))
    print(Color.bold("DAG Execution Summary"))
    print(Color.header("=" * 60))
    print(f"  Total:     {result.total}")
    print(Color.success(f"  Completed: {result.completed}"))
    if result.stuck:
        print(Color.warning(f"  Stuck:     {result.stuck}"))
    if result.max_iterations:
        print(Color.info(f"  Max Iter:  {result.max_iterations}"))
    if result.failed:
        print(Color.error(f"  Failed:    {result.failed}"))
    if result.blocked:
        print(Color.warning(f"  Blocked:   {result.blocked}"))
    print(f"  Duration:  {result.duration_seconds:.1f}s")
    print(Color.header("=" * 60))


def _get_dag_exit_code(result) -> int:
    """Determine the exit code for DAG execution result."""
    if result.completed == result.total:
        return 0
    elif result.failed > 0 or result.blocked > 0:
        return 1  # Error takes priority
    elif result.max_iterations > 0:
        return 3  # Max iterations
    elif result.stuck > 0:
        return 2  # Stuck
    else:
        return 1  # Fallback to error


async def _cleanup_worktrees_if_requested(cleanup_requested: bool):
    """Clean up worktrees if requested."""
    if not cleanup_requested:
        return

    from grind.worktree import WorktreeManager
    try:
        manager = WorktreeManager()
        count = await manager.cleanup_all(force=True)
        if count:
            print(Color.info(f"Cleaned up {count} stale worktrees"))
    except Exception as e:
        print(Color.warning(f"Could not cleanup worktrees: {e}"))


def _warn_if_parallel_without_worktrees(parallel: int, worktrees: bool):
    """Warn about parallel without worktrees."""
    if parallel > 1 and not worktrees:
        print(Color.warning(
            "Warning: --parallel > 1 without --worktrees may cause Git conflicts"
        ))
        print(Color.warning(
            "Consider: grind dag tasks.yaml --parallel 3 --worktrees"
        ))


async def handle_dag_command(args: argparse.Namespace) -> int:
    """Handle the 'dag' command - execute tasks with dependency ordering."""
    from grind.dag import DAGExecutor
    from grind.tasks import build_task_graph

    try:
        graph = build_task_graph(args.tasks_file)
    except ValueError as e:
        print(Color.error(f"Invalid task graph: {e}"))
        return 2  # Exit code for invalid graph

    await _cleanup_worktrees_if_requested(args.cleanup_worktrees)
    _warn_if_parallel_without_worktrees(args.parallel, args.worktrees)

    if args.dry_run:
        _print_dag_dry_run(graph)
        return 0

    def on_start(node):
        print(Color.info(f"\n{'=' * 60}"))
        print(Color.bold(f"Starting: {node.id}"))
        print(Color.dim(f"Task: {node.task_def.task[:60]}..."))
        print(Color.info(f"{'=' * 60}"))

    def on_complete(node, result):
        if result.status == GrindStatus.COMPLETE:
            print(Color.success(
                f"Completed: {node.id} ({result.iterations} iterations)"
            ))
        elif node.status == "blocked":
            print(Color.warning(f"Blocked: {node.id}"))
        else:
            print(Color.error(f"Failed: {node.id} - {result.message}"))

    executor = DAGExecutor(graph)
    result = await executor.execute(
        verbose=args.verbose,
        max_parallel=args.parallel,
        use_worktrees=args.worktrees,
        on_task_start=on_start,
        on_task_complete=on_complete,
    )

    _print_dag_summary(result)
    return _get_dag_exit_code(result)


async def main_async(args: argparse.Namespace) -> int:
    if args.command == "run" or (args.command is None and args.task):
        return await handle_run_command(args)

    elif args.command == "batch":
        return await handle_batch_command(args)

    elif args.command == "decompose":
        return await handle_decompose_command(args)

    elif args.command == "tui":
        return await handle_tui_command(args)

    elif args.command == "dag":
        return await handle_dag_command(args)

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
    run.add_argument("--model", "-m", default="haiku", choices=["sonnet", "opus", "haiku"],
                     help="Model to use (default: haiku - faster/cheaper for most tasks)")
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

    # DAG execution with dependencies
    dag_parser = sub.add_parser(
        "dag",
        help="Run tasks with dependency ordering"
    )
    dag_parser.add_argument("tasks_file", help="Path to tasks YAML/JSON file")
    dag_parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Show detailed output"
    )
    dag_parser.add_argument(
        "--dry-run", action="store_true",
        help="Show execution plan without running tasks"
    )
    dag_parser.add_argument(
        "--parallel", "-p", type=int, default=1, metavar="N",
        help="Max parallel tasks (default: 1 = sequential)"
    )
    dag_parser.add_argument(
        "--worktrees", "-w", action="store_true",
        help="Use git worktrees for isolation (recommended with --parallel)"
    )
    dag_parser.add_argument(
        "--cleanup-worktrees", action="store_true",
        help="Remove all .worktrees/ before starting"
    )

    # TUI interface
    tui_parser = sub.add_parser(
        "tui",
        help="Launch the Agent Orchestration TUI"
    )
    tui_parser.add_argument(
        "--task-file", "-t",
        help="Optional tasks.yaml to load on startup"
    )
    tui_parser.add_argument(
        "--model", "-m", default="haiku",
        choices=["sonnet", "opus", "haiku"],
        help="Default model for new agents (default: haiku - faster/cheaper for most tasks)"
    )
    tui_parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose logging"
    )

    p.add_argument("--task", "-t")
    p.add_argument("--verify", "-v")
    p.add_argument("--max-iter", "-n", type=int, default=10)
    p.add_argument("--cwd", "-c", default=".")
    p.add_argument("--model", "-m", default="haiku", choices=["sonnet", "opus", "haiku"],
                   help="Model to use (default: haiku - faster/cheaper for most tasks)")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--quiet", "-q", action="store_true")

    args = p.parse_args()
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print(Color.warning("\nInterrupted"))
        return 130
