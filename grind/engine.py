import json
import subprocess
from datetime import datetime
from typing import Callable

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
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
    log_iteration_end,
    log_iteration_start,
    log_result,
    log_system_prompt,
    log_task_start,
    log_text_block,
    log_tool_use,
    setup_logger,
)
from grind.models import CheckpointAction, GrindResult, GrindStatus, TaskDefinition
from grind.prompts import CONTINUE_PROMPT, DECOMPOSE_PROMPT, build_prompt
from grind.utils import Color

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
    try:
        result = subprocess.run(
            verify_cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
        )
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(Color.error(result.stderr))
        print(Color.header("=" * 60))
        print(Color.info(f"Exit code: {result.returncode}"))
    except Exception as e:
        print(Color.error(f"Error running verify: {e}"))
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


async def grind(
    task_def: TaskDefinition,
    verbose: bool = False,
    on_iteration: Callable[[int, str], None] | None = None,
) -> GrindResult:
    options = ClaudeAgentOptions(
        allowed_tools=(
            task_def.allowed_tools
            if task_def.allowed_tools
            else ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]
        ),
        permission_mode=task_def.permission_mode,
        cwd=task_def.cwd,
        max_turns=task_def.max_turns,
        model=task_def.model,
    )

    start_time = datetime.now()
    all_tools: list[str] = []
    all_hooks_executed: list[tuple[str, str, bool]] = []

    # Set up file logging for this task
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

            await client.query(system_prompt)

            iteration = 0
            while iteration < task_def.max_iterations:
                iteration += 1
                log_iteration_start(iteration, task_def.max_iterations)
                if on_iteration:
                    on_iteration(iteration, "running")
                if verbose:
                    print(f"\n{Color.header('=' * 60)}")
                    print(Color.bold(f"ITERATION {iteration}/{task_def.max_iterations}"))
                    print(Color.header("=" * 60))
                    # Show interject hint if interactive mode is enabled
                    if task_def.interactive.enabled:
                        show_interject_hint()

                collected = ""
                tools: list[str] = []
                had_error = False

                iteration_start = datetime.now()
                async for msg in client.receive_response():
                    if isinstance(msg, AssistantMessage):
                        for block in msg.content:
                            if isinstance(block, TextBlock):
                                log_text_block(block.text)
                                if verbose:
                                    print(Color.dim(block.text))
                                collected += block.text
                            elif isinstance(block, ToolUseBlock):
                                log_tool_use(block.name, block.id, block.input)
                                tools.append(block.name)
                                if verbose:
                                    print(Color.info(f"  -> {block.name}"))
                    elif isinstance(msg, ResultMessage):
                        all_tools.extend(tools)
                        duration = (datetime.now() - start_time).total_seconds()

                        # Log what we collected for debugging
                        _log(verbose, f"\n--- Iteration {iteration} complete ---", "header")
                        _log(verbose, f"Tools used this iteration: {tools}", "dim")
                        _log(verbose, f"Collected text length: {len(collected)} chars", "dim")

                        # Log iteration end
                        iteration_duration_ms = (datetime.now() - iteration_start).total_seconds() * 1000
                        log_iteration_end(iteration, tools, len(collected), iteration_duration_ms)

                        # Check for completion signal
                        has_complete = "GRIND_COMPLETE" in collected
                        has_stuck = "GRIND_STUCK" in collected
                        log_completion_check(has_complete, has_stuck, len(collected), collected)
                        _log(verbose, f"GRIND_COMPLETE found: {has_complete}", "info")
                        _log(verbose, f"GRIND_STUCK found: {has_stuck}", "info")

                        if has_complete:
                            message = ""
                            if "GRIND_COMPLETE:" in collected:
                                message = (
                                    collected.split("GRIND_COMPLETE:")[1]
                                    .split("\n")[0]
                                    .strip()
                                )
                            _log(verbose, f"Completion message: {message or '(none)'}", "success")

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

                        if has_stuck:
                            reason = "Unknown"
                            if "GRIND_STUCK:" in collected:
                                reason = (
                                    collected.split("GRIND_STUCK:")[1]
                                    .split("\n")[0]
                                    .strip()
                                )
                            had_error = True
                            _log(verbose, f"Stuck reason: {reason}", "error")
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

                        # Neither complete nor stuck - continuing
                        _log(verbose, "No completion signal found, will continue...", "warning")

                if task_def.hooks.post_iteration:
                    if verbose:
                        print("\n" + Color.header("=" * 60))
                        print(Color.info("POST-ITERATION HOOKS"))
                        print(Color.header("=" * 60))
                    hook_results = await execute_hooks(
                        client,
                        task_def.hooks.post_iteration,
                        iteration,
                        had_error,
                        verbose,
                    )
                    all_hooks_executed.extend(hook_results)

                # Check for interject request (non-blocking keyboard signal)
                should_checkpoint = (
                    task_def.interactive.enabled
                    and iteration < task_def.max_iterations
                    and is_interject_requested()
                )

                if should_checkpoint:
                    clear_interject()
                    show_checkpoint_menu()
                    duration = (datetime.now() - start_time).total_seconds()

                    while True:
                        action, guidance_text = get_checkpoint_input()

                        if action == CheckpointAction.ABORT:
                            _log(verbose, "User aborted at checkpoint", "warning")
                            tools = list(set(all_tools))
                            log_result("ABORTED", iteration, "User aborted", tools, duration)
                            stop_keyboard_listener()
                            return GrindResult(
                                GrindStatus.STUCK,
                                iteration,
                                "User aborted at checkpoint",
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
                            continue  # Show menu again

                        elif action == CheckpointAction.RUN_VERIFY:
                            _run_verify_command(task_def.verify, task_def.cwd)
                            continue  # Show menu again

                        elif action == CheckpointAction.GUIDANCE and guidance_text:
                            # Inject one-shot guidance into the continue prompt
                            guidance_prompt = GUIDANCE_PROMPT.format(guidance=guidance_text)
                            print(Color.success(f"Injecting guidance: {guidance_text}"))
                            await client.query(guidance_prompt + "\n\n" + CONTINUE_PROMPT)
                            break  # Continue to next iteration

                        elif action == CheckpointAction.GUIDANCE_PERSIST and guidance_text:
                            # Add persistent guidance to prompt config
                            guidance_str = f"Human guidance: {guidance_text}"
                            if task_def.prompt_config.additional_context:
                                ctx = task_def.prompt_config.additional_context
                                task_def.prompt_config.additional_context = f"{ctx}\n\n{guidance_str}"
                            else:
                                task_def.prompt_config.additional_context = guidance_str
                            guidance_prompt = GUIDANCE_PROMPT.format(guidance=guidance_text)
                            print(Color.success(f"Persistent guidance: {guidance_text}"))
                            await client.query(guidance_prompt + "\n\n" + CONTINUE_PROMPT)
                            break  # Continue to next iteration

                        else:  # CONTINUE
                            await client.query(CONTINUE_PROMPT)
                            break  # Continue to next iteration

                elif iteration < task_def.max_iterations:
                    _log(verbose, f"\nSending continue prompt for iteration {iteration + 1}...", "info")
                    log_continue_prompt(iteration)
                    await client.query(CONTINUE_PROMPT)
                else:
                    _log(verbose, f"\nReached max iterations ({task_def.max_iterations})", "warning")

            final_duration = (datetime.now() - start_time).total_seconds()
            _log(verbose, f">>> RETURNING MAX_ITERATIONS after {iteration} iterations", "warning")
            log_result("MAX_ITERATIONS", iteration, f"Reached max iterations ({task_def.max_iterations})", list(set(all_tools)), final_duration)
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
                            print(Color.dim(block.text))
                        collected += block.text

    start = collected.find("{")
    end = collected.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("No JSON found in response")

    data = json.loads(collected[start:end])
    return [
        TaskDefinition(
            task=t["task"],
            verify=t["verify"],
            max_iterations=t.get("max_iterations", 5),
        )
        for t in data.get("tasks", [])
    ]
