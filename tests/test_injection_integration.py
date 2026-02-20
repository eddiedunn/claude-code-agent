"""Integration tests for programmatic message injection."""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from httpx import ASGITransport, AsyncClient

from grind.server import create_app
from grind.server.models.responses import SessionStatus
from grind.server.services.event_bridge import EventBridge
from grind.server.services.session_manager import SessionManager
from grind.server.routes.health import set_server_start_time
from grind.models import CheckpointAction


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def async_client(app):
    """Create async client with app state initialized."""
    # Manually initialize app state since ASGITransport doesn't run lifespan
    event_bridge = EventBridge()
    session_manager = SessionManager(event_bridge=event_bridge, max_concurrent_sessions=10)
    await session_manager.recover_sessions()

    app.state.event_bridge = event_bridge
    app.state.session_manager = session_manager
    set_server_start_time()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    # Cleanup
    await session_manager.shutdown()


class TestProgrammaticInjection:
    @pytest.mark.asyncio
    @patch("grind.engine.grind")
    @patch("grind.interactive_v2.inject_guidance")
    async def test_inject_guidance_during_session(self, mock_inject, mock_grind, async_client):
        """Test injecting guidance into a running session."""
        # Create a session that runs for a while
        session_created = asyncio.Event()

        async def mock_grind_run(*args, **kwargs):
            session_created.set()
            await asyncio.sleep(0.5)  # Reduced from 2s to speed up tests

        mock_grind.side_effect = mock_grind_run
        mock_inject.return_value = True  # Simulate successful injection

        # Create session
        response = await async_client.post(
            "/sessions/",
            json={"task": "Test injection", "max_iterations": 5}
        )
        assert response.status_code == 201
        session_id = response.json()["id"]

        # Wait for session to start
        await asyncio.wait_for(session_created.wait(), timeout=5.0)

        # Small delay to ensure status is updated to RUNNING
        await asyncio.sleep(0.1)

        # Inject guidance
        response = await async_client.post(
            f"/sessions/{session_id}/inject",
            json={"message": "Try a different approach", "action": "guidance"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "injected"

        # Wait for session to complete
        await asyncio.sleep(0.6)

    @pytest.mark.asyncio
    @patch("grind.engine.grind")
    @patch("grind.interactive_v2.inject_guidance")
    async def test_inject_abort_action(self, mock_inject, mock_grind, async_client):
        """Test aborting a session via injection."""
        session_started = asyncio.Event()

        async def mock_grind_run(*args, **kwargs):
            session_started.set()
            await asyncio.sleep(0.5)  # Reduced from 2s

        mock_grind.side_effect = mock_grind_run
        mock_inject.return_value = True

        # Create session
        response = await async_client.post(
            "/sessions/",
            json={"task": "Test abort", "max_iterations": 10}
        )
        session_id = response.json()["id"]

        # Wait for session to start
        await asyncio.wait_for(session_started.wait(), timeout=5.0)
        await asyncio.sleep(0.1)

        # Inject abort action
        response = await async_client.post(
            f"/sessions/{session_id}/inject",
            json={"message": "", "action": "abort"}
        )
        assert response.status_code == 200

        # Wait for session to complete
        await asyncio.sleep(0.6)

    @pytest.mark.asyncio
    async def test_inject_into_nonexistent_session(self, async_client):
        """Test error handling for nonexistent session."""
        response = await async_client.post(
            "/sessions/nonexistent/inject",
            json={"message": "Test"}
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    @patch("grind.engine.grind")
    async def test_inject_into_completed_session(self, mock_grind, async_client):
        """Test error handling for completed session."""
        # Create a session that runs briefly then completes
        # We need a small delay so the status transition PENDING -> RUNNING happens
        # before the session completes
        async def mock_grind_run(*args, **kwargs):
            await asyncio.sleep(0.1)  # Allow status transition to RUNNING

        mock_grind.side_effect = mock_grind_run

        response = await async_client.post(
            "/sessions/",
            json={"task": "Quick task"}
        )
        assert response.status_code == 201
        session_id = response.json()["id"]

        # Wait for completion (0.1s for grind + buffer for status updates)
        await asyncio.sleep(0.5)

        # Try to inject into completed session
        response = await async_client.post(
            f"/sessions/{session_id}/inject",
            json={"message": "Too late"}
        )
        assert response.status_code == 400  # SessionNotRunningError

    @pytest.mark.asyncio
    @patch("grind.engine.grind")
    @patch("grind.interactive_v2.inject_guidance")
    async def test_inject_status_action(self, mock_inject, mock_grind, async_client):
        """Test status action type."""
        session_started = asyncio.Event()

        async def mock_grind_run(*args, **kwargs):
            session_started.set()
            await asyncio.sleep(0.5)  # Reduced from 2s

        mock_grind.side_effect = mock_grind_run
        mock_inject.return_value = True

        # Create session
        response = await async_client.post(
            "/sessions/",
            json={"task": "Test status", "max_iterations": 5}
        )
        session_id = response.json()["id"]

        await asyncio.wait_for(session_started.wait(), timeout=5.0)
        await asyncio.sleep(0.1)

        # Inject status request
        response = await async_client.post(
            f"/sessions/{session_id}/inject",
            json={"message": "", "action": "status"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "injected"

        # Wait for session to complete
        await asyncio.sleep(0.6)

    @pytest.mark.asyncio
    @patch("grind.engine.grind")
    @patch("grind.interactive_v2.inject_guidance")
    async def test_inject_verify_action(self, mock_inject, mock_grind, async_client):
        """Test verify action type."""
        session_started = asyncio.Event()

        async def mock_grind_run(*args, **kwargs):
            session_started.set()
            await asyncio.sleep(0.5)  # Reduced from 2s

        mock_grind.side_effect = mock_grind_run
        mock_inject.return_value = True

        # Create session
        response = await async_client.post(
            "/sessions/",
            json={"task": "Test verify", "max_iterations": 5}
        )
        session_id = response.json()["id"]

        await asyncio.wait_for(session_started.wait(), timeout=5.0)
        await asyncio.sleep(0.1)

        # Inject verify request
        response = await async_client.post(
            f"/sessions/{session_id}/inject",
            json={"message": "", "action": "verify"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "injected"

        # Wait for session to complete
        await asyncio.sleep(0.6)

    @pytest.mark.asyncio
    @patch("grind.engine.grind")
    @patch("grind.interactive_v2.inject_guidance")
    async def test_inject_race_condition_during_state_transition(self, mock_inject, mock_grind, async_client):
        """Test race conditions (inject during state transition)."""
        # This tests the scenario where we inject while session is transitioning
        transition_lock = asyncio.Event()
        ready_for_inject = asyncio.Event()

        async def mock_grind_run(*args, **kwargs):
            ready_for_inject.set()
            # Wait for a signal then complete quickly
            await transition_lock.wait()

        mock_grind.side_effect = mock_grind_run
        mock_inject.return_value = True

        # Create session
        response = await async_client.post(
            "/sessions/",
            json={"task": "Test race", "max_iterations": 5}
        )
        session_id = response.json()["id"]

        # Wait for session to be running
        await asyncio.wait_for(ready_for_inject.wait(), timeout=5.0)
        await asyncio.sleep(0.1)

        # Inject should work while running
        response = await async_client.post(
            f"/sessions/{session_id}/inject",
            json={"message": "During run", "action": "guidance"}
        )
        assert response.status_code == 200

        # Signal session to complete
        transition_lock.set()

        # Wait for completion
        await asyncio.sleep(0.5)

        # Now inject should fail since session completed
        response = await async_client.post(
            f"/sessions/{session_id}/inject",
            json={"message": "After complete", "action": "guidance"}
        )
        assert response.status_code == 400  # SessionNotRunningError

    @pytest.mark.asyncio
    @patch("grind.engine.grind")
    @patch("grind.interactive_v2.inject_guidance")
    async def test_inject_with_persistent_guidance(self, mock_inject, mock_grind, async_client):
        """Test injection with persistent flag."""
        session_started = asyncio.Event()

        async def mock_grind_run(*args, **kwargs):
            session_started.set()
            await asyncio.sleep(0.5)  # Reduced from 2s

        mock_grind.side_effect = mock_grind_run
        mock_inject.return_value = True

        # Create session
        response = await async_client.post(
            "/sessions/",
            json={"task": "Test persistent", "max_iterations": 5}
        )
        session_id = response.json()["id"]

        await asyncio.wait_for(session_started.wait(), timeout=5.0)
        await asyncio.sleep(0.1)

        # Inject with persistent flag
        response = await async_client.post(
            f"/sessions/{session_id}/inject",
            json={
                "message": "Always remember this",
                "action": "guidance",
                "persistent": True
            }
        )
        assert response.status_code == 200
        assert response.json()["status"] == "injected"

        # Wait for session to complete
        await asyncio.sleep(0.6)

    @pytest.mark.asyncio
    @patch("grind.engine.grind")
    @patch("grind.interactive_v2.inject_guidance")
    async def test_multiple_sequential_injections(self, mock_inject, mock_grind, async_client):
        """Test multiple injections into the same session."""
        session_started = asyncio.Event()

        async def mock_grind_run(*args, **kwargs):
            session_started.set()
            await asyncio.sleep(1.0)  # Reduced from 3s

        mock_grind.side_effect = mock_grind_run
        mock_inject.return_value = True

        # Create session
        response = await async_client.post(
            "/sessions/",
            json={"task": "Test multiple", "max_iterations": 10}
        )
        session_id = response.json()["id"]

        await asyncio.wait_for(session_started.wait(), timeout=5.0)
        await asyncio.sleep(0.1)

        # First injection
        response = await async_client.post(
            f"/sessions/{session_id}/inject",
            json={"message": "First guidance", "action": "guidance"}
        )
        assert response.status_code == 200

        # Second injection
        response = await async_client.post(
            f"/sessions/{session_id}/inject",
            json={"message": "Second guidance", "action": "guidance"}
        )
        assert response.status_code == 200

        # Third injection with different action
        response = await async_client.post(
            f"/sessions/{session_id}/inject",
            json={"message": "", "action": "status"}
        )
        assert response.status_code == 200

        # Wait for session to complete
        await asyncio.sleep(1.1)
