"""Tests for programmatic injection system."""
import asyncio
import pytest
from datetime import datetime, timedelta

from grind.interactive_v2 import (
    MessageQueueManager,
    InjectionMessage,
    inject_guidance,
    inject_action,
    get_message_queue_manager,
    DEFAULT_MESSAGE_TTL,
)
from grind.models import CheckpointAction


class TestMessageQueueManager:
    @pytest.mark.asyncio
    async def test_enqueue_dequeue(self):
        """Test basic enqueue and dequeue operations."""
        manager = MessageQueueManager()
        msg = InjectionMessage(
            action=CheckpointAction.GUIDANCE,
            message="Test guidance",
            timestamp=datetime.now(),
            source="test",
            session_id="sess_123",
        )
        await manager.enqueue("sess_123", msg)

        retrieved = await manager.dequeue("sess_123")
        assert retrieved is not None
        assert retrieved.message == "Test guidance"
        assert retrieved.session_id == "sess_123"

    @pytest.mark.asyncio
    async def test_session_isolation(self):
        """Verify messages don't leak between sessions."""
        manager = MessageQueueManager()

        msg1 = InjectionMessage(
            action=CheckpointAction.GUIDANCE,
            message="Session 1",
            timestamp=datetime.now(),
            source="test",
            session_id="sess_1",
        )
        msg2 = InjectionMessage(
            action=CheckpointAction.GUIDANCE,
            message="Session 2",
            timestamp=datetime.now(),
            source="test",
            session_id="sess_2",
        )

        await manager.enqueue("sess_1", msg1)
        await manager.enqueue("sess_2", msg2)

        # Session 1 should only see its message
        retrieved1 = await manager.dequeue("sess_1")
        assert retrieved1.message == "Session 1"

        # Session 2 should only see its message
        retrieved2 = await manager.dequeue("sess_2")
        assert retrieved2.message == "Session 2"

    @pytest.mark.asyncio
    async def test_timeout_on_empty_queue(self):
        """Test dequeue returns None when queue is empty after timeout."""
        manager = MessageQueueManager()
        msg = await manager.dequeue("nonexistent", timeout=0.1)
        assert msg is None

    @pytest.mark.asyncio
    async def test_inject_guidance_api(self):
        """Test high-level guidance injection API."""
        manager = MessageQueueManager()

        result = await inject_guidance(
            "test_session",
            "Fix the bug",
            persistent=False,
            manager=manager
        )
        assert result is True

        msg = await manager.dequeue("test_session")
        assert msg.message == "Fix the bug"
        assert msg.action == CheckpointAction.GUIDANCE

    @pytest.mark.asyncio
    async def test_inject_action_api(self):
        """Test control action injection."""
        manager = MessageQueueManager()

        result = await inject_action(
            "test_session",
            CheckpointAction.ABORT,
            manager=manager
        )
        assert result is True

        msg = await manager.dequeue("test_session")
        assert msg.action == CheckpointAction.ABORT
        assert msg.message is None

    @pytest.mark.asyncio
    async def test_concurrent_access(self):
        """Test multiple async tasks accessing queues concurrently."""
        manager = MessageQueueManager()

        async def enqueue_messages(session_id: str, count: int):
            """Helper to enqueue multiple messages."""
            for i in range(count):
                msg = InjectionMessage(
                    action=CheckpointAction.GUIDANCE,
                    message=f"{session_id}-msg-{i}",
                    timestamp=datetime.now(),
                    source="test",
                    session_id=session_id,
                )
                await manager.enqueue(session_id, msg)

        async def dequeue_messages(session_id: str, count: int):
            """Helper to dequeue multiple messages."""
            messages = []
            for _ in range(count):
                msg = await manager.dequeue(session_id, timeout=1.0)
                if msg:
                    messages.append(msg)
            return messages

        # Start multiple enqueue tasks concurrently
        await asyncio.gather(
            enqueue_messages("sess_1", 5),
            enqueue_messages("sess_2", 5),
            enqueue_messages("sess_3", 5),
        )

        # Verify each session got its messages
        for i in range(1, 4):
            session_id = f"sess_{i}"
            messages = await dequeue_messages(session_id, 5)
            assert len(messages) == 5
            for j, msg in enumerate(messages):
                assert msg.message == f"{session_id}-msg-{j}"

    @pytest.mark.asyncio
    async def test_concurrent_same_session(self):
        """Test concurrent enqueue/dequeue on the same session."""
        manager = MessageQueueManager()
        session_id = "concurrent_session"

        async def producer():
            """Producer task."""
            for i in range(10):
                msg = InjectionMessage(
                    action=CheckpointAction.GUIDANCE,
                    message=f"msg-{i}",
                    timestamp=datetime.now(),
                    source="test",
                    session_id=session_id,
                )
                await manager.enqueue(session_id, msg)
                await asyncio.sleep(0.01)  # Small delay

        async def consumer():
            """Consumer task."""
            messages = []
            for _ in range(10):
                msg = await manager.dequeue(session_id, timeout=1.0)
                if msg:
                    messages.append(msg)
            return messages

        # Run producer and consumer concurrently
        _, messages = await asyncio.gather(
            producer(),
            consumer(),
        )

        assert len(messages) == 10

    @pytest.mark.asyncio
    async def test_ttl_cleanup(self):
        """Test that old messages are removed during cleanup."""
        manager = MessageQueueManager()

        # Create old message (expired)
        old_msg = InjectionMessage(
            action=CheckpointAction.GUIDANCE,
            message="Old message",
            timestamp=datetime.now() - timedelta(hours=1),
            source="test",
            session_id="sess_1",
        )

        # Create fresh message
        new_msg = InjectionMessage(
            action=CheckpointAction.GUIDANCE,
            message="New message",
            timestamp=datetime.now(),
            source="test",
            session_id="sess_1",
        )

        await manager.enqueue("sess_1", old_msg)
        await manager.enqueue("sess_1", new_msg)

        # Run cleanup
        expired_count = await manager.cleanup_expired()
        assert expired_count == 1

        # Only new message should remain
        msg = await manager.dequeue("sess_1", timeout=0.1)
        assert msg is not None
        assert msg.message == "New message"

        # Queue should now be empty
        msg = await manager.dequeue("sess_1", timeout=0.1)
        assert msg is None

    @pytest.mark.asyncio
    async def test_ttl_automatic_skip_on_dequeue(self):
        """Test that expired messages are automatically skipped during dequeue."""
        manager = MessageQueueManager()

        # Create expired message
        expired_msg = InjectionMessage(
            action=CheckpointAction.GUIDANCE,
            message="Expired",
            timestamp=datetime.now() - timedelta(hours=1),
            source="test",
            session_id="sess_1",
        )

        # Create valid message
        valid_msg = InjectionMessage(
            action=CheckpointAction.GUIDANCE,
            message="Valid",
            timestamp=datetime.now(),
            source="test",
            session_id="sess_1",
        )

        await manager.enqueue("sess_1", expired_msg)
        await manager.enqueue("sess_1", valid_msg)

        # Dequeue should skip expired and return valid
        msg = await manager.dequeue("sess_1", timeout=0.1)
        assert msg is not None
        assert msg.message == "Valid"

    @pytest.mark.asyncio
    async def test_session_cleanup(self):
        """Test session cleanup removes all messages and queue."""
        manager = MessageQueueManager()

        # Add messages to multiple sessions
        for i in range(3):
            msg = InjectionMessage(
                action=CheckpointAction.GUIDANCE,
                message=f"Message {i}",
                timestamp=datetime.now(),
                source="test",
                session_id="sess_1",
            )
            await manager.enqueue("sess_1", msg)

        msg = InjectionMessage(
            action=CheckpointAction.GUIDANCE,
            message="Session 2",
            timestamp=datetime.now(),
            source="test",
            session_id="sess_2",
        )
        await manager.enqueue("sess_2", msg)

        # Verify sessions exist
        sessions = await manager.get_session_ids()
        assert "sess_1" in sessions
        assert "sess_2" in sessions

        # Clear sess_1
        await manager.clear_session("sess_1")

        # sess_1 should be gone
        sessions = await manager.get_session_ids()
        assert "sess_1" not in sessions
        assert "sess_2" in sessions

        # sess_2 should still have its message
        msg = await manager.dequeue("sess_2")
        assert msg is not None
        assert msg.message == "Session 2"

    @pytest.mark.asyncio
    async def test_clear_nonexistent_session(self):
        """Test clearing a session that doesn't exist is safe."""
        manager = MessageQueueManager()

        # Should not raise an error
        await manager.clear_session("nonexistent_session")

    @pytest.mark.asyncio
    async def test_empty_queue_edge_cases(self):
        """Test edge cases with empty queues."""
        manager = MessageQueueManager()

        # Dequeue from nonexistent session
        msg = await manager.dequeue("nonexistent", timeout=0.1)
        assert msg is None

        # Check has_messages on nonexistent session
        has_msgs = await manager.has_messages("nonexistent")
        assert has_msgs is False

        # Get queue depth on nonexistent session
        depth = await manager.get_queue_depth("nonexistent")
        assert depth == 0

    @pytest.mark.asyncio
    async def test_invalid_session_ids(self):
        """Test handling of various session ID formats."""
        manager = MessageQueueManager()

        # Empty string session ID (edge case)
        msg = InjectionMessage(
            action=CheckpointAction.GUIDANCE,
            message="Empty session",
            timestamp=datetime.now(),
            source="test",
            session_id="",
        )
        await manager.enqueue("", msg)

        retrieved = await manager.dequeue("", timeout=0.1)
        assert retrieved is not None
        assert retrieved.message == "Empty session"

        # Special characters in session ID
        special_session = "sess!@#$%^&*()"
        msg = InjectionMessage(
            action=CheckpointAction.GUIDANCE,
            message="Special chars",
            timestamp=datetime.now(),
            source="test",
            session_id=special_session,
        )
        await manager.enqueue(special_session, msg)

        retrieved = await manager.dequeue(special_session, timeout=0.1)
        assert retrieved is not None
        assert retrieved.message == "Special chars"

    @pytest.mark.asyncio
    async def test_has_messages(self):
        """Test has_messages method."""
        manager = MessageQueueManager()

        # Empty queue
        assert await manager.has_messages("sess_1") is False

        # Add message
        msg = InjectionMessage(
            action=CheckpointAction.GUIDANCE,
            message="Test",
            timestamp=datetime.now(),
            source="test",
            session_id="sess_1",
        )
        await manager.enqueue("sess_1", msg)

        # Should have messages
        assert await manager.has_messages("sess_1") is True

        # Dequeue
        await manager.dequeue("sess_1", timeout=0.1)

        # Should be empty again
        assert await manager.has_messages("sess_1") is False

    @pytest.mark.asyncio
    async def test_get_queue_depth(self):
        """Test get_queue_depth method."""
        manager = MessageQueueManager()

        # Empty queue
        assert await manager.get_queue_depth("sess_1") == 0

        # Add messages
        for i in range(5):
            msg = InjectionMessage(
                action=CheckpointAction.GUIDANCE,
                message=f"Message {i}",
                timestamp=datetime.now(),
                source="test",
                session_id="sess_1",
            )
            await manager.enqueue("sess_1", msg)

        # Check depth
        assert await manager.get_queue_depth("sess_1") == 5

        # Dequeue one
        await manager.dequeue("sess_1", timeout=0.1)

        # Check depth again
        assert await manager.get_queue_depth("sess_1") == 4

    @pytest.mark.asyncio
    async def test_get_session_ids(self):
        """Test get_session_ids method."""
        manager = MessageQueueManager()

        # No sessions initially
        assert await manager.get_session_ids() == []

        # Add sessions
        for i in range(3):
            msg = InjectionMessage(
                action=CheckpointAction.GUIDANCE,
                message=f"Message {i}",
                timestamp=datetime.now(),
                source="test",
                session_id=f"sess_{i}",
            )
            await manager.enqueue(f"sess_{i}", msg)

        # Check all sessions exist
        sessions = await manager.get_session_ids()
        assert len(sessions) == 3
        assert "sess_0" in sessions
        assert "sess_1" in sessions
        assert "sess_2" in sessions

    @pytest.mark.asyncio
    async def test_fifo_ordering(self):
        """Test that messages are dequeued in FIFO order."""
        manager = MessageQueueManager()

        # Enqueue messages in order
        for i in range(5):
            msg = InjectionMessage(
                action=CheckpointAction.GUIDANCE,
                message=f"Message {i}",
                timestamp=datetime.now(),
                source="test",
                session_id="sess_1",
            )
            await manager.enqueue("sess_1", msg)

        # Dequeue and verify order
        for i in range(5):
            msg = await manager.dequeue("sess_1", timeout=0.1)
            assert msg is not None
            assert msg.message == f"Message {i}"

    @pytest.mark.asyncio
    async def test_message_to_dict(self):
        """Test InjectionMessage serialization."""
        msg = InjectionMessage(
            action=CheckpointAction.GUIDANCE,
            message="Test message",
            timestamp=datetime.now(),
            source="api",
            session_id="sess_1",
        )

        msg_dict = msg.to_dict()
        assert msg_dict["action"] == "guidance"
        assert msg_dict["message"] == "Test message"
        assert msg_dict["source"] == "api"
        assert msg_dict["session_id"] == "sess_1"
        assert "timestamp" in msg_dict

    @pytest.mark.asyncio
    async def test_message_is_expired(self):
        """Test InjectionMessage expiration check."""
        # Fresh message
        fresh_msg = InjectionMessage(
            action=CheckpointAction.GUIDANCE,
            message="Fresh",
            timestamp=datetime.now(),
            source="test",
            session_id="sess_1",
        )
        assert fresh_msg.is_expired() is False

        # Old message
        old_msg = InjectionMessage(
            action=CheckpointAction.GUIDANCE,
            message="Old",
            timestamp=datetime.now() - timedelta(hours=1),
            source="test",
            session_id="sess_1",
        )
        assert old_msg.is_expired() is True

        # Custom TTL
        msg = InjectionMessage(
            action=CheckpointAction.GUIDANCE,
            message="Test",
            timestamp=datetime.now() - timedelta(seconds=10),
            source="test",
            session_id="sess_1",
        )
        assert msg.is_expired(ttl=timedelta(seconds=5)) is True
        assert msg.is_expired(ttl=timedelta(seconds=20)) is False

    @pytest.mark.asyncio
    async def test_global_manager_singleton(self):
        """Test get_message_queue_manager returns singleton."""
        manager1 = get_message_queue_manager()
        manager2 = get_message_queue_manager()

        # Should be the same instance
        assert manager1 is manager2

        # Test it works
        msg = InjectionMessage(
            action=CheckpointAction.GUIDANCE,
            message="Test",
            timestamp=datetime.now(),
            source="test",
            session_id="test_session",
        )
        await manager1.enqueue("test_session", msg)

        retrieved = await manager2.dequeue("test_session", timeout=0.1)
        assert retrieved is not None
        assert retrieved.message == "Test"

    @pytest.mark.asyncio
    async def test_inject_guidance_with_global_manager(self):
        """Test inject_guidance uses global manager when none provided."""
        result = await inject_guidance("test_session", "Global test")
        assert result is True

        # Retrieve using global manager
        manager = get_message_queue_manager()
        msg = await manager.dequeue("test_session", timeout=0.1)
        assert msg is not None
        assert msg.message == "Global test"

    @pytest.mark.asyncio
    async def test_inject_action_with_global_manager(self):
        """Test inject_action uses global manager when none provided."""
        result = await inject_action("test_session", CheckpointAction.STATUS)
        assert result is True

        # Retrieve using global manager
        manager = get_message_queue_manager()
        msg = await manager.dequeue("test_session", timeout=0.1)
        assert msg is not None
        assert msg.action == CheckpointAction.STATUS

    @pytest.mark.asyncio
    async def test_multiple_action_types(self):
        """Test enqueuing different action types."""
        manager = MessageQueueManager()

        actions = [
            CheckpointAction.GUIDANCE,
            CheckpointAction.ABORT,
            CheckpointAction.STATUS,
            CheckpointAction.CONTINUE,
            CheckpointAction.RUN_VERIFY,
        ]

        # Enqueue all action types
        for action in actions:
            msg = InjectionMessage(
                action=action,
                message=f"Test {action.value}",
                timestamp=datetime.now(),
                source="test",
                session_id="sess_1",
            )
            await manager.enqueue("sess_1", msg)

        # Dequeue and verify
        for action in actions:
            msg = await manager.dequeue("sess_1", timeout=0.1)
            assert msg is not None
            assert msg.action == action
