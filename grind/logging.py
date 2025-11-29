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


def get_log_dir() -> Path:
    """Get the log directory, creating it if needed."""
    log_dir = Path(os.getcwd()) / ".grind" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def setup_logger(task_name: str | None = None) -> logging.Logger:
    """Set up file logging for a grind session."""
    global _logger, _log_file

    log_dir = get_log_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Sanitize task name for filename
    if task_name:
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in task_name[:30])
        filename = f"{timestamp}_{safe_name}.log"
    else:
        filename = f"{timestamp}_grind.log"

    _log_file = log_dir / filename

    # Create logger
    _logger = logging.getLogger(f"grind_{timestamp}")
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
    _logger.info(f"Working directory: {os.getcwd()}")
    _logger.info(f"Python: {sys.version}")
    _logger.info(f"Platform: {platform.platform()}")
    _logger.info("=" * 80)

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


def log_tool_result(tool_name: str, tool_id: str, result: str, is_error: bool = False) -> None:
    """Log tool execution result."""
    logger = get_logger()
    status = "ERROR" if is_error else "OK"
    logger.info(f"TOOL RESULT [{status}]: {tool_name} ({tool_id})")

    # Log full result
    if len(result) > RESULT_TRUNCATION_LIMIT:
        logger.info(f"  Result (truncated, {len(result)} chars):")
        for line in result[:RESULT_TRUNCATION_LIMIT].split("\n"):
            logger.debug(f"    {line}")
        logger.info("    ... (truncated)")
    else:
        for line in result.split("\n"):
            logger.debug(f"    {line}")


def log_text_block(text: str) -> None:
    """Log assistant text output - full content."""
    logger = get_logger()
    logger.info("ASSISTANT TEXT:")
    for line in text.split("\n"):
        logger.info(f"  | {line}")


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
