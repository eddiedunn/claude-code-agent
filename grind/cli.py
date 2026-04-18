import argparse
import asyncio
import functools
import hashlib
import json
import sqlite3
import time as _time
from datetime import datetime
from pathlib import Path

from grind.utils import Color


async def handle_evolve_command(args: argparse.Namespace) -> int:
    """Handle 'grind run --repo ... --prompt ...' — self-evolution loop."""
    from grind.contract import ExecutionContract
    from grind.executor import claude_executor
    from grind.team import AgentTask, SelfEvolutionLoop

    if not getattr(args, "repo", None):
        print(Color.error("Error: --repo is required"))
        return 1
    if not getattr(args, "prompt", None):
        print(Color.error("Error: --prompt is required"))
        return 1

    contract_file = getattr(args, "contract_file", None)
    contract_cmd = getattr(args, "contract_cmd", None)

    if not contract_file and not contract_cmd:
        print(Color.error("Error: provide --contract-file or --contract-cmd"))
        return 1
    if contract_file and contract_cmd:
        print(Color.error("Error: --contract-file and --contract-cmd are mutually exclusive"))
        return 1

    task_id = getattr(args, "task_id", None) or _generate_task_id()
    model = getattr(args, "model", "sonnet")
    timeout = getattr(args, "timeout", 600)
    max_retries = getattr(args, "max_retries", 3)
    observer_url = getattr(args, "observer_url", None)

    base_executor = functools.partial(
        claude_executor, model=model, timeout_seconds=timeout
    )

    if contract_file:
        cf = contract_file

        async def executor(task: AgentTask, path: Path, attempt: int) -> None:
            await base_executor(task, path, attempt)
            if (path / cf).exists():
                (path / "state" / "_contract_pass").write_text("ok", encoding="utf-8")
    else:
        cmd = contract_cmd

        async def executor(task: AgentTask, path: Path, attempt: int) -> None:
            await base_executor(task, path, attempt)
            proc = await asyncio.create_subprocess_shell(cmd, cwd=path)
            await proc.wait()
            if proc.returncode == 0:
                (path / "state" / "_contract_pass").write_text("ok", encoding="utf-8")

    contract = ExecutionContract(required_outputs=["_contract_pass"])
    task = AgentTask(
        task_id=task_id,
        prompt=args.prompt,
        contract=contract,
        max_retries=max_retries,
    )
    loop = SelfEvolutionLoop(repo_root=args.repo, observer_url=observer_url)

    result = await loop.run(task, executor)

    cr_status = result.contract_result.status.value if result.contract_result else "n/a"
    print(f"\ntask_id:  {result.task_id}")
    print(f"status:   {result.status}")
    print(f"attempts: {result.attempts}")
    print(f"contract: {cr_status}")

    return 0 if result.status == "accepted" else 1


async def handle_show_command(args: argparse.Namespace) -> int:
    """Handle 'grind show <task_id>' — query observer DB and print events."""
    db_path = Path(getattr(args, "db", None) or Path.home() / ".grind" / "observer.db")
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        return 1

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM events WHERE session_id = ? ORDER BY timestamp",
        (args.task_id,),
    ).fetchall()
    conn.close()

    if not rows:
        print(f"No events for task_id '{args.task_id}'")
        return 1

    for row in rows:
        ts = datetime.fromtimestamp(row["timestamp"]).isoformat(timespec="seconds")
        event_type = row["event_type"]
        payload = json.loads(row["payload"] or "{}")
        parts: list[str] = []
        if row["tool_name"]:
            parts.append(f"tool={row['tool_name']}")
        if "attempt" in payload:
            parts.append(f"attempt={payload['attempt']}")
        if "status" in payload:
            parts.append(f"status={payload['status']}")
        extra = "  ".join(parts)
        print(f"{ts}  {event_type:<25}  {extra}")

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


def _generate_task_id() -> str:
    ts = datetime.now().strftime("%Y%m%d")
    h = hashlib.md5(str(_time.time()).encode()).hexdigest()[:4]
    return f"job-{ts}-{h}"


async def main_async(args: argparse.Namespace) -> int:
    if args.command == "run":
        return await handle_evolve_command(args)

    elif args.command == "show":
        return await handle_show_command(args)

    elif args.command == "observe":
        return await handle_observe_command(args)

    elif args.command == "tmux":
        return await handle_tmux_command(args)

    elif args.command == "hooks":
        return await handle_hooks_command(args)

    print(Color.error("Usage: grind [run|show|observe|tmux|hooks] [options]"))
    print(Color.dim("  grind run --repo /path --prompt 'Create hello.py' --contract-file hello.py"))
    print(Color.dim("  grind show <task-id>"))
    print(Color.dim("  grind observe                              # Start observer server"))
    print(Color.dim("  grind tmux --session my-project --attach   # Launch in tmux"))
    print(Color.dim("  grind hooks install                        # Install observer hooks"))
    return 1


def main():
    p = argparse.ArgumentParser(description="Grind — self-evolution loop for Claude")
    sub = p.add_subparsers(dest="command")

    run = sub.add_parser("run", help="Run a self-evolution job")
    run.add_argument("--repo", required=True, metavar="PATH",
                     help="Absolute path to target repo")
    run.add_argument("--prompt", required=True,
                     help="Task prompt")
    run.add_argument("--task-id", dest="task_id", default=None, metavar="SLUG",
                     help="Task identifier slug (default: auto-generated)")
    run.add_argument("--model", "-m", default="sonnet",
                     choices=["sonnet", "opus", "haiku"],
                     help="Model to use (default: sonnet)")
    run.add_argument("--max-retries", dest="max_retries", type=int, default=3,
                     metavar="N")
    run.add_argument("--timeout", type=int, default=600,
                     metavar="N", help="Per-attempt timeout in seconds (default: 600)")
    run.add_argument("--observer-url", dest="observer_url", default=None,
                     metavar="URL", help="Observer server URL (default: http://localhost:8421)")
    run.add_argument("--contract-file", dest="contract_file", default=None,
                     metavar="PATH",
                     help="Contract: file must exist at PATH inside worktree after attempt")
    run.add_argument("--contract-cmd", dest="contract_cmd", default=None,
                     metavar="CMD",
                     help="Contract: command must return 0 when run with cwd=worktree")

    show_parser = sub.add_parser("show", help="Show events for a task from the observer DB")
    show_parser.add_argument("task_id", help="Task ID to look up")
    show_parser.add_argument("--db", default=None, metavar="PATH",
                             help="SQLite DB path (default: ~/.grind/observer.db)")

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

    args = p.parse_args()
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print(Color.warning("\nInterrupted"))
        return 130
