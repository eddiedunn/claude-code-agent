"""Verify CLI functionality is not affected by server module."""
import subprocess
import sys
from pathlib import Path

import pytest

def test_grind_cli_imports():
    """Verify grind CLI can still import without server dependencies."""
    result = subprocess.run(
        [sys.executable, "-c", "from grind.cli import main; print('OK')"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, f"CLI import failed: {result.stderr}"
    assert "OK" in result.stdout

def test_grind_engine_imports():
    """Verify grind engine imports work independently."""
    result = subprocess.run(
        [sys.executable, "-c", "from grind.engine import grind; print('OK')"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, f"Engine import failed: {result.stderr}"
    assert "OK" in result.stdout

def test_grind_interactive_imports():
    """Verify interactive module still works."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from grind.interactive import is_interject_requested; print('OK')",
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, f"Interactive import failed: {result.stderr}"
    assert "OK" in result.stdout

def test_grind_command_exists():
    """Verify grind CLI command is still available."""
    result = subprocess.run(
        ["grind", "--help"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, f"grind command failed: {result.stderr}"
    assert "grind" in result.stdout.lower()

def test_server_module_isolation():
    """Verify server module doesn't pollute grind namespace."""
    code = """
import sys
import grind

# Server module should not be auto-imported
assert not hasattr(grind, 'server'), "Server should not be in grind namespace"

# But should be importable explicitly
from grind.server import create_app
assert create_app is not None

print('OK')
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, f"Isolation test failed: {result.stderr}"
    assert "OK" in result.stdout

def test_cli_and_server_coexist():
    """Verify CLI and server can be imported together."""
    code = """
# Import both CLI and server
from grind.cli import main as cli_main
from grind.server import create_app

# Both should be callable
assert callable(cli_main)
assert callable(create_app)

print('OK')
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, f"Coexistence test failed: {result.stderr}"
    assert "OK" in result.stdout
