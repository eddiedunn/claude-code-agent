"""Tests for grind.orchestration.events module."""

import pytest
import time
from unittest.mock import AsyncMock

from grind.orchestration.events import AgentEvent, EventBus, EventType


class TestEventType:
    """Test EventType enum."""

    def test_enum_values(self):
        """EventType should have correct string values."""
        assert EventType.AGENT_STARTED.value == "agent_started"
        assert EventType.AGENT_COMPLETED.value == "agent_completed"
        assert EventType.AGENT_FAILED.value == "agent_failed"
        assert EventType.TASK_STARTED.value == "task_started"
        assert EventType.TASK_COMPLETED.value == "task_completed"
        assert EventType.TASK_FAILED.value == "task_failed"
        assert EventType.ITERATION_STARTED.value == "iteration_started"
        assert EventType.ITERATION_COMPLETED.value == "iteration_completed"

    def test_enum_members(self):
        """EventType should have all expected members."""
        expected_members = {
            "AGENT_STARTED", "AGENT_COMPLETED", "AGENT_FAILED",
            "TASK_STARTED", "TASK_COMPLETED", "TASK_FAILED",
            "ITERATION_STARTED", "ITERATION_COMPLETED"
        }
        actual_members = {member.name for member in EventType}
        assert actual_members == expected_members


class TestAgentEvent:
    """Test AgentEvent dataclass."""

    def test_creation_minimal(self):
        """AgentEvent should work with minimal required fields."""
        event = AgentEvent(
            event_type=EventType.AGENT_STARTED,
            agent_id="agent_1"
        )

        assert event.event_type == EventType.AGENT_STARTED
        assert event.agent_id == "agent_1"
        assert event.data == {}
        assert event.timestamp == 0.0

    def test_creation_full(self):
        """AgentEvent should store all provided fields."""
        event = AgentEvent(
            event_type=EventType.TASK_COMPLETED,
            agent_id="agent_2",
            data={"result": "success", "count": 42},
            timestamp=1234567890.5
        )

        assert event.event_type == EventType.TASK_COMPLETED
        assert event.agent_id == "agent_2"
        assert event.data == {"result": "success", "count": 42}
        assert event.timestamp == 1234567890.5

    def test_different_event_types(self):
        """AgentEvent should support all event types."""
        for event_type in EventType:
            event = AgentEvent(event_type=event_type, agent_id="test")
            assert event.event_type == event_type

    def test_data_dict_isolation(self):
        """AgentEvent data dict should be isolated per instance."""
        event1 = AgentEvent(
            event_type=EventType.AGENT_STARTED,
            agent_id="agent_1"
        )
        event2 = AgentEvent(
            event_type=EventType.AGENT_STARTED,
            agent_id="agent_2"
        )

        event1.data["key"] = "value1"
        event2.data["key"] = "value2"

        assert event1.data["key"] == "value1"
        assert event2.data["key"] == "value2"


class TestEventBusSubscribe:
    """Test EventBus subscribe/unsubscribe functionality."""

    def test_subscribe_single_handler(self):
        """EventBus should allow subscribing a handler."""
        bus = EventBus()
        handler = AsyncMock()

        bus.subscribe(EventType.AGENT_STARTED, handler)

        # Check that handler is in subscribers
        assert EventType.AGENT_STARTED in bus._subscribers
        assert handler in bus._subscribers[EventType.AGENT_STARTED]

    def test_subscribe_multiple_handlers_same_type(self):
        """EventBus should allow multiple handlers for same event type."""
        bus = EventBus()
        handler1 = AsyncMock()
        handler2 = AsyncMock()
        handler3 = AsyncMock()

        bus.subscribe(EventType.AGENT_STARTED, handler1)
        bus.subscribe(EventType.AGENT_STARTED, handler2)
        bus.subscribe(EventType.AGENT_STARTED, handler3)

        handlers = bus._subscribers[EventType.AGENT_STARTED]
        assert len(handlers) == 3
        assert handler1 in handlers
        assert handler2 in handlers
        assert handler3 in handlers

    def test_subscribe_different_event_types(self):
        """EventBus should allow subscribing to different event types."""
        bus = EventBus()
        handler1 = AsyncMock()
        handler2 = AsyncMock()

        bus.subscribe(EventType.AGENT_STARTED, handler1)
        bus.subscribe(EventType.TASK_COMPLETED, handler2)

        assert handler1 in bus._subscribers[EventType.AGENT_STARTED]
        assert handler2 in bus._subscribers[EventType.TASK_COMPLETED]

    def test_unsubscribe_handler(self):
        """EventBus should allow unsubscribing a handler."""
        bus = EventBus()
        handler = AsyncMock()

        bus.subscribe(EventType.AGENT_STARTED, handler)
        assert handler in bus._subscribers[EventType.AGENT_STARTED]

        bus.unsubscribe(EventType.AGENT_STARTED, handler)
        assert handler not in bus._subscribers[EventType.AGENT_STARTED]

    def test_unsubscribe_one_of_many(self):
        """EventBus should only remove the specified handler."""
        bus = EventBus()
        handler1 = AsyncMock()
        handler2 = AsyncMock()
        handler3 = AsyncMock()

        bus.subscribe(EventType.AGENT_STARTED, handler1)
        bus.subscribe(EventType.AGENT_STARTED, handler2)
        bus.subscribe(EventType.AGENT_STARTED, handler3)

        bus.unsubscribe(EventType.AGENT_STARTED, handler2)

        handlers = bus._subscribers[EventType.AGENT_STARTED]
        assert handler1 in handlers
        assert handler2 not in handlers
        assert handler3 in handlers

    def test_unsubscribe_nonexistent_handler(self):
        """EventBus should handle unsubscribing a handler that wasn't subscribed."""
        bus = EventBus()
        handler = AsyncMock()

        # Should not raise an error
        bus.unsubscribe(EventType.AGENT_STARTED, handler)

    def test_unsubscribe_from_nonexistent_event_type(self):
        """EventBus should handle unsubscribing from event type with no subscribers."""
        bus = EventBus()
        handler = AsyncMock()

        # Should not raise an error
        bus.unsubscribe(EventType.AGENT_STARTED, handler)


