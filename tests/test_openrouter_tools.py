"""Unit tests for grind/providers/openrouter_tools.py.

Tests cover:
- build_tool_schemas: schema builder returns correct structure.
- _resolve_safe: path traversal rejection.
- Individual tool executors: Read, Write, Edit, Bash, Glob, Grep.
- execute_tool dispatch: unknown tool, known tool success, known tool error.
"""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

from grind.providers.openrouter_tools import (
    SUPPORTED_TOOLS,
    _resolve_safe,
    build_tool_schemas,
    execute_tool,
)


# ---------------------------------------------------------------------------
# build_tool_schemas
# ---------------------------------------------------------------------------

class TestBuildToolSchemas:
    def test_empty_list_returns_empty(self):
        assert build_tool_schemas([]) == []

    def test_single_known_tool(self):
        schemas = build_tool_schemas(["Read"])
        assert len(schemas) == 1
        s = schemas[0]
        assert s["type"] == "function"
        assert s["function"]["name"] == "Read"
        assert "parameters" in s["function"]

    def test_all_supported_tools(self):
        schemas = build_tool_schemas(list(SUPPORTED_TOOLS))
        assert len(schemas) == len(SUPPORTED_TOOLS)
        names = [s["function"]["name"] for s in schemas]
        for tool in SUPPORTED_TOOLS:
            assert tool in names

    def test_unknown_tools_skipped(self):
        schemas = build_tool_schemas(["Read", "NonExistent", "Write"])
        assert len(schemas) == 2
        names = [s["function"]["name"] for s in schemas]
        assert "Read" in names
        assert "Write" in names

    def test_schema_has_required_fields(self):
        schemas = build_tool_schemas(["Bash"])
        fn = schemas[0]["function"]
        assert "name" in fn
        assert "description" in fn
        assert "parameters" in fn
        params = fn["parameters"]
        assert params["type"] == "object"
        assert "properties" in params
        assert "required" in params
        assert "command" in params["required"]

    def test_write_schema_requires_file_path_and_content(self):
        schemas = build_tool_schemas(["Write"])
        fn = schemas[0]["function"]
        assert "file_path" in fn["parameters"]["required"]
        assert "content" in fn["parameters"]["required"]

    def test_read_schema_optional_offset_limit(self):
        schemas = build_tool_schemas(["Read"])
        fn = schemas[0]["function"]
        props = fn["parameters"]["properties"]
        assert "offset" in props
        assert "limit" in props
        # offset and limit should NOT be required
        assert "offset" not in fn["parameters"].get("required", [])
        assert "limit" not in fn["parameters"].get("required", [])


# ---------------------------------------------------------------------------
# _resolve_safe — path traversal guard
# ---------------------------------------------------------------------------

class TestResolveSafe:
    def test_relative_path_inside_cwd(self, tmp_path):
        result = _resolve_safe("subdir/file.txt", str(tmp_path))
        assert result == tmp_path.resolve() / "subdir" / "file.txt"

    def test_absolute_path_inside_cwd(self, tmp_path):
        abs_path = str(tmp_path / "file.txt")
        result = _resolve_safe(abs_path, str(tmp_path))
        assert result == Path(abs_path).resolve()

    def test_dotdot_traversal_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="outside"):
            _resolve_safe("../../etc/passwd", str(tmp_path))

    def test_absolute_path_outside_cwd_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="outside"):
            _resolve_safe("/etc/passwd", str(tmp_path))

    def test_deep_relative_still_inside(self, tmp_path):
        result = _resolve_safe("a/b/c/d.py", str(tmp_path))
        assert str(result).startswith(str(tmp_path.resolve()))

    def test_path_equal_to_cwd_root(self, tmp_path):
        # Resolving "." should land exactly on cwd
        result = _resolve_safe(".", str(tmp_path))
        assert result == tmp_path.resolve()


# ---------------------------------------------------------------------------
# Read executor
# ---------------------------------------------------------------------------

