"""Daemon mode for grind-server (Unix only)."""
from __future__ import annotations

import os
import signal
import sys
from pathlib import Path
from typing import NoReturn

from grind.server.logging import get_logger

logger = get_logger("daemon")

GRIND_DIR = Path.home() / ".grind"
PID_FILE = GRIND_DIR / "server.pid"
LOG_FILE = GRIND_DIR / "server.log"

def daemonize(host: str, port: int) -> NoReturn:
    """Fork and run server as daemon."""
    GRIND_DIR.mkdir(parents=True, exist_ok=True)

    # First fork
    pid = os.fork()
    if pid > 0:
        sys.exit(0)

    os.setsid()

    # Second fork
    pid = os.fork()
    if pid > 0:
        sys.exit(0)

    # Redirect stdout/stderr to log file
    sys.stdout.flush()
    sys.stderr.flush()
    with open(LOG_FILE, "a") as log:
        os.dup2(log.fileno(), sys.stdout.fileno())
        os.dup2(log.fileno(), sys.stderr.fileno())

    # Write PID file
    PID_FILE.write_text(str(os.getpid()))

    # Set up signal handler for graceful shutdown
    def handle_sigterm(signum, frame):
        logger.info("Received SIGTERM, shutting down...")
        PID_FILE.unlink(missing_ok=True)
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_sigterm)

    # Run server
    import uvicorn
    uvicorn.run(
        "grind.server.app:create_app",
        factory=True,
        host=host,
        port=port,
    )

def get_pid() -> int | None:
    """Get daemon PID if running."""
    if not PID_FILE.exists():
        return None
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)  # Check if process exists
        return pid
    except (ValueError, OSError):
        return None

def stop_daemon() -> bool:
    """Stop the daemon. Returns True if stopped."""
    pid = get_pid()
    if pid is None:
        return False
    os.kill(pid, signal.SIGTERM)
    # Wait for process to exit
    import time
    for _ in range(30):
        if get_pid() is None:
            return True
        time.sleep(0.1)
    return False
