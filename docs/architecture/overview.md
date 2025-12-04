# Grind Loop - Architecture

Clean, modular architecture for automated fix-verify loops with AI agents.

---

## Project Structure

```
grind/
├── __init__.py          # Public API exports
├── models.py            # Data structures and enums
├── prompts.py           # Prompt templates and builders
├── hooks.py             # Slash command hook execution
├── engine.py            # Core grind loop orchestration
├── logging.py           # Structured logging and telemetry
├── tasks.py             # Task loading and parsing
├── batch.py             # Batch execution runner
├── dag.py               # DAG executor for task dependencies
├── worktree.py          # Git worktree management
├── cli.py               # Command-line interface
└── utils.py             # Colors and output formatting

grind.py                 # Entry point (thin wrapper)
examples/
└── enhanced-tasks.yaml  # Example task definitions
```

---

## Module Responsibilities

### models.py
**Purpose**: All data structures, no logic

**Contents**:
- `HookTrigger` - Enum for hook timing
- `SlashCommandHook` - Hook definition with trigger logic
- `GrindHooks` - Collection of pre/post/iteration hooks
- `PromptConfig` - Prompt customization settings
- `GrindStatus` - Result status enum
- `GrindResult` - Single task execution result
- `TaskDefinition` - Complete task specification
- `BatchResult` - Batch execution results
- `TaskNode` - Task with dependency metadata
- `TaskGraph` - Directed acyclic graph of tasks
- `DAGResult` - DAG execution results
- `WorktreeConfig` - Git worktree isolation settings

**Why**: Single source of truth for data structures. Easy to find, easy to import.

---

### prompts.py
**Purpose**: Prompt generation logic

**Contents**:
- `GRIND_PROMPT` - Default system prompt template
- `CONTINUE_PROMPT` - Iteration continuation prompt
- `DECOMPOSE_PROMPT` - Problem decomposition prompt
- `build_prompt()` - Combines config with templates

**Why**: Prompts are critical. Keep them together, version them, test them.

---

### hooks.py
**Purpose**: Slash command execution at lifecycle points

**Contents**:
- `execute_slash_command()` - Run single command, capture output
- `execute_hooks()` - Run list of hooks based on triggers

**Why**: Hooks are a distinct feature. Isolate for testing and extension.

---

### logging.py
**Purpose**: Structured logging and telemetry

**Contents**:
- `setup_logger()` - Initialize session logging
- `log_task_start()`, `log_result()` - Task lifecycle events
- `log_tool_use()`, `log_tool_result()` - Tool execution tracing
- `log_result_message()` - SDK telemetry (cost, tokens, duration)
- `log_verify_command()` - Verification command output
- `_write_jsonl_event()` - Machine-parseable event output
- `get_log_file()`, `get_jsonl_file()` - Access current log paths

**Output**:
- `.grind/logs/*.log` - Human-readable text logs
- `.grind/logs/*.jsonl` - Structured JSON events for analysis

**Why**: Comprehensive logging enables debugging and telemetry. Dual format (text + JSONL) serves both human and programmatic consumers.

---

### engine.py
**Purpose**: Core orchestration logic

**Contents**:
- `grind()` - Main loop: query → iterate → verify → fix → complete
- `decompose()` - Break problems into subtasks

**Why**: This IS the grind loop. Everything else supports this.

---

### tasks.py
**Purpose**: Task definition loading and parsing

**Contents**:
- `parse_task_from_yaml()` - Convert YAML dict to TaskDefinition
- `load_tasks()` - Load from file (YAML or JSON)
- `build_task_graph()` - Load tasks with dependencies as a DAG

**Why**: Clean separation between file I/O and task execution.

---

### batch.py
**Purpose**: Run multiple tasks sequentially

**Contents**:
- `run_batch()` - Execute list of tasks, aggregate results

**Why**: Batch is a distinct mode. Keep it separate from single-task logic.

---

### dag.py
**Purpose**: DAG-based task execution with dependencies

**Contents**:
- `DAGExecutor` - Execute tasks in topological order with optional parallelism

**Why**: Dependency-aware execution is a distinct orchestration mode.

---

### worktree.py
**Purpose**: Git worktree management for parallel isolation

**Contents**:
- `WorktreeManager` - Create, merge, and cleanup Git worktrees
- `WorktreeError` - Exception for worktree operations

**Why**: Git operations isolated for testability and reuse.

---

### cli.py
**Purpose**: Command-line interface

**Contents**:
- `main()` - Argument parsing
- `main_async()` - Command dispatch (run/batch/decompose/dag)

**Why**: CLI is presentation layer. Core logic stays in engine.

---

### utils.py
**Purpose**: Output formatting and display

**Contents**:
- `Color` - ANSI color utilities
- `print_result()` - Format single task result
- `print_batch_summary()` - Format batch results

