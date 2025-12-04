"""Metrics collection for agent orchestration.

This module provides the MetricsCollector class for tracking performance metrics
during agent execution, including duration, cost, and success rate per agent.
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Dict


@dataclass
class AgentMetrics:
    """Metrics for a single agent.

    Tracks execution statistics including duration, cost, and success rate.
    """
    total_duration: float = 0.0
    total_cost: float = 0.0
    total_runs: int = 0
    successful_runs: int = 0

    @property
    def success_rate(self) -> float:
        """Calculate success rate as a percentage.

        Returns:
            Success rate from 0.0 to 1.0, or 0.0 if no runs
        """
        if self.total_runs == 0:
            return 0.0
        return self.successful_runs / self.total_runs

    @property
    def average_duration(self) -> float:
        """Calculate average duration per run.

        Returns:
            Average duration in seconds, or 0.0 if no runs
        """
        if self.total_runs == 0:
            return 0.0
        return self.total_duration / self.total_runs

    @property
    def average_cost(self) -> float:
        """Calculate average cost per run.

        Returns:
            Average cost, or 0.0 if no runs
        """
        if self.total_runs == 0:
            return 0.0
        return self.total_cost / self.total_runs


class MetricsCollector:
    """Collects and aggregates metrics for agent execution.

    Tracks duration, cost, and success rate per agent across multiple runs.
    Provides methods to record execution results and query aggregated metrics.

    Example:
        collector = MetricsCollector()

        # Record a successful agent run
        collector.record_run(
            agent_id="agent_1",
            duration=1.5,
            cost=0.002,
            success=True
        )

        # Get metrics for an agent
        metrics = collector.get_metrics("agent_1")
        print(f"Success rate: {metrics.success_rate:.2%}")
        print(f"Average duration: {metrics.average_duration:.2f}s")

        # Get all metrics
        all_metrics = collector.get_all_metrics()
    """

    def __init__(self):
        """Initialize the metrics collector with empty metrics."""
        self._metrics: Dict[str, AgentMetrics] = defaultdict(AgentMetrics)

    def record_run(
        self,
        agent_id: str,
        duration: float,
        cost: float = 0.0,
        success: bool = True
    ) -> None:
        """Record metrics for a single agent run.

        Args:
            agent_id: Unique identifier for the agent
            duration: Duration of the run in seconds
            cost: Cost of the run (e.g., API costs)
            success: Whether the run was successful
        """
        metrics = self._metrics[agent_id]
        metrics.total_duration += duration
        metrics.total_cost += cost
        metrics.total_runs += 1
        if success:
            metrics.successful_runs += 1

    def get_metrics(self, agent_id: str) -> AgentMetrics:
        """Get metrics for a specific agent.

        Args:
            agent_id: Unique identifier for the agent

        Returns:
            AgentMetrics for the specified agent
        """
        return self._metrics[agent_id]

    def get_all_metrics(self) -> Dict[str, AgentMetrics]:
        """Get metrics for all agents.

        Returns:
            Dictionary mapping agent_id to AgentMetrics
        """
        return dict(self._metrics)

    def reset(self) -> None:
        """Reset all metrics to zero."""
        self._metrics.clear()

    def reset_agent(self, agent_id: str) -> None:
        """Reset metrics for a specific agent.

        Args:
            agent_id: Unique identifier for the agent
        """
        if agent_id in self._metrics:
            del self._metrics[agent_id]
