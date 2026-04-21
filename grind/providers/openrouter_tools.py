"""OpenAI-compatible tool schemas and local executors for OpenRouter provider.

This module provides two things:

1. **Schemas** — OpenAI function-calling schema definitions for a useful subset
   of grind tools (Read, Write, Edit, Bash, Glob, Grep).  These are sent to the
   model in the ``tools`` field of the chat completions request.

2. **Executors** — pure-Python implementations that run each tool locally inside
   the worktree directory (``config.cwd``).  Executors enforce:
   - All paths are resolved relative to cwd; absolute paths that escape cwd are
     rejected (path traversal guard).
   - Bash runs via ``subprocess`` with a configurable timeout.
   - No network access is performed by any executor.

Usage::

    schemas = build_tool_schemas(["Read", "Write", "Bash"])
    result = execute_tool("Read", {"file_path": "src/foo.py"}, cwd="/tmp/worktree")
"""
from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Supported tool names
# ---------------------------------------------------------------------------

SUPPORTED_TOOLS = ("Read", "Write", "Edit", "Bash", "Glob", "Grep")

# Default Bash timeout (seconds)
_BASH_TIMEOUT = 60

# Maximum file size to read (bytes) — prevents accidentally reading huge binaries
_MAX_READ_BYTES = 512 * 1024  # 512 KB

# ---------------------------------------------------------------------------
# Schema definitions
# ---------------------------------------------------------------------------

