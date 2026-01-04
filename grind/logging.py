import json
import logging
import os
import platform
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Truncation limits for log output
INPUT_TRUNCATION_LIMIT = 5000
RESULT_TRUNCATION_LIMIT = 10000
MAX_QUERY_LOG_LINES = 50

_logger: logging.Logger | None = None
_log_file: Path | None = None
_jsonl_file: Path | None = None
_log_dir_override: Path | None = None
_logging_disabled: bool = False
_json_logging_enabled: bool = True  # Enable JSON logging by default

# Session-level state management
_session_dir: Path | None = None
_task_counter: int = 0
_session_logger: logging.Logger | None = None
_session_jsonl_file: Path | None = None


def disable_logging() -> None:
    """Disable file logging. Useful for tests."""
    global _logging_disabled
    _logging_disabled = True


def enable_logging() -> None:
    """Re-enable file logging."""
    global _logging_disabled
    _logging_disabled = False


def set_log_dir(path: Path | None) -> None:
    """Set a custom log directory. Pass None to reset to default."""
    global _log_dir_override
    _log_dir_override = path


def reset_logger() -> None:
    """Reset the logger state. Call between tests for isolation."""
    global _logger, _log_file, _jsonl_file
    if _logger is not None:
        for handler in _logger.handlers[:]:
            handler.close()
            _logger.removeHandler(handler)
    _logger = None
    _log_file = None
    _jsonl_file = None


def reset_session() -> None:
    """Reset all session-level state. Call between tests for isolation."""
    global _session_dir, _task_counter, _session_logger, _session_jsonl_file
    if _session_logger is not None:
        for handler in _session_logger.handlers[:]:
            handler.close()
            _session_logger.removeHandler(handler)
    _session_dir = None
    _task_counter = 0
    _session_logger = None
    _session_jsonl_file = None


def set_json_logging(enabled: bool) -> None:
    """Enable or disable JSON logging."""
    global _json_logging_enabled
    _json_logging_enabled = enabled


def _write_jsonl_event(event_type: str, data: dict[str, Any]) -> None:
    """Write a structured event to the JSONL log file."""
    if _jsonl_file is None:
        return

    event = {
        "timestamp": datetime.now().isoformat(),
        "event": event_type,
        **data,
    }

    try:
        with open(_jsonl_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, default=str) + "\n")
    except Exception:
        pass  # Don't let logging failures affect execution


def get_jsonl_file() -> Path | None:
    """Get the current JSONL log file path."""
    return _jsonl_file


def get_log_dir() -> Path:
    """Get the log directory, creating it if needed."""
    if _log_dir_override is not None:
        log_dir = _log_dir_override
    else:
        log_dir = Path(os.getcwd()) / ".grind" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _create_null_logger() -> logging.Logger:
    """Create a logger that discards all output."""
    logger = logging.getLogger("grind_null")
    logger.setLevel(logging.CRITICAL + 1)
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    return logger


