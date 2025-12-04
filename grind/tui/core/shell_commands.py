#!/usr/bin/env python3
"""
Command parser for the REPL shell.

Provides a command language for agent orchestration, including
command registration, parsing, and execution.
"""

import shlex
import subprocess
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from grind.tui.core.agent_executor import AgentExecutor
    from grind.tui.core.models import AgentInfo
    from grind.tui.core.session import AgentSession


@dataclass
class ShellCommand:
    """Represents a command available in the shell."""

    name: str
    description: str
    usage: str
    handler: Callable[["list[str]", "ShellContext"], Awaitable[str]]
    aliases: list[str] = field(default_factory=list)


@dataclass
class ShellContext:
    """Context passed to command handlers."""

    session: "AgentSession"
    agents: list["AgentInfo"]
    current_agent_id: str | None
    history: list[str]
    variables: dict[str, str]
    executor: "AgentExecutor | None" = None


class CommandRegistry:
    """Registry for shell commands."""

    def __init__(self):
        """Initialize the command registry."""
        self.commands: dict[str, ShellCommand] = {}
        self._alias_map: dict[str, str] = {}  # alias -> command name
        self._register_builtins()

    def register(self, cmd: ShellCommand) -> None:
        """
        Register a command in the registry.

        Args:
            cmd: The ShellCommand to register
        """
        self.commands[cmd.name] = cmd
        for alias in cmd.aliases:
            self._alias_map[alias] = cmd.name

    def get_command(self, name: str) -> ShellCommand | None:
        """
        Get a command by name or alias.

        Args:
            name: Command name or alias

        Returns:
            ShellCommand if found, None otherwise
        """
        # Check direct command name
        if name in self.commands:
            return self.commands[name]
        # Check aliases
        if name in self._alias_map:
            return self.commands[self._alias_map[name]]
        return None

    def get_all_commands(self) -> list[ShellCommand]:
        """
        Get all registered commands.

        Returns:
            List of all ShellCommand instances
        """
        return list(self.commands.values())

    def get_completions(self, partial: str) -> list[str]:
        """
        Get command completions for a partial input.

        Args:
            partial: Partial command string

        Returns:
            List of matching command names and aliases
        """
        completions: list[str] = []
        # Match command names
        for name in self.commands:
            if name.startswith(partial):
                completions.append(name)
        # Match aliases
        for alias in self._alias_map:
            if alias.startswith(partial):
                completions.append(alias)
        return sorted(completions)

    def _register_builtins(self) -> None:
        """Register all built-in commands."""
        self.register(
            ShellCommand(
                name="help",
                description="Show available commands",
                usage="help [command]",
                handler=cmd_help,
            )
        )
        self.register(
            ShellCommand(
                name="status",
                description="Show current agent status summary",
                usage="status",
                handler=cmd_status,
            )
        )
        self.register(
            ShellCommand(
                name="agents",
                description="List all agents",
                usage="agents",
                handler=cmd_agents,
                aliases=["ls"],
            )
        )
        self.register(
            ShellCommand(
                name="agent",
                description="Show detailed agent info",
                usage="agent <id>",
                handler=cmd_agent,
            )
        )
        self.register(
            ShellCommand(
                name="logs",
                description="Tail logs for agent",
                usage="logs <id>",
                handler=cmd_logs,
                aliases=["tail"],
            )
        )
        self.register(
            ShellCommand(
                name="run",
                description="Start batch execution",
                usage="run <task.yaml>",
                handler=cmd_run,
            )
        )
        self.register(
            ShellCommand(
                name="spawn",
                description="Create new agent interactively",
                usage="spawn",
                handler=cmd_spawn,
            )
        )
        self.register(
            ShellCommand(
                name="cancel",
                description="Cancel running agent",
                usage="cancel <id>",
                handler=cmd_cancel,
            )
        )
        self.register(
            ShellCommand(
                name="pause",
                description="Request pause at next iteration",
                usage="pause <id>",
                handler=cmd_pause,
            )
        )
        self.register(
            ShellCommand(
                name="resume",
                description="Resume paused agent",
                usage="resume <id>",
                handler=cmd_resume,
            )
        )
        self.register(
            ShellCommand(
                name="start",
                description="Start a pending agent or all pending agents",
                usage="start [id|all]",
                handler=cmd_start,
            )
        )
        self.register(
            ShellCommand(
                name="clear",
                description="Clear the shell output",
                usage="clear",
                handler=cmd_clear,
            )
        )
        self.register(
            ShellCommand(
                name="history",
                description="Show command history",
                usage="history",
                handler=cmd_history,
            )
        )


# ============================================================================
# Command Implementations
# ============================================================================