_SCHEMAS: dict[str, dict] = {
    "Read": {
        "type": "function",
        "function": {
            "name": "Read",
            "description": (
                "Read the contents of a file.  Path is relative to the working directory "
                "unless it is already absolute (absolute paths must stay inside the cwd)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to read (relative to cwd or absolute within cwd).",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Line number to start reading from (1-based).  Defaults to 1.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of lines to return.  Omit to read the whole file.",
                    },
                },
                "required": ["file_path"],
            },
        },
    },
    "Write": {
        "type": "function",
        "function": {
            "name": "Write",
            "description": (
                "Write (or overwrite) a file with the given content.  "
                "Creates parent directories automatically.  "
                "Path is relative to cwd."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Destination path (relative to cwd or absolute within cwd).",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full content to write to the file.",
                    },
                },
                "required": ["file_path", "content"],
            },
        },
    },
    "Edit": {
        "type": "function",
        "function": {
            "name": "Edit",
            "description": (
                "Replace a unique substring in an existing file with new text.  "
                "Fails if old_string is not found exactly once."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to edit (relative to cwd or absolute within cwd).",
                    },
                    "old_string": {
                        "type": "string",
                        "description": "Exact text to find and replace (must appear exactly once).",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "Replacement text.",
                    },
                },
                "required": ["file_path", "old_string", "new_string"],
            },
        },
    },
    "Bash": {
        "type": "function",
        "function": {
            "name": "Bash",
            "description": (
                "Execute a shell command in the working directory.  "
                "Returns combined stdout and stderr.  "
                "Commands run with a 60-second timeout."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute.",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Optional timeout override in seconds (max 120).",
                    },
                },
                "required": ["command"],
            },
        },
    },
    "Glob": {
        "type": "function",
        "function": {
            "name": "Glob",
            "description": (
                "Find files matching a glob pattern, relative to cwd.  "
                "Returns a newline-separated list of matching paths."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern (e.g. '**/*.py', 'src/*.ts').",
                    },
                    "path": {
                        "type": "string",
                        "description": "Sub-directory to search within (optional, defaults to cwd root).",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    "Grep": {
        "type": "function",
        "function": {
            "name": "Grep",
            "description": (
                "Search for a regex pattern in files.  "
                "Returns matching lines with file path and line number."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regex pattern to search for.",
                    },
                    "path": {
                        "type": "string",
                        "description": "File or directory to search (optional, defaults to cwd root).",
                    },
                    "glob": {
                        "type": "string",
                        "description": "File glob filter (e.g. '*.py').  Optional.",
                    },
                    "output_mode": {
                        "type": "string",
                        "enum": ["content", "files_with_matches", "count"],
                        "description": "Output mode: 'content' (default), 'files_with_matches', or 'count'.",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
}


def build_tool_schemas(tool_names: list[str]) -> list[dict]:
    """Return OpenAI-compatible tool schema objects for the requested tools.

    Only tools in *SUPPORTED_TOOLS* are included; unknown names are silently
    skipped.  If *tool_names* is empty, returns an empty list.

    Args:
        tool_names: List of grind tool names (e.g. ``["Read", "Write", "Bash"]``).

    Returns:
        List of OpenAI function-schema dicts suitable for the ``tools`` field.
    """
    schemas = []
    for name in tool_names:
        if name in _SCHEMAS:
            schemas.append(_SCHEMAS[name])
    return schemas


# ---------------------------------------------------------------------------
# Path safety helpers
# ---------------------------------------------------------------------------

def _resolve_safe(path_str: str, cwd: str) -> Path:
    """Resolve *path_str* relative to *cwd*, raising ValueError if it escapes.

    Absolute paths are accepted only if they are inside *cwd*.

    Raises:
        ValueError: if the resolved path escapes *cwd*.
    """
    cwd_path = Path(cwd).resolve()
    candidate = Path(path_str)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (cwd_path / candidate).resolve()

    # Ensure resolved is under cwd
    try:
        resolved.relative_to(cwd_path)
    except ValueError:
        raise ValueError(
            f"Path '{path_str}' resolves to '{resolved}' which is outside "
            f"the working directory '{cwd_path}'"
        )
    return resolved


# ---------------------------------------------------------------------------
# Individual tool executors
# ---------------------------------------------------------------------------

def _exec_read(inputs: dict[str, Any], cwd: str) -> str:
    """Execute the Read tool."""
    file_path = inputs.get("file_path", "")
    offset = int(inputs.get("offset") or 1)
    limit = inputs.get("limit")

    resolved = _resolve_safe(file_path, cwd)

    if not resolved.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    if not resolved.is_file():
        raise IsADirectoryError(f"Path is a directory, not a file: {file_path}")

    # Guard against huge files
    size = resolved.stat().st_size
    if size > _MAX_READ_BYTES:
        raise ValueError(
            f"File is too large to read ({size} bytes > {_MAX_READ_BYTES} limit). "
            "Use offset/limit parameters to read in chunks."
        )

    lines = resolved.read_text(errors="replace").splitlines(keepends=True)
    start = max(0, offset - 1)  # convert to 0-based
    if limit is not None:
        end = start + int(limit)
        lines = lines[start:end]
    else:
        lines = lines[start:]

    # Add line numbers (matching the Read tool's cat -n style)
    numbered = []
    for i, line in enumerate(lines, start=start + 1):
        numbered.append(f"{i}\t{line}")
    return "".join(numbered)


def _exec_write(inputs: dict[str, Any], cwd: str) -> str:
    """Execute the Write tool."""
    file_path = inputs.get("file_path", "")
    content = inputs.get("content", "")

    resolved = _resolve_safe(file_path, cwd)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content)
    return f"File written: {file_path} ({len(content)} bytes)"


def _exec_edit(inputs: dict[str, Any], cwd: str) -> str:
    """Execute the Edit tool (exact-string replacement)."""
    file_path = inputs.get("file_path", "")
    old_string = inputs.get("old_string", "")
    new_string = inputs.get("new_string", "")

    resolved = _resolve_safe(file_path, cwd)

    if not resolved.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    content = resolved.read_text(errors="replace")
    count = content.count(old_string)
    if count == 0:
        raise ValueError(f"old_string not found in {file_path}")
    if count > 1:
        raise ValueError(
            f"old_string matches {count} locations in {file_path}; "
            "provide a longer unique context."
        )

    new_content = content.replace(old_string, new_string, 1)
    resolved.write_text(new_content)
    return f"Edit applied to {file_path}"


def _exec_bash(inputs: dict[str, Any], cwd: str) -> str:
    """Execute the Bash tool."""
    command = inputs.get("command", "")
    timeout_raw = inputs.get("timeout")
    timeout = min(int(timeout_raw), 120) if timeout_raw else _BASH_TIMEOUT

    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output_parts = []
        if proc.stdout:
            output_parts.append(proc.stdout)
        if proc.stderr:
            output_parts.append(proc.stderr)
        combined = "".join(output_parts)
        if proc.returncode != 0:
            return f"Exit code: {proc.returncode}\n{combined}"
        return combined if combined else "(no output)"
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout}s: {command}"


def _exec_glob(inputs: dict[str, Any], cwd: str) -> str:
    """Execute the Glob tool."""
    pattern = inputs.get("pattern", "")
    sub_path = inputs.get("path", "")

    cwd_path = Path(cwd).resolve()
    if sub_path:
        search_root = _resolve_safe(sub_path, cwd)
    else:
        search_root = cwd_path

    matches = sorted(search_root.glob(pattern))
    # Return paths relative to cwd
    rel_matches = []
    for m in matches:
        try:
            rel_matches.append(str(m.relative_to(cwd_path)))
        except ValueError:
            pass  # shouldn't happen due to _resolve_safe

    if not rel_matches:
        return "(no matches)"
    return "\n".join(rel_matches)


def _exec_grep(inputs: dict[str, Any], cwd: str) -> str:
    """Execute the Grep tool (delegates to rg/grep subprocess)."""
    pattern = inputs.get("pattern", "")
    sub_path = inputs.get("path", "")
    glob_filter = inputs.get("glob", "")
    output_mode = inputs.get("output_mode", "content")

    cwd_path = Path(cwd).resolve()
    if sub_path:
        search_target = str(_resolve_safe(sub_path, cwd))
    else:
        search_target = str(cwd_path)

    # Try rg first, fall back to grep
    use_rg = _rg_available()

    if use_rg:
        cmd = ["rg", "--no-heading"]
        if output_mode == "files_with_matches":
            cmd.append("-l")
        elif output_mode == "count":
            cmd.append("--count")
        else:
            cmd += ["-n"]  # line numbers for content mode
        if glob_filter:
            cmd += ["--glob", glob_filter]
        cmd += [pattern, search_target]
    else:
        cmd = ["grep", "-r", "-n"]
        if output_mode == "files_with_matches":
            cmd = ["grep", "-r", "-l"]
        if glob_filter:
            # grep's --include
            cmd += [f"--include={glob_filter}"]
        cmd += [pattern, search_target]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = proc.stdout
        if not output.strip():
            return "(no matches)"
        return output
    except subprocess.TimeoutExpired:
        return "Grep timed out after 30s"
    except FileNotFoundError:
        # Neither rg nor grep available — shouldn't happen on any Unix system
        return "grep/rg not available"


def _rg_available() -> bool:
    """Return True if ripgrep (rg) is available on PATH."""
    try:
        subprocess.run(["rg", "--version"], capture_output=True, check=True, timeout=5)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_EXECUTORS = {
    "Read": _exec_read,
    "Write": _exec_write,
    "Edit": _exec_edit,
    "Bash": _exec_bash,
    "Glob": _exec_glob,
    "Grep": _exec_grep,
}


def execute_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    cwd: str,
) -> tuple[str, bool]:
    """Execute a tool and return ``(result_text, is_error)``.

    Args:
        tool_name: Name of the tool to execute (e.g. ``"Read"``).
        tool_input: Dict of tool arguments as provided by the model.
        cwd: Working directory (worktree root) for the tool invocation.

    Returns:
        A ``(result_text, is_error)`` tuple.  *is_error* is True only for
        user-visible error conditions (file not found, path traversal, etc.);
        the error text is returned as *result_text* so the model can react.
        Non-zero Bash exit codes are NOT treated as errors — they are surfaced
        in the result text.
    """
    executor = _EXECUTORS.get(tool_name)
    if executor is None:
        return f"Unknown tool: {tool_name}", True

    try:
        result = executor(tool_input, cwd)
        return result, False
    except (ValueError, FileNotFoundError, IsADirectoryError, PermissionError) as exc:
        return str(exc), True
    except Exception as exc:  # noqa: BLE001
        return f"Tool execution error ({type(exc).__name__}): {exc}", True
