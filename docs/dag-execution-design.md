# DAG Execution and Git Worktree Design

This document describes the design for adding task dependencies (DAG execution) and Git worktree isolation to the Grind Loop system. It serves as a reference for implementers.

## Problem Statement

Currently, Grind Loop executes tasks sequentially in `run_batch()`. This has limitations:

1. **No dependency awareness**: Tasks run in file order, not dependency order
2. **No parallel execution**: Independent tasks can't run concurrently
3. **Git conflicts**: Parallel execution would cause Git index locks and merge conflicts
4. **No output passing**: One task's results can't inform another task

## Solution Overview

We're adding two complementary features:

1. **DAG Execution**: Tasks declare dependencies, executor runs them in topological order
2. **Git Worktrees**: Each parallel task gets an isolated working directory on its own branch

## Architecture

### Data Flow

```
YAML File --> build_task_graph() --> TaskGraph --> DAGExecutor --> DAGResult
                                          |
                                          v
                                   WorktreeManager (optional)
                                          |
                                          v
                                   grind() per task
```

### New Modules

| Module | Responsibility |
|--------|----------------|
| `grind/dag.py` | DAGExecutor class, orchestrates task execution |
| `grind/worktree.py` | WorktreeManager class, Git worktree operations |

### Modified Modules

| Module | Changes |
|--------|---------|
| `grind/models.py` | Add TaskNode, TaskGraph, DAGResult, WorktreeConfig |
| `grind/tasks.py` | Add build_task_graph(), parse dependencies and worktree config |
| `grind/cli.py` | Add `dag` subcommand |
| `grind/utils.py` | Add print_dag_summary() |

## Data Models

### TaskNode

Wraps a TaskDefinition with dependency and orchestration metadata:

```python
@dataclass
class TaskNode:
    id: str                                    # Unique identifier (e.g., "lint", "test")
    task_def: TaskDefinition                   # The actual task to run
    depends_on: list[str] = []                 # IDs of tasks that must complete first
    outputs: dict[str, Any] = {}               # Results to pass to downstream tasks
    status: str = "pending"                    # pending|ready|running|completed|failed|blocked
    worktree: WorktreeConfig | None = None     # Optional worktree isolation config
```

### TaskGraph

A directed acyclic graph of TaskNodes:

```python
@dataclass
class TaskGraph:
    nodes: dict[str, TaskNode]                 # task_id -> TaskNode

    def get_ready_tasks(self, completed: set[str]) -> list[TaskNode]:
        """Return tasks whose dependencies are all in `completed`."""

    def get_execution_order(self) -> list[str]:
        """Return topologically sorted task IDs (Kahn's algorithm)."""

    def validate(self) -> list[str]:
        """Check for cycles, missing deps, duplicates. Return error messages."""
```

### WorktreeConfig

Configuration for Git worktree isolation:

```python
@dataclass
class WorktreeConfig:
    branch: str                      # Branch name for this task (e.g., "fix/lint")
    base_branch: str = "HEAD"        # Create branch from this ref
    merge_from: list[str] = []       # Branches to merge before starting work
    cleanup_on_success: bool = True  # Remove worktree after success
    cleanup_on_failure: bool = False # Keep worktree on failure for debugging
```

### DAGResult

Execution result for the entire DAG:

```python
@dataclass
class DAGResult:
    total: int                           # Total tasks in graph
    completed: int                       # Tasks that finished successfully
    failed: int                          # Tasks that failed (STUCK, ERROR, MAX_ITERATIONS)
    blocked: int                         # Tasks skipped due to failed dependencies
    execution_order: list[str]           # Order tasks were executed
    results: dict[str, GrindResult]      # task_id -> individual result
    duration_seconds: float
```

## YAML Format Extension

### Basic Dependencies

```yaml
tasks:
  - id: lint
    task: "Fix all linting errors"
    verify: "ruff check ."
    model: haiku

  - id: typecheck
    task: "Fix type errors"
    verify: "mypy src/"
    model: sonnet
    depends_on: [lint]          # Waits for lint to complete

  - id: tests
    task: "Fix failing tests"
    verify: "pytest"
    model: sonnet
    depends_on: [lint]          # Also waits for lint (parallel with typecheck)

  - id: integration
    task: "Fix integration tests"
    verify: "pytest tests/integration/"
    model: opus
    depends_on: [typecheck, tests]  # Waits for BOTH
```

### With Git Worktrees

```yaml
tasks:
  - id: lint
    task: "Fix all linting errors"
    verify: "ruff check ."
    branch: fix/lint              # Shorthand: creates worktree on this branch

  - id: typecheck
    task: "Fix type errors"
    verify: "mypy src/"
    depends_on: [lint]
    branch: fix/types
    merge_from: [fix/lint]        # Merge lint's changes before starting

  - id: tests
    task: "Fix failing tests"
    verify: "pytest"
    depends_on: [lint]
    worktree:                     # Full form: explicit worktree config
      branch: fix/tests
      base_branch: main
      merge_from: [fix/lint]
      cleanup_on_success: true
      cleanup_on_failure: false
```

### Execution Visualization

```
lint ─────┬──> typecheck ────┬──> integration
          │                  │
          └──> tests ────────┘

Timeline (parallel=2):
  [lint        ]
                [typecheck] [tests]    <- run in parallel
                                      [integration]
```

## DAG Executor Algorithm

### Sequential Mode (max_parallel=1)

```python
async def execute(self, ...):
    execution_order = self.graph.get_execution_order()  # Topological sort

    for task_id in execution_order:
        node = self.graph.nodes[task_id]

        # Check if blocked by failed dependency
        failed_deps = [d for d in node.depends_on if d in self.failed]
        if failed_deps:
            self.blocked.add(task_id)
            continue

        # Run the task
        result = await grind(node.task_def, verbose=verbose)

        if result.status == GrindStatus.COMPLETE:
            self.completed.add(task_id)
        else:
            self.failed.add(task_id)
```

