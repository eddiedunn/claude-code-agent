import asyncio
import json
import re
import shlex
import subprocess
import time
from datetime import datetime
from typing import Callable

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
)

from grind.hooks import execute_hooks
from grind.interactive import (
    clear_interject,
    get_checkpoint_input,
    is_interject_requested,
    show_checkpoint_menu,
    show_interject_hint,
    start_keyboard_listener,
    stop_keyboard_listener,
)
from grind.logging import (
    log_completion_check,
    log_continue_prompt,
    log_error,
    log_interject_check,
    log_iteration_end,
    log_iteration_start,
    log_result,
    log_result_message,
    log_system_prompt,
    log_task_start,
    log_text_block,
    log_thinking_block,
    log_tool_result,
    log_tool_use,
    log_verify_command,
    setup_logger,
)
from grind.models import CheckpointAction, GrindResult, GrindStatus, TaskDefinition
from grind.orchestration.events import AgentEvent, EventBus, EventType
from grind.prompts import CONTINUE_PROMPT, DECOMPOSE_PROMPT, build_prompt
from grind.router import CostAwareRouter
from grind.utils import Color

# Default set of tools available to the agent
DEFAULT_ALLOWED_TOOLS = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]

# User abort message constants
MSG_USER_ABORTED_AT_CHECKPOINT = "User aborted at checkpoint"
MSG_USER_ABORTED = "User aborted"


