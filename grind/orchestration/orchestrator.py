"""Orchestrator for managing and executing multiple agents.

This module provides the Orchestrator class that coordinates the execution
of multiple agents, integrating with EventBus for pub-sub communication
and MetricsCollector for tracking agent performance.
"""

import time
from typing import Any

from grind.orchestration.agent import Agent, AgentResult, AgentStatus
from grind.orchestration.events import AgentEvent, EventBus, EventType
from grind.orchestration.metrics import MetricsCollector


class Orchestrator:
    """Stateless orchestrator for managing and executing multiple agents.

    The Orchestrator coordinates agent execution, publishes events via EventBus,
    and collects metrics via MetricsCollector. It maintains a registry of agents
    and can execute them all in sequence or individually.

    Example:
        orchestrator = Orchestrator()

        # Add agents
        orchestrator.add_agent("agent_1", my_agent_1)
        orchestrator.add_agent("agent_2", my_agent_2)

        # Run all agents
        results = await orchestrator.run_all({"input_data": "value"})

        # Check metrics
        metrics = orchestrator.metrics_collector.get_all_metrics()
    """

    def __init__(
        self, event_bus: EventBus | None = None, metrics_collector: MetricsCollector | None = None
    ):
        """Initialize the orchestrator with optional EventBus and MetricsCollector.

        Args:
            event_bus: Optional EventBus instance for event publishing.
                      If not provided, a new EventBus is created.
            metrics_collector: Optional MetricsCollector instance for tracking metrics.
                              If not provided, a new MetricsCollector is created.
        """
        self.event_bus = event_bus or EventBus()
        self.metrics_collector = metrics_collector or MetricsCollector()
        self._agents: dict[str, Agent] = {}

    def add_agent(self, agent_id: str, agent: Agent) -> None:
        """Add an agent to the orchestrator.

        Args:
            agent_id: Unique identifier for the agent
            agent: Agent instance implementing the Agent protocol
        """
        self._agents[agent_id] = agent

    def remove_agent(self, agent_id: str) -> None:
        """Remove an agent from the orchestrator.

        Args:
            agent_id: Unique identifier for the agent to remove
        """
        if agent_id in self._agents:
            del self._agents[agent_id]

    def get_agent(self, agent_id: str) -> Agent | None:
        """Get an agent by ID.

        Args:
            agent_id: Unique identifier for the agent

        Returns:
            The agent instance or None if not found
        """
        return self._agents.get(agent_id)

    def list_agents(self) -> list[str]:
        """Get list of all registered agent IDs.

        Returns:
            List of agent IDs
        """
        return list(self._agents.keys())

    async def run_agent(self, agent_id: str, input_data: dict[str, Any]) -> AgentResult:
        """Run a single agent with the given input.

        Publishes AGENT_STARTED, AGENT_COMPLETED/AGENT_FAILED events
        and records metrics for the agent run.

        Args:
            agent_id: Unique identifier for the agent to run
            input_data: Input data to pass to the agent

        Returns:
            AgentResult from the agent execution

        Raises:
            KeyError: If agent_id is not registered
        """
        if agent_id not in self._agents:
            raise KeyError(f"Agent '{agent_id}' not found in orchestrator")

        agent = self._agents[agent_id]

        # Publish AGENT_STARTED event
        await self.event_bus.publish(AgentEvent(
            event_type=EventType.AGENT_STARTED,
            agent_id=agent_id,
            data={"input": input_data},
            timestamp=time.time()
        ))

        start_time = time.time()
        result: AgentResult | None = None
        success = False

        try:
            # Run the agent
            result = await agent.run(input_data)
            success = result.status == AgentStatus.COMPLETE

            # Publish AGENT_COMPLETED event
            await self.event_bus.publish(AgentEvent(
                event_type=EventType.AGENT_COMPLETED,
                agent_id=agent_id,
                data={
                    "status": result.status.value,
                    "iterations": result.iterations,
                    "output": result.output,
                    "message": result.message
                },
                timestamp=time.time()
            ))
        except Exception as e:
            # Publish AGENT_FAILED event
            duration = time.time() - start_time
            await self.event_bus.publish(AgentEvent(
                event_type=EventType.AGENT_FAILED,
                agent_id=agent_id,
                data={"error": str(e), "duration": duration},
                timestamp=time.time()
            ))

            # Create error result
            result = AgentResult(
                status=AgentStatus.ERROR,
                iterations=0,
                output={},
                message=str(e),
                duration_seconds=duration
            )
            success = False

        # Record metrics
        duration = time.time() - start_time
        self.metrics_collector.record_run(
            agent_id=agent_id,
            duration=duration,
            cost=0.0,  # Cost tracking can be enhanced later
            success=success
        )

        return result

    async def run_all(self, input_data: dict[str, Any]) -> dict[str, AgentResult]:
        """Run all registered agents with the same input data.

        Executes agents sequentially and returns results for all agents.
        Each agent receives the same input_data.

        Args:
            input_data: Input data to pass to each agent

        Returns:
            Dictionary mapping agent_id to AgentResult
        """
        results: dict[str, AgentResult] = {}

        for agent_id in self._agents:
            result = await self.run_agent(agent_id, input_data)
            results[agent_id] = result

        return results

    def clear_agents(self) -> None:
        """Remove all agents from the orchestrator."""
        self._agents.clear()

    def reset_metrics(self) -> None:
        """Reset all collected metrics."""
        self.metrics_collector.reset()