async def cmd_help(args: list[str], context: ShellContext) -> str:
    """Show available commands or help for a specific command."""
    # Need to get the registry from somewhere - we'll use a module-level approach
    registry = _get_default_registry()

    if args:
        # Help for specific command
        cmd = registry.get_command(args[0])
        if cmd:
            aliases_str = f" (aliases: {', '.join(cmd.aliases)})" if cmd.aliases else ""
            return f"{cmd.name}{aliases_str}\n  {cmd.description}\n  Usage: {cmd.usage}"
        return f"Unknown command: {args[0]}"

    # List all commands
    lines = ["Available commands:", ""]
    for cmd in registry.get_all_commands():
        aliases_str = f" ({', '.join(cmd.aliases)})" if cmd.aliases else ""
        lines.append(f"  {cmd.name}{aliases_str:<12} - {cmd.description}")
    lines.append("")
    lines.append("Type 'help <command>' for detailed usage.")
    lines.append("Use !<cmd> to execute shell commands.")
    return "\n".join(lines)


async def cmd_status(args: list[str], context: ShellContext) -> str:
    """Show current agent status summary."""
    agents = context.agents
    if not agents:
        return "No agents in session."

    from grind.tui.core.models import AgentStatus

    # Count by status
    status_counts: dict[AgentStatus, int] = {}
    for agent in agents:
        status_counts[agent.status] = status_counts.get(agent.status, 0) + 1

    lines = ["Agent Status Summary:", ""]
    for status, count in sorted(status_counts.items(), key=lambda x: x[0].value):
        lines.append(f"  {status.value:<12}: {count}")
    lines.append(f"  {'Total':<12}: {len(agents)}")

    if context.current_agent_id:
        lines.append(f"\nCurrent agent: {context.current_agent_id}")

    return "\n".join(lines)


async def cmd_agents(args: list[str], context: ShellContext) -> str:
    """List all agents."""
    agents = context.agents
    if not agents:
        return "No agents in session."

    lines = ["ID                    Status       Type         Progress  Duration", "-" * 70]
    for agent in agents:
        progress_pct = f"{agent.progress * 100:.0f}%"
        lines.append(
            f"{agent.agent_id:<22} {agent.status.value:<12} {agent.agent_type.value:<12} "
            f"{progress_pct:<9} {agent.duration}"
        )
    return "\n".join(lines)


async def cmd_agent(args: list[str], context: ShellContext) -> str:
    """Show detailed agent info."""
    if not args:
        return "Usage: agent <id>"

    agent_id = args[0]
    agent = None
    for a in context.agents:
        if a.agent_id == agent_id:
            agent = a
            break

    if not agent:
        return f"Agent not found: {agent_id}"

    lines = [
        f"Agent: {agent.agent_id}",
        "-" * 40,
        f"Task ID:       {agent.task_id}",
        f"Description:   {agent.task_description}",
        f"Type:          {agent.agent_type.value}",
        f"Status:        {agent.status.value}",
        f"Model:         {agent.model}",
        f"Iteration:     {agent.iteration}/{agent.max_iterations}",
        f"Progress:      {agent.progress * 100:.1f}%",
        f"Duration:      {agent.duration}",
        f"Created:       {agent.created_at}",
    ]

    if agent.started_at:
        lines.append(f"Started:       {agent.started_at}")
    if agent.completed_at:
        lines.append(f"Completed:     {agent.completed_at}")
    if agent.output_file:
        lines.append(f"Log file:      {agent.output_file}")
    if agent.error_message:
        lines.append(f"Error:         {agent.error_message}")
    if agent.needs_human_input:
        lines.append(f"Awaiting input: {agent.human_prompt or 'Yes'}")

    return "\n".join(lines)


async def cmd_logs(args: list[str], context: ShellContext) -> str:
    """Tail logs for agent."""
    if not args:
        return "Usage: logs <id>"

    agent_id = args[0]
    agent = None
    for a in context.agents:
        if a.agent_id == agent_id:
            agent = a
            break

    if not agent:
        return f"Agent not found: {agent_id}"

    log_path = context.session.get_agent_log_path(agent_id)
    if not log_path.exists():
        return f"No log file found for agent {agent_id}"

    # Read last N lines
    num_lines = 20
    if len(args) > 1:
        try:
            num_lines = int(args[1])
        except ValueError:
            return f"Invalid line count: {args[1]}"

    try:
        with open(log_path) as f:
            lines = f.readlines()
            tail_lines = lines[-num_lines:] if len(lines) > num_lines else lines
            return "".join(tail_lines).rstrip()
    except Exception as e:
        return f"Error reading log file: {e}"