def _get_git_author_env() -> dict[str, str]:
    """Get git author environment variables from git config.

    This ensures agents commit with the user's git identity rather than
    Claude Code's default identity.

    Returns:
        Dict with GIT_AUTHOR_NAME, GIT_AUTHOR_EMAIL, GIT_COMMITTER_NAME,
        GIT_COMMITTER_EMAIL if available from git config.
    """
    env = {}
    try:
        result = subprocess.run(
            ["git", "config", "--get", "user.name"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            name = result.stdout.strip()
            env["GIT_AUTHOR_NAME"] = name
            env["GIT_COMMITTER_NAME"] = name

        result = subprocess.run(
            ["git", "config", "--get", "user.email"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            email = result.stdout.strip()
            env["GIT_AUTHOR_EMAIL"] = email
            env["GIT_COMMITTER_EMAIL"] = email
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return env

# Regex patterns for detecting completion signals
# Signals must be on their own line (not embedded in prose)
# Supports optional markdown formatting: **GRIND_COMPLETE**, *GRIND_COMPLETE*, etc.
# Also supports markdown headings: ## GRIND_COMPLETE, # GRIND_COMPLETE, etc.
# Pattern: ^ + whitespace? + heading? + markdown? + signal + markdown? + message? + $
COMPLETE_PATTERN = re.compile(
    r'^'              # Start of line
    r'\s*'            # Optional leading whitespace
    r'(?:[#]+\s+)?'   # Optional markdown heading (# ## ### etc followed by space)
    r'[*_]{0,3}'      # Optional markdown formatting (*, **, ***, _, __, ___)
    r'GRIND_COMPLETE' # The signal
    r'[*_]{0,3}'      # Optional closing markdown
    r'(?::\s*(.*))?'  # Optional message after colon
    r'\s*$',          # Optional trailing whitespace + end of line
    re.MULTILINE
)
STUCK_PATTERN = re.compile(
    r'^'
    r'\s*'
    r'(?:[#]+\s+)?'   # Optional markdown heading
    r'[*_]{0,3}'
    r'GRIND_STUCK'
    r'[*_]{0,3}'
    r'(?::\s*(.*))?'
    r'\s*$',
    re.MULTILINE
)

GUIDANCE_PROMPT = """The human operator observing this session has provided the following guidance:

"{guidance}"

Consider this input as you continue working on the task."""


def _show_status(
    iteration: int,
    max_iterations: int,
    tools_used: list[str],
    duration: float,
    verify_cmd: str,
    cwd: str | None,
) -> None:
    """Display current grind status."""
    print()
    print(Color.header("=" * 60))
    print(Color.bold("STATUS"))
    print(Color.header("=" * 60))
    print(Color.info(f"  Iteration:      {iteration}/{max_iterations}"))
    print(Color.info(f"  Duration:       {duration:.1f}s"))
    print(Color.info(f"  Working dir:    {cwd or 'current'}"))
    print(Color.info(f"  Verify command: {verify_cmd}"))
    print(Color.info(f"  Tools used:     {', '.join(set(tools_used)) or 'none'}"))
    print(Color.header("=" * 60))


def _run_verify_command(verify_cmd: str, cwd: str | None) -> None:
    """Run the verify command and display output."""
    print()
    print(Color.header("=" * 60))
    print(Color.bold(f"RUNNING: {verify_cmd}"))
    print(Color.header("=" * 60))

    start_time = datetime.now()
    try:
        cmd_parts = shlex.split(verify_cmd)
    except ValueError as e:
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        print(Color.error(f"Invalid command syntax: {e}"))
        print(Color.header("=" * 60))
        log_verify_command(verify_cmd, cwd, None, "", "", duration_ms, str(e))
        return

    try:
        result = subprocess.run(
            cmd_parts,
            shell=False,
            cwd=cwd,
            capture_output=True,
            text=True,
        )
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000

        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(Color.error(result.stderr))
        print(Color.header("=" * 60))
        print(Color.info(f"Exit code: {result.returncode}"))

        # Log the verify command execution
        log_verify_command(
            verify_cmd, cwd, result.returncode,
            result.stdout or "", result.stderr or "", duration_ms
        )
    except Exception as e:
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        print(Color.error(f"Error running verify: {e}"))
        log_verify_command(verify_cmd, cwd, None, "", "", duration_ms, str(e))

    print(Color.header("=" * 60))


def _log(verbose: bool, msg: str, level: str = "info") -> None:
    """Structured logging helper for verbose output."""
    if not verbose:
        return
    color_fn = {
        "info": Color.info,
        "success": Color.success,
        "error": Color.error,
        "warning": Color.warning,
        "dim": Color.dim,
        "header": Color.header,
        "bold": Color.bold,
    }.get(level, Color.dim)
    print(color_fn(msg))


def _process_text_block(
    block: TextBlock,
    collected: str,
    verbose: bool,
) -> str:
    """Process a text block and append to collected text."""
    log_text_block(block.text)
    if verbose:
        print(Color.dim(block.text))
    # Ensure newline between text blocks for signal detection
    if collected and not collected.endswith('\n'):
        collected += '\n'
    return collected + block.text


def _process_tool_use_block(
    block: ToolUseBlock,
    tools: list[str],
    pending_tool_calls: dict[str, str],
    verbose: bool,
) -> None:
    """Process a tool use block."""
    log_tool_use(block.name, block.id, block.input)
    tools.append(block.name)
    pending_tool_calls[block.id] = block.name
    if verbose:
        print(Color.info(f"  -> {block.name}"))


def _process_tool_result_block(
    block: ToolResultBlock,
    pending_tool_calls: dict[str, str],
    verbose: bool,
) -> None:
    """Process a tool result block."""
    tool_id = block.tool_use_id
    tool_name = pending_tool_calls.get(tool_id, "unknown")
    if isinstance(block.content, str):
        result_content = block.content
    else:
        result_content = str(block.content)
    is_err = block.is_error or False
    log_tool_result(tool_name, tool_id, result_content, is_err)
    if verbose and is_err:
        print(Color.error(f"  <- {tool_name} ERROR"))


async def _handle_complete_signal(
    task_def: TaskDefinition,
    client: ClaudeSDKClient,
    complete_match: re.Match,
    iteration: int,
    all_tools: list[str],
    all_hooks_executed: list[tuple[str, str, bool]],
    start_time: datetime,
    verbose: bool,
) -> GrindResult:
    """Handle GRIND_COMPLETE signal."""
    message = complete_match.group(1) or "Task completed"
    message = message.split('\n')[0].strip()  # First line only
    _log(verbose, f"Completion message: {message}", "success")

    # Check for interject even on completion
    interject_req = is_interject_requested()
    checkpoint = task_def.interactive.enabled and interject_req
    log_interject_check(
        "on_complete",
        task_def.interactive.enabled,
        iteration,
        task_def.max_iterations,
        interject_req,
        checkpoint,
    )
    if checkpoint:
        clear_interject()
        msg = "\n[Interject caught - pausing before completion]"
        print(Color.warning(msg))
        show_checkpoint_menu()
        action, _ = get_checkpoint_input()
        if action == CheckpointAction.ABORT:
            _log(verbose, MSG_USER_ABORTED_AT_CHECKPOINT, "warning")
            duration = (datetime.now() - start_time).total_seconds()
            tools = list(set(all_tools))
            log_result("ABORTED", iteration, MSG_USER_ABORTED, tools, duration)
            return GrindResult(
                GrindStatus.STUCK,
                iteration,
                MSG_USER_ABORTED_AT_CHECKPOINT,
                list(set(all_tools)),
                duration,
                all_hooks_executed,
                task_def.model,
            )

    if task_def.hooks.post_grind:
        if verbose:
            print("\n" + Color.header("=" * 60))
            print(Color.success("POST-GRIND HOOKS"))
            print(Color.header("=" * 60))
        hook_results = await execute_hooks(
            client,
            task_def.hooks.post_grind,
            iteration,
            False,
            verbose,
        )
        all_hooks_executed.extend(hook_results)

    duration = (datetime.now() - start_time).total_seconds()
    _log(verbose, f">>> RETURNING COMPLETE after {iteration} iterations", "success")
    log_result("COMPLETE", iteration, message, list(set(all_tools)), duration)
    return GrindResult(
        GrindStatus.COMPLETE,
        iteration,
        message,
        list(set(all_tools)),
        duration,
        all_hooks_executed,
        task_def.model,
    )


def _handle_stuck_signal(
    task_def: TaskDefinition,
    stuck_match: re.Match,
    iteration: int,
    all_tools: list[str],
    all_hooks_executed: list[tuple[str, str, bool]],
    start_time: datetime,
    verbose: bool,
) -> GrindResult:
    """Handle GRIND_STUCK signal."""
    reason = stuck_match.group(1) or "Unknown reason"
    reason = reason.split('\n')[0].strip()  # First line only
    _log(verbose, f"Stuck reason: {reason}", "error")

    # Check for interject even on stuck
    interject_req = is_interject_requested()
    checkpoint = task_def.interactive.enabled and interject_req
    log_interject_check(
        "on_stuck",
        task_def.interactive.enabled,
        iteration,
        task_def.max_iterations,
        interject_req,
        checkpoint,
    )
    if checkpoint:
        clear_interject()
        msg = "\n[Interject caught - pausing before stuck]"
        print(Color.warning(msg))
        show_checkpoint_menu()
        action, _ = get_checkpoint_input()
        if action == CheckpointAction.ABORT:
            _log(verbose, MSG_USER_ABORTED_AT_CHECKPOINT, "warning")
            duration = (datetime.now() - start_time).total_seconds()
            tools = list(set(all_tools))
            log_result("ABORTED", iteration, MSG_USER_ABORTED, tools, duration)
            return GrindResult(
                GrindStatus.STUCK,
                iteration,
                MSG_USER_ABORTED_AT_CHECKPOINT,
                list(set(all_tools)),
                duration,
                all_hooks_executed,
                task_def.model,
            )

    duration = (datetime.now() - start_time).total_seconds()
    _log(verbose, f">>> RETURNING STUCK after {iteration} iterations", "error")
    log_result("STUCK", iteration, reason, list(set(all_tools)), duration)
    return GrindResult(
        GrindStatus.STUCK,
        iteration,
        reason,
        list(set(all_tools)),
        duration,
        all_hooks_executed,
        task_def.model,
    )


async def _process_messages(
    client: ClaudeSDKClient,
    iteration: int,
    iteration_start: datetime,
    verbose: bool,
) -> tuple[str, list[str]]:
    """Process messages from client and return collected text and tools used."""
    collected = ""
    tools: list[str] = []
    pending_tool_calls: dict[str, str] = {}  # tool_id -> tool_name

    async for msg in client.receive_response():
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    collected = _process_text_block(block, collected, verbose)
                elif isinstance(block, ThinkingBlock):
                    log_thinking_block(block.thinking)
                    if verbose:
                        thinking_len = len(block.thinking)
                        print(Color.dim(f"[thinking: {thinking_len} chars]"))
                elif isinstance(block, ToolUseBlock):
                    _process_tool_use_block(block, tools, pending_tool_calls, verbose)
                elif isinstance(block, ToolResultBlock):
                    _process_tool_result_block(block, pending_tool_calls, verbose)
        elif isinstance(msg, ResultMessage):
            # Log SDK telemetry from ResultMessage
            log_result_message(
                duration_ms=msg.duration_ms,
                duration_api_ms=msg.duration_api_ms,
                is_error=msg.is_error,
                num_turns=msg.num_turns,
                session_id=msg.session_id,
                total_cost_usd=msg.total_cost_usd,
                usage=msg.usage,
            )

            # Log what we collected for debugging
            _log(verbose, f"\n--- Iteration {iteration} complete ---", "header")
            _log(verbose, f"Tools used this iteration: {tools}", "dim")
            _log(verbose, f"Collected text length: {len(collected)} chars", "dim")

            # Log iteration end
            iteration_duration = (datetime.now() - iteration_start).total_seconds()
            iteration_duration_ms = iteration_duration * 1000
            log_iteration_end(iteration, tools, len(collected), iteration_duration_ms)

    return collected, tools


async def _check_completion_signals(
    task_def: TaskDefinition,
    client: ClaudeSDKClient,
    collected: str,
    iteration: int,
    all_tools: list[str],
    all_hooks_executed: list[tuple[str, str, bool]],
    start_time: datetime,
    verbose: bool,
) -> tuple[GrindResult | None, bool]:
    """Check for completion signals and return result if found.

    Returns (GrindResult if found, had_error flag).
    """
    # Check for completion signals using regex patterns
    complete_match = COMPLETE_PATTERN.search(collected)
    stuck_match = STUCK_PATTERN.search(collected)
    has_complete = complete_match is not None
    has_stuck = stuck_match is not None
    log_completion_check(has_complete, has_stuck, len(collected), collected)
    _log(verbose, f"GRIND_COMPLETE found: {has_complete}", "info")
    _log(verbose, f"GRIND_STUCK found: {has_stuck}", "info")

    if complete_match:
        result = await _handle_complete_signal(
            task_def, client, complete_match, iteration,
            all_tools, all_hooks_executed, start_time, verbose
        )
        return result, False

    if stuck_match:
        result = _handle_stuck_signal(
            task_def, stuck_match, iteration,
            all_tools, all_hooks_executed, start_time, verbose
        )
        return result, True

    # Neither complete nor stuck - continuing
    _log(verbose, "No completion signal found, will continue...", "warning")
    return None, False


def _setup_task_logging(task_def: TaskDefinition, verbose: bool) -> str:
    """Set up logging and build system prompt for the task."""
    setup_logger(task_def.task)
    log_task_start(
        task_def.task,
        task_def.verify,
        task_def.model,
        task_def.max_iterations,
        task_def.cwd,
        task_def.allowed_tools,
        task_def.permission_mode,
    )

    system_prompt = build_prompt(task_def.prompt_config, task_def.task, task_def.verify)
    log_system_prompt(system_prompt)

    if verbose:
        print(f"\n{Color.dim('Model:')} {Color.model_badge(task_def.model)}")
        print(f"{Color.dim('Task:')} {Color.bold(task_def.task)}")
        print(f"{Color.dim('Verify:')} {Color.info(task_def.verify)}")
        print(f"{Color.dim('Max iterations:')} {task_def.max_iterations}")
        print("\n" + Color.header("=" * 60))
        print(Color.header("SYSTEM PROMPT"))
        print(Color.header("=" * 60))
        print(Color.dim(system_prompt))
        print(Color.header("=" * 60) + "\n")

    return system_prompt


async def _run_iteration(
    task_def: TaskDefinition,
    client: ClaudeSDKClient,
    iteration: int,
    all_tools: list[str],
    all_hooks_executed: list[tuple[str, str, bool]],
    start_time: datetime,
    verbose: bool,
    on_iteration: Callable[[int, str], None] | None,
    event_bus: EventBus | None,
) -> GrindResult | None:
    """Run a single iteration of the grind loop.

    Returns GrindResult if should exit, None to continue.
    """
    log_iteration_start(iteration, task_def.max_iterations)

    # Emit ITERATION_STARTED event
    if event_bus:
        await event_bus.publish(AgentEvent(
            event_type=EventType.ITERATION_STARTED,
            agent_id="grind",
            data={"iteration": iteration, "max_iterations": task_def.max_iterations},
            timestamp=time.time()
        ))
    if on_iteration:
        on_iteration(iteration, "running")
    if verbose:
        print(f"\n{Color.header('=' * 60)}")
        print(Color.bold(f"ITERATION {iteration}/{task_def.max_iterations}"))
        print(Color.header("=" * 60))
        if task_def.interactive.enabled:
            show_interject_hint()

    had_error = False
    iteration_start = datetime.now()

    # Process messages with timeout protection
    try:
        async with asyncio.timeout(task_def.query_timeout * 2):
            collected, tools = await _process_messages(
                client, iteration, iteration_start, verbose
            )
            all_tools.extend(tools)

            # Check for completion signals
            result, had_error = await _check_completion_signals(
                task_def, client, collected, iteration,
                all_tools, all_hooks_executed, start_time, verbose
            )
            if result is not None:
                # Emit ITERATION_COMPLETED event before returning
                if event_bus:
                    await event_bus.publish(AgentEvent(
                        event_type=EventType.ITERATION_COMPLETED,
                        agent_id="grind",
                        data={"iteration": iteration, "tools_used": list(set(all_tools))},
                        timestamp=time.time()
                    ))
                return result
    except asyncio.TimeoutError:
        timeout_secs = task_def.query_timeout * 2
        timeout_msg = (
            f">>> Response timed out after {timeout_secs} seconds, continuing..."
        )
        _log(verbose, timeout_msg, "warning")
        return None

    # Run post-iteration hooks
    if task_def.hooks.post_iteration:
        if verbose:
            print("\n" + Color.header("=" * 60))
            print(Color.info("POST-ITERATION HOOKS"))
            print(Color.header("=" * 60))
        hook_results = await execute_hooks(
            client, task_def.hooks.post_iteration, iteration, had_error, verbose
        )
        all_hooks_executed.extend(hook_results)

    # Check for interactive checkpoint
    interject_req = is_interject_requested()
    should_checkpoint = (
        task_def.interactive.enabled
        and iteration < task_def.max_iterations
        and interject_req
    )
    log_interject_check(
        "end_of_iteration",
        task_def.interactive.enabled,
        iteration,
        task_def.max_iterations,
        interject_req,
        should_checkpoint,
    )

    if should_checkpoint:
        clear_interject()
        show_checkpoint_menu()
        result = await _handle_checkpoint_actions(
            task_def, client, iteration, all_tools,
            all_hooks_executed, start_time, verbose
        )
        if result is not None:
            # Emit ITERATION_COMPLETED event before returning
            if event_bus:
                await event_bus.publish(AgentEvent(
                    event_type=EventType.ITERATION_COMPLETED,
                    agent_id="grind",
                    data={"iteration": iteration, "tools_used": list(set(all_tools))},
                    timestamp=time.time()
                ))
            return result
    elif iteration < task_def.max_iterations:
        await _send_continue_prompt(task_def, client, iteration, verbose)
    else:
        _log(
            verbose,
            f"\nReached max iterations ({task_def.max_iterations})",
            "warning",
        )

    # Emit ITERATION_COMPLETED event
    if event_bus:
        await event_bus.publish(AgentEvent(
            event_type=EventType.ITERATION_COMPLETED,
            agent_id="grind",
            data={"iteration": iteration, "tools_used": list(set(all_tools))},
            timestamp=time.time()
        ))

    return None


async def _send_continue_prompt(
    task_def: TaskDefinition,
    client: ClaudeSDKClient,
    iteration: int,
    verbose: bool,
) -> None:
    """Send continue prompt to the client."""
    _log(
        verbose,
        f"\nSending continue prompt for iteration {iteration + 1}...",
        "info",
    )
    log_continue_prompt(iteration)
    try:
        async with asyncio.timeout(task_def.query_timeout):
            await client.query(CONTINUE_PROMPT)
    except asyncio.TimeoutError:
        timeout_msg = (
            f">>> Continue query timed out after {task_def.query_timeout} seconds"
        )
        _log(verbose, timeout_msg, "warning")


async def _handle_checkpoint_actions(
    task_def: TaskDefinition,
    client: ClaudeSDKClient,
    iteration: int,
    all_tools: list[str],
    all_hooks_executed: list[tuple[str, str, bool]],
    start_time: datetime,
    verbose: bool,
) -> GrindResult | None:
    """Handle checkpoint actions.

    Returns GrindResult if should exit, None to continue.
    """
    duration = (datetime.now() - start_time).total_seconds()

    while True:
        action, guidance_text = get_checkpoint_input()

        if action == CheckpointAction.ABORT:
            _log(verbose, MSG_USER_ABORTED_AT_CHECKPOINT, "warning")
            tools = list(set(all_tools))
            log_result("ABORTED", iteration, MSG_USER_ABORTED, tools, duration)
            stop_keyboard_listener()
            return GrindResult(
                GrindStatus.STUCK,
                iteration,
                MSG_USER_ABORTED_AT_CHECKPOINT,
                list(set(all_tools)),
                duration,
                all_hooks_executed,
                task_def.model,
            )

        elif action == CheckpointAction.STATUS:
            _show_status(
                iteration,
                task_def.max_iterations,
                all_tools,
                duration,
                task_def.verify,
                task_def.cwd,
            )

        elif action == CheckpointAction.RUN_VERIFY:
            _run_verify_command(task_def.verify, task_def.cwd)

        elif action == CheckpointAction.GUIDANCE and guidance_text:
            # Inject one-shot guidance into the continue prompt
            guidance_prompt = GUIDANCE_PROMPT.format(guidance=guidance_text)
            print(Color.success(f"Injecting guidance: {guidance_text}"))
            try:
                async with asyncio.timeout(task_def.query_timeout):
                    await client.query(guidance_prompt + "\n\n" + CONTINUE_PROMPT)
            except asyncio.TimeoutError:
                _log(
                    verbose,
                    f">>> Guidance query timed out after {task_def.query_timeout} seconds",
                    "warning",
                )
            return None  # Continue to next iteration

        elif action == CheckpointAction.GUIDANCE_PERSIST and guidance_text:
            # Add persistent guidance to prompt config
            guidance_str = f"Human guidance: {guidance_text}"
            if task_def.prompt_config.additional_context:
                ctx = task_def.prompt_config.additional_context
                new_context = f"{ctx}\n\n{guidance_str}"
                task_def.prompt_config.additional_context = new_context
            else:
                task_def.prompt_config.additional_context = guidance_str
            guidance_prompt = GUIDANCE_PROMPT.format(guidance=guidance_text)
            print(Color.success(f"Persistent guidance: {guidance_text}"))
            try:
                async with asyncio.timeout(task_def.query_timeout):
                    await client.query(guidance_prompt + "\n\n" + CONTINUE_PROMPT)
            except asyncio.TimeoutError:
                timeout_msg = (
                    f">>> Persistent guidance query timed out after "
                    f"{task_def.query_timeout} seconds"
                )
                _log(verbose, timeout_msg, "warning")
            return None  # Continue to next iteration

        else:  # CONTINUE
            try:
                async with asyncio.timeout(task_def.query_timeout):
                    await client.query(CONTINUE_PROMPT)
            except asyncio.TimeoutError:
                _log(
                    verbose,
                    f">>> Continue query timed out after {task_def.query_timeout} seconds",
                    "warning",
                )
            return None  # Continue to next iteration


async def grind(
    task_def: TaskDefinition,
    verbose: bool = False,
    on_iteration: Callable[[int, str], None] | None = None,
    event_bus: EventBus | None = None,
) -> GrindResult:
    # NOTE: task_def.enable_interleaved_thinking is currently not used
    # The Claude Agent SDK does not yet support the anthropic-beta header for interleaved thinking
    # This field is kept for backward compatibility and may be enabled in a future SDK version
    options = ClaudeAgentOptions(
        allowed_tools=(
            task_def.allowed_tools
            if task_def.allowed_tools
            else DEFAULT_ALLOWED_TOOLS
        ),
        permission_mode=task_def.permission_mode,
        cwd=task_def.cwd,
        max_turns=task_def.max_turns,
        model=task_def.model,
        env=_get_git_author_env(),
    )

    start_time = datetime.now()
    all_tools: list[str] = []
    all_hooks_executed: list[tuple[str, str, bool]] = []

    # Set up logging and get system prompt
    system_prompt = _setup_task_logging(task_def, verbose)

    # Start keyboard listener for interactive mode
    if task_def.interactive.enabled:
        start_keyboard_listener()
        print(Color.info("Interactive mode enabled - press 'i' to interject"))

    try:
        async with ClaudeSDKClient(options=options) as client:
            if task_def.hooks.pre_grind:
                if verbose:
                    print("\n" + Color.header("=" * 60))
                    print(Color.info("PRE-GRIND HOOKS"))
                    print(Color.header("=" * 60))
                hook_results = await execute_hooks(
                    client, task_def.hooks.pre_grind, 0, False, verbose
                )
                all_hooks_executed.extend(hook_results)

            # Send initial query with timeout protection
            try:
                async with asyncio.timeout(task_def.query_timeout):
                    await client.query(system_prompt)
            except asyncio.TimeoutError:
                error_msg = f"SDK query timed out after {task_def.query_timeout} seconds"
                _log(verbose, f">>> TIMEOUT: {error_msg}", "error")
                log_error(error_msg)
                return GrindResult(
                    GrindStatus.ERROR,
                    0,
                    error_msg,
                    list(set(all_tools)),
                    (datetime.now() - start_time).total_seconds(),
                    all_hooks_executed,
                    task_def.model,
                )

            iteration = 0
            while iteration < task_def.max_iterations:
                iteration += 1
                result = await _run_iteration(
                    task_def, client, iteration, all_tools,
                    all_hooks_executed, start_time, verbose, on_iteration, event_bus
                )
                if result is not None:
                    return result

            final_duration = (datetime.now() - start_time).total_seconds()
            _log(
                verbose,
                f">>> RETURNING MAX_ITERATIONS after {iteration} iterations",
                "warning",
            )
            log_result(
                "MAX_ITERATIONS",
                iteration,
                f"Reached max iterations ({task_def.max_iterations})",
                list(set(all_tools)),
                final_duration,
            )
            return GrindResult(
                GrindStatus.MAX_ITERATIONS,
                iteration,
                f"Reached max iterations ({task_def.max_iterations})",
                list(set(all_tools)),
                (datetime.now() - start_time).total_seconds(),
                all_hooks_executed,
                task_def.model,
            )

    except Exception as e:
        _log(verbose, f">>> EXCEPTION: {e}", "error")
        _log(verbose, ">>> RETURNING ERROR", "error")
        log_error(str(e), exc_info=True)
        error_duration = (datetime.now() - start_time).total_seconds()
        log_result("ERROR", 0, str(e), list(set(all_tools)), error_duration)
        return GrindResult(
            GrindStatus.ERROR,
            0,
            str(e),
            [],
            (datetime.now() - start_time).total_seconds(),
            all_hooks_executed,
            task_def.model,
        )

    finally:
        # Always stop keyboard listener when grind exits
        if task_def.interactive.enabled:
            stop_keyboard_listener()


async def decompose(
    problem: str,
    verify_cmd: str,
    cwd: str | None = None,
    verbose: bool = False
) -> list[TaskDefinition]:
    options = ClaudeAgentOptions(
        allowed_tools=["Bash", "Read", "Glob", "Grep", "WebSearch", "WebFetch"],
        permission_mode="acceptEdits",
        cwd=cwd,
        max_turns=10,
        model="opus",
        max_thinking_tokens=10000,
        env=_get_git_author_env(),
    )

    collected = ""
    async with ClaudeSDKClient(options=options) as client:
        await client.query(DECOMPOSE_PROMPT.format(problem=problem, verify_cmd=verify_cmd))
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        if verbose:
                            print(Color.dim(block.text))
                        collected += block.text

    start = collected.find("{")
    end = collected.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("No JSON found in response")

    data = json.loads(collected[start:end])
    router = CostAwareRouter()
    return [
        TaskDefinition(
            task=t["task"],
            verify=t["verify"],
            max_iterations=t.get("max_iterations", 5),
            model=t.get('model') or router.route_task(t["task"]),
            depends_on=t.get('depends_on', []),
        )
        for t in data.get("tasks", [])
    ]
