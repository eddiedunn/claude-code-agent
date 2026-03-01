<!-- description: Grind Loop is an autonomous AI coding agent built on the Claude Agent SDK that runs fix-verify loops, decomposes problems into DAG-scheduled tasks, executes them in parallel Git worktrees, and merges results — all without human supervision. -->

# Grind Loop

[![Python](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Claude Agent SDK](https://img.shields.io/badge/Claude%20Agent%20SDK-0.1%2B-blueviolet?logo=anthropic)](https://github.com/anthropics/claude-agent-sdk)
[![uv](https://img.shields.io/badge/uv-package%20manager-orange)](https://github.com/astral-sh/uv)

**An autonomous AI coding agent that fixes your codebase while you're away — powered by Anthropic's Claude Agent SDK.**

---

## The Problem

You spend hours trapped in this loop:

```
See failure -> Paste to Claude -> Apply fix -> Run tests -> See failure -> repeat...
```

## The Solution

```bash
uv run grind run --task "Fix all failing tests" --verify "pytest tests/ -v"
```

Walk away. Come back to passing tests.

Grind Loop is an **agentic workflow** engine that drives Claude through automated **fix-verify loops**, intelligently decomposes large problems into a **DAG** of parallel subtasks, executes each in isolated **Git worktrees**, and merges the results — no human in the loop required.

---

## Key Features

- **Autonomous fix-verify loop** — Claude iterates until your verification command exits 0, signaling `GRIND_COMPLETE`
- **Intelligent task decomposition** — analyzes a broad problem and breaks it into a prioritized, dependency-ordered task list
- **DAG execution** — runs independent subtasks in parallel with dependency management for maximum throughput
- **Git worktree isolation** — each parallel task runs in its own worktree, eliminating merge conflicts during execution
- **Multi-agent orchestration** — coordinates multiple Claude Agent SDK instances across concurrent tasks
- **CostAwareRouter** — automatically selects Haiku, Sonnet, or Opus based on task complexity (3-5x cost savings)
- **Extended Thinking** — optional 10K-token reasoning budget for complex decomposition and planning
- **Slash command hooks** — inject custom Claude Code commands at lifecycle points (`pre_grind`, `post_iteration`, `post_grind`)
- **Intelligent merge** — combines parallel worktree branches with conflict detection, backup staging, and post-merge verification
- **Batch mode** — run a YAML/JSON task list sequentially with aggregated result summaries
- **Interactive TUI** — terminal interface for monitoring running agents and streaming logs (alpha)

---

## Quick Start

Three commands to get running:

```bash
git clone https://github.com/eddiedunn/claude-code-agent.git && cd claude-code-agent
uv sync
uv run grind run --task "Fix all ruff linting errors" --verify "ruff check src/"
```

> **Prerequisites**: Python 3.11+, [uv](https://github.com/astral-sh/uv), and the [Claude Code CLI](https://claude.ai/code) installed and authenticated.

---

## Installation

```bash
# Clone and enter the repo
git clone https://github.com/eddiedunn/claude-code-agent.git
cd claude-code-agent

# Install dependencies with uv
uv sync

# Verify Claude Code CLI is available
claude --version
```

---

## Usage Examples

### Single Task — fix-verify loop

Run a single autonomous coding task with a verification command:

```bash
# Fix linting (uses Haiku by default — fast and cheap)
uv run grind run --task "Fix all ruff linting errors" --verify "ruff check src/"

# Fix type errors with more iterations
uv run grind run -t "Fix all mypy type errors" -v "mypy src/ --strict" -n 15

# Short form
uv run grind -t "Fix tests" -v "pytest"
```

### Batch Mode — run a task list from YAML

```bash
uv run grind batch tasks.yaml
```

`tasks.yaml` format:

```yaml
tasks:
  - task: "Fix authentication test failures"
    verify: "pytest tests/auth/ -v"
    model: haiku
    max_iterations: 5

  - task: "Fix API endpoint tests"
    verify: "pytest tests/api/ -v"
    model: sonnet
    max_iterations: 8
```

### Decompose — let Claude break down a large problem

```bash
# Analyze the problem and generate a task list
uv run grind decompose \
  --problem "Fix all 47 failing tests" \
  --verify "pytest tests/ -v" \
  --output tasks.yaml

# Review the generated plan, then execute
cat tasks.yaml
uv run grind batch tasks.yaml
```

### DAG Execution — parallel task scheduling

When tasks have dependencies, Grind Loop builds a DAG and schedules them for maximum parallelism:

```yaml
tasks:
  - task: "Fix database models"
    verify: "pytest tests/models/"
    id: fix-models

  - task: "Fix API endpoints that depend on models"
    verify: "pytest tests/api/"
    depends_on: [fix-models]
```

```bash
uv run grind batch tasks.yaml  # fix-models runs first, then API tests run in parallel
```

### Git Worktrees — conflict-free parallel execution

Each parallel task is automatically assigned an isolated Git worktree so branches never interfere:

```bash
# Grind Loop creates and manages worktrees automatically during DAG execution
uv run grind batch dag-tasks.yaml --worktrees
```

### Merge — combine parallel worktree branches

After parallel tasks complete, merge their branches intelligently:

```bash
# Interactive merge with conflict resolution
uv run grind merge

# Merge specific branches
uv run grind merge fix/lint fix/tests fix/types

# With post-merge verification
uv run grind merge --verify "pytest && ruff check"

# Dry run — see what would be merged without doing it
uv run grind merge --dry-run
```

When conflicts occur you are prompted to: show the diff, keep ours, keep theirs, skip the branch, or abort. A backup staging branch is always created before touching `main`.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                        CLI (grind.py)                   │
│           run │ batch │ decompose │ merge │ tui          │
└────────────────────────────┬────────────────────────────┘
                             │
              ┌──────────────▼──────────────┐
              │        engine.py            │
              │   Core fix-verify loop      │
              │   grind() / decompose()     │
              └──┬───────────┬─────────────┘
                 │           │
    ┌────────────▼──┐  ┌─────▼──────────┐
    │  batch.py     │  │   hooks.py     │
    │  Sequential / │  │  Slash command │
    │  DAG runner   │  │  lifecycle     │
    └────────────┬──┘  └────────────────┘
                 │
    ┌────────────▼────────────────────────┐
    │        Claude Agent SDK             │
    │  (Haiku / Sonnet / Opus instances)  │
    │  CostAwareRouter  •  Extended Think │
    └────────────┬────────────────────────┘
                 │
    ┌────────────▼────────────────────────┐
    │         Git Worktrees               │
    │  Isolated branch per parallel task  │
    │  GrindMerger for conflict resolution│
    └─────────────────────────────────────┘
```

**Module responsibilities:**

| Module | Responsibility |
|--------|---------------|
| `grind/engine.py` | Core fix-verify loop orchestration, `grind()` and `decompose()` |
| `grind/batch.py` | Batch and DAG task runner, parallel execution |
| `grind/cli.py` | CLI argument parsing and command dispatch |
| `grind/models.py` | All data structures (`TaskDefinition`, `GrindResult`, `GrindStatus`) |
| `grind/prompts.py` | Prompt templates and `build_prompt()` |
| `grind/hooks.py` | Slash command hook execution at lifecycle points |
| `grind/tasks.py` | YAML/JSON task file loading and parsing |
| `grind/utils.py` | ANSI output formatting and result display |

---

## CLI Reference

### `grind run`

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--task` | `-t` | required | Natural-language task description |
| `--verify` | `-v` | required | Shell command to verify success (exit 0 = pass) |
| `--max-iter` | `-n` | `10` | Maximum fix-verify iterations |
| `--model` | `-m` | `haiku` | Model to use: `haiku`, `sonnet`, `opus` |
| `--cwd` | `-c` | `.` | Working directory for the agent |
| `--verbose` | | `false` | Stream full Claude output |
| `--quiet` | `-q` | `false` | Suppress all non-essential output |

### `grind batch`

| Option | Default | Description |
|--------|---------|-------------|
| `file` | required | Path to YAML or JSON task list |
| `--verbose` | `false` | Show full output per task |
| `--stop-on-stuck` | `false` | Halt batch if any task gets stuck |

### `grind decompose`

| Option | Short | Description |
|--------|-------|-------------|
| `--problem` | `-p` | High-level problem description |
| `--verify` | `-v` | Verification command for generated subtasks |
| `--output` | `-o` | File path to write generated `tasks.yaml` |
| `--cwd` | `-c` | Working directory |
| `--verbose` | | Show decomposition reasoning |

### `grind merge`

| Option | Description |
|--------|-------------|
| `[branches...]` | Branch names to merge (default: auto-detect) |
| `--pattern` | Glob pattern for branch selection (e.g. `fix/*`) |
| `--verify` | Command to run after merge |
| `--dry-run` | Show merge plan without executing |

### `grind tui`

| Option | Description |
|--------|-------------|
| `-t` | Pre-load a task file on launch |

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | All tasks completed successfully |
| `1` | Runtime error |
| `2` | Agent got stuck (signaled `GRIND_STUCK`) |
| `3` | Max iterations reached without success |

---

## Model Selection

| Model | Alias | Best For | Input / Output (per 1M tokens) |
|-------|-------|----------|-------------------------------|
| Claude Haiku | `haiku` | Linting, formatting, simple fixes (~90% of tasks) | $0.25 / $1.25 |
| Claude Sonnet | `sonnet` | Complex refactors, multi-file bugs | $3.00 / $15.00 |
| Claude Opus | `opus` | Architecture, planning, decomposition | $15.00 / $75.00 |

Start with `haiku` (the default). Haiku handles the vast majority of coding tasks at roughly 50x lower cost than Opus. Use `sonnet` for multi-file refactors and `opus` for high-level decomposition.

---

## Real-World Examples

### Fix an Entire Test Suite

```bash
# Let Claude analyze and decompose all 47 failures into a parallel plan
uv run grind decompose \
  -p "Fix all failing pytest tests" \
  -v "pytest tests/ -v --tb=short" \
  -o test-tasks.yaml

# Review the generated plan
cat test-tasks.yaml

# Execute — tasks with no dependencies run in parallel
uv run grind batch test-tasks.yaml
```

### Resolve All SonarQube Code Smells

```bash
uv run grind decompose \
  -p "Fix all SonarQube code smells and bugs" \
  -v "sonar-scanner && ./check-quality-gate.sh" \
  -o sonar-tasks.yaml

uv run grind batch sonar-tasks.yaml
```

### Full Linting + Type-Check + Test Pipeline

```bash
# Run three independent fix tasks in parallel via worktrees
uv run grind batch - <<'EOF'
tasks:
  - task: "Fix all ruff linting errors"
    verify: "ruff check src/"
    id: lint

  - task: "Fix all mypy type errors"
    verify: "mypy src/ --strict"
    id: types

  - task: "Fix failing unit tests (excluding integration)"
    verify: "pytest tests/unit/ -v"
    id: unit-tests
    depends_on: [lint, types]
EOF
```

---

## Slash Command Hooks

Inject custom Claude Code slash commands at key lifecycle points:

```yaml
tasks:
  - task: "Implement OAuth authentication"
    verify: "pytest tests/auth/ -v && mypy src/auth/"
    model: sonnet
    max_iterations: 20
    hooks:
      pre_grind:
        - "/compact"
        - "/explain-codebase auth/"
      post_iteration:
        - command: "/compact"
          trigger: every_n
          trigger_count: 5
      post_grind:
        - "/code-review"
        - "/security-audit"
```

Hook triggers: `once` · `every` · `every_n` · `on_error` · `on_success`

---

## Python API

Use Grind Loop programmatically inside your own agentic workflows:

```python
from grind import grind, TaskDefinition, GrindStatus

# Simple fix-verify loop
task = TaskDefinition(
    task="Fix linting errors",
    verify="ruff check .",
    model="haiku"
)

result = await grind(task)

if result.status == GrindStatus.COMPLETE:
    print(f"Done in {result.iterations} iterations!")
```

---

## Project Structure

```
claude-code-agent/
├── grind/
│   ├── __init__.py      # Public API exports
│   ├── models.py        # Data structures and enums
│   ├── engine.py        # Core fix-verify loop
│   ├── batch.py         # Batch and DAG runner
│   ├── cli.py           # Command-line interface
│   ├── hooks.py         # Slash command lifecycle hooks
│   ├── prompts.py       # Prompt templates
│   ├── tasks.py         # YAML/JSON task loading
│   └── utils.py         # Output formatting
├── grind.py             # Entry point
├── examples/
│   └── example-tasks.yaml
└── tests/
```

---

## Contributing

Contributions are welcome. Please open an issue before submitting a pull request for significant changes.

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Install dev dependencies: `uv sync --group dev`
4. Run the test suite: `uv run pytest`
5. Lint: `uv run ruff check grind/`
6. Submit a pull request

---

## License

[MIT](LICENSE)

---

*Built on [Anthropic's Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk) and [Claude Code](https://claude.ai/code).*
