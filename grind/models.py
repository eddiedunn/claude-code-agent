from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


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
