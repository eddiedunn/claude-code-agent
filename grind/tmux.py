"""Tmux session management for multi-agent orchestration.

Provides functions to create/manage tmux sessions and panes so that
Claude Code agents can run visually in separate panes. This is the
foundation for Dan's multi-agent approach: each sub-agent gets its
own tmux pane, and the user can watch all agents work simultaneously.

Why tmux (not a TUI framework):
- Claude Code's AGENT_TEAMS feature natively spawns sub-agents in tmux panes
- tmux survives terminal disconnects
- tmux panes are the visual backbone for observability
- No Python library — we call the tmux CLI directly (Dan's approach)
"""

import shlex
import shutil
import subprocess
from dataclasses import dataclass


class TmuxError(Exception):
    """Error during tmux operations."""
    pass


# Module-level cache for tmux availability check
_tmux_available: bool | None = None


@dataclass
class PaneInfo:
    """Information about a tmux pane."""
    pane_id: str
    session: str
    window: str
    index: int
    active: bool
    title: str
    pid: int
    current_command: str


def _check_tmux() -> None:
    """Verify tmux is installed and available."""
    global _tmux_available
    if _tmux_available is True:
        return
    if _tmux_available is False or not shutil.which("tmux"):
        _tmux_available = False
        raise TmuxError(
            "tmux is not installed. Install with: brew install tmux (macOS) "
            "or apt install tmux (Linux)"
        )
    _tmux_available = True