class TestReadExecutor:
    def test_read_simple_file(self, tmp_path):
        f = tmp_path / "hello.txt"
        f.write_text("line1\nline2\nline3\n")
        result, is_error = execute_tool("Read", {"file_path": "hello.txt"}, str(tmp_path))
        assert not is_error
        assert "line1" in result
        assert "line2" in result

    def test_read_adds_line_numbers(self, tmp_path):
        f = tmp_path / "numbered.txt"
        f.write_text("alpha\nbeta\ngamma\n")
        result, is_error = execute_tool("Read", {"file_path": "numbered.txt"}, str(tmp_path))
        assert not is_error
        assert "1\t" in result or "1 " in result  # some line number format

    def test_read_with_offset(self, tmp_path):
        f = tmp_path / "data.txt"
        lines = "\n".join(f"line{i}" for i in range(1, 11))
        f.write_text(lines + "\n")
        result, is_error = execute_tool(
            "Read", {"file_path": "data.txt", "offset": 5}, str(tmp_path)
        )
        assert not is_error
        assert "line5" in result
        # line1 through line4 should not appear (but line10 contains "line1" as substr)
        # so check that line1\n is absent (as standalone line)
        assert "\tline1\n" not in result
        assert "\tline2\n" not in result
        assert "\tline3\n" not in result
        assert "\tline4\n" not in result

    def test_read_with_limit(self, tmp_path):
        f = tmp_path / "data.txt"
        f.write_text("\n".join(f"line{i}" for i in range(1, 20)) + "\n")
        result, is_error = execute_tool(
            "Read", {"file_path": "data.txt", "limit": 3}, str(tmp_path)
        )
        assert not is_error
        # Should have 3 lines
        lines = [l for l in result.strip().split("\n") if l]
        assert len(lines) == 3

    def test_read_nonexistent_file(self, tmp_path):
        result, is_error = execute_tool(
            "Read", {"file_path": "missing.txt"}, str(tmp_path)
        )
        assert is_error
        assert "not found" in result.lower() or "missing" in result.lower()

    def test_read_path_traversal_rejected(self, tmp_path):
        result, is_error = execute_tool(
            "Read", {"file_path": "../../etc/passwd"}, str(tmp_path)
        )
        assert is_error
        assert "outside" in result.lower()

    def test_read_directory_rejected(self, tmp_path):
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        result, is_error = execute_tool(
            "Read", {"file_path": "subdir"}, str(tmp_path)
        )
        assert is_error


# ---------------------------------------------------------------------------
# Write executor
# ---------------------------------------------------------------------------

class TestWriteExecutor:
    def test_write_creates_file(self, tmp_path):
        result, is_error = execute_tool(
            "Write",
            {"file_path": "output.txt", "content": "hello world\n"},
            str(tmp_path),
        )
        assert not is_error
        assert (tmp_path / "output.txt").read_text() == "hello world\n"

    def test_write_creates_parent_dirs(self, tmp_path):
        result, is_error = execute_tool(
            "Write",
            {"file_path": "nested/deep/file.py", "content": "# code\n"},
            str(tmp_path),
        )
        assert not is_error
        assert (tmp_path / "nested" / "deep" / "file.py").exists()

    def test_write_overwrites_existing(self, tmp_path):
        f = tmp_path / "existing.txt"
        f.write_text("old content")
        result, is_error = execute_tool(
            "Write",
            {"file_path": "existing.txt", "content": "new content"},
            str(tmp_path),
        )
        assert not is_error
        assert f.read_text() == "new content"

    def test_write_path_traversal_rejected(self, tmp_path):
        result, is_error = execute_tool(
            "Write",
            {"file_path": "../../evil.txt", "content": "pwned"},
            str(tmp_path),
        )
        assert is_error
        assert not (Path("/tmp") / "evil.txt").exists()


# ---------------------------------------------------------------------------
# Edit executor
# ---------------------------------------------------------------------------