async def cmd_run(args: list[str], context: ShellContext) -> str:
    """Start batch execution from task file."""
    if not args:
        return "Usage: run <task.yaml>"

    task_file = args[0]

    # Validate file exists
    from pathlib import Path

    task_path = Path(task_file)
    if not task_path.exists():
        return f"Task file not found: {task_file}"

    # Check if executor is available
    if not context.executor:
        return "Executor not available in context"

    try:
        # Load tasks
        import asyncio

        from grind.tasks import load_tasks

        tasks = await asyncio.to_thread(load_tasks, str(task_path))

        if not tasks:
            return f"No tasks found in {task_file}"

        # Create agents for each task
        agent_ids = []
        for task_def in tasks:
            agent = context.executor.create_agent(task_def)
            agent_ids.append(agent.agent_id)

        # Auto-start agents (respecting max_parallel)
        started = 0
        for agent_id in agent_ids:
            if context.executor.start_agent(agent_id):
                started += 1

        return (
            f"Loaded {len(tasks)} tasks from {task_file}\n"
            f"Created {len(agent_ids)} agents, started {started}\n"
            f"Use 'start all' to start remaining pending agents"
        )

    except Exception as e:
        return f"Error loading task file: {e}"


async def cmd_spawn(args: list[str], context: ShellContext) -> str:
    """Create new agent from command line arguments.

    Usage: spawn <model> <max_iterations> <verify_cmd> -- <task_description>
    Example: spawn sonnet 10 "pytest tests/" -- Fix failing unit tests
    """
    if not args or len(args) < 4:
        return (
            "Usage: spawn <model> <max_iterations> <verify_cmd> -- <task>\n"
            "Example: spawn sonnet 10 'pytest tests/' -- Fix failing tests\n"
            "Models: haiku, sonnet, opus"
        )

    # Parse arguments
    try:
        model = args[0]
        if model not in ["haiku", "sonnet", "opus"]:
            return f"Invalid model: {model}. Use haiku, sonnet, or opus"

        max_iterations = int(args[1])
        if max_iterations < 1 or max_iterations > 50:
            return "max_iterations must be between 1 and 50"

        verify_cmd = args[2]

        # Find the "--" separator
        if "--" not in args:
            return "Missing '--' separator before task description"

        sep_index = args.index("--")
        task_description = " ".join(args[sep_index + 1:])

        if not task_description:
            return "Task description cannot be empty"

        # Create TaskDefinition
        from grind.models import TaskDefinition
        task_def = TaskDefinition(
            task=task_description,
            verify=verify_cmd,
            model=model,
            max_iterations=max_iterations,
            cwd=".",
        )

        # Create agent
        if not context.executor:
            return "Executor not available in context"

        agent = context.executor.create_agent(task_def)

        # Auto-start the agent
        started = context.executor.start_agent(agent.agent_id)
        status_msg = "Started" if started else "Created (pending - at max parallel capacity)"

        return (
            f"{status_msg} agent {agent.agent_id}\n"
            f"Task: {task_description[:60]}...\n"
            f"Model: {model}, Max iterations: {max_iterations}\n"
            f"Verify: {verify_cmd}\n"
            f"Check 'Running' tab to monitor progress."
        )

    except ValueError as e:
        return f"Invalid argument: {e}"
    except Exception as e:
        return f"Error creating agent: {e}"


async def cmd_cancel(args: list[str], context: ShellContext) -> str:
    """Cancel running agent."""
    if not args:
        return "Usage: cancel <id>"

    agent_id = args[0]
    agent = None
    for a in context.agents:
        if a.agent_id == agent_id:
            agent = a
            break

    if not agent:
        return f"Agent not found: {agent_id}"

    from grind.tui.core.models import AgentStatus

    if agent.status not in (AgentStatus.RUNNING, AgentStatus.PAUSED, AgentStatus.PENDING):
        return f"Agent {agent_id} cannot be cancelled (status: {agent.status.value})"

    # Check if there's an active task to cancel
    if agent_id in context.session.active_agents:
        task = context.session.active_agents[agent_id]
        task.cancel()
        return f"Cancellation requested for agent {agent_id}"

    return f"No active task found for agent {agent_id}"


async def cmd_pause(args: list[str], context: ShellContext) -> str:
    """Request pause at next iteration."""
    if not args:
        return "Usage: pause <id>"

    agent_id = args[0]
    agent = None
    for a in context.agents:
        if a.agent_id == agent_id:
            agent = a
            break

    if not agent:
        return f"Agent not found: {agent_id}"

    from grind.tui.core.models import AgentStatus

    if agent.status != AgentStatus.RUNNING:
        return f"Agent {agent_id} is not running (status: {agent.status.value})"

    if not context.executor:
        return "Executor not available"

    if await context.executor.pause_agent(agent_id):
        return f"Pause requested for agent {agent_id}"
    else:
        return f"Could not pause agent {agent_id} (not running or not found)"


