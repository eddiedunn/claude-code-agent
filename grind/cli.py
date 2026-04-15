import argparse
import asyncio
from pathlib import Path

import yaml

from grind.batch import run_batch
from grind.engine import decompose, grind
from grind.models import GrindStatus, InteractiveConfig, TaskDefinition
from grind.tasks import load_tasks
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

    result = await run_batch(
        tasks, args.verbose, getattr(args, 'stop_on_stuck', False), task_file=args.file
    )
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


async def handle_observe_command(args: argparse.Namespace) -> int:
    """Handle the 'observe' command - start the observability server."""
    from grind.observer.server import run_server_async

    print(Color.header("=" * 60))
    print(Color.header("GRIND OBSERVER"))
    print(Color.header("=" * 60))
    print(Color.info(f"Listening on: http://{args.host}:{args.port}"))
    print(Color.info(f"Events endpoint: POST http://{args.host}:{args.port}/events"))
    print(Color.info(f"Live stream: ws://{args.host}:{args.port}/stream"))
    if args.db:
        print(Color.info(f"Database: {args.db}"))
    print(Color.header("=" * 60))

    await run_server_async(host=args.host, port=args.port, db_path=args.db)
    return 0


async def handle_tmux_command(args: argparse.Namespace) -> int:
    """Handle the 'tmux' command - launch Claude Code in a tmux session."""
    from grind.tmux import (
        TmuxError,
        launch_claude_code_in_session,
        list_sessions,
    )

    session_name = args.session or "grind"

    # If --list, show sessions and exit
    if getattr(args, 'list', False):
        sessions = list_sessions()
        if not sessions:
            print(Color.info("No tmux sessions found"))
        else:
            print(Color.header(f"{'Session':<20} {'Windows':<10} {'Attached':<10}"))
            print(Color.header("-" * 40))
            for s in sessions:
                attached = "yes" if s["attached"] == "1" else "no"
                print(f"  {s['name']:<20} {s['windows']:<10} {attached:<10}")
        return 0

    print(Color.header("=" * 60))
    print(Color.header("GRIND TMUX"))
    print(Color.header("=" * 60))

    # Install hooks if requested
    if not args.no_hooks:
        from grind.hooks_config import generate_hooks_config, install_hooks

        observer_url = args.observer_url or "http://localhost:8421"
        config = generate_hooks_config(observer_url)
        settings_path = install_hooks(config, project_dir=args.cwd)
        print(Color.success(f"Hooks installed: {settings_path}"))
        print(Color.info(f"Observer URL: {observer_url}"))

    try:
        session = launch_claude_code_in_session(
            session_name=session_name,
            prompt=args.prompt,
            model=args.model,
            cwd=args.cwd,
            agent_teams=args.agent_teams,
        )
        print(Color.success(f"Session created: {session}"))
        print(Color.info(f"Attach with: tmux attach -t {session}"))
        if args.attach:
            import subprocess
            subprocess.run(["tmux", "attach", "-t", session])
    except TmuxError as e:
        if "already exists" in str(e):
            print(Color.warning(f"Session '{session_name}' already exists"))
            print(Color.info(f"Attach with: tmux attach -t {session_name}"))
            if args.attach:
                import subprocess
                subprocess.run(["tmux", "attach", "-t", session_name])
        else:
            print(Color.error(f"Error: {e}"))
            return 1

    return 0


