from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


class HookTrigger(Enum):
    EVERY = "every"
    EVERY_N = "every_n"
    ON_ERROR = "on_error"
    ON_SUCCESS = "on_success"
    ONCE = "once"


class CheckpointAction(Enum):
    """Actions available at interactive checkpoints between iterations."""
    CONTINUE = "continue"        # Continue to next iteration
    GUIDANCE = "guidance"        # Inject one-shot guidance
    GUIDANCE_PERSIST = "persist" # Inject persistent guidance
    STATUS = "status"            # Show detailed status
    ABORT = "abort"              # Abort gracefully
    RUN_VERIFY = "verify"        # Run verify command manually


@dataclass
class InteractiveConfig:
    """Configuration for interactive mode.

    When enabled, press 'i' during execution to request an interject checkpoint.
    The grind loop will pause at the next iteration boundary to accept guidance.
    """
    enabled: bool = False


@dataclass
class SlashCommandHook:
    command: str
    trigger: str | HookTrigger = "once"
    trigger_count: int = 1

    def __post_init__(self):
        if isinstance(self.trigger, str):
            try:
                self.trigger = HookTrigger(self.trigger)
            except ValueError:
                self.trigger = HookTrigger.ONCE

    def should_run(self, iteration: int, is_error: bool = False) -> bool:
        if self.trigger == HookTrigger.EVERY:
            return True
        elif self.trigger == HookTrigger.EVERY_N:
            return iteration % self.trigger_count == 0
        elif self.trigger == HookTrigger.ON_ERROR:
            return is_error
        elif self.trigger == HookTrigger.ONCE:
            return iteration == 1
        return False


@dataclass
class GrindHooks:
    pre_grind: list[str | SlashCommandHook] = field(default_factory=list)
    post_iteration: list[str | SlashCommandHook] = field(default_factory=list)
    post_grind: list[str | SlashCommandHook] = field(default_factory=list)

    def normalize(self) -> None:
        self.pre_grind = [
            SlashCommandHook(cmd) if isinstance(cmd, str) else cmd
            for cmd in self.pre_grind
        ]
        self.post_iteration = [
            SlashCommandHook(cmd) if isinstance(cmd, str) else cmd
            for cmd in self.post_iteration
        ]
        self.post_grind = [
            SlashCommandHook(cmd) if isinstance(cmd, str) else cmd
            for cmd in self.post_grind
        ]


@dataclass
class PromptConfig:
    custom_prompt: str | None = None
    preamble: str | None = None
    additional_rules: list[str] = field(default_factory=list)
    additional_context: str | None = None


class GrindStatus(Enum):
    COMPLETE = "complete"
    STUCK = "stuck"
    MAX_ITERATIONS = "max_iterations"
    ERROR = "error"


@dataclass
class GrindResult:
    status: GrindStatus
    iterations: int
    message: str = ""
    tools_used: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    hooks_executed: list[tuple[str, str, bool]] = field(default_factory=list)
    model: str = "sonnet"


@dataclass
class TaskDefinition:
    task: str
    verify: str
    max_iterations: int = 10
    cwd: str | None = None
    model: Literal["sonnet", "opus", "haiku"] = "sonnet"
    hooks: GrindHooks = field(default_factory=GrindHooks)
    prompt_config: PromptConfig = field(default_factory=PromptConfig)
    allowed_tools: list[str] | None = None
    permission_mode: str = "acceptEdits"
    max_turns: int = 50
    interactive: InteractiveConfig = field(default_factory=InteractiveConfig)
    query_timeout: int = 300  # Timeout in seconds for SDK query operations

    def validate(self) -> list[str]:
        """Validate task definition, return list of error messages."""
        errors = []
        if not self.task or not self.task.strip():
            errors.append("Task description cannot be empty")
        if not self.verify or not self.verify.strip():
            errors.append("Verify command cannot be empty")
        if self.model not in ("sonnet", "opus", "haiku"):
            errors.append(f"Invalid model: {self.model}")
        if self.max_iterations < 1:
            errors.append(f"max_iterations must be >= 1, got {self.max_iterations}")
        if self.max_turns < 1:
            errors.append(f"max_turns must be >= 1, got {self.max_turns}")
        return errors


