"""Agent-specific data models for the TUI."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from grind.models import TaskDefinition


class AgentStatus(Enum):
    """Status of an agent in the TUI."""

    PENDING = "pending"  # Agent created but not started
    RUNNING = "running"  # Agent actively working
    PAUSED = "paused"  # Agent paused for human input
    COMPLETE = "complete"  # Agent finished successfully
    STUCK = "stuck"  # Agent reported stuck status
    FAILED = "failed"  # Agent encountered error
    CANCELLED = "cancelled"  # Agent was cancelled by user


class AgentType(Enum):
    """Type of agent executing a task."""

    WORKER = "worker"  # Standard grind loop agent
    ORCHESTRATOR = "orchestrator"  # DAG orchestrator agent
    EVALUATOR = "evaluator"  # Quality evaluation agent


@dataclass
class AgentInfo:
    """Information about an agent instance."""

    agent_id: str  # Unique identifier
    task_id: str  # From TaskNode if applicable
    task_description: str  # First 100 chars of task
    agent_type: AgentType
    status: AgentStatus
    model: str  # sonnet/opus/haiku
    iteration: int  # Current iteration
    max_iterations: int
    progress: float  # 0.0 to 1.0, estimated from iteration/max
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    output_file: Path | None = None  # Log file location
    error_message: str | None = None
    needs_human_input: bool = False  # For PAUSED state
    human_prompt: str | None = None  # What the agent is asking

    @property
    def duration(self) -> str:
        """Return formatted duration string."""
        if self.started_at is None:
            return "Not started"

        end_time = self.completed_at if self.completed_at else datetime.now()
        delta = end_time - self.started_at

        total_seconds = int(delta.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"

    def __post_init__(self):
        """Validate AgentInfo fields."""
        if self.iteration < 0:
            raise ValueError("iteration must be >= 0")
        if self.max_iterations < 1:
            raise ValueError("max_iterations must be >= 1")
        if not 0.0 <= self.progress <= 1.0:
            raise ValueError("progress must be between 0.0 and 1.0")
        if len(self.task_description) > 100:
            self.task_description = self.task_description[:100]


class DAGNodeStatus(Enum):
    """Status of a DAG node."""

    PENDING = "pending"  # Not started
    READY = "ready"  # Dependencies satisfied, can run
    RUNNING = "running"  # Currently executing
    COMPLETED = "completed"  # Finished successfully
    FAILED = "failed"  # Failed during execution
    BLOCKED = "blocked"  # Blocked by failed dependency


@dataclass
class DAGNodeInfo:
    """Information about a DAG node for visualization."""

    node_id: str
    task_def: TaskDefinition  # Reference to TaskDefinition from grind/models.py
    depends_on: list[str] = field(default_factory=list)
    status: DAGNodeStatus = DAGNodeStatus.PENDING
    agent_id: str | None = None  # Linked agent when running
    position: tuple[int, int] | None = None  # For visualization (x, y)

    def __post_init__(self):
        """Validate DAGNodeInfo fields."""
        if not self.node_id:
            raise ValueError("node_id cannot be empty")

        # Validate task_def
        errors = self.task_def.validate()
        if errors:
            raise ValueError(f"Invalid task_def: {'; '.join(errors)}")

        # Ensure depends_on is a list (handle mutable default)
        if not isinstance(self.depends_on, list):
            self.depends_on = list(self.depends_on) if self.depends_on else []