**Why**: UI concerns separated from business logic.

---

## Data Flow

```
CLI Input
    ↓
Task Definition (from args or file)
    ↓
┌─────────────────────────────────────────────┐
│           Execution Mode                     │
├─────────────────────────────────────────────┤
│  run      → Engine (grind loop)             │
│  batch    → Batch Runner → Engine           │
│  dag      → DAGExecutor → WorktreeManager   │
│                         → Engine            │
└─────────────────────────────────────────────┘
    ↓
ClaudeSDKClient ← → Hooks (at lifecycle points)
    ↓
Result
    ↓
Output Formatting
```

---

## Key Design Principles

### 1. Single Responsibility
Each module does ONE thing:
- Models hold data
- Engine runs loops
- Hooks execute commands
- CLI handles user input

### 2. No Duplication
Every concept exists in exactly ONE place. Want to change how prompts are built? Look in `prompts.py`. Done.

### 3. Clear Dependencies
```
cli.py → engine.py → hooks.py → models.py
       → tasks.py  → prompts.py
       → batch.py
       → dag.py    → worktree.py
       → utils.py
```

No circular dependencies. Clear hierarchy.

### 4. Extensibility
Want to add a new feature?
- New model? Add to `models.py`
- New hook trigger? Add to `HookTrigger` enum
- New CLI command? Add to `cli.py`
- New prompt template? Add to `prompts.py`

### 5. Testability
Each module can be tested independently:
```python
from grind.models import SlashCommandHook
from grind.hooks import execute_hooks
from grind.prompts import build_prompt
```

---

## Usage Patterns

### Import the package
```python
from grind import grind, TaskDefinition, GrindStatus

task = TaskDefinition(
    task="Fix linting errors",
    verify="ruff check .",
    model="haiku"
)

result = await grind(task)
if result.status == GrindStatus.COMPLETE:
    print("Success!")
```

### Use as CLI
```bash
uv run grind.py run -t "Fix tests" -v "pytest" -m sonnet
uv run grind.py batch tasks.yaml
uv run grind.py decompose -p "Fix all errors" -v "pytest" -o tasks.yaml
```

---

## Comparison: Before vs After

### Before (Monolithic)
```
grind.py                    (883 lines - EVERYTHING)
grind_enhanced_spec.py      (240 lines - duplicate definitions)
grind_enhanced_impl.py      (383 lines - duplicate implementation)

Total: 1,506 lines with massive duplication
```

### After (Modular)
```
grind/__init__.py           (40 lines - exports)
grind/models.py             (105 lines - data structures)
grind/prompts.py            (90 lines - prompt logic)
grind/hooks.py              (55 lines - hook execution)
grind/engine.py             (230 lines - core orchestration)
grind/tasks.py              (45 lines - task loading)
grind/batch.py              (45 lines - batch runner)
grind/cli.py                (125 lines - CLI interface)
grind/utils.py              (95 lines - output formatting)
grind.py                    (23 lines - entry point)

Total: ~850 lines, zero duplication, clear structure
```

**Result**: 40% code reduction, 100% clarity increase

---

## Extension Points

### Adding Custom Hook Triggers
```python
# In models.py
class HookTrigger(Enum):
    EVERY = "every"
    EVERY_N = "every_n"
    ON_ERROR = "on_error"
    ON_SUCCESS = "on_success"
    ONCE = "once"
    ON_TOOL_USE = "on_tool_use"  # NEW
```

### Adding New Commands
```python
# In cli.py
inspect = sub.add_parser("inspect", help="Inspect task file")
inspect.add_argument("file")
```

### Custom Result Processors
```python
# In utils.py
def print_result_json(r: GrindResult) -> str:
    return json.dumps(dataclasses.asdict(r), indent=2)
```

---

## Testing Strategy

### Unit Tests
Each module tested independently:
```python
# test_models.py
def test_hook_trigger():
    hook = SlashCommandHook("/compact", trigger="every_n", trigger_count=3)
    assert hook.should_run(3, False) == True
    assert hook.should_run(4, False) == False

# test_prompts.py
def test_build_prompt():
    config = PromptConfig(preamble="Custom intro")
    prompt = build_prompt(config, "Fix tests", "pytest")
    assert "Custom intro" in prompt
```

### Integration Tests
```python
# test_engine.py
async def test_grind_success():
    task = TaskDefinition(task="echo hello", verify="true")
    result = await grind(task)
    assert result.status == GrindStatus.COMPLETE
```

---

## Migration Guide

### Old Code
```python
from grind import grind, GrindResult
```

### New Code
```python
from grind import grind, GrindResult, TaskDefinition
```

Same imports work. Internal structure changed, API stayed stable.

---

**Architecture Version**: 2.0 (Modular)
**Last Updated**: 2025-11-28