class TestEditExecutor:
    def test_edit_replaces_unique_string(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("def foo():\n    return 1\n")
        result, is_error = execute_tool(
            "Edit",
            {
                "file_path": "code.py",
                "old_string": "return 1",
                "new_string": "return 42",
            },
            str(tmp_path),
        )
        assert not is_error
        assert f.read_text() == "def foo():\n    return 42\n"

    def test_edit_fails_when_old_string_not_found(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("def foo():\n    pass\n")
        result, is_error = execute_tool(
            "Edit",
            {
                "file_path": "code.py",
                "old_string": "DOES_NOT_EXIST",
                "new_string": "replacement",
            },
            str(tmp_path),
        )
        assert is_error
        assert "not found" in result.lower()

    def test_edit_fails_when_multiple_matches(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("x = 1\nx = 1\n")
        result, is_error = execute_tool(
            "Edit",
            {
                "file_path": "code.py",
                "old_string": "x = 1",
                "new_string": "x = 2",
            },
            str(tmp_path),
        )
        assert is_error
        assert "2" in result  # mentions count

    def test_edit_nonexistent_file(self, tmp_path):
        result, is_error = execute_tool(
            "Edit",
            {
                "file_path": "missing.py",
                "old_string": "foo",
                "new_string": "bar",
            },
            str(tmp_path),
        )
        assert is_error

    def test_edit_path_traversal_rejected(self, tmp_path):
        result, is_error = execute_tool(
            "Edit",
            {
                "file_path": "../../etc/passwd",
                "old_string": "root",
                "new_string": "hacked",
            },
            str(tmp_path),
        )
        assert is_error
        assert "outside" in result.lower()


# ---------------------------------------------------------------------------
# Bash executor
# ---------------------------------------------------------------------------

class TestBashExecutor:
    def test_bash_simple_command(self, tmp_path):
        result, is_error = execute_tool(
            "Bash", {"command": "echo hello"}, str(tmp_path)
        )
        assert not is_error
        assert "hello" in result

    def test_bash_cwd_is_worktree(self, tmp_path):
        result, is_error = execute_tool(
            "Bash", {"command": "pwd"}, str(tmp_path)
        )
        assert not is_error
        # The pwd output should match (resolve symlinks)
        assert Path(result.strip()).resolve() == tmp_path.resolve()

    def test_bash_nonzero_exit_not_provider_error(self, tmp_path):
        result, is_error = execute_tool(
            "Bash", {"command": "exit 1"}, str(tmp_path)
        )
        # Non-zero exit is surfaced in result text, NOT as a provider error
        assert not is_error
        assert "1" in result  # exit code mentioned

    def test_bash_timeout_respected(self, tmp_path):
        result, is_error = execute_tool(
            "Bash",
            {"command": "sleep 10", "timeout": 1},
            str(tmp_path),
        )
        assert not is_error
        assert "timed out" in result.lower() or "timeout" in result.lower()

    def test_bash_writes_file(self, tmp_path):
        result, is_error = execute_tool(
            "Bash",
            {"command": "echo 'from bash' > output.txt"},
            str(tmp_path),
        )
        assert not is_error
        assert (tmp_path / "output.txt").exists()

    def test_bash_stderr_captured(self, tmp_path):
        result, is_error = execute_tool(
            "Bash",
            {"command": "echo error_message >&2"},
            str(tmp_path),
        )
        assert not is_error
        assert "error_message" in result


# ---------------------------------------------------------------------------
# Glob executor
# ---------------------------------------------------------------------------

class TestGlobExecutor:
    def test_glob_finds_files(self, tmp_path):
        (tmp_path / "a.py").write_text("")
        (tmp_path / "b.py").write_text("")
        (tmp_path / "c.txt").write_text("")
        result, is_error = execute_tool(
            "Glob", {"pattern": "*.py"}, str(tmp_path)
        )
        assert not is_error
        assert "a.py" in result
        assert "b.py" in result
        assert "c.txt" not in result

    def test_glob_recursive_pattern(self, tmp_path):
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "deep.py").write_text("")
        result, is_error = execute_tool(
            "Glob", {"pattern": "**/*.py"}, str(tmp_path)
        )
        assert not is_error
        assert "deep.py" in result

    def test_glob_no_matches(self, tmp_path):
        result, is_error = execute_tool(
            "Glob", {"pattern": "*.nonexistent"}, str(tmp_path)
        )
        assert not is_error
        assert "no matches" in result.lower()

    def test_glob_path_traversal_rejected(self, tmp_path):
        result, is_error = execute_tool(
            "Glob",
            {"pattern": "*.py", "path": "../../"},
            str(tmp_path),
        )
        assert is_error


# ---------------------------------------------------------------------------
# Grep executor
# ---------------------------------------------------------------------------

class TestGrepExecutor:
    def test_grep_finds_pattern(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("def hello():\n    pass\ndef world():\n    pass\n")
        result, is_error = execute_tool(
            "Grep", {"pattern": "def hello"}, str(tmp_path)
        )
        assert not is_error
        assert "hello" in result

    def test_grep_no_matches(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("nothing here\n")
        result, is_error = execute_tool(
            "Grep", {"pattern": "DOES_NOT_EXIST_XYZ"}, str(tmp_path)
        )
        assert not is_error
        assert "no matches" in result.lower()

    def test_grep_with_glob_filter(self, tmp_path):
        (tmp_path / "code.py").write_text("FIND_ME\n")
        (tmp_path / "code.txt").write_text("FIND_ME\n")
        result, is_error = execute_tool(
            "Grep",
            {"pattern": "FIND_ME", "glob": "*.py"},
            str(tmp_path),
        )
        assert not is_error
        # Should mention the .py file
        assert "code.py" in result


# ---------------------------------------------------------------------------
# execute_tool dispatch
# ---------------------------------------------------------------------------

class TestExecuteToolDispatch:
    def test_unknown_tool_returns_error(self, tmp_path):
        result, is_error = execute_tool(
            "NonExistentTool", {}, str(tmp_path)
        )
        assert is_error
        assert "unknown tool" in result.lower()

    def test_known_tool_success(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("content")
        result, is_error = execute_tool(
            "Read", {"file_path": "file.txt"}, str(tmp_path)
        )
        assert not is_error

    def test_tool_error_does_not_raise(self, tmp_path):
        # Calling Read on a missing file should return (error_msg, True),
        # not raise an exception.
        result, is_error = execute_tool(
            "Read", {"file_path": "missing.txt"}, str(tmp_path)
        )
        assert isinstance(result, str)
        assert isinstance(is_error, bool)
        assert is_error