async def cmd_resume(args: list[str], context: ShellContext) -> str:
    """Resume paused agent."""
    if not args:
        return "Usage: resume <id>"

    agent_id = args[0]
    agent = None
    for a in context.agents:
        if a.agent_id == agent_id:
            agent = a
            break

    if not agent:
        return f"Agent not found: {agent_id}"

    from grind.tui.core.models import AgentStatus

    if agent.status != AgentStatus.PAUSED:
        return f"Agent {agent_id} is not paused (status: {agent.status.value})"

    if not context.executor:
        return "Executor not available"

    if await context.executor.resume_agent(agent_id):
        return f"Resumed agent {agent_id}"
    else:
        return f"Could not resume agent {agent_id} (not paused or not found)"


async def cmd_start(args: list[str], context: ShellContext) -> str:
    """Start a pending agent or all pending agents."""
    from grind.tui.core.models import AgentStatus

    if not context.executor:
        return "Executor not available"

    # Get all pending agents
    pending_agents = [a for a in context.agents if a.status == AgentStatus.PENDING]

    if not pending_agents:
        return "No pending agents to start"

    if not args or args[0] == "all":
        # Start all pending agents
        started = []
        for agent in pending_agents:
            if context.executor.start_agent(agent.agent_id):
                started.append(agent.agent_id)

        if started:
            return f"Started {len(started)} agent(s): {', '.join(started)}"
        else:
            return "Could not start any agents (may be at max parallel capacity)"

    # Start specific agent
    agent_id = args[0]
    agent = None
    for a in context.agents:
        if a.agent_id == agent_id:
            agent = a
            break

    if not agent:
        return f"Agent not found: {agent_id}"

    if agent.status != AgentStatus.PENDING:
        return f"Agent {agent_id} is not pending (status: {agent.status.value})"

    if context.executor.start_agent(agent_id):
        return f"Started agent {agent_id}"
    else:
        return f"Could not start agent {agent_id} (may be at max parallel capacity)"


async def cmd_clear(args: list[str], context: ShellContext) -> str:
    """Clear the shell output."""
    # Return a special marker that the TUI can interpret
    return "\x1b[2J\x1b[H"  # ANSI escape to clear screen


async def cmd_history(args: list[str], context: ShellContext) -> str:
    """Show command history."""
    if not context.history:
        return "No command history."

    lines = []
    for i, cmd in enumerate(context.history, 1):
        lines.append(f"{i:4d}  {cmd}")
    return "\n".join(lines)


async def execute_shell_command(cmd: str) -> str:
    """
    Execute a shell command and return output.

    Args:
        cmd: Shell command to execute

    Returns:
        Command output (stdout + stderr)
    """
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout
        if result.stderr:
            output += result.stderr
        if result.returncode != 0:
            output += f"\n[Exit code: {result.returncode}]"
        return output.rstrip() if output else "(no output)"
    except subprocess.TimeoutExpired:
        return "Command timed out after 30 seconds"
    except Exception as e:
        return f"Error executing command: {e}"


# ============================================================================
# Parser and Executor
# ============================================================================


# Module-level default registry for help command
_default_registry: CommandRegistry | None = None


def _get_default_registry() -> CommandRegistry:
    """Get or create the default command registry."""
    global _default_registry
    if _default_registry is None:
        _default_registry = CommandRegistry()
    return _default_registry


async def parse_and_execute(
    line: str,
    registry: CommandRegistry,
    context: ShellContext,
) -> str:
    """
    Parse and execute a command line.

    Args:
        line: The command line to parse and execute
        registry: The command registry to look up commands
        context: The shell context for command execution

    Returns:
        Output string from command execution
    """
    # Update the default registry for help command
    global _default_registry
    _default_registry = registry

    line = line.strip()
    if not line:
        return ""

    # Handle shell escape (!command)
    if line.startswith("!"):
        shell_cmd = line[1:].strip()
        if not shell_cmd:
            return "Usage: !<command>"
        return await execute_shell_command(shell_cmd)

    # Parse command line using shlex
    try:
        tokens = shlex.split(line)
    except ValueError as e:
        return f"Parse error: {e}"

    if not tokens:
        return ""

    cmd_name = tokens[0]
    args = tokens[1:]

    # Look up command
    cmd = registry.get_command(cmd_name)
    if not cmd:
        return f"Unknown command: {cmd_name}. Type 'help' for available commands."

    # Execute handler
    try:
        return await cmd.handler(args, context)
    except Exception as e:
        return f"Error executing {cmd_name}: {e}"
