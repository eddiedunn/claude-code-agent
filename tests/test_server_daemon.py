"""Tests for Grind Server daemon mode."""
import subprocess
import time
from pathlib import Path

import pytest

GRIND_DIR = Path.home() / ".grind"
PID_FILE = GRIND_DIR / "server.pid"

@pytest.fixture(autouse=True)
def cleanup_daemon():
    """Ensure daemon is stopped after each test."""
    yield
    if PID_FILE.exists():
        subprocess.run(["grind-server", "stop"], capture_output=True)
        time.sleep(0.5)
    PID_FILE.unlink(missing_ok=True)

class TestDaemonMode:
    def test_status_when_not_running(self):
        result = subprocess.run(
            ["grind-server", "status"],
            capture_output=True,
            text=True,
        )
        assert "not running" in result.stdout.lower() or result.returncode != 0

    @pytest.mark.slow
    def test_daemon_start_stop(self):
        # Start daemon
        result = subprocess.run(
            ["grind-server", "start", "--daemon"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        time.sleep(1)  # Wait for daemon to start

        assert PID_FILE.exists()

        # Stop daemon
        result = subprocess.run(
            ["grind-server", "stop"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        time.sleep(1)

        assert not PID_FILE.exists() or not _pid_exists(PID_FILE)

def _pid_exists(pid_file: Path) -> bool:
    import os
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)
        return True
    except (ValueError, OSError):
        return False