class TestEventBusPublish:
    """Test EventBus publish (emit) functionality."""

    @pytest.mark.asyncio
    async def test_publish_to_single_subscriber(self):
        """EventBus should call handler when publishing event."""
        bus = EventBus()
        handler = AsyncMock()

        bus.subscribe(EventType.AGENT_STARTED, handler)

        event = AgentEvent(
            event_type=EventType.AGENT_STARTED,
            agent_id="agent_1",
            data={"test": "value"}
        )

        await bus.publish(event)

        handler.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_publish_to_multiple_subscribers(self):
        """EventBus should call all handlers subscribed to event type."""
        bus = EventBus()
        handler1 = AsyncMock()
        handler2 = AsyncMock()
        handler3 = AsyncMock()

        bus.subscribe(EventType.AGENT_STARTED, handler1)
        bus.subscribe(EventType.AGENT_STARTED, handler2)
        bus.subscribe(EventType.AGENT_STARTED, handler3)

        event = AgentEvent(
            event_type=EventType.AGENT_STARTED,
            agent_id="agent_1"
        )

        await bus.publish(event)

        handler1.assert_called_once_with(event)
        handler2.assert_called_once_with(event)
        handler3.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_publish_only_to_matching_type(self):
        """EventBus should only call handlers for matching event type."""
        bus = EventBus()
        started_handler = AsyncMock()
        completed_handler = AsyncMock()
        failed_handler = AsyncMock()

        bus.subscribe(EventType.AGENT_STARTED, started_handler)
        bus.subscribe(EventType.AGENT_COMPLETED, completed_handler)
        bus.subscribe(EventType.AGENT_FAILED, failed_handler)

        event = AgentEvent(
            event_type=EventType.AGENT_STARTED,
            agent_id="agent_1"
        )

        await bus.publish(event)

        started_handler.assert_called_once_with(event)
        completed_handler.assert_not_called()
        failed_handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_publish_with_no_subscribers(self):
        """EventBus should handle publishing event with no subscribers."""
        bus = EventBus()

        event = AgentEvent(
            event_type=EventType.AGENT_STARTED,
            agent_id="agent_1"
        )

        # Should not raise an error
        await bus.publish(event)

    @pytest.mark.asyncio
    async def test_publish_multiple_events(self):
        """EventBus should handle publishing multiple events."""
        bus = EventBus()
        handler = AsyncMock()

        bus.subscribe(EventType.AGENT_STARTED, handler)

        event1 = AgentEvent(
            event_type=EventType.AGENT_STARTED,
            agent_id="agent_1"
        )
        event2 = AgentEvent(
            event_type=EventType.AGENT_STARTED,
            agent_id="agent_2"
        )

        await bus.publish(event1)
        await bus.publish(event2)

        assert handler.call_count == 2
        handler.assert_any_call(event1)
        handler.assert_any_call(event2)


