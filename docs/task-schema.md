# Grind Task File Schema

**Authoritative reference for `tasks.yaml` / `tasks.json` files consumed by `grind batch` and `grind dag`.**

The parser is `grind/tasks.py:parse_task_from_yaml` and `build_task_graph`.

---

## Top-level structure

```yaml
tasks:
  - <task>
  - <task>
  ...
```

Each element in `tasks` is a task object described below.

---

## Task fields

### Required

| Field | Type | Description |
|-------|------|-------------|
| `task` | string | Imperative instruction for the agent. Must be non-empty. |
| `verify` | string | Shell command that exits 0 on success. Must be non-empty. |

### Optional — identity and dependencies

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | string | `task_N` (1-indexed) | Unique kebab-case slug within the file. Required if other tasks reference this task in `depends_on`. |
| `depends_on` | list[string] | `[]` | IDs of tasks that must complete before this task runs. Enables DAG ordering (`grind dag`). |

### Optional — model selection

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `model` | string | `"sonnet"` | Model to run this task on. Accepted forms: bare name (`haiku`, `sonnet`, `opus`) or provider-prefixed (`claude/sonnet`, `claude/opus`, `openrouter/openai/gpt-4o`, `openrouter/google/gemini-pro`). |

### Optional — execution limits

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_iterations` | int | `10` | Maximum fix-verify retry cycles. Use 5 for simple tasks, 10 for standard, 20 for complex. Must be ≥ 1. |
| `max_turns` | int | `50` | Maximum SDK turns per iteration. Must be ≥ 1. |

### Optional — task semantics

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `spec` | string | `""` | Acceptance criterion in 1–2 sentences. Describes what "done" looks like. Separate from `task` (the agent instruction). |
| `parallel_safe` | bool | `false` | Set `true` only if this task does not write to any files that other tasks also write. Enables safe concurrent execution. |

### Optional — worktree isolation

Three equivalent ways to configure git worktree isolation:

| Field | Type | Description |
|-------|------|-------------|
| `worktree` | `true` / `false` / dict | `true` = isolated worktree with auto-named branch. `false` / omit = no worktree. Dict = full config (see below). |
| `branch` | string | Shorthand: creates a worktree with this branch name (implies `worktree`). |
| `merge_from` | list[string] | Branches to merge into this task's worktree before starting. Used with `branch`. |

**`worktree` dict fields:**

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `branch` | string | — | Branch name for this worktree. |
| `base_branch` | string | `"HEAD"` | Create branch from this ref. |
| `merge_from` | list[string] | `[]` | Branches to merge in before starting. |
| `cleanup_on_success` | bool | `true` | Remove worktree directory after successful completion. |
| `cleanup_on_failure` | bool | `false` | Remove worktree directory even on failure (default: keep for debugging). |

### Optional — agent permissions

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `allowed_tools` | list[string] | `null` (all) | Restrict agent to this set of tools (e.g. `["Read", "Write", "Bash"]`). |
| `permission_mode` | string | `"acceptEdits"` | Claude Code permission mode. One of `acceptEdits`, `requireApproval`. |

### Optional — advanced / low-level

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `cwd` | string | task file's parent dir | Working directory for this task. Overrides the default. |
| `hooks` | dict | — | Slash command hooks. Sub-keys: `pre_grind`, `post_iteration`, `post_grind` (each a list of hook specs). |
| `prompt_config` | dict | — | Prompt customisation. Sub-keys: `custom_prompt`, `preamble`, `additional_rules` (list), `additional_context`. |

---

## Examples

### Minimal single task

```yaml
# example: minimal
tasks:
  - task: "Fix all ruff linting errors"
    verify: "ruff check ."
```

### Multi-task DAG with worktree shorthand

```yaml
# example: dag-worktree
tasks:
  - id: lint
    task: "Fix all ruff linting errors in src/"
    verify: "ruff check src/"
    model: haiku
    max_iterations: 5
    worktree: true
    parallel_safe: true

  - id: types
    task: "Fix all mypy type errors in src/"
    verify: "mypy src/"
    model: sonnet
    max_iterations: 10
    worktree: true
    parallel_safe: true

  - id: tests
    task: "Fix failing unit tests"
    verify: "pytest tests/unit/ -v"
    model: sonnet
    max_iterations: 15
    depends_on: [lint, types]
    worktree: true
```

### Provider-prefixed models

```yaml
# example: provider-models
tasks:
  - id: draft
    task: "Implement the feature described in SPEC.md"
    verify: "pytest tests/feature/ -v"
    model: claude/opus
    max_iterations: 20
    worktree: true

  - id: review
    task: "Review the implementation and fix any style issues"
    verify: "ruff check . && mypy src/"
    model: openrouter/openai/gpt-4o
    max_iterations: 5
    depends_on: [draft]
```

### spec and parallel_safe

```yaml
# example: spec-parallel
tasks:
  - id: add-logging
    spec: "Every public function in src/api/ emits a structured log entry on entry and exit."
    task: "Add structured logging to all public functions in src/api/"
    verify: "grep -r 'logger\\.' src/api/ | wc -l | awk '$1 > 10'"
    model: sonnet
    max_iterations: 10
    parallel_safe: false

  - id: add-metrics
    spec: "A Prometheus counter increments for each HTTP request processed by the server."
    task: "Add Prometheus metrics instrumentation to the HTTP request handler"
    verify: "python -c \"import src.server; print('metrics ok')\""
    model: sonnet
    max_iterations: 10
    parallel_safe: false
    depends_on: [add-logging]
```

---

## Notes

- `id` is optional but strongly recommended for any file with more than one task.
- `spec` and `task` serve different purposes: `spec` is the acceptance criterion (what done looks like); `task` is the agent instruction (what to do).
- `parallel_safe: true` only guarantees safety if the tasks genuinely don't write overlapping files. When in doubt, use `depends_on` instead.
- Provider-prefixed models: `claude/` routes to the Claude Agent SDK; `openrouter/` routes to the OpenRouter API. Bare model names (`haiku`, `sonnet`, `opus`) default to the `claude` provider.
- `grind batch` ignores `depends_on`; use `grind dag` to get dependency-ordered (and potentially parallel) execution.