@dataclass
class BatchResult:
    total: int
    completed: int
    stuck: int
    failed: int
    results: list[tuple[str, GrindResult]]
    duration_seconds: float


@dataclass
class WorktreeConfig:
    """Configuration for Git worktree isolation.

    See docs/dag-execution-design.md for usage details.
    """
    branch: str  # Branch name for this task (e.g., "fix/lint")
    base_branch: str = "HEAD"  # Create branch from this ref
    merge_from: list[str] = field(default_factory=list)  # Branches to merge
    cleanup_on_success: bool = True  # Remove worktree after success
    cleanup_on_failure: bool = False  # Keep worktree on failure for debugging


@dataclass
class TaskNode:
    """A task with dependency and orchestration metadata.

    Used by TaskGraph to track task dependencies and execution state.
    See docs/dag-execution-design.md for architecture details.
    """
    id: str
    task_def: TaskDefinition
    depends_on: list[str] = field(default_factory=list)
    outputs: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending|ready|running|completed|failed|blocked
    worktree: "WorktreeConfig | None" = None     # Optional worktree isolation config


@dataclass
class TaskGraph:
    """A directed acyclic graph of TaskNodes.

    Provides methods for topological sorting and dependency validation.
    See docs/dag-execution-design.md for algorithm details.
    """
    nodes: dict[str, TaskNode] = field(default_factory=dict)

    def get_ready_tasks(self, completed: set[str]) -> list[TaskNode]:
        """Return tasks whose dependencies are all satisfied.

        A task is ready when:
        - Its status is "pending"
        - All tasks in its depends_on list are in the completed set
        """
        ready = []
        for node in self.nodes.values():
            if node.status == "pending":
                if all(dep in completed for dep in node.depends_on):
                    ready.append(node)
        return ready

    def get_execution_order(self) -> list[str]:
        """Return topologically sorted task IDs using Kahn's algorithm.

        Algorithm:
        1. Calculate in-degree (number of dependencies) for each node
        2. Start with nodes that have in-degree 0 (no dependencies)
        3. Process each node, reducing in-degree of its dependents
        4. Add nodes to result when their in-degree reaches 0
        """
        # Calculate in-degree for each node
        in_degree = {nid: 0 for nid in self.nodes}
        for node in self.nodes.values():
            for dep in node.depends_on:
                if dep in self.nodes:
                    in_degree[node.id] += 1

        # Start with nodes that have no dependencies
        queue = [nid for nid, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            nid = queue.pop(0)
            result.append(nid)
            # Reduce in-degree for nodes that depend on this one
            for node in self.nodes.values():
                if nid in node.depends_on:
                    in_degree[node.id] -= 1
                    if in_degree[node.id] == 0:
                        queue.append(node.id)

        return result

    def validate(self) -> list[str]:
        """Validate graph structure. Returns list of error messages.

        Checks:
        1. All dependencies reference existing tasks
        2. No cycles exist in the dependency graph
        """
        errors = []

        # Check for missing dependencies
        for node in self.nodes.values():
            for dep in node.depends_on:
                if dep not in self.nodes:
                    errors.append(
                        f"Task '{node.id}' depends on non-existent task '{dep}'"
                    )

        # Check for cycles using DFS
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def has_cycle(nid: str) -> bool:
            visited.add(nid)
            rec_stack.add(nid)
            node = self.nodes.get(nid)
            if node:
                for dep in node.depends_on:
                    if dep not in visited:
                        if has_cycle(dep):
                            return True
                    elif dep in rec_stack:
                        return True
            rec_stack.remove(nid)
            return False

        for nid in self.nodes:
            if nid not in visited:
                if has_cycle(nid):
                    errors.append("Cycle detected in task dependencies")
                    break

        return errors


@dataclass
class DAGResult:
    """Result of DAG execution.

    Tracks completion status across all tasks in the graph.
    """
    total: int
    completed: int
    failed: int
    blocked: int  # Tasks skipped due to failed dependencies
    execution_order: list[str]
    results: dict[str, GrindResult] = field(default_factory=dict)
    duration_seconds: float = 0.0
