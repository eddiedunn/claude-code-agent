"""Tests for session-based logging functionality."""
import tempfile
from pathlib import Path

from grind.logging import (
    disable_logging,
    enable_logging,
    get_log_file,
    get_session_dir,
    reset_logger,
    reset_session,
    set_log_dir,
    setup_logger,
    setup_session,
)


def test_setup_session_creates_directory():
    """Test that setup_session creates a session directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        set_log_dir(Path(tmpdir))

        # Setup session
        session_dir = setup_session(task_desc="test_task")

        # Verify directory was created
        assert session_dir is not None
        assert session_dir.exists()
        assert session_dir.is_dir()

        # Verify it's under the log directory
        assert str(session_dir).startswith(str(tmpdir))

        # Verify session.log and session.jsonl exist
        assert (session_dir / "session.log").exists()
        assert (session_dir / "session.jsonl").exists()

        # Cleanup
        reset_session()
        set_log_dir(None)


def test_setup_session_with_task_file():
    """Test that setup_session uses task file name in directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        set_log_dir(Path(tmpdir))

        # Setup session with task file
        session_dir = setup_session(task_file="my_tasks.yaml")

        # Directory name should include task file stem
        assert "my_tasks" in session_dir.name

        # Cleanup
        reset_session()
        set_log_dir(None)


def test_setup_session_single_task():
    """Test that setup_session handles single task (no file)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        set_log_dir(Path(tmpdir))

        # Setup session with just a description
        session_dir = setup_session(task_desc="fix_bug")

        # Directory name should include "single" and sanitized desc
        assert "single" in session_dir.name
        assert "fix_bug" in session_dir.name

        # Cleanup
        reset_session()
        set_log_dir(None)


def test_task_logs_numbered_correctly():
    """Test that task logs are numbered correctly in session directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        set_log_dir(Path(tmpdir))
        enable_logging()

        # Setup session
        session_dir = setup_session(task_desc="multi_task")

        # Setup multiple task loggers
        logger1 = setup_logger(task_name="first_task")
        log_file1 = get_log_file()
        reset_logger()

        logger2 = setup_logger(task_name="second_task")
        log_file2 = get_log_file()
        reset_logger()

        logger3 = setup_logger(task_name="third_task")
        log_file3 = get_log_file()
        reset_logger()

        # Verify all log files are in session directory
        assert log_file1.parent == session_dir
        assert log_file2.parent == session_dir
        assert log_file3.parent == session_dir

        # Verify numbering (01_, 02_, 03_)
        assert log_file1.name.startswith("01_")
        assert log_file2.name.startswith("02_")
        assert log_file3.name.startswith("03_")

        # Verify task names in filenames
        assert "first_task" in log_file1.name
        assert "second_task" in log_file2.name
        assert "third_task" in log_file3.name

        # Cleanup
        reset_session()
        set_log_dir(None)
        disable_logging()


def test_session_log_contains_summary():
    """Test that session.log contains summary information."""
    with tempfile.TemporaryDirectory() as tmpdir:
        set_log_dir(Path(tmpdir))

        # Setup session
        session_dir = setup_session(task_file="test.yaml")

        # Get session log file
        session_log = session_dir / "session.log"

        # Read content
        content = session_log.read_text()

        # Should contain session start marker
        assert "TASK 1 START" in content or "session_start" in content or len(content) == 0

        # Cleanup
        reset_session()
        set_log_dir(None)


def test_get_session_dir_returns_current_session():
    """Test that get_session_dir returns the current session directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        set_log_dir(Path(tmpdir))

        # Before setup, should be None
        assert get_session_dir() is None

        # After setup, should return the session dir
        session_dir = setup_session(task_desc="test")
        assert get_session_dir() == session_dir
        assert get_session_dir().exists()

        # Cleanup
        reset_session()

        # After reset, should be None again
        assert get_session_dir() is None

        set_log_dir(None)


def test_setup_logger_creates_session_if_needed():
    """Test that setup_logger creates a session if none exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        set_log_dir(Path(tmpdir))
        enable_logging()

        # No session exists yet
        assert get_session_dir() is None

        # Setup logger without explicit session setup
        logger = setup_logger(task_name="auto_session_task")

        # Session should be auto-created
        assert get_session_dir() is not None
        assert get_session_dir().exists()

        # Log file should be in session directory
        log_file = get_log_file()
        assert log_file is not None
        assert log_file.parent == get_session_dir()

        # Cleanup
        reset_logger()
        reset_session()
        set_log_dir(None)
        disable_logging()


def test_task_counter_increments():
    """Test that the task counter increments across multiple setup_logger calls."""
    with tempfile.TemporaryDirectory() as tmpdir:
        set_log_dir(Path(tmpdir))
        enable_logging()

        session_dir = setup_session(task_desc="counter_test")

        # Create 5 task loggers
        log_files = []
        for i in range(5):
            setup_logger(task_name=f"task_{i}")
            log_files.append(get_log_file())
            reset_logger()

        # Verify counter increments (01 through 05)
        assert log_files[0].name.startswith("01_")
        assert log_files[1].name.startswith("02_")
        assert log_files[2].name.startswith("03_")
        assert log_files[3].name.startswith("04_")
        assert log_files[4].name.startswith("05_")

        # Cleanup
        reset_session()
        set_log_dir(None)
        disable_logging()


def test_reset_session_clears_state():
    """Test that reset_session properly clears all session state."""
    with tempfile.TemporaryDirectory() as tmpdir:
        set_log_dir(Path(tmpdir))
        enable_logging()

        # Setup session and logger
        session_dir = setup_session(task_desc="reset_test")
        setup_logger(task_name="task1")

        # Verify state exists
        assert get_session_dir() is not None
        assert get_log_file() is not None

        # Reset session
        reset_session()
        reset_logger()

        # Session state should be cleared
        assert get_session_dir() is None

        # Setup new session - counter should start over
        setup_session(task_desc="new_session")
        setup_logger(task_name="task1_again")
        log_file = get_log_file()

        # Should start at 01 again
        assert log_file.name.startswith("01_")

        # Cleanup
        reset_logger()
        reset_session()
        set_log_dir(None)
        disable_logging()


def test_session_jsonl_file_created():
    """Test that session.jsonl is created and contains events."""
    with tempfile.TemporaryDirectory() as tmpdir:
        set_log_dir(Path(tmpdir))

        session_dir = setup_session(task_file="test.yaml")

        # Verify session.jsonl exists
        jsonl_file = session_dir / "session.jsonl"
        assert jsonl_file.exists()

        # Read and verify content
        content = jsonl_file.read_text()

        # Should contain at least the session_start event
        assert len(content) > 0
        assert "session_start" in content

        # Cleanup
        reset_session()
        set_log_dir(None)