class TestEventPropagation:
    """Test event propagation through the EventBus."""

    @pytest.mark.asyncio
    async def test_event_data_propagation(self):
        """EventBus should propagate event data to handlers."""
        bus = EventBus()
        received_events = []

        async def handler(event: AgentEvent):
            received_events.append(event)

        bus.subscribe(EventType.TASK_COMPLETED, handler)

        event = AgentEvent(
            event_type=EventType.TASK_COMPLETED,
            agent_id="agent_1",
            data={"iterations": 5, "status": "complete"},
            timestamp=1234567890.0
        )

        await bus.publish(event)

        assert len(received_events) == 1
        received = received_events[0]
        assert received.event_type == EventType.TASK_COMPLETED
        assert received.agent_id == "agent_1"
        assert received.data == {"iterations": 5, "status": "complete"}
        assert received.timestamp == 1234567890.0

    @pytest.mark.asyncio
    async def test_handlers_receive_same_event_instance(self):
        """EventBus should pass the same event instance to all handlers."""
        bus = EventBus()
        received_events_1 = []
        received_events_2 = []

        async def handler1(event: AgentEvent):
            received_events_1.append(event)

        async def handler2(event: AgentEvent):
            received_events_2.append(event)

        bus.subscribe(EventType.AGENT_STARTED, handler1)
        bus.subscribe(EventType.AGENT_STARTED, handler2)

        event = AgentEvent(
            event_type=EventType.AGENT_STARTED,
            agent_id="agent_1"
        )

        await bus.publish(event)

        assert received_events_1[0] is received_events_2[0]

    @pytest.mark.asyncio
    async def test_handlers_called_in_order(self):
        """EventBus should call handlers in subscription order."""
        bus = EventBus()
        call_order = []

        async def handler1(event: AgentEvent):
            call_order.append(1)

        async def handler2(event: AgentEvent):
            call_order.append(2)

        async def handler3(event: AgentEvent):
            call_order.append(3)

        bus.subscribe(EventType.AGENT_STARTED, handler1)
        bus.subscribe(EventType.AGENT_STARTED, handler2)
        bus.subscribe(EventType.AGENT_STARTED, handler3)

        event = AgentEvent(
            event_type=EventType.AGENT_STARTED,
            agent_id="agent_1"
        )

        await bus.publish(event)

        assert call_order == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_complex_event_workflow(self):
        """EventBus should handle complex event workflows."""
        bus = EventBus()
        events_log = []

        async def log_started(event: AgentEvent):
            events_log.append(("started", event.agent_id))

        async def log_completed(event: AgentEvent):
            events_log.append(("completed", event.agent_id, event.data.get("iterations")))

        async def log_failed(event: AgentEvent):
            events_log.append(("failed", event.agent_id, event.data.get("error")))

        bus.subscribe(EventType.AGENT_STARTED, log_started)
        bus.subscribe(EventType.AGENT_COMPLETED, log_completed)
        bus.subscribe(EventType.AGENT_FAILED, log_failed)

        # Simulate a workflow
        await bus.publish(AgentEvent(
            event_type=EventType.AGENT_STARTED,
            agent_id="agent_1"
        ))

        await bus.publish(AgentEvent(
            event_type=EventType.AGENT_COMPLETED,
            agent_id="agent_1",
            data={"iterations": 3}
        ))

        await bus.publish(AgentEvent(
            event_type=EventType.AGENT_STARTED,
            agent_id="agent_2"
        ))

        await bus.publish(AgentEvent(
            event_type=EventType.AGENT_FAILED,
            agent_id="agent_2",
            data={"error": "timeout"}
        ))

        assert len(events_log) == 4
        assert events_log[0] == ("started", "agent_1")
        assert events_log[1] == ("completed", "agent_1", 3)
        assert events_log[2] == ("started", "agent_2")
        assert events_log[3] == ("failed", "agent_2", "timeout")

    @pytest.mark.asyncio
    async def test_handler_can_modify_event_data(self):
        """Handlers can modify event data (shared reference)."""
        bus = EventBus()

        async def handler1(event: AgentEvent):
            event.data["handler1"] = "modified"

        async def handler2(event: AgentEvent):
            # Should see modification from handler1
            assert event.data.get("handler1") == "modified"
            event.data["handler2"] = "also_modified"

        bus.subscribe(EventType.AGENT_STARTED, handler1)
        bus.subscribe(EventType.AGENT_STARTED, handler2)

        event = AgentEvent(
            event_type=EventType.AGENT_STARTED,
            agent_id="agent_1",
            data={}
        )

        await bus.publish(event)

        # Event data should be modified
        assert event.data["handler1"] == "modified"
        assert event.data["handler2"] == "also_modified"

    @pytest.mark.asyncio
    async def test_unsubscribe_during_workflow(self):
        """EventBus should handle unsubscribing during workflow."""
        bus = EventBus()
        handler = AsyncMock()

        bus.subscribe(EventType.AGENT_STARTED, handler)

        event1 = AgentEvent(
            event_type=EventType.AGENT_STARTED,
            agent_id="agent_1"
        )
        await bus.publish(event1)

        handler.assert_called_once()

        # Unsubscribe
        bus.unsubscribe(EventType.AGENT_STARTED, handler)

        event2 = AgentEvent(
            event_type=EventType.AGENT_STARTED,
            agent_id="agent_2"
        )
        await bus.publish(event2)

        # Should still only be called once (not twice)
        handler.assert_called_once()
