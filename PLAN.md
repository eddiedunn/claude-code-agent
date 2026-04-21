# Grind — Forward Plan

## What We Have (A76 baseline)

The working tool at `0010a76`: SDK-driven agent loop with batch execution, DAG
task ordering, worktrees for isolation, interactive checkpoints, TUI, and a
cost-aware model router. This is the foundation we build on.

---

## What We're Adding Back (from the rewrite)

Three pieces from the multi-agent rewrite are worth grafting in:

**1. Observer (`grind/observer/`)** — SQLite-backed event store + aiohttp
server. Records raw structured events per run (start, iteration, tool use,
completion). This is what makes model comparison measurable rather than
impressionistic.

**2. Execution Contracts (`grind/contract.py`)** — harness-enforced pass/fail
criteria independent of model judgment. A task either produced the required
artifact or it didn't. Essential for fair model comparison.

**3. Hooks Config (`grind/hooks_config.py`)** — auto-installs Claude Code hooks
so interactive sessions also emit events to the observer. Keeps telemetry
consistent whether grind drives the run or the user does interactively.

---

## Base Case

The default execution path is simple: one task, run via the Claude Agent SDK
in an isolated worktree (or the current codebase if no worktree is needed).
Everything else is optional on top of that.

```
grind run --task "..." --verify "pytest"
```

No comparison, no multi-model, no observer required. Just the loop.

---

## New Capabilities

### Provider Abstraction + Model Comparison

The engine talks to a `Provider` interface, never to a specific SDK. Every
provider implements the same contract:

```python
class Provider(Protocol):
    async def run(self, prompt: str, tools: list, config: RunConfig) -> AsyncIterator[Event]:
        ...
```

Providers are plugins. No provider is architecturally privileged:

| Provider | Model IDs | Notes |
|----------|-----------|-------|
| `claude` | `sonnet`, `opus`, `haiku` | Default — uses Claude Agent SDK |
| `openrouter` | `openai/gpt-4o`, `google/gemini-pro`, etc. | Uses OpenRouter API |
| *(future)* | anything | Add a new provider file, done |

Selecting a model: `--model claude/sonnet` or `--model openrouter/openai/gpt-4o`.
The prefix routes to the right provider. Default is `claude/sonnet`.

`grind compare` runs the same task against multiple models in parallel
worktrees and emits all results to the observer:

```
grind compare --task "..." --verify "pytest" \
  --models claude/sonnet claude/opus openrouter/openai/gpt-4o
```

Output: summary table of model × contract status × iterations × wall time.

### Standard Task File (Claude Code → Grind)

Claude Code's native decomposition (via slash commands or Agent tool) produces
structured task lists. Grind should consume these directly so Claude Code
becomes the standard decomposition layer and grind is purely the executor.

**Standard format** (extend existing YAML schema):

```yaml
tasks:
  - id: unique-slug
    task: "What the agent should do"
    verify: "Command that exits 0 on success"
    model: sonnet          # optional, overrides router
    depends_on: []         # existing DAG support
    worktree: true         # optional, defaults true
```

A Claude Code slash command (`/generate-tasks`) produces this file. Grind
consumes it via `grind batch <file>` as today. This keeps the decomposition
concern out of grind entirely — Claude Code is better at it.

---

## Phases

| # | Work | Depends on |
|---|------|------------|
| 1 | Graft observer + hooks_config from rewrite branch | — |
| 2 | Graft contract.py, wire into engine.py verify step | 1 |
| 3 | `Provider` protocol + adapters for Claude SDK and OpenRouter | 2 |
| 4 | `grind compare` subcommand: same task, N models, parallel worktrees, summary table | 3 |
| 5 | Ratify task file schema, update `/generate-tasks` skill to emit it | — |

Phases 3–4 and Phase 5 are independent and can proceed in parallel.

---

## What We're Not Doing

- No more self-evolution loop naming — the retry loop is just a retry loop
- No phase-by-phase rewrite cadence — ship working increments
- No rebuilding what A76 already does well (TUI, batch, DAG, interactive checkpoints)
