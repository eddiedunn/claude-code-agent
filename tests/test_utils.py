"""Tests for grind.utils module."""

import pytest
from io import StringIO
import sys
from grind.utils import Color, print_result, print_batch_summary
from grind.models import GrindResult, GrindStatus, BatchResult


class TestColor:
    def test_color_constants(self):
        assert Color.RESET == "\033[0m"
        assert Color.BOLD == "\033[1m"
        assert Color.RED == "\033[91m"
        assert Color.GREEN == "\033[92m"

    def test_header(self):
        result = Color.header("Test")
        assert "Test" in result
        assert Color.BOLD in result
        assert Color.CYAN in result
        assert Color.RESET in result

    def test_success(self):
        result = Color.success("Success")
        assert "Success" in result
        assert Color.GREEN in result
        assert Color.RESET in result

    def test_error(self):
        result = Color.error("Error")
        assert "Error" in result
        assert Color.RED in result
        assert Color.RESET in result

    def test_warning(self):
        result = Color.warning("Warning")
        assert "Warning" in result
        assert Color.YELLOW in result
        assert Color.RESET in result

    def test_info(self):
        result = Color.info("Info")
        assert "Info" in result
        assert Color.BLUE in result
        assert Color.RESET in result

    def test_dim(self):
        result = Color.dim("Dim")
        assert "Dim" in result
        assert "\033[2m" in result
        assert Color.RESET in result


class TestPrintResult:
    def test_print_complete_result(self, capsys, sample_grind_result):
        print_result(sample_grind_result)
        captured = capsys.readouterr()

        assert "COMPLETE" in captured.out
        assert "Verification passed" in captured.out
        assert "All tests passed" in captured.out
        assert "sonnet" in captured.out
        assert "3" in captured.out
        assert "45.2s" in captured.out

    def test_print_stuck_result(self, capsys):
        result = GrindResult(
            status=GrindStatus.STUCK,
            iterations=5,
            message="Cannot resolve import error",
            tools_used=["Read"],
            duration_seconds=20.0,
            hooks_executed=[],
            model="sonnet"
        )
        print_result(result)
        captured = capsys.readouterr()

        assert "STUCK" in captured.out
        assert "Cannot resolve import error" in captured.out

    def test_print_max_iterations_result(self, capsys):
        result = GrindResult(
            status=GrindStatus.MAX_ITERATIONS,
            iterations=10,
            message="Reached limit",
            tools_used=[],
            duration_seconds=100.0,
            hooks_executed=[],
            model="opus"
        )
        print_result(result)
        captured = capsys.readouterr()

        assert "MAX ITERATIONS" in captured.out
        assert "opus" in captured.out

    def test_print_error_result(self, capsys):
        result = GrindResult(
            status=GrindStatus.ERROR,
            iterations=0,
            message="Connection failed",
            tools_used=[],
            duration_seconds=5.0,
            hooks_executed=[],
            model="sonnet"
        )
        print_result(result)
        captured = capsys.readouterr()

        assert "ERROR" in captured.out
        assert "Connection failed" in captured.out

    def test_print_with_hooks(self, capsys):
        result = GrindResult(
            status=GrindStatus.COMPLETE,
            iterations=3,
            message="",
            tools_used=[],
            duration_seconds=10.0,
            hooks_executed=[
                ("/compact", "output", True),
                ("/test", "failed", False),
            ],
            model="sonnet"
        )
        print_result(result)
        captured = capsys.readouterr()

        assert "Hooks Executed (2)" in captured.out
        assert "/compact" in captured.out
        assert "/test" in captured.out
        assert "OK" in captured.out
        assert "FAILED" in captured.out


class TestPrintBatchSummary:
    def test_print_batch_all_complete(self, capsys):
        results = [
            ("Task 1", GrindResult(GrindStatus.COMPLETE, 3, "", [], 10.0, [], "sonnet")),
            ("Task 2", GrindResult(GrindStatus.COMPLETE, 5, "", [], 15.0, [], "sonnet")),
        ]
        batch = BatchResult(
            total=2,
            completed=2,
            stuck=0,
            failed=0,
            results=results,
            duration_seconds=25.0
        )

        print_batch_summary(batch)
        captured = capsys.readouterr()

        assert "BATCH COMPLETE" in captured.out
        assert "2 COMPLETE" in captured.out
        assert "2 tasks" in captured.out
        assert "Results:" in captured.out
        assert "Task 1" in captured.out
        assert "Task 2" in captured.out
        assert "[OK]" in captured.out
        assert "25.0s" in captured.out

    def test_print_batch_with_failures(self, capsys):
        results = [
            ("Task 1", GrindResult(GrindStatus.COMPLETE, 3, "", [], 10.0, [], "sonnet")),
            ("Task 2", GrindResult(GrindStatus.STUCK, 5, "Error", [], 15.0, [], "sonnet")),
            ("Task 3", GrindResult(GrindStatus.ERROR, 0, "Failed", [], 2.0, [], "sonnet")),
        ]
        batch = BatchResult(
            total=3,
            completed=1,
            stuck=1,
            failed=1,
            results=results,
            duration_seconds=27.0
        )

        print_batch_summary(batch)
        captured = capsys.readouterr()

        assert "BATCH COMPLETE" in captured.out
        assert "1 COMPLETE" in captured.out
        assert "1 STUCK" in captured.out
        assert "1 FAILED" in captured.out
        assert "Action Required:" in captured.out
        assert "Task 2" in captured.out
        assert "Task 3" in captured.out
        assert "STUCK:" in captured.out
        assert "FAILED:" in captured.out
