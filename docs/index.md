# Grind Loop

Automated fix-verify loops powered by Claude AI agents.

## What is Grind Loop?

Grind Loop is a tool that automates repetitive fix-verify cycles in software development. Instead of manually running tests, analyzing failures, making fixes, and repeating - you define the task once and let Claude handle the iteration.

```bash
# Before: Hours of manual iteration
pytest → see failures → fix → pytest → see failures → fix → ...

# After: One command
uv run grind.py run -t "Fix all test failures" -v "pytest tests/ -v"
```

## Key Features

- **Model Selection**: Choose haiku/sonnet/opus per task for optimal cost/quality
- **Slash Command Hooks**: Execute commands at key lifecycle points
- **Custom Prompts**: Add domain-specific expertise to tasks
- **Task Decomposition**: Automatically break large problems into subtasks
- **Batch Execution**: Run multiple tasks sequentially
- **Context-Aware**: `/generate-tasks` command analyzes conversation history

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

- **[Getting Started](getting-started/quickstart.md)** - Installation and first steps
- **[User Guide](guide/features.md)** - Complete feature reference
- **[Architecture](architecture/overview.md)** - System design and principles
- **[SDK Reference](sdk/overview.md)** - Claude Agent SDK documentation
- **[Development](development/contributing.md)** - Contributing guidelines

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
