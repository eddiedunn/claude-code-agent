"""Agent protocol and result types for orchestration.

This module provides the Agent protocol and AgentResult types for defining
agents that can be orchestrated in task graphs. Agents use simple dict-based
input/output to maintain flexibility.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol


class AgentStatus(Enum):
    """Status of agent execution."""
    COMPLETE = "complete"
    STUCK = "stuck"
    MAX_ITERATIONS = "max_iterations"
    ERROR = "error"


@dataclass
class AgentResult:
    """Result of agent execution.

    Uses simple dict for input/output to maintain flexibility
    and follow DAGExecutor pattern.
    """
    status: AgentStatus
    iterations: int
    output: dict[str, object] = field(default_factory=dict)
    message: str = ""
    duration_seconds: float = 0.0


class Agent(Protocol):
    """Protocol for agents that can be orchestrated.

    Agents take dict input and return AgentResult with dict output.
    This simple signature enables flexible composition in task graphs.

    Example:
        class MyAgent:
            async def run(self, input: dict[str, object]) -> AgentResult:
                # Process input
                result = process(input)
                return AgentResult(
                    status=AgentStatus.COMPLETE,
                    iterations=1,
                    output={"result": result}
                )
    """

    async def run(self, input: dict[str, object]) -> AgentResult:
        """Execute the agent with given input.

        Args:
            input: Dict containing agent input parameters

        Returns:
            AgentResult with status, iterations, and output dict
        """
        ...
