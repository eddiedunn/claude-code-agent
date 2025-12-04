#!/usr/bin/env python3
"""
Event handler widget for Agent TUI.

Subscribes to EventBus and updates TUI state based on orchestration events.
"""

import logging
from datetime import datetime
from typing import Callable

from textual.widget import Widget

from grind.orchestration.events import AgentEvent, EventBus, EventType
from grind.tui.core.models import AgentInfo, AgentStatus, AgentType

logger = logging.getLogger(__name__)


class EventHandler(Widget):
    """
    Event handler widget that subscribes to EventBus and updates TUI state.

    This widget acts as a bridge between the orchestration layer's EventBus
    and the TUI's state management, converting orchestration events into
    TUI state updates.

    Events Handled:
    ===============
    - AGENT_STARTED: Creates/updates agent info when agent begins execution
    - AGENT_COMPLETED: Marks agent as complete and records completion time
    - AGENT_FAILED: Marks agent as failed and captures error message
    - ITERATION_STARTED: Updates agent iteration progress when iteration begins
    - ITERATION_COMPLETED: Updates agent iteration progress when iteration completes

    Usage Example:
    ==============

    # In AgentTUI:
    event_handler = EventHandler(event_bus=self.event_bus)
    event_handler.on_agent_updated = self._handle_agent_update

    # The widget will automatically subscribe to events and call
    # on_agent_updated callback when agent state changes

    Callbacks:
    ==========

    - on_agent_updated: Called when an agent's state changes
      Signature: (agent_info: AgentInfo) -> None
    """

    def __init__(
        self,
        event_bus: EventBus,
        *args,
        **kwargs,
    ):
        """
        Initialize the event handler.

        Args:
            event_bus: EventBus instance to subscribe to
            *args: Additional positional arguments for Widget
            **kwargs: Additional keyword arguments for Widget
        """
        super().__init__(*args, **kwargs)
        self.event_bus = event_bus
        self.on_agent_updated: Callable[[AgentInfo], None] | None = None

        # Subscribe to relevant events
        self._subscribe_to_events()

    def _subscribe_to_events(self):
        """Subscribe to EventBus events."""
        self.event_bus.subscribe(EventType.AGENT_STARTED, self._handle_agent_started)
        self.event_bus.subscribe(EventType.AGENT_COMPLETED, self._handle_agent_completed)
        self.event_bus.subscribe(EventType.AGENT_FAILED, self._handle_agent_failed)
        self.event_bus.subscribe(EventType.ITERATION_STARTED, self._handle_iteration_started)
        self.event_bus.subscribe(EventType.ITERATION_COMPLETED, self._handle_iteration_completed)

    async def _handle_agent_started(self, event: AgentEvent):
        """
        Handle AGENT_STARTED event.

        Args:
            event: AgentEvent with agent_started data
        """
        logger.debug(f"EventHandler: Agent started - {event.agent_id}")

        # Extract data from event
        data = event.data
        agent_info = AgentInfo(
            agent_id=event.agent_id,
            task_id=data.get("task_id", event.agent_id),
            task_description=data.get("task_description", "")[:100],
            agent_type=AgentType(data.get("agent_type", "worker")),
            status=AgentStatus.RUNNING,
            model=data.get("model", "sonnet"),
            iteration=data.get("iteration", 0),
            max_iterations=data.get("max_iterations", 5),
            progress=0.0,
            created_at=datetime.fromtimestamp(event.timestamp) if event.timestamp else datetime.now(),
            started_at=datetime.fromtimestamp(event.timestamp) if event.timestamp else datetime.now(),
        )

        # Notify callback if registered
        if self.on_agent_updated:
            self.on_agent_updated(agent_info)

    async def _handle_agent_completed(self, event: AgentEvent):
        """
        Handle AGENT_COMPLETED event.

        Args:
            event: AgentEvent with agent_completed data
        """
        logger.debug(f"EventHandler: Agent completed - {event.agent_id}")

        # Extract data from event
        data = event.data
        agent_info = AgentInfo(
            agent_id=event.agent_id,
            task_id=data.get("task_id", event.agent_id),
            task_description=data.get("task_description", "")[:100],
            agent_type=AgentType(data.get("agent_type", "worker")),
            status=AgentStatus.COMPLETE,
            model=data.get("model", "sonnet"),
            iteration=data.get("iteration", 0),
            max_iterations=data.get("max_iterations", 5),
            progress=1.0,
            created_at=datetime.fromtimestamp(data.get("created_at", event.timestamp)) if data.get("created_at") or event.timestamp else datetime.now(),
            started_at=datetime.fromtimestamp(data.get("started_at", event.timestamp)) if data.get("started_at") or event.timestamp else datetime.now(),
            completed_at=datetime.fromtimestamp(event.timestamp) if event.timestamp else datetime.now(),
        )

        # Notify callback if registered
        if self.on_agent_updated:
            self.on_agent_updated(agent_info)

    async def _handle_agent_failed(self, event: AgentEvent):
        """
        Handle AGENT_FAILED event.

        Args:
            event: AgentEvent with agent_failed data
        """
        logger.debug(f"EventHandler: Agent failed - {event.agent_id}")

        # Extract data from event
        data = event.data
        agent_info = AgentInfo(
            agent_id=event.agent_id,
            task_id=data.get("task_id", event.agent_id),
            task_description=data.get("task_description", "")[:100],
            agent_type=AgentType(data.get("agent_type", "worker")),
            status=AgentStatus.FAILED,
            model=data.get("model", "sonnet"),
            iteration=data.get("iteration", 0),
            max_iterations=data.get("max_iterations", 5),
            progress=data.get("progress", 0.0),
            created_at=datetime.fromtimestamp(data.get("created_at", event.timestamp)) if data.get("created_at") or event.timestamp else datetime.now(),
            started_at=datetime.fromtimestamp(data.get("started_at", event.timestamp)) if data.get("started_at") or event.timestamp else datetime.now(),
            completed_at=datetime.fromtimestamp(event.timestamp) if event.timestamp else datetime.now(),
            error_message=data.get("error_message"),
        )

        # Notify callback if registered
        if self.on_agent_updated:
            self.on_agent_updated(agent_info)

    async def _handle_iteration_started(self, event: AgentEvent):
        """
        Handle ITERATION_STARTED event.

        Updates agent iteration count when a new iteration starts.

        Args:
            event: AgentEvent with iteration_started data
        """
        logger.debug(f"EventHandler: Iteration started - {event.agent_id}")

        # Extract data from event
        data = event.data

        # Create partial update with iteration info
        # Note: This assumes there's an existing agent that will be updated
        # The full agent info will be merged by the TUI's state manager
        agent_info = AgentInfo(
            agent_id=event.agent_id,
            task_id=data.get("task_id", event.agent_id),
            task_description=data.get("task_description", ""),
            agent_type=AgentType(data.get("agent_type", "worker")),
            status=AgentStatus.RUNNING,
            model=data.get("model", "sonnet"),
            iteration=data.get("iteration", 0),
            max_iterations=data.get("max_iterations", 5),
            progress=data.get("iteration", 0) / data.get("max_iterations", 5) if data.get("max_iterations", 5) > 0 else 0.0,
            created_at=datetime.fromtimestamp(data.get("created_at", event.timestamp)) if data.get("created_at") or event.timestamp else datetime.now(),
            started_at=datetime.fromtimestamp(data.get("started_at", event.timestamp)) if data.get("started_at") or event.timestamp else datetime.now(),
        )

        # Notify callback if registered
        if self.on_agent_updated:
            self.on_agent_updated(agent_info)

    async def _handle_iteration_completed(self, event: AgentEvent):
        """
        Handle ITERATION_COMPLETED event.

        Updates agent iteration count after iteration completes.

        Args:
            event: AgentEvent with iteration_completed data
        """
        logger.debug(f"EventHandler: Iteration completed - {event.agent_id}")

        # Extract data from event
        data = event.data

        # Create partial update with iteration info
        agent_info = AgentInfo(
            agent_id=event.agent_id,
            task_id=data.get("task_id", event.agent_id),
            task_description=data.get("task_description", ""),
            agent_type=AgentType(data.get("agent_type", "worker")),
            status=AgentStatus.RUNNING,  # Still running after iteration
            model=data.get("model", "sonnet"),
            iteration=data.get("iteration", 0),
            max_iterations=data.get("max_iterations", 5),
            progress=data.get("iteration", 0) / data.get("max_iterations", 5) if data.get("max_iterations", 5) > 0 else 0.0,
            created_at=datetime.fromtimestamp(data.get("created_at", event.timestamp)) if data.get("created_at") or event.timestamp else datetime.now(),
            started_at=datetime.fromtimestamp(data.get("started_at", event.timestamp)) if data.get("started_at") or event.timestamp else datetime.now(),
        )

        # Notify callback if registered
        if self.on_agent_updated:
            self.on_agent_updated(agent_info)

    def unsubscribe(self):
        """Unsubscribe from all EventBus events."""
        self.event_bus.unsubscribe(EventType.AGENT_STARTED, self._handle_agent_started)
        self.event_bus.unsubscribe(EventType.AGENT_COMPLETED, self._handle_agent_completed)
        self.event_bus.unsubscribe(EventType.AGENT_FAILED, self._handle_agent_failed)
        self.event_bus.unsubscribe(EventType.ITERATION_STARTED, self._handle_iteration_started)
        self.event_bus.unsubscribe(EventType.ITERATION_COMPLETED, self._handle_iteration_completed)

    def on_unmount(self):
        """Clean up subscriptions when widget is unmounted."""
        self.unsubscribe()
