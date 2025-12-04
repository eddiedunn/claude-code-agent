"""Orchestration module for managing and coordinating agents.

This module provides the core components for agent orchestration:
- Agent: Protocol for defining agents
- AgentResult: Result type for agent execution
- GrindAgent: Agent wrapper for the grind() function
- Orchestrator: Coordinates execution of multiple agents
- EventBus: Pub-sub event system for orchestration
- MetricsCollector: Tracks performance metrics
"""

from grind.orchestration.agent import Agent, AgentResult
from grind.orchestration.events import EventBus
from grind.orchestration.grind_agent import GrindAgent
from grind.orchestration.metrics import MetricsCollector
from grind.orchestration.orchestrator import Orchestrator

__all__ = [
    "Agent",
    "AgentResult",
    "GrindAgent",
    "Orchestrator",
    "EventBus",
    "MetricsCollector",
]
