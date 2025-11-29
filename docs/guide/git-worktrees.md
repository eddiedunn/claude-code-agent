# Git Worktrees - Parallel Task Isolation

Run tasks in parallel with isolated Git worktrees. Each task gets its own working directory and branch, preventing conflicts during concurrent execution.

---

## Why Worktrees?

When running tasks in parallel, multiple agents may try to:

- Modify the same files simultaneously
- Run Git commands that conflict (stage, commit, checkout)
- Leave the repository in an inconsistent state

Git worktrees solve this by giving each task:

- Its own working directory
- Its own Git index
- Its own branch
- Full isolation from other tasks

---

## Quick Start

### 1. Define Tasks with Branches

```yaml
# tasks.yaml
tasks:
  - id: lint
    task: "Fix linting errors"
    verify: "ruff check ."
    branch: fix/lint

  - id: tests
    task: "Fix test failures"
    verify: "pytest"
    branch: fix/tests
    depends_on: [lint]
    merge_from: [fix/lint]
```

### 2. Run with Worktrees

```bash
uv run grind dag tasks.yaml --parallel 3 --worktrees
```

### 3. View Results

Each task creates a branch with its changes:

```bash
git branch
# * main
#   fix/lint
#   fix/tests
```

---

## YAML Configuration

### Shorthand: `branch`

Simple worktree configuration using just the branch name:

```yaml
tasks:
  - id: lint
    task: "Fix linting"
    verify: "ruff check ."
    branch: fix/lint
```

This creates:
- Worktree at `.worktrees/lint/`
- Branch `fix/lint` from current HEAD
- Auto-cleanup on success

### Full: `worktree` Block

Complete control over worktree behavior:

```yaml
tasks:
  - id: tests
    task: "Fix tests"
    verify: "pytest"
    worktree:
      branch: fix/tests
      base_branch: main
      merge_from: [fix/lint, fix/types]
      cleanup_on_success: true
      cleanup_on_failure: false
```

### Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `branch` | (required) | Branch name to create |
| `base_branch` | `HEAD` | Create branch from this ref |
| `merge_from` | `[]` | Branches to merge before starting |
| `cleanup_on_success` | `true` | Remove worktree after success |
| `cleanup_on_failure` | `false` | Keep worktree for debugging |

### Merge From

Use `merge_from` to incorporate changes from upstream tasks:

```yaml
tasks:
  - id: lint
    task: "Fix linting"
    verify: "ruff check ."
    branch: fix/lint

  - id: tests
    task: "Fix tests"
    verify: "pytest"
    branch: fix/tests
    depends_on: [lint]
    merge_from: [fix/lint]  # Get lint fixes before running
```

This ensures the tests task sees the linting fixes.

---

## Directory Structure

During execution, worktrees are created in `.worktrees/`:

```
repo/
├── .git/                      # Shared Git database
├── .worktrees/                # Grind-managed worktrees
│   ├── lint/                  # Worktree for lint task
│   │   ├── .git               # Worktree git link
│   │   ├── src/
│   │   └── tests/
│   ├── tests/                 # Worktree for tests task
│   │   ├── .git
│   │   ├── src/
│   │   └── tests/
│   └── typecheck/             # Worktree for typecheck task
├── src/                       # Main working directory
└── tests/
```

!!! note
    Add `.worktrees/` to your `.gitignore` to avoid committing temporary directories.

---

## CLI Options

### Worktree Flags

```bash
# Enable worktree isolation
uv run grind dag tasks.yaml --worktrees

# With parallelism (recommended combination)
uv run grind dag tasks.yaml --parallel 3 --worktrees

# Clean up stale worktrees first
uv run grind dag tasks.yaml --cleanup-worktrees --worktrees
```

### Warning: Parallel without Worktrees

Running parallel without worktrees shows a warning:

```bash
uv run grind dag tasks.yaml --parallel 3
# Warning: --parallel > 1 without --worktrees may cause Git conflicts
# Consider: grind dag tasks.yaml --parallel 3 --worktrees
```

---

## Workflow Patterns

### Independent Tasks

Tasks without code dependencies can run fully in parallel:

```yaml
tasks:
  - id: frontend
    task: "Fix frontend tests"
    verify: "npm test"
    cwd: "./frontend"
    branch: fix/frontend

  - id: backend
    task: "Fix backend tests"
    verify: "pytest"
    cwd: "./backend"
    branch: fix/backend

  - id: docs
    task: "Fix documentation"
    verify: "mkdocs build"
    branch: fix/docs
```

```bash
uv run grind dag tasks.yaml --parallel 3 --worktrees
```

### Cascading Changes

When tasks build on each other's changes:

```yaml
tasks:
  - id: lint
    task: "Fix linting"
    verify: "ruff check ."
    branch: fix/lint

  - id: types
    task: "Fix type errors"
    verify: "mypy ."
    branch: fix/types
    depends_on: [lint]
    merge_from: [fix/lint]

  - id: tests
    task: "Fix tests"
    verify: "pytest"
    branch: fix/tests
    depends_on: [types]
    merge_from: [fix/lint, fix/types]
```

### Final Merge

After all tasks complete, merge branches manually or with a script:

```bash
# After grind completes
git checkout main
git merge fix/lint
git merge fix/types
git merge fix/tests
```

Or create a final integration task:

```yaml
tasks:
  # ... other tasks ...

  - id: integrate
    task: "Verify all changes work together"
    verify: "pytest && ruff check . && mypy ."
    branch: fix/all
    depends_on: [lint, types, tests]
    merge_from: [fix/lint, fix/types, fix/tests]
```

---

## Cleanup

### Automatic Cleanup

By default, worktrees are removed when tasks complete successfully:

```yaml
worktree:
  branch: fix/task
  cleanup_on_success: true   # Default
  cleanup_on_failure: false  # Keep for debugging
```

### Manual Cleanup

Remove all worktrees:

```bash
# Using grind
uv run grind dag tasks.yaml --cleanup-worktrees --dry-run

# Using git directly
git worktree list
git worktree remove .worktrees/lint
git worktree remove .worktrees/tests
rm -rf .worktrees
```

### Debugging Failed Tasks

When `cleanup_on_failure: false`, you can inspect the worktree:

```bash
# See what went wrong
cd .worktrees/failed-task
git status
git diff

# Try manual fixes
# ...

# Clean up when done
cd ../..
git worktree remove .worktrees/failed-task
```

---

## Best Practices

### 1. Use Descriptive Branch Names

```yaml
# Good
branch: fix/auth-tests
branch: feature/user-api
branch: refactor/database-layer

# Avoid
branch: task1
branch: fix
```

### 2. Keep Worktrees for Debugging

For complex tasks, disable cleanup on failure:

```yaml
worktree:
  branch: fix/complex-issue
  cleanup_on_failure: false
```

### 3. Base on Appropriate Branch

For feature work, base on main:

```yaml
worktree:
  branch: fix/feature
  base_branch: main
```

For hotfixes, base on production:

```yaml
worktree:
  branch: hotfix/urgent
  base_branch: production
```

### 4. Merge Upstream Changes

Always merge changes from dependency tasks:

```yaml
- id: downstream
  depends_on: [upstream]
  merge_from: [fix/upstream]  # Don't forget this!
```

### 5. Add to .gitignore

```gitignore
# Grind worktrees
.worktrees/
```

---

## Troubleshooting

### Branch Already Exists

```
WorktreeError: Branch already exists: fix/lint
```

Solution: Delete the existing branch or use a different name:

```bash
git branch -D fix/lint
```

### Worktree Path Exists

```
WorktreeError: Worktree path already exists: .worktrees/lint
```

Solution: Clean up stale worktrees:

```bash
uv run grind dag tasks.yaml --cleanup-worktrees
# or
git worktree remove .worktrees/lint --force
```

### Merge Conflicts

If `merge_from` causes conflicts, the task will fail. Solutions:

1. Fix the upstream task first
2. Reduce parallelism to avoid conflicts
3. Restructure dependencies

### Not in a Git Repository

```
WorktreeError: Not in a git repository
```

Solution: Run from within a Git repository:

```bash
git init  # or clone an existing repo
```

---

## See Also

- [DAG Execution](dag-execution.md) - Task dependencies and execution order
- [Batch Execution](features.md#5-batch-execution) - Simple sequential execution
- [Git Worktree Documentation](https://git-scm.com/docs/git-worktree) - Official Git docs

---

**Last Updated**: 2025-11-29