async def handle_hooks_command(args: argparse.Namespace) -> int:
    """Handle the 'hooks' command - manage Claude Code hook configuration."""
    from grind.hooks_config import (
        generate_hooks_config,
        install_hooks,
        print_hooks_config,
        uninstall_hooks,
    )

    if args.hooks_action == "show":
        print_hooks_config(args.observer_url)
        return 0

    elif args.hooks_action == "install":
        config = generate_hooks_config(args.observer_url)
        path = install_hooks(config, project_dir=args.project_dir)
        print(Color.success(f"Hooks installed to: {path}"))
        return 0

    elif args.hooks_action == "uninstall":
        removed = uninstall_hooks(project_dir=args.project_dir)
        if removed:
            print(Color.success("Observer hooks removed"))
        else:
            print(Color.info("No observer hooks found to remove"))
        return 0

    print(Color.error("Usage: grind hooks [show|install|uninstall]"))
    return 1


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
        task_file=args.tasks_file,
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

    elif args.command == "dag":
        return await handle_dag_command(args)

    elif args.command == "observe":
        return await handle_observe_command(args)

    elif args.command == "tmux":
        return await handle_tmux_command(args)

    elif args.command == "hooks":
        return await handle_hooks_command(args)

    print(Color.error("Usage: grind [run|batch|decompose|dag|observe|tmux|hooks] [options]"))
    print(Color.dim("  grind run -t 'Fix tests' -v 'pytest' -m sonnet"))
    print(Color.dim("  grind batch tasks.yaml"))
    print(Color.dim("  grind decompose -p 'Fix failures' -v 'pytest' -o tasks.yaml"))
    print(Color.dim("  grind dag tasks.yaml --parallel 3 --worktrees"))
    print(Color.dim("  grind observe                              # Start observer server"))
    print(Color.dim("  grind tmux --session my-project --attach   # Launch in tmux"))
    print(Color.dim("  grind hooks install                        # Install observer hooks"))
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

    # Observer server
    observe_parser = sub.add_parser(
        "observe",
        help="Start the observability server (receives hook events)"
    )
    observe_parser.add_argument(
        "--host", default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )
    observe_parser.add_argument(
        "--port", type=int, default=8421,
        help="Port to listen on (default: 8421)"
    )
    observe_parser.add_argument(
        "--db", default=None,
        help="SQLite database path (default: ~/.grind/observer.db)"
    )

    # Tmux session launcher
    tmux_parser = sub.add_parser(
        "tmux",
        help="Launch Claude Code in a tmux session with observability"
    )
    tmux_parser.add_argument(
        "--session", "-s", default="grind",
        help="Tmux session name (default: grind)"
    )
    tmux_parser.add_argument(
        "--model", "-m", default="opus",
        choices=["sonnet", "opus", "haiku"],
        help="Claude model (default: opus)"
    )
    tmux_parser.add_argument(
        "--cwd", "-c", default=None,
        help="Working directory"
    )
    tmux_parser.add_argument(
        "--prompt", "-p", default=None,
        help="Initial prompt to send to Claude Code"
    )
    tmux_parser.add_argument(
        "--attach", "-a", action="store_true",
        help="Attach to the session after creation"
    )
    tmux_parser.add_argument(
        "--agent-teams", action="store_true",
        help="Enable CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"
    )
    tmux_parser.add_argument(
        "--no-hooks", action="store_true",
        help="Skip installing observer hooks"
    )
    tmux_parser.add_argument(
        "--observer-url", default=None,
        help="Observer server URL (default: http://localhost:8421)"
    )
    tmux_parser.add_argument(
        "--list", "-l", action="store_true",
        help="List existing tmux sessions"
    )

    # Hooks management
    hooks_parser = sub.add_parser(
        "hooks",
        help="Manage Claude Code observer hooks"
    )
    hooks_sub = hooks_parser.add_subparsers(dest="hooks_action")
    hooks_show = hooks_sub.add_parser("show", help="Show hook configuration")
    hooks_show.add_argument("--observer-url", default=None)
    hooks_install = hooks_sub.add_parser("install", help="Install hooks into settings")
    hooks_install.add_argument("--observer-url", default=None)
    hooks_install.add_argument("--project-dir", default=None)
    hooks_uninstall = hooks_sub.add_parser("uninstall", help="Remove observer hooks")
    hooks_uninstall.add_argument("--project-dir", default=None)

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
