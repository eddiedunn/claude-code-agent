# Grind Loop

Automated fix-verify loops powered by Claude AI agents with intelligent model selection.

> **December 2025 Update:** Now featuring Opus 4.5 decomposition, Haiku 4.5 by default, and intelligent cost-aware routing for 3-5x cost savings.

## What is Grind Loop?

Grind Loop is a tool that automates repetitive fix-verify cycles in software development. Instead of manually running tests, analyzing failures, making fixes, and repeating - you define the task once and let Claude handle the iteration.

```bash
# Before: Hours of manual iteration
pytest → see failures → fix → pytest → see failures → fix → ...

# After: One command
uv run grind.py run -t "Fix all test failures" -v "pytest tests/ -v"
```

## Key Features

- **Model Selection**: haiku default for speed/cost, sonnet for medium complexity, opus for planning/architecture
- **Slash Command Hooks**: Execute commands at key lifecycle points
- **Custom Prompts**: Add domain-specific expertise to tasks
- **Task Decomposition**: Automatically break large problems into subtasks
- **Batch Execution**: Run multiple tasks sequentially
- **Context-Aware**: `/generate-tasks` command analyzes conversation history

## Model Selection & Pricing

Choose the right model for your task based on complexity and budget (December 2025 rates):

| Model | Use Case | Input (per 1M tokens) | Output (per 1M tokens) |
|-------|----------|----------------------|------------------------|
| **haiku** (default) | Simple fixes, linting, formatting | $0.25 | $1.25 |
| **sonnet** | Bug fixes, refactoring, medium complexity | $3.00 | $15.00 |
| **opus** | Planning, architecture, complex logic | $15.00 | $75.00 |

**Recommendation**: Start with haiku for most tasks. Use sonnet for medium complexity work. Reserve opus for architectural decisions and complex planning tasks.

## Quick Start

### Installation

```bash
git clone https://github.com/eddiedunn/claude-code-agent
cd claude-code-agent
uv sync
```

### Run Your First Task

```bash
uv run grind.py run \
  --task "Fix linting errors" \
  --verify "ruff check ." \
  --model haiku
```

### Generate Tasks from Conversation

```bash
# In Claude Code conversation:
# Discuss your problems, then:
/generate-tasks
```

## Architecture

```
grind/
├── models.py      # Data structures
├── engine.py      # Core grind loop
├── hooks.py       # Hook execution
├── prompts.py     # Prompt templates
├── tasks.py       # Task loading
├── batch.py       # Batch runner
├── cli.py         # CLI interface
└── utils.py       # Output formatting
```

Clean, modular, single-responsibility design throughout.

## Documentation

### New in v2.0 (December 2025)
- **[Model Selection Guide](guide/model-selection.md)** - Haiku/Sonnet/Opus selection & CostAwareRouter
- **[Task Decomposition Guide](guide/decompose.md)** - Opus 4.5 with extended thinking
- **[Migration Guide](MIGRATION.md)** - Upgrade from v1.x

### Core Documentation
- **[Getting Started](getting-started/quickstart.md)** - Installation and first steps
- **[User Guide](guide/features.md)** - Complete feature reference
- **[Architecture](architecture/overview.md)** - System design and principles
- **[SDK Reference](sdk/overview.md)** - Claude Agent SDK documentation

## Examples

### Fix Test Failures
```yaml
tasks:
  - task: "Fix failing test suite"
    verify: "pytest tests/ -v"
    model: sonnet
    max_iterations: 10
```

### Complex Task with Hooks
```yaml
tasks:
  - task: "Implement OAuth authentication"
    verify: "pytest tests/auth/ -v && ruff check . && mypy ."
    model: opus
    max_iterations: 20
    hooks:
      pre_grind:
        - "/compact"
      post_grind:
        - "/code-review"
        - "/security-audit"
    prompt_config:
      preamble: "You are a senior backend engineer specializing in authentication."
      additional_rules:
        - "Follow OAuth 2.0 best practices"
        - "Store secrets securely"
```

## Project Status

- **Version**: 2.0 (Modular Architecture)
- **Python**: 3.11+
- **License**: MIT
- **Status**: Production Ready

## Links

- [GitHub Repository](https://github.com/eddiedunn/claude-code-agent)
- [Issue Tracker](https://github.com/eddiedunn/claude-code-agent/issues)
- [Claude Agent SDK](https://platform.claude.com/docs/en/agent-sdk/)
