# DAG Execution - Task Dependencies

Run tasks with dependencies using directed acyclic graph (DAG) execution. Tasks are executed in topological order, ensuring dependencies complete before dependents start.

---

## Quick Start

### 1. Define Tasks with Dependencies

```yaml
# tasks.yaml
tasks:
  - id: lint
    task: "Fix all linting errors"
    verify: "ruff check ."
    model: haiku

  - id: typecheck
    task: "Fix type errors"
    verify: "mypy src/"
    depends_on: [lint]

  - id: tests
    task: "Fix failing tests"
    verify: "pytest"
    depends_on: [lint]

  - id: integration
    task: "Fix integration tests"
    verify: "pytest tests/integration/"
    depends_on: [typecheck, tests]
```

### 2. Preview Execution Plan

```bash
uv run grind dag tasks.yaml --dry-run
```

Output:
```
============================================================
DAG Execution Plan
============================================================
  1. lint
     Fix all linting errors...
  2. typecheck (after: lint)
     Fix type errors...
  3. tests (after: lint)
     Fix failing tests...
  4. integration (after: typecheck, tests)
     Fix integration tests...
============================================================
Total: 4 tasks
```

### 3. Run Tasks

```bash
# Sequential execution
uv run grind dag tasks.yaml

# Parallel execution (with worktrees for isolation)
uv run grind dag tasks.yaml --parallel 3 --worktrees
```

---

## YAML Format

### Task ID

Every task needs a unique identifier. You can specify it explicitly or let it be auto-generated:

```yaml
tasks:
  # Explicit ID
  - id: lint
    task: "Fix linting"
    verify: "ruff check ."

  # Auto-generated ID (task_1, task_2, etc.)
  - task: "Fix tests"
    verify: "pytest"
```

### Dependencies

Use `depends_on` to declare which tasks must complete first:

```yaml
tasks:
  - id: a
    task: "Task A"
    verify: "echo a"

  - id: b
    task: "Task B - runs after A"
    verify: "echo b"
    depends_on: [a]

  - id: c
    task: "Task C - runs after A and B"
    verify: "echo c"
    depends_on: [a, b]
```

### Dependency Patterns

**Linear Chain**:
```yaml
tasks:
  - id: step1
    task: "Step 1"
    verify: "echo 1"

  - id: step2
    task: "Step 2"
    verify: "echo 2"
    depends_on: [step1]

  - id: step3
    task: "Step 3"
    verify: "echo 3"
    depends_on: [step2]
```

**Fan-out (parallel after one)**:
```yaml
tasks:
  - id: setup
    task: "Setup"
    verify: "echo setup"

  - id: frontend
    task: "Fix frontend"
    verify: "npm test"
    depends_on: [setup]

  - id: backend
    task: "Fix backend"
    verify: "pytest"
    depends_on: [setup]

  - id: mobile
    task: "Fix mobile"
    verify: "flutter test"
    depends_on: [setup]
```

**Diamond (converge)**:
```yaml
tasks:
  - id: lint
    task: "Lint"
    verify: "ruff check ."

  - id: typecheck
    task: "Type check"
    verify: "mypy ."
    depends_on: [lint]

  - id: tests
    task: "Tests"
    verify: "pytest"
    depends_on: [lint]

  - id: deploy
    task: "Deploy"
    verify: "echo deployed"
    depends_on: [typecheck, tests]
```

---

## CLI Reference

### Commands

```bash
# Show execution plan
uv run grind dag tasks.yaml --dry-run

# Run sequentially (default)
uv run grind dag tasks.yaml

# Run with parallelism
uv run grind dag tasks.yaml --parallel 3

# Run with Git worktree isolation (recommended for parallel)
uv run grind dag tasks.yaml --parallel 3 --worktrees

# Clean up stale worktrees before running
uv run grind dag tasks.yaml --cleanup-worktrees --parallel 3 --worktrees

# Verbose output
uv run grind dag tasks.yaml -v
```

### Options

| Option | Description |
|--------|-------------|
| `--dry-run` | Show execution plan without running |
| `-v, --verbose` | Show detailed output |
| `-p N, --parallel N` | Max parallel tasks (default: 1) |
| `-w, --worktrees` | Use Git worktrees for isolation |
| `--cleanup-worktrees` | Remove stale worktrees before running |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All tasks completed successfully |
| 1 | One or more tasks failed or were blocked |
| 2 | Invalid task graph (cycle or missing dependency) |

---

## Execution Behavior

### Task States