### Parallel Mode (max_parallel>1)

```python
async def execute(self, max_parallel=3, use_worktrees=False, ...):
    semaphore = asyncio.Semaphore(max_parallel)

    async def run_task(node):
        async with semaphore:
            if use_worktrees and node.worktree:
                # Create isolated worktree
                path = await worktree_manager.create(node.id, node.worktree.branch)
                await worktree_manager.merge_branches(path, node.worktree.merge_from)
                node.task_def.cwd = str(path)

            result = await grind(node.task_def)

            if use_worktrees and node.worktree:
                if result.status == GrindStatus.COMPLETE and node.worktree.cleanup_on_success:
                    await worktree_manager.cleanup(node.id)

            return result

    # Main loop: keep running until all tasks done or blocked
    while len(self.completed) + len(self.failed) + len(self.blocked) < len(self.graph.nodes):
        ready = self.graph.get_ready_tasks(self.completed)
        ready = [n for n in ready if n.id not in self.failed and n.id not in self.blocked]

        if not ready:
            # Mark remaining as blocked
            break

        # Run all ready tasks concurrently
        await asyncio.gather(*[run_task(node) for node in ready])
```

## Git Worktree Operations

### WorktreeManager Methods

| Method | Git Commands | Purpose |
|--------|--------------|---------|
| `create(task_id, branch, base)` | `git worktree add .worktrees/{id} -b {branch} {base}` | Create isolated directory |
| `merge_branches(path, branches)` | `git merge {branch} --no-edit` (in worktree) | Pull in upstream changes |
| `cleanup(task_id)` | `git worktree remove .worktrees/{id}` | Remove worktree |
| `cleanup_all()` | Remove all in `.worktrees/` | Clean slate |
| `list_worktrees()` | `git worktree list --porcelain` | Show active worktrees |

### Directory Structure

```
repo/
├── .git/                      # Shared repository database
├── .worktrees/                # Grind-managed worktrees
│   ├── lint/                  # Worktree for lint task
│   │   ├── src/
│   │   └── tests/
│   ├── typecheck/             # Worktree for typecheck task
│   │   ├── src/
│   │   └── tests/
│   └── tests/                 # Worktree for tests task
├── src/                       # Main working directory
└── tests/
```

### Safety Checks

Before creating worktrees:
1. Verify we're in a Git repository
2. Warn if uncommitted changes exist
3. Error if branch name already exists
4. Error if worktree path already exists

## CLI Interface

### New `dag` Command

```bash
# Show execution plan without running
uv run grind dag tasks.yaml --dry-run

# Run sequentially (safe, no worktrees needed)
uv run grind dag tasks.yaml

# Run with parallelism (requires worktrees for safety)
uv run grind dag tasks.yaml --parallel 3 --worktrees

# Clean up stale worktrees first
uv run grind dag tasks.yaml --cleanup-worktrees --parallel 3 --worktrees

# Verbose output
uv run grind dag tasks.yaml -v --parallel 2 --worktrees
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All tasks completed successfully |
| 1 | One or more tasks failed or were blocked |
| 2 | Invalid task graph (cycle, missing dependency) |

## Implementation Phases

| Phase | Components | Tests |
|-------|------------|-------|
| 1 | TaskNode, TaskGraph, DAGResult in models.py | test_models.py |
| 2 | build_task_graph() in tasks.py | test_tasks.py |
| 3 | DAGExecutor (sequential) in dag.py | test_dag.py |
| 4 | CLI `dag` command | test_cli.py |
| 5 | WorktreeConfig, WorktreeManager | test_worktree.py |
| 6 | Parallel DAGExecutor with worktrees | test_dag.py |
| 7 | YAML worktree parsing | test_tasks.py |
| 8 | Documentation updates | - |
| 9 | Integration test | test_integration.py |

## Key Design Decisions

### Why Worktrees Instead of Stashing?

- Worktrees provide true isolation (separate index, working tree)
- No risk of stash conflicts or lost changes
- Each task can commit independently
- Branches can be inspected/debugged after failure

### Why Topological Sort for Sequential?

- Guarantees dependencies run before dependents
- Deterministic execution order
- Simple to understand and debug

### Why Semaphore for Parallel?

- Limits concurrent tasks to avoid resource exhaustion
- Simple asyncio primitive, no external dependencies
- Each task still runs in its own worktree

### Why `merge_from` Separate from `depends_on`?

- `depends_on`: Execution ordering (task B waits for task A)
- `merge_from`: Git branch merging (task B needs code changes from branch A)
- Often the same, but not always (e.g., might depend on a task but not need its code)

## Testing Strategy

### Unit Tests

- TaskGraph cycle detection
- TaskGraph topological sort
- WorktreeManager Git operations (use tmp_path fixture with real git repo)
- YAML parsing with dependencies and worktree config

### Integration Tests

- Full DAG execution with mocked grind()
- Worktree creation/cleanup lifecycle
- Parallel execution timing verification

### Manual Testing

```bash
# Create a test tasks.yaml with dependencies
# Run with --dry-run to verify execution order
# Run with --verbose to see detailed output
# Check .worktrees/ directory during parallel runs
```

## Future Extensions

These are NOT part of the current implementation but inform the design:

1. **Output passing**: Store task outputs, inject into downstream task prompts
2. **Conditional execution**: Skip tasks based on conditions
3. **Final merge**: Automatically merge all task branches into main
4. **Retry policies**: Retry failed tasks with backoff
5. **Checkpoints**: Human approval gates between phases
