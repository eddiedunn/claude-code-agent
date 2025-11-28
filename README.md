# Grind Loop

Automated fix-verify loops using the Claude Agent SDK.

## The Problem

You spend hours doing this:
```
See failure -> Paste to Claude -> Apply fix -> Run tests -> See failure -> repeat...
```

## The Solution

```bash
uv run grind run --task "Fix failing tests" --verify "pytest tests/ -v"
```

Walk away. Come back to passing tests.

## Installation

```bash
# Clone the repo
cd claude_code_agent

# Install dependencies
uv sync

# Verify Claude Code CLI is installed
claude --version
```

## Three Ways to Grind

### 1. Single Task

Fix one thing:

```bash
uv run grind run --task "Fix failing unit tests" --verify "pytest tests/ -v"

# Short form
uv run grind -t "Fix tests" -v "pytest"
```

### 2. Batch Mode

When you have a list of tasks:

```bash
# Create a tasks file (or use decompose to generate one)
uv run grind batch tasks.yaml
```

tasks.yaml format:
```yaml
tasks:
  - task: "Fix auth tests"
    verify: "pytest tests/auth/ -v"
    max_iterations: 5

  - task: "Fix API tests"
    verify: "pytest tests/api/ -v"
    max_iterations: 5
```

### 3. Decompose Mode

When you have a big problem and need Claude to break it down:

```bash
# Analyze and create task list
uv run grind decompose \
  --problem "Fix all 47 failing tests" \
  --verify "pytest tests/ -v" \
  --output tasks.yaml

# Then run the generated tasks
uv run grind batch tasks.yaml
```

## Real-World Examples

### Fix All Failing Tests

```bash
# Let Claude analyze and decompose
uv run grind decompose \
  -p "Fix all failing pytest tests" \
  -v "pytest tests/ -v --tb=short" \
  -o test-tasks.yaml

# Review the generated tasks
cat test-tasks.yaml

# Run them
uv run grind batch test-tasks.yaml
```

### Fix SonarQube Issues

```bash
# Decompose by issue type/file
uv run grind decompose \
  -p "Fix all SonarQube code smells and bugs" \
  -v "sonar-scanner && ./check-quality-gate.sh" \
  -o sonar-tasks.yaml

uv run grind batch sonar-tasks.yaml
```

### Fix Linting Issues

```bash
# Usually a single grind is enough for linting
uv run grind run \
  -t "Fix all ruff linting errors" \
  -v "ruff check src/"
```

### Fix Type Errors

```bash
uv run grind run \
  -t "Fix all mypy type errors" \
  -v "mypy src/ --strict" \
  -n 15  # May need more iterations for complex type fixes
```

## Options

### grind run
| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| --task | -t | required | What to fix |
| --verify | -v | required | Command to verify (exit 0 = pass) |
| --max-iter | -n | 10 | Max iterations |
| --cwd | -c | . | Working directory |
| --verbose | | false | Show full Claude output |
| --quiet | -q | false | Minimal output |

### grind batch
| Option | Description |
|--------|-------------|
| file | YAML/JSON file with task list |
| --verbose | Show full output |
| --stop-on-stuck | Stop if any task gets stuck |

### grind decompose
| Option | Short | Description |
|--------|-------|-------------|
| --problem | -p | Problem to analyze |
| --verify | -v | Verification command |
| --output | -o | Save tasks to file |
| --cwd | -c | Working directory |
| --verbose | | Show analysis |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error |
| 2 | Agent got stuck |
| 3 | Max iterations reached |

## Tips

1. **Start with decompose** for large problems - let Claude figure out the chunks
2. **Review generated tasks** before running batch - you can edit the YAML
3. **Use --verbose** while learning to see what Claude is doing
4. **Lower max_iterations** for quick tasks, higher for complex ones
5. **Good verification commands** give useful error output

## Project Structure

```
src/grind_loop/
  __init__.py    # Package exports
  core.py        # Single task grind loop
  batch.py       # Batch processing
  decompose.py   # Task decomposition
  cli.py         # Command-line interface
examples/
  tasks.yaml     # Example task file
```
