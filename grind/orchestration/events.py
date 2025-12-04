"""Event system for agent orchestration.

This module provides an event bus and event types for pub-sub communication
between orchestration components. Agents can publish events and subscribers
can react to specific event types.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable


class EventType(Enum):
    """Types of events that can be published during orchestration."""
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    AGENT_FAILED = "agent_failed"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    ITERATION_STARTED = "iteration_started"
    ITERATION_COMPLETED = "iteration_completed"


@dataclass
class AgentEvent:
    """Event emitted during agent orchestration.

    Events carry information about agent execution state changes
    and can include arbitrary data payloads.
    """
    event_type: EventType
    agent_id: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0


class EventBus:
    """Pub-sub event bus for agent orchestration.

    Allows components to subscribe to specific event types and receive
    notifications when those events are published.

    Example:
        bus = EventBus()

        async def on_agent_started(event: AgentEvent):
            print(f"Agent {event.agent_id} started")

        bus.subscribe(EventType.AGENT_STARTED, on_agent_started)
        await bus.publish(AgentEvent(
            event_type=EventType.AGENT_STARTED,
            agent_id="agent_1"
        ))
    """

    def __init__(self):
        """Initialize the event bus with empty subscriber lists."""
        self._subscribers: dict[EventType, list[Callable[[AgentEvent], Awaitable[None]]]] = {}

    def subscribe(
        self,
        event_type: EventType,
        handler: Callable[[AgentEvent], Awaitable[None]]
    ) -> None:
        """Subscribe to events of a specific type.

        Args:
            event_type: The type of event to subscribe to
            handler: Async function to call when event is published
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    def unsubscribe(
        self,
        event_type: EventType,
        handler: Callable[[AgentEvent], Awaitable[None]]
    ) -> None:
        """Unsubscribe from events of a specific type.

        Args:
            event_type: The type of event to unsubscribe from
            handler: The handler function to remove
        """
        if event_type in self._subscribers:
            try:
                self._subscribers[event_type].remove(handler)
            except ValueError:
                pass  # Handler wasn't subscribed

    async def publish(self, event: AgentEvent) -> None:
        """Publish an event to all subscribers.

        Args:
            event: The event to publish
        """
        handlers = self._subscribers.get(event.event_type, [])
        for handler in handlers:
            await handler(event)
