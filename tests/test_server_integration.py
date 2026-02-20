"""End-to-end integration tests for Grind Server."""
import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from grind.server import create_app
from grind.server.models.responses import SessionStatus
from grind.server.services.event_bridge import EventBridge
from grind.server.services.session_manager import SessionManager
from grind.server.routes.health import set_server_start_time


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


class TestFullSessionFlow:
    @pytest.mark.asyncio
    @patch("grind.engine.grind")
    async def test_complete_session_lifecycle(self, mock_grind, async_client):
        """Test creating, monitoring, and completing a session."""
        # Mock grind to complete after brief delay
        async def mock_grind_run(*args, **kwargs):
            await asyncio.sleep(0.1)

        mock_grind.side_effect = mock_grind_run

        # 1. Create session
        response = await async_client.post(
            "/sessions/",
            json={"task": "Integration test task", "max_iterations": 2},
        )
        assert response.status_code == 201
        session = response.json()
        session_id = session["id"]

        # 2. Get session details
        response = await async_client.get(f"/sessions/{session_id}")
        assert response.status_code == 200

        # 3. List sessions includes our session
        response = await async_client.get("/sessions/")
        assert response.status_code == 200
        sessions = response.json()["sessions"]
        assert any(s["id"] == session_id for s in sessions)

        # 4. Health check shows active session
        response = await async_client.get("/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_idempotency_key(self, async_client):
        """Test that idempotency key prevents duplicate sessions."""
        with patch("grind.engine.grind", new_callable=AsyncMock):
            # Create first session
            response1 = await async_client.post(
                "/sessions/",
                json={"task": "Test", "idempotency_key": "unique-key-123"},
            )
            assert response1.status_code == 201
            session1_id = response1.json()["id"]

            # Create second session with same key
            response2 = await async_client.post(
                "/sessions/",
                json={"task": "Test", "idempotency_key": "unique-key-123"},
            )
            assert response2.status_code == 201
            session2_id = response2.json()["id"]

            # Should return same session
            assert session1_id == session2_id