def setup_logger(task_name: str | None = None, task_index: int | None = None) -> logging.Logger:
    """Set up file logging for a grind session.

    Args:
        task_name: Optional task name for log file naming
        task_index: Optional explicit task index. If not provided, will auto-increment _task_counter

    Returns:
        Logger instance
    """
    global _logger, _log_file, _jsonl_file, _session_dir, _task_counter

    # If logging is disabled, return a null logger
    if _logging_disabled:
        _logger = _create_null_logger()
        _log_file = None
        _jsonl_file = None
        return _logger

    # If no session directory exists, create one
    if _session_dir is None:
        setup_session(task_desc=task_name or "task")

    # Determine task index
    if task_index is not None:
        current_task_index = task_index
    else:
        _task_counter += 1
        current_task_index = _task_counter

    # Sanitize task name for filename
    if task_name:
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in task_name[:30])
    else:
        safe_name = "task"

    # Create log files in session directory with task counter
    filename = f"{current_task_index:02d}_{safe_name}.log"
    jsonl_filename = f"{current_task_index:02d}_{safe_name}.jsonl"

    _log_file = _session_dir / filename
    _jsonl_file = _session_dir / jsonl_filename if _json_logging_enabled else None

    # Create logger
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    _logger = logging.getLogger(f"grind_{timestamp}_{current_task_index}")
    _logger.setLevel(logging.DEBUG)
    _logger.handlers.clear()

    # File handler - always logs everything
    file_handler = logging.FileHandler(_log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter(
        "%(asctime)s.%(msecs)03d | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_format)
    _logger.addHandler(file_handler)

    # Log session header with environment info
    _logger.info("=" * 80)
    _logger.info("GRIND SESSION STARTED")
    _logger.info("=" * 80)
    _logger.info(f"Timestamp: {datetime.now().isoformat()}")
    _logger.info(f"Log file: {_log_file}")
    if _jsonl_file:
        _logger.info(f"JSON log file: {_jsonl_file}")
    _logger.info(f"Working directory: {os.getcwd()}")
    _logger.info(f"Python: {sys.version}")
    _logger.info(f"Platform: {platform.platform()}")
    _logger.info("=" * 80)

    # Write initial session event to JSONL
    if _jsonl_file:
        _write_jsonl_event("session_start", {
            "timestamp": datetime.now().isoformat(),
            "log_file": str(_log_file),
            "jsonl_file": str(_jsonl_file),
            "working_directory": os.getcwd(),
            "python_version": sys.version,
            "platform": platform.platform(),
        })

    return _logger


def get_logger() -> logging.Logger:
    """Get the current logger, creating one if needed."""
    global _logger
    if _logger is None:
        _logger = setup_logger()
    return _logger


def get_log_file() -> Path | None:
    """Get the current log file path."""
    return _log_file


def log_task_start(
    task: str,
    verify: str,
    model: str,
    max_iterations: int,
    cwd: str | None = None,
    allowed_tools: list[str] | None = None,
    permission_mode: str | None = None,
) -> None:
    """Log task start with full configuration details."""
    logger = get_logger()
    logger.info("")
    logger.info("#" * 80)
    logger.info("# TASK START")
    logger.info("#" * 80)
    logger.info(f"Task: {task}")
    logger.info(f"Verify command: {verify}")
    logger.info(f"Model: {model}")
    logger.info(f"Max iterations: {max_iterations}")
    logger.info(f"CWD: {cwd or os.getcwd()}")
    logger.info(f"Allowed tools: {allowed_tools or 'default'}")
    logger.info(f"Permission mode: {permission_mode or 'default'}")
    logger.info("#" * 80)

    _write_jsonl_event("task_start", {
        "task": task,
        "verify": verify,
        "model": model,
        "max_iterations": max_iterations,
        "cwd": cwd or os.getcwd(),
        "allowed_tools": allowed_tools,
        "permission_mode": permission_mode,
    })


def log_system_prompt(prompt: str) -> None:
    """Log the full system prompt being sent."""
    logger = get_logger()
    logger.debug("")
    logger.debug("=" * 80)
    logger.debug("SYSTEM PROMPT START")
    logger.debug("=" * 80)
    for line in prompt.split("\n"):
        logger.debug(f"  {line}")
    logger.debug("=" * 80)
    logger.debug("SYSTEM PROMPT END")
    logger.debug("=" * 80)


def log_iteration_start(iteration: int, max_iterations: int) -> None:
    """Log iteration start."""
    logger = get_logger()
    logger.info("")
    logger.info("*" * 80)
    logger.info(f"* ITERATION {iteration}/{max_iterations}")
    logger.info("*" * 80)


def log_iteration_end(
    iteration: int, tools_used: list[str], text_length: int, duration_ms: float
) -> None:
    """Log iteration end with summary."""
    logger = get_logger()
    logger.info("-" * 40)
    logger.info(f"ITERATION {iteration} COMPLETE")
    logger.info(f"  Tools used: {tools_used}")
    logger.info(f"  Text collected: {text_length} chars")
    logger.info(f"  Duration: {duration_ms:.0f}ms")
    logger.info("-" * 40)

    _write_jsonl_event("iteration_end", {
        "iteration": iteration,
        "tools_used": tools_used,
        "text_length": text_length,
        "duration_ms": duration_ms,
    })


def log_tool_use(tool_name: str, tool_id: str, tool_input: dict[str, Any]) -> None:
    """Log tool usage with full input details."""
    logger = get_logger()
    logger.info(f"TOOL CALL: {tool_name}")
    logger.info(f"  ID: {tool_id}")

    # Log full input, handling large values
    try:
        input_str = json.dumps(tool_input, indent=2, default=str)
        if len(input_str) > INPUT_TRUNCATION_LIMIT:
            # For very large inputs, truncate but show structure
            logger.info(f"  Input (truncated, {len(input_str)} chars):")
            for line in input_str[:INPUT_TRUNCATION_LIMIT].split("\n"):
                logger.info(f"    {line}")
            logger.info("    ... (truncated)")
        else:
            logger.info("  Input:")
            for line in input_str.split("\n"):
                logger.info(f"    {line}")
    except Exception as e:
        logger.info(f"  Input: {tool_input} (serialization error: {e})")

    _write_jsonl_event("tool_use", {
        "tool_name": tool_name,
        "tool_id": tool_id,
        "tool_input": tool_input,
    })


def log_tool_result(tool_name: str, tool_id: str, result: str, is_error: bool = False) -> None:
    """Log tool execution result with full content."""
    logger = get_logger()
    status = "ERROR" if is_error else "OK"
    logger.info(f"TOOL RESULT [{status}]: {tool_name} ({tool_id})")
    logger.info(f"  Result length: {len(result)} chars")

    # Log full result at INFO level (important for debugging)
    if len(result) > RESULT_TRUNCATION_LIMIT:
        logger.info(f"  Result (truncated at {RESULT_TRUNCATION_LIMIT} chars):")
        for line in result[:RESULT_TRUNCATION_LIMIT].split("\n"):
            logger.info(f"    {line}")
        logger.info(f"    ... ({len(result) - RESULT_TRUNCATION_LIMIT} more chars)")
    else:
        logger.info("  Result:")
        for line in result.split("\n"):
            logger.info(f"    {line}")

    truncated = len(result) > RESULT_TRUNCATION_LIMIT
    _write_jsonl_event("tool_result", {
        "tool_name": tool_name,
        "tool_id": tool_id,
        "result_length": len(result),
        "is_error": is_error,
        "result": result[:RESULT_TRUNCATION_LIMIT] if truncated else result,
        "truncated": truncated,
    })


def log_text_block(text: str) -> None:
    """Log assistant text output - full content."""
    logger = get_logger()
    logger.info("ASSISTANT TEXT:")
    for line in text.split("\n"):
        logger.info(f"  | {line}")


def log_thinking_block(thinking: str) -> None:
    """Log assistant thinking/reasoning block."""
    logger = get_logger()
    logger.info("ASSISTANT THINKING:")
    logger.info(f"  Length: {len(thinking)} chars")
    for line in thinking.split("\n"):
        logger.info(f"  ~ {line}")


def log_result_message(
    duration_ms: int,
    duration_api_ms: int,
    is_error: bool,
    num_turns: int,
    session_id: str,
    total_cost_usd: float | None,
    usage: dict[str, Any] | None,
) -> None:
    """Log SDK result message with cost and usage telemetry."""
    logger = get_logger()
    logger.info("")
    logger.info("=" * 60)
    logger.info("SDK RESULT MESSAGE")
    logger.info("=" * 60)
    logger.info(f"  Session ID: {session_id}")
    logger.info(f"  Duration (total): {duration_ms}ms ({duration_ms/1000:.2f}s)")
    logger.info(f"  Duration (API): {duration_api_ms}ms ({duration_api_ms/1000:.2f}s)")
    logger.info(f"  Num turns: {num_turns}")
    logger.info(f"  Is error: {is_error}")

    if total_cost_usd is not None:
        logger.info(f"  Total cost: ${total_cost_usd:.6f}")

    if usage:
        logger.info("  Usage:")
        for key, value in usage.items():
            logger.info(f"    {key}: {value}")
    logger.info("=" * 60)

    _write_jsonl_event("sdk_result", {
        "session_id": session_id,
        "duration_ms": duration_ms,
        "duration_api_ms": duration_api_ms,
        "is_error": is_error,
        "num_turns": num_turns,
        "total_cost_usd": total_cost_usd,
        "usage": usage,
    })


def log_completion_check(
    has_complete: bool,
    has_stuck: bool,
    text_length: int,
    collected_text: str | None = None
) -> None:
    """Log completion signal check with context."""
    logger = get_logger()
    logger.info("")
    logger.info("=" * 40)
    logger.info("COMPLETION CHECK")
    logger.info("=" * 40)
    logger.info(f"  GRIND_COMPLETE found: {has_complete}")
    logger.info(f"  GRIND_STUCK found: {has_stuck}")
    logger.info(f"  Total text length: {text_length} chars")

    # If we found a signal, log context around it
    if collected_text:
        if has_complete and "GRIND_COMPLETE" in collected_text:
            idx = collected_text.find("GRIND_COMPLETE")
            start = max(0, idx - 100)
            end = min(len(collected_text), idx + 200)
            logger.info("  Context around GRIND_COMPLETE:")
            logger.info(f"    ...{collected_text[start:end]}...")
        if has_stuck and "GRIND_STUCK" in collected_text:
            idx = collected_text.find("GRIND_STUCK")
            start = max(0, idx - 100)
            end = min(len(collected_text), idx + 200)
            logger.info("  Context around GRIND_STUCK:")
            logger.info(f"    ...{collected_text[start:end]}...")
    logger.info("=" * 40)


def log_continue_prompt(iteration: int) -> None:
    """Log when sending continue prompt."""
    logger = get_logger()
    logger.info(f"SENDING CONTINUE PROMPT for iteration {iteration + 1}")


def log_interject_check(
    context: str,
    interactive_enabled: bool,
    iteration: int,
    max_iterations: int,
    interject_requested: bool,
    checkpoint_triggered: bool,
) -> None:
    """Log interject/checkpoint check with all conditions."""
    logger = get_logger()
    logger.info("")
    logger.info("=" * 40)
    logger.info(f"INTERJECT CHECK ({context})")
    logger.info("=" * 40)
    logger.info(f"  interactive.enabled: {interactive_enabled}")
    logger.info(f"  iteration: {iteration} < max_iterations: {max_iterations}")
    logger.info(f"  is_interject_requested(): {interject_requested}")
    logger.info(f"  checkpoint_triggered: {checkpoint_triggered}")
    logger.info("=" * 40)

    _write_jsonl_event("interject_check", {
        "context": context,
        "interactive_enabled": interactive_enabled,
        "iteration": iteration,
        "max_iterations": max_iterations,
        "interject_requested": interject_requested,
        "checkpoint_triggered": checkpoint_triggered,
    })


def log_result(
    status: str, iterations: int, message: str, tools_used: list[str], duration: float
) -> None:
    """Log final result with full details."""
    logger = get_logger()
    logger.info("")
    logger.info("#" * 80)
    logger.info("# TASK RESULT")
    logger.info("#" * 80)
    logger.info(f"Status: {status}")
    logger.info(f"Iterations: {iterations}")
    logger.info(f"Duration: {duration:.2f}s")
    logger.info(f"Message: {message or '(none)'}")
    logger.info(f"All tools used: {tools_used}")
    logger.info("#" * 80)

    _write_jsonl_event("task_result", {
        "status": status,
        "iterations": iterations,
        "duration_seconds": duration,
        "message": message,
        "tools_used": tools_used,
    })


def log_error(error: str, exc_info: bool = False) -> None:
    """Log an error with optional traceback."""
    logger = get_logger()
    logger.error("!" * 80)
    logger.error("! ERROR")
    logger.error("!" * 80)
    logger.error(f"  {error}")
    if exc_info:
        logger.exception("Full traceback:")
    logger.error("!" * 80)

    _write_jsonl_event("error", {
        "error": error,
        "has_traceback": exc_info,
    })


def log_hook_start(command: str, trigger: str, iteration: int) -> None:
    """Log hook execution start."""
    logger = get_logger()
    logger.info(f"HOOK START: {command}")
    logger.info(f"  Trigger: {trigger}")
    logger.info(f"  Iteration: {iteration}")


def log_hook(command: str, success: bool, output: str = "", duration_ms: float = 0) -> None:
    """Log hook execution result with full output."""
    logger = get_logger()
    status = "OK" if success else "FAILED"
    logger.info(f"HOOK RESULT [{status}]: {command}")
    logger.info(f"  Duration: {duration_ms:.0f}ms")

    # Log full output
    if output:
        logger.info(f"  Output ({len(output)} chars):")
        for line in output.split("\n"):
            logger.debug(f"    {line}")


def log_query_sent(query: str) -> None:
    """Log a query being sent to the SDK."""
    logger = get_logger()
    logger.debug(f"QUERY SENT ({len(query)} chars):")
    for line in query.split("\n")[:MAX_QUERY_LOG_LINES]:
        logger.debug(f"  > {line}")
    if query.count("\n") > MAX_QUERY_LOG_LINES:
        logger.debug(
            f"  ... ({query.count(chr(10)) - MAX_QUERY_LOG_LINES} more lines)"
        )


def log_session_end(
    total_tasks: int, completed: int, stuck: int, failed: int, duration: float
) -> None:
    """Log batch session summary."""
    logger = get_logger()
    logger.info("")
    logger.info("#" * 80)
    logger.info("# SESSION COMPLETE")
    logger.info("#" * 80)
    logger.info(f"Total tasks: {total_tasks}")
    logger.info(f"Completed: {completed}")
    logger.info(f"Stuck: {stuck}")
    logger.info(f"Failed: {failed}")
    logger.info(f"Total duration: {duration:.2f}s")
    logger.info(f"Log file: {_log_file}")
    logger.info("#" * 80)


def log_raw(level: str, message: str) -> None:
    """Log a raw message at specified level."""
    logger = get_logger()
    log_fn = getattr(logger, level.lower(), logger.info)
    log_fn(message)


def log_verify_command(
    command: str,
    cwd: str | None,
    exit_code: int | None,
    stdout: str,
    stderr: str,
    duration_ms: float,
    error: str | None = None,
) -> None:
    """Log verification command execution with full output."""
    logger = get_logger()
    logger.info("")
    logger.info("%" * 80)
    logger.info("% VERIFY COMMAND")
    logger.info("%" * 80)
    logger.info(f"  Command: {command}")
    logger.info(f"  CWD: {cwd or '(current)'}")
    logger.info(f"  Duration: {duration_ms:.0f}ms")

    if error:
        logger.error(f"  Error: {error}")
    else:
        logger.info(f"  Exit code: {exit_code}")

    if stdout:
        logger.info(f"  STDOUT ({len(stdout)} chars):")
        for line in stdout.split("\n"):
            logger.info(f"    {line}")

    if stderr:
        logger.info(f"  STDERR ({len(stderr)} chars):")
        for line in stderr.split("\n"):
            logger.info(f"    {line}")

    logger.info("%" * 80)

    _write_jsonl_event("verify_command", {
        "command": command,
        "cwd": cwd,
        "exit_code": exit_code,
        "stdout_length": len(stdout),
        "stderr_length": len(stderr),
        "duration_ms": duration_ms,
        "error": error,
        "success": exit_code == 0 if exit_code is not None else False,
    })


def sanitize(name: str) -> str:
    """Replace non-alphanumeric characters with underscores."""
    return "".join(c if c.isalnum() else "_" for c in name)


def setup_session(task_file: str | None = None, task_desc: str | None = None) -> Path:
    """
    Set up a session directory for logging multiple tasks.

    Args:
        task_file: Optional path to a task file (used for naming)
        task_desc: Optional task description (used for naming if no file)

    Returns:
        Path to the created session directory
    """
    global _session_dir, _task_counter, _session_logger, _session_jsonl_file

    # Reset task counter
    _task_counter = 0

    # Generate timestamp
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

    # Determine directory name
    if task_file:
        dir_name = f"{timestamp}_{Path(task_file).stem}"
    else:
        sanitized_desc = sanitize(task_desc)[:30] if task_desc else "session"
        dir_name = f"{timestamp}_single_{sanitized_desc}"

    # Create session directory
    _session_dir = get_log_dir() / dir_name
    _session_dir.mkdir(parents=True, exist_ok=True)

    # Create session log files
    session_log_file = _session_dir / "session.log"
    _session_jsonl_file = _session_dir / "session.jsonl"

    # Set up session logger
    _session_logger = logging.getLogger(f"grind_session_{timestamp}")
    _session_logger.setLevel(logging.DEBUG)
    _session_logger.handlers.clear()

    # File handler for session.log
    file_handler = logging.FileHandler(session_log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter(
        "%(asctime)s.%(msecs)03d | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_format)
    _session_logger.addHandler(file_handler)

    # Write session_start event to session.jsonl
    session_start_event = {
        "timestamp": datetime.now().isoformat(),
        "event": "session_start",
        "session_dir": str(_session_dir),
        "task_file": task_file,
        "task_desc": task_desc,
    }

    try:
        with open(_session_jsonl_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(session_start_event, default=str) + "\n")
    except Exception:
        pass  # Don't let logging failures affect execution

    return _session_dir


def get_session_dir() -> Path | None:
    """Get the current session directory."""
    return _session_dir


def log_session_task_start(task_id: str, task_name: str, task_index: int) -> None:
    """
    Log to session.log that a task is starting and write event to session.jsonl.

    Args:
        task_id: Unique identifier for the task
        task_name: Human-readable task name
        task_index: Index of the task in the session (1-based)
    """
    if _session_logger is None:
        return

    _session_logger.info("")
    _session_logger.info("=" * 80)
    _session_logger.info(f"TASK {task_index} START: {task_name}")
    _session_logger.info("=" * 80)
    _session_logger.info(f"  Task ID: {task_id}")
    _session_logger.info(f"  Task name: {task_name}")
    _session_logger.info(f"  Task index: {task_index}")
    _session_logger.info("=" * 80)

    # Write event to session.jsonl
    if _session_jsonl_file is not None:
        event = {
            "timestamp": datetime.now().isoformat(),
            "event": "task_start",
            "task_id": task_id,
            "task_name": task_name,
            "task_index": task_index,
        }
        try:
            with open(_session_jsonl_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, default=str) + "\n")
        except Exception:
            pass  # Don't let logging failures affect execution


def log_session_task_end(task_id: str, status: str, duration: float) -> None:
    """
    Log to session.log that a task finished and write event to session.jsonl.

    Args:
        task_id: Unique identifier for the task
        status: Final status of the task (e.g., 'complete', 'stuck', 'error')
        duration: Duration of the task in seconds
    """
    if _session_logger is None:
        return

    _session_logger.info("")
    _session_logger.info("=" * 80)
    _session_logger.info(f"TASK END: {task_id}")
    _session_logger.info("=" * 80)
    _session_logger.info(f"  Task ID: {task_id}")
    _session_logger.info(f"  Status: {status}")
    _session_logger.info(f"  Duration: {duration:.2f}s")
    _session_logger.info("=" * 80)

    # Write event to session.jsonl
    if _session_jsonl_file is not None:
        event = {
            "timestamp": datetime.now().isoformat(),
            "event": "task_end",
            "task_id": task_id,
            "status": status,
            "duration": duration,
        }
        try:
            with open(_session_jsonl_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, default=str) + "\n")
        except Exception:
            pass  # Don't let logging failures affect execution


def log_session_summary(
    total: int, completed: int, stuck: int, failed: int, duration: float
) -> None:
    """
    Write final summary to session.log and session_end event to session.jsonl.

    Args:
        total: Total number of tasks
        completed: Number of completed tasks
        stuck: Number of stuck tasks
        failed: Number of failed tasks
        duration: Total session duration in seconds
    """
    if _session_logger is None:
        return

    _session_logger.info("")
    _session_logger.info("#" * 80)
    _session_logger.info("# SESSION SUMMARY")
    _session_logger.info("#" * 80)
    _session_logger.info(f"  Total tasks: {total}")
    _session_logger.info(f"  Completed: {completed}")
    _session_logger.info(f"  Stuck: {stuck}")
    _session_logger.info(f"  Failed: {failed}")
    _session_logger.info(f"  Total duration: {duration:.2f}s")
    if _session_dir:
        _session_logger.info(f"  Session directory: {_session_dir}")
    _session_logger.info("#" * 80)

    # Write session_end event to session.jsonl
    if _session_jsonl_file is not None:
        event = {
            "timestamp": datetime.now().isoformat(),
            "event": "session_end",
            "total": total,
            "completed": completed,
            "stuck": stuck,
            "failed": failed,
            "duration": duration,
        }
        try:
            with open(_session_jsonl_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, default=str) + "\n")
        except Exception:
            pass  # Don't let logging failures affect execution


def write_session_summary(
    task_file: str | None,
    tasks: list[dict],
    total_duration: float,
    start_time: datetime,
) -> Path:
    """
    Write a markdown session summary to summary.md in the session directory.

    Args:
        task_file: Optional path to task file (used in header)
        tasks: List of task dictionaries with keys: id, task, status, duration, iterations, message
        total_duration: Total session duration in seconds
        start_time: Session start time

    Returns:
        Path to the created summary.md file
    """
    if _session_dir is None:
        raise RuntimeError("No session directory set. Call setup_session() first.")

    summary_path = _session_dir / "summary.md"

    # Format duration as human-readable (e.g., "5m 32s")
    def format_duration(seconds: float) -> str:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        if mins > 0:
            return f"{mins}m {secs}s"
        else:
            return f"{secs}s"

    # Count statuses
    status_counts: dict[str, int] = {}
    for task in tasks:
        status = task.get("status", "UNKNOWN")
        status_counts[status] = status_counts.get(status, 0) + 1

    # Ensure common statuses are present even if count is 0
    for status in ["COMPLETE", "STUCK", "ERROR", "MAX_ITERATIONS"]:
        if status not in status_counts:
            status_counts[status] = 0

    # Build markdown content
    lines = [
        "# Grind Session Summary",
        "",
        f"**Started:** {start_time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Duration:** {format_duration(total_duration)}",
        f"**Task File:** {task_file or 'N/A'}",
        "",
        "## Results",
        "",
        "| Status | Count |",
        "|--------|-------|",
    ]

    # Add status counts to table
    for status in sorted(status_counts.keys()):
        count = status_counts[status]
        lines.append(f"| {status} | {count} |")

    lines.extend([
        "",
        "## Tasks",
        "",
    ])

    # Add individual task details
    for i, task in enumerate(tasks, 1):
        task_name = task.get("task", "unknown")
        status = task.get("status", "UNKNOWN")
        iterations = task.get("iterations", 0)
        duration = task.get("duration", 0.0)
        message = task.get("message", "")

        lines.extend([
            f"### {i}. {task_name}",
            f"- **Status:** {status}",
            f"- **Iterations:** {iterations}",
            f"- **Duration:** {format_duration(duration)}",
            f"- **Message:** {message}",
            "",
        ])

    # Write to file
    summary_path.write_text("\n".join(lines), encoding="utf-8")

    return summary_path
