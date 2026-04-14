"""End-to-end tests for Phase 1: Observer + Hooks + Tmux.

Run with: uv run python -m pytest tests/test_phase1_e2e.py -v
"""

import json
import os
import subprocess
import sys
import time
import urllib.request

import pytest


def _wait_for_server(url: str, timeout: int = 15) -> bool:
    """Wait for server to be ready."""
    for _ in range(timeout):
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(1)
    return False


def _post_event(base_url: str, event: dict) -> dict:
    """Post an event to the observer."""
    req = urllib.request.Request(
        f"{base_url}/events",
        data=json.dumps(event).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req).read())


def _get_json(url: str) -> dict:
    """GET a JSON endpoint."""
    return json.loads(urllib.request.urlopen(url).read())


@pytest.fixture(scope="module")
def observer_server():
    """Start the observer server for the test module and tear it down after."""
    base = "http://127.0.0.1:18423"
    db = "/tmp/test_phase1_e2e.db"

    # Clean up any leftover DB files
    for f in [db, db + "-journal", db + "-wal"]:
        if os.path.exists(f):
            os.unlink(f)

    # Start observer using the installed entry point
    grind_bin = os.path.join(os.path.dirname(sys.executable), "grind")
    proc = subprocess.Popen(
        [grind_bin, "observe",
         "--port", "18423", "--db", db, "--host", "127.0.0.1"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )

    if not _wait_for_server(f"{base}/health"):
        proc.terminate()
        proc.wait(timeout=5)
        pytest.fail("Observer server failed to start")

    yield base

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    for f in [db, db + "-journal", db + "-wal"]:
        if os.path.exists(f):
            os.unlink(f)


def test_health_check(observer_server):
    """Test that the health endpoint returns ok."""
    health = _get_json(f"{observer_server}/health")
    assert health["status"] == "ok", f"Health check failed: {health}"


def test_post_session_start(observer_server):
    """Test posting a session_start event."""
    result = _post_event(observer_server, {
        "event_type": "session_start",
        "session_id": "test-sess-1",
        "agent_name": "primary-opus",
    })
    assert result["ok"], f"Session start failed: {result}"


def test_post_pre_tool_use(observer_server):
    """Test posting a pre_tool_use event."""
    result = _post_event(observer_server, {
        "event_type": "pre_tool_use",
        "session_id": "test-sess-1",
        "agent_name": "primary-opus",
        "tool_name": "Read",
    })
    assert result["ok"]


def test_post_post_tool_use(observer_server):
    """Test posting a post_tool_use event."""
    result = _post_event(observer_server, {
        "event_type": "post_tool_use",
        "session_id": "test-sess-1",
        "agent_name": "primary-opus",
        "tool_name": "Read",
        "duration_ms": 150.5,
        "tool_result": "file contents here...",
    })
    assert result["ok"]


def test_post_sub_agent_events(observer_server):
    """Test posting events from a sub-agent."""
    for tool in ["Bash", "Grep", "Edit"]:
        result = _post_event(observer_server, {
            "event_type": "post_tool_use",
            "session_id": "test-sess-1",
            "agent_name": "sub-agent-haiku-1",
            "tool_name": tool,
            "duration_ms": 200,
        })
        assert result["ok"]


def test_query_all_events(observer_server):
    """Test querying all events returns correct count."""
    events = _get_json(f"{observer_server}/events")
    assert events["count"] == 6, f"Expected 6, got {events['count']}"


def test_query_by_session(observer_server):
    """Test querying events filtered by session_id."""
    events = _get_json(f"{observer_server}/events?session_id=test-sess-1")
    assert events["count"] == 6


def test_query_by_event_type(observer_server):
    """Test querying events filtered by event_type."""
    events = _get_json(f"{observer_server}/events?event_type=post_tool_use")
    assert events["count"] == 4


def test_query_by_agent_name(observer_server):
    """Test querying events filtered by agent_name."""
    events = _get_json(f"{observer_server}/events?agent_name=sub-agent-haiku-1")
    assert events["count"] == 3


def test_list_sessions(observer_server):
    """Test listing sessions returns correct data."""
    sessions = _get_json(f"{observer_server}/sessions")
    assert len(sessions["sessions"]) == 1
    sess = sessions["sessions"][0]
    assert sess["session_id"] == "test-sess-1"
    assert sess["event_count"] == 6


def test_hooks_config_generation():
    """Test that hooks config generates valid structure."""
    from grind.hooks_config import generate_hooks_config

    config = generate_hooks_config("http://localhost:8421")
    assert "hooks" in config
    assert "session_start" in config["hooks"]
    assert "pre_tool_use" in config["hooks"]
    assert "post_tool_use" in config["hooks"]


def test_tmux_module_imports():
    """Test that tmux module imports and functions are callable."""
    from grind.tmux import (
        TmuxError,
        create_pane,
        create_session,
        kill_session,
        launch_claude_code_in_session,
        list_panes,
        list_sessions,
        send_keys,
        session_exists,
    )

    assert callable(create_session)
    assert callable(list_sessions)
    assert callable(create_pane)
    assert callable(kill_session)
    assert callable(launch_claude_code_in_session)
    assert callable(list_panes)
    assert callable(send_keys)
    assert callable(session_exists)
