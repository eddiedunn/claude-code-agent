"""Tests for write_session_summary function."""
from datetime import datetime
from pathlib import Path
import tempfile
import shutil

from grind.logging import write_session_summary, setup_session, reset_session


def test_write_session_summary_basic():
    """Test basic session summary generation."""
    # Setup a temporary session
    with tempfile.TemporaryDirectory() as tmpdir:
        from grind.logging import set_log_dir
        set_log_dir(Path(tmpdir))

        session_dir = setup_session(task_file="test_tasks.yaml")

        # Create sample task data
        tasks = [
            {
                "id": "task_1",
                "task": "reduce_default_health_check",
                "status": "COMPLETE",
                "duration": 45.0,
                "iterations": 3,
                "message": "All tests passing",
            },
            {
                "id": "task_2",
                "task": "update_health_check_backoff",
                "status": "STUCK",
                "duration": 135.0,
                "iterations": 10,
                "message": "Unable to resolve type error in config.py",
            },
        ]

        start_time = datetime(2025, 12, 15, 4, 30, 40)
        total_duration = 332.0  # 5m 32s

        # Call the function
        summary_path = write_session_summary(
            task_file="platform_fixes.yaml",
            tasks=tasks,
            total_duration=total_duration,
            start_time=start_time,
        )

        # Verify the file exists
        assert summary_path.exists()
        assert summary_path.name == "summary.md"
        assert summary_path.parent == session_dir

        # Read and verify content
        content = summary_path.read_text()

        # Check header
        assert "# Grind Session Summary" in content

        # Check metadata
        assert "**Started:** 2025-12-15 04:30:40" in content
        assert "**Duration:** 5m 32s" in content
        assert "**Task File:** platform_fixes.yaml" in content

        # Check results table
        assert "| Status | Count |" in content
        assert "| COMPLETE | 1 |" in content
        assert "| STUCK | 1 |" in content
        assert "| ERROR | 0 |" in content

        # Check task details
        assert "### 1. reduce_default_health_check" in content
        assert "- **Status:** COMPLETE" in content
        assert "- **Iterations:** 3" in content
        assert "- **Duration:** 45s" in content
        assert "- **Message:** All tests passing" in content

        assert "### 2. update_health_check_backoff" in content
        assert "- **Status:** STUCK" in content
        assert "- **Iterations:** 10" in content
        assert "- **Duration:** 2m 15s" in content
        assert "- **Message:** Unable to resolve type error in config.py" in content

        # Cleanup
        reset_session()
        set_log_dir(None)


def test_write_session_summary_no_task_file():
    """Test session summary without a task file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from grind.logging import set_log_dir
        set_log_dir(Path(tmpdir))

        session_dir = setup_session(task_desc="single_task")

        tasks = [
            {
                "id": "task_1",
                "task": "fix_bug",
                "status": "COMPLETE",
                "duration": 30.0,
                "iterations": 2,
                "message": "Bug fixed",
            },
        ]

        start_time = datetime(2025, 12, 15, 10, 0, 0)
        total_duration = 30.0

        summary_path = write_session_summary(
            task_file=None,
            tasks=tasks,
            total_duration=total_duration,
            start_time=start_time,
        )

        assert summary_path.exists()
        content = summary_path.read_text()

        # Should show "N/A" when no task file
        assert "**Task File:** N/A" in content

        # Cleanup
        reset_session()
        set_log_dir(None)


def test_write_session_summary_multiple_statuses():
    """Test session summary with multiple task statuses."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from grind.logging import set_log_dir
        set_log_dir(Path(tmpdir))

        session_dir = setup_session(task_file="multi.yaml")

        tasks = [
            {"id": "1", "task": "a", "status": "COMPLETE", "duration": 10.0, "iterations": 1, "message": "OK"},
            {"id": "2", "task": "b", "status": "COMPLETE", "duration": 10.0, "iterations": 1, "message": "OK"},
            {"id": "3", "task": "c", "status": "STUCK", "duration": 60.0, "iterations": 5, "message": "Stuck"},
            {"id": "4", "task": "d", "status": "ERROR", "duration": 5.0, "iterations": 1, "message": "Error"},
            {"id": "5", "task": "e", "status": "MAX_ITERATIONS", "duration": 120.0, "iterations": 10, "message": "Max"},
        ]

        start_time = datetime.now()
        total_duration = 205.0

        summary_path = write_session_summary(
            task_file="multi.yaml",
            tasks=tasks,
            total_duration=total_duration,
            start_time=start_time,
        )

        content = summary_path.read_text()

        # Check counts
        assert "| COMPLETE | 2 |" in content
        assert "| STUCK | 1 |" in content
        assert "| ERROR | 1 |" in content
        assert "| MAX_ITERATIONS | 1 |" in content

        # Cleanup
        reset_session()
        set_log_dir(None)
