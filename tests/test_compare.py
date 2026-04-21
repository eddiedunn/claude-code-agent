"""Tests for grind compare subcommand (argument parsing and table rendering)."""
from __future__ import annotations

import argparse
from unittest.mock import AsyncMock, patch

import pytest

from grind.compare import (
    CompareResult,
    CompareSession,
    _branch_name,
    _sanitize_model,
    _task_id,
    render_table,
)
from grind.models import GrindStatus


# ---------------------------------------------------------------------------
# Unit tests: helpers
# ---------------------------------------------------------------------------

class TestSanitizeModel:
    def test_claude_sonnet(self):
        assert _sanitize_model("claude/sonnet") == "claude-sonnet"

    def test_openrouter_gpt4o(self):
        assert _sanitize_model("openrouter/openai/gpt-4o") == "openrouter-openai-gpt-4o"

    def test_bare_model(self):
        assert _sanitize_model("haiku") == "haiku"

    def test_strips_leading_trailing_dashes(self):
        result = _sanitize_model("/weird//model/")
        assert not result.startswith("-")
        assert not result.endswith("-")


class TestBranchName:
    def test_basic(self):
        branch = _branch_name("compare/", "mytask", "claude/sonnet")
        assert branch == "compare/mytask/claude-sonnet"

    def test_prefix_without_trailing_slash(self):
        branch = _branch_name("compare", "mytask", "claude/opus")
        assert branch == "compare/mytask/claude-opus"

    def test_openrouter(self):
        branch = _branch_name("compare/", "fix", "openrouter/openai/gpt-4o")
        assert branch == "compare/fix/openrouter-openai-gpt-4o"


class TestTaskId:
    def test_format(self):
        tid = _task_id("fix-tests", "claude/sonnet")
        assert tid == "fix-tests-claude-sonnet"


# ---------------------------------------------------------------------------
# Unit tests: CompareSession slug derivation
# ---------------------------------------------------------------------------

class TestCompareSession:
    def test_slug_derived_from_task(self):
        s = CompareSession(task="Fix the failing tests", verify="pytest", models=["claude/sonnet"])
        assert s.slug == "fix-the-failing-tests"

    def test_explicit_slug(self):
        s = CompareSession(task="Fix tests", verify="pytest", models=[], slug="myslug")
        assert s.slug == "myslug"

    def test_slug_truncated(self):
        long_task = "a" * 200
        s = CompareSession(task=long_task, verify="pytest", models=[])
        assert len(s.slug) <= 30


# ---------------------------------------------------------------------------
# Unit tests: render_table
# ---------------------------------------------------------------------------

class TestRenderTable:
    def _make_results(self):
        return [
            CompareResult(
                model="claude/sonnet",
                status=GrindStatus.COMPLETE,
                iterations=3,
                wall_time_s=42.1,
            ),
            CompareResult(
                model="claude/opus",
                status=GrindStatus.STUCK,
                iterations=5,
                wall_time_s=91.7,
                error="got stuck",
            ),
            CompareResult(
                model="openrouter/openai/gpt-4o",
                status=GrindStatus.ERROR,
                iterations=0,
                wall_time_s=3.2,
                error="Provider error",
            ),
        ]

    def test_headers_present(self):
        table = render_table(self._make_results())
        assert "model" in table
        assert "status" in table
        assert "iterations" in table
        assert "wall_time_s" in table
        assert "note" in table

    def test_model_names_in_table(self):
        table = render_table(self._make_results())
        assert "claude/sonnet" in table
        assert "claude/opus" in table
        assert "openrouter/openai/gpt-4o" in table

    def test_status_labels(self):
        table = render_table(self._make_results())
        assert "COMPLETE" in table
        assert "STUCK" in table
        assert "ERROR" in table

    def test_error_note_included(self):
        table = render_table(self._make_results())
        assert "Provider error" in table

    def test_separator_line_present(self):
        table = render_table(self._make_results())
        assert "---" in table

    def test_timeout_result_shows_timeout_label(self):
        results = [CompareResult(model="claude/haiku", status=None, wall_time_s=30.0)]
        table = render_table(results)
        assert "TIMEOUT" in table

    def test_empty_results(self):
        table = render_table([])
        assert "model" in table   # headers still present

    def test_columns_are_aligned(self):
        """Each row should have the same number of double-space separators as the header."""
        results = self._make_results()
        table = render_table(results)
        lines = table.strip().split("\n")
        # header + separator + N rows
        assert len(lines) == len(results) + 2


# ---------------------------------------------------------------------------
# Integration-level test: handle_compare_command with mocked grind
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_compare_command_all_ok():
    """handle_compare_command returns 0 when all models complete."""
    from grind.cli import handle_compare_command

    args = argparse.Namespace(
        task="Fix the bug",
        verify="pytest",
        models=["claude/sonnet", "claude/haiku"],
        max_iter=5,
        timeout=None,
        branch_prefix="compare/",
        verbose=False,
    )

    mock_result = CompareResult(
        model="claude/sonnet",
        status=GrindStatus.COMPLETE,
        iterations=2,
        wall_time_s=10.0,
    )

    with patch("grind.cli.handle_compare_command.__module__"), \
         patch("grind.compare.run_compare", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = [
            CompareResult(model="claude/sonnet", status=GrindStatus.COMPLETE, iterations=2, wall_time_s=5.0),
            CompareResult(model="claude/haiku", status=GrindStatus.COMPLETE, iterations=1, wall_time_s=3.0),
        ]
        exit_code = await handle_compare_command(args)

    assert exit_code == 0


@pytest.mark.asyncio
async def test_handle_compare_command_partial_failure():
    """handle_compare_command returns 1 when at least one model fails."""
    from grind.cli import handle_compare_command

    args = argparse.Namespace(
        task="Fix the bug",
        verify="pytest",
        models=["claude/sonnet", "claude/haiku"],
        max_iter=5,
        timeout=None,
        branch_prefix="compare/",
        verbose=False,
    )

    with patch("grind.compare.run_compare", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = [
            CompareResult(model="claude/sonnet", status=GrindStatus.COMPLETE, iterations=2, wall_time_s=5.0),
            CompareResult(model="claude/haiku", status=GrindStatus.ERROR, iterations=0, wall_time_s=1.0, error="boom"),
        ]
        exit_code = await handle_compare_command(args)

    assert exit_code == 1