def _run_tmux(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a tmux command synchronously."""
    _check_tmux()
    result = subprocess.run(
        ["tmux", *args],
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise TmuxError(f"tmux {' '.join(args)} failed: {result.stderr.strip()}")
    return result



def session_exists(name: str) -> bool:
    """Check if a tmux session exists."""
    result = _run_tmux("has-session", "-t", name, check=False)
    return result.returncode == 0


def create_session(name: str, command: str | None = None, cwd: str | None = None) -> str:
    """Create a new tmux session.

    Args:
        name: Session name (e.g., "grind-main")
        command: Optional command to run in the initial pane
        cwd: Working directory for the session

    Returns:
        Session name

    Raises:
        TmuxError: If session already exists or creation fails
    """
    if session_exists(name):
        raise TmuxError(f"Session '{name}' already exists")

    args = ["new-session", "-d", "-s", name]
    if cwd:
        args.extend(["-c", cwd])
    if command:
        args.append(command)

    _run_tmux(*args)
    return name


def create_pane(
    session: str,
    command: str | None = None,
    cwd: str | None = None,
    vertical: bool = False,
    size: int | None = None,
) -> str:
    """Split the current window to create a new pane.

    Args:
        session: Target session name
        command: Command to run in the new pane
        cwd: Working directory
        vertical: If True, split vertically (side-by-side). Default horizontal (top-bottom).
        size: Percentage size of the new pane (1-99)

    Returns:
        The new pane ID (e.g., "%5")
    """
    args = ["split-window"]
    if vertical:
        args.append("-h")
    else:
        args.append("-v")
    args.extend(["-t", session])
    if cwd:
        args.extend(["-c", cwd])
    if size:
        args.extend(["-p", str(size)])

    # Print the pane ID so we can capture it
    args.extend(["-P", "-F", "#{pane_id}"])

    if command:
        args.append(command)

    result = _run_tmux(*args)
    return result.stdout.strip()


def send_keys(target: str, keys: str, enter: bool = True) -> None:
    """Send keystrokes to a tmux pane.

    Args:
        target: Pane target (session:window.pane or pane_id like "%5")
        keys: The text/command to send
        enter: Whether to press Enter after sending
    """
    _run_tmux("send-keys", "-t", target, keys, "Enter" if enter else "")


def list_panes(session: str) -> list[PaneInfo]:
    """List all panes in a session.

    Args:
        session: Session name

    Returns:
        List of PaneInfo objects
    """
    fmt = "#{pane_id}|#{session_name}|#{window_index}|#{pane_index}|#{pane_active}|#{pane_title}|#{pane_pid}|#{pane_current_command}"
    result = _run_tmux(
        "list-panes", "-t", session, "-a", "-F", fmt,
        check=False,
    )
    if result.returncode != 0:
        return []

    panes = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("|")
        if len(parts) >= 8:
            panes.append(PaneInfo(
                pane_id=parts[0],
                session=parts[1],
                window=parts[2],
                index=int(parts[3]),
                active=parts[4] == "1",
                title=parts[5],
                pid=int(parts[6]) if parts[6].isdigit() else 0,
                current_command=parts[7],
            ))
    return panes


def list_sessions() -> list[dict[str, str]]:
    """List all tmux sessions.

    Returns:
        List of dicts with 'name', 'windows', 'created', 'attached' keys
    """
    fmt = "#{session_name}|#{session_windows}|#{session_created}|#{session_attached}"
    result = _run_tmux("list-sessions", "-F", fmt, check=False)
    if result.returncode != 0:
        return []

    sessions = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("|")
        if len(parts) >= 4:
            sessions.append({
                "name": parts[0],
                "windows": parts[1],
                "created": parts[2],
                "attached": parts[3],
            })
    return sessions


def kill_pane(pane_id: str) -> None:
    """Kill a specific pane."""
    _run_tmux("kill-pane", "-t", pane_id, check=False)


def kill_session(name: str) -> None:
    """Kill an entire tmux session."""
    _run_tmux("kill-session", "-t", name, check=False)


def select_layout(session: str, layout: str = "tiled") -> None:
    """Apply a layout to the session's current window.

    Layouts: even-horizontal, even-vertical, main-horizontal, main-vertical, tiled
    """
    _run_tmux("select-layout", "-t", session, layout)


def set_pane_title(pane_id: str, title: str) -> None:
    """Set the title of a pane (useful for identifying agent panes)."""
    _run_tmux("select-pane", "-t", pane_id, "-T", title)


def capture_pane(pane_id: str, lines: int = 50) -> str:
    """Capture the visible content of a pane.

    Useful for checking what an agent is currently showing.

    Args:
        pane_id: Target pane
        lines: Number of lines to capture from the end

    Returns:
        The pane's visible text content
    """
    result = _run_tmux(
        "capture-pane", "-t", pane_id, "-p",
        "-S", f"-{lines}",
        check=False,
    )
    return result.stdout if result.returncode == 0 else ""


def launch_claude_code_in_session(
    session_name: str,
    prompt: str | None = None,
    model: str = "opus",
    cwd: str | None = None,
    env_vars: dict[str, str] | None = None,
    agent_teams: bool = False,
) -> str:
    """Create a tmux session and launch Claude Code inside it.

    This is the primary entry point for Phase 1: get a single agent
    running inside tmux with visibility.

    Args:
        session_name: Name for the tmux session
        prompt: Optional initial prompt to send to Claude Code
        model: Claude model to use
        cwd: Working directory
        env_vars: Additional environment variables to set
        agent_teams: Enable CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS

    Returns:
        Session name
    """
    # Build the environment export commands
    env_cmds = []
    if agent_teams:
        env_cmds.append("export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1")
    if env_vars:
        for key, val in env_vars.items():
            env_cmds.append(f"export {key}={shlex.quote(val)}")

    # Create the session
    create_session(session_name, cwd=cwd)

    # Set up environment
    for cmd in env_cmds:
        send_keys(session_name, cmd)

    # Launch Claude Code
    claude_cmd = f"claude --model {model}"
    if prompt:
        claude_cmd += f" -p {_shell_quote(prompt)}"

    send_keys(session_name, claude_cmd)
    return session_name


def _shell_quote(s: str) -> str:
    """Quote a string for shell use."""
    return "'" + s.replace("'", "'\\''") + "'"