| State | Description |
|-------|-------------|
| `pending` | Task waiting to run |
| `ready` | Dependencies satisfied, can run |
| `running` | Currently executing |
| `completed` | Finished successfully |
| `failed` | Task failed (STUCK, ERROR, MAX_ITERATIONS) |
| `blocked` | Skipped due to failed dependency |

### Blocking on Failure

When a task fails, all downstream tasks are marked as `blocked`:

```
lint (failed) --> typecheck (blocked) --> integration (blocked)
             \
              --> tests (blocked) -------/
```

This prevents wasted effort running tasks that depend on broken code.

### Topological Ordering

Tasks are sorted using Kahn's algorithm to ensure:

1. Tasks with no dependencies run first
2. A task only runs after all its dependencies complete
3. Independent tasks can run in parallel

---

## Validation

The DAG is validated before execution:

### Cycle Detection

Circular dependencies are rejected:

```yaml
# ERROR: Cycle detected
tasks:
  - id: a
    task: "A"
    verify: "echo a"
    depends_on: [b]

  - id: b
    task: "B"
    verify: "echo b"
    depends_on: [a]
```

```
Invalid task graph: Cycle detected in task dependencies
```

### Missing Dependencies

References to non-existent tasks are rejected:

```yaml
# ERROR: Missing dependency
tasks:
  - id: test
    task: "Test"
    verify: "pytest"
    depends_on: [nonexistent]
```

```
Invalid task graph: Task 'test' depends on non-existent task 'nonexistent'
```

---

## Examples

### CI Pipeline

```yaml
tasks:
  - id: install
    task: "Install dependencies"
    verify: "uv sync"
    model: haiku

  - id: lint
    task: "Fix linting errors"
    verify: "ruff check ."
    model: haiku
    depends_on: [install]

  - id: typecheck
    task: "Fix type errors"
    verify: "mypy src/"
    model: sonnet
    depends_on: [install]

  - id: unit-tests
    task: "Fix unit tests"
    verify: "pytest tests/unit/"
    model: sonnet
    depends_on: [lint, typecheck]

  - id: integration-tests
    task: "Fix integration tests"
    verify: "pytest tests/integration/"
    model: opus
    depends_on: [unit-tests]
```

### Monorepo

```yaml
tasks:
  - id: shared
    task: "Fix shared library"
    verify: "pytest packages/shared/"
    model: sonnet

  - id: api
    task: "Fix API service"
    verify: "pytest packages/api/"
    model: sonnet
    depends_on: [shared]

  - id: web
    task: "Fix web frontend"
    verify: "npm test"
    cwd: "./packages/web"
    model: sonnet
    depends_on: [shared]

  - id: mobile
    task: "Fix mobile app"
    verify: "flutter test"
    cwd: "./packages/mobile"
    model: sonnet
    depends_on: [shared]
```

---

## Best Practices

### 1. Start Simple

Begin with sequential execution to verify your dependency graph:

```bash
uv run grind dag tasks.yaml --dry-run
uv run grind dag tasks.yaml
```

### 2. Use Explicit IDs

Always use explicit, descriptive task IDs:

```yaml
# Good
- id: fix-auth-tests
  task: "Fix authentication tests"

# Avoid
- task: "Fix tests"  # Gets auto-generated ID like task_1
```

### 3. Keep Dependencies Minimal

Only declare dependencies that are actually required:

```yaml
# Good: typecheck and tests can run in parallel
- id: typecheck
  depends_on: [lint]
- id: tests
  depends_on: [lint]

# Avoid: unnecessary sequential execution
- id: typecheck
  depends_on: [lint]
- id: tests
  depends_on: [lint, typecheck]  # tests doesn't need typecheck!
```

### 4. Use Parallel for Independent Tasks

When tasks are independent, run them in parallel:

```bash
uv run grind dag tasks.yaml --parallel 3 --worktrees
```

### 5. Combine with Existing Features

DAG execution works with all existing grind features:

```yaml
tasks:
  - id: complex-refactor
    task: "Refactor authentication"
    verify: "pytest tests/auth/"
    model: opus
    max_iterations: 20
    depends_on: [lint]
    hooks:
      pre_grind:
        - "/compact"
      post_grind:
        - "/code-review"
    prompt_config:
      preamble: "You are a security expert."
```

---

## See Also

- [Git Worktrees](git-worktrees.md) - Parallel execution with isolated working directories
- [Batch Execution](features.md#5-batch-execution) - Simple sequential task execution
- [Task Decomposition](features.md#4-task-decomposition) - Auto-generate task lists

---

**Last Updated**: 2025-11-29
