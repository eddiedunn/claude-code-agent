# Grind Loop

Automated fix-verify loops using Claude Agent SDK with intelligent model selection and task decomposition.

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

## Key Features (December 2025)

- **Intelligent Model Selection**: Opus 4.5 for planning, Haiku 4.5 for execution (3-5x cost savings)
- **Extended Thinking**: 10K token reasoning budget for complex decomposition
- **CostAwareRouter**: Automatic model assignment based on task complexity
- **Interleaved Thinking**: Better reasoning between tool calls
- **DAG Execution**: Parallel task execution with dependency management
- **Git Worktrees**: Conflict-free parallel execution
- **WebSearch Integration**: Research capability during decomposition

**Pricing (Dec 2025):**
- Haiku 4.5: $1/$5 per million tokens (default, 73% of Opus capability)
- Sonnet 4.5: $3/$15 per million tokens (medium complexity)
- Opus 4.5: $5/$25 per million tokens (planning, 67% cheaper than Opus 4.1)

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

**Option A: Using slash command in conversation**
```
Talk to Claude about your problems, then:
/generate-tasks

Reviews context and generates tasks.yaml automatically
```

**Option B: Using CLI decompose**
```bash
# Analyze and create task list
uv run grind decompose \
  --problem "Fix all 47 failing tests" \
  --verify "pytest tests/ -v" \
  --output tasks.yaml

# Then run the generated tasks
uv run grind batch tasks.yaml
```

## Experimental: TUI (Terminal Interface)

⚠️ **Alpha Status** - Interactive terminal interface for grind orchestration.

**What works:**
- Interactive shell for running grind tasks
- Command history and tab completion
- Basic task execution and status tracking

**What's planned:**
- Real-time multi-agent monitoring
- DAG visualization
- Log streaming dashboard

Try it:
```bash
# Launch TUI
uv run grind tui

# Launch with task file
uv run grind tui -t tasks.yaml
```

Navigate tabs with 1-6 keys. Use tab 6 (Shell) for interactive commands.

## Merging Task Branches

After running DAG tasks with worktrees, you'll have multiple branches with fixes. Use the intelligent merge command to combine them:

```bash
# Interactive merge with conflict resolution
uv run grind merge

# Merge specific branches
uv run grind merge fix/lint fix/tests fix/types

# Custom pattern
uv run grind merge --pattern "feature/*,bugfix/*"

# With post-merge verification
uv run grind merge --verify "pytest && ruff check"

# Dry run (see what would be merged)
uv run grind merge --dry-run
```

**What makes this smart:**
- ✓ Merges clean branches automatically
- ⚠️ Prompts only when conflicts occur
- 💾 Creates backup and staging branches (never touches main directly)
- 🧪 Runs verification after merging
- 📊 Shows clear summary with next steps

**Conflict resolution options:**
When conflicts occur, you'll be prompted:
1. Show diff (investigate the conflict)
2. Keep ours (discard their changes)
3. Keep theirs (accept their changes)
4. Skip this branch (handle manually later)
5. Abort entire merge

**After merging:**
```bash
# Review the merged result
git diff main..grind-merge-20251207-1430

# If satisfied, merge to main
git checkout main
git merge grind-merge-20251207-1430 --ff-only
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

## Slash Commands

Custom slash commands for use in Claude Code conversations:

### `/generate-tasks`
Generate a `tasks.yaml` file from conversation context.

**Usage**: Just type `/generate-tasks` after discussing problems/goals with Claude.

**It will**:
- Analyze what you've been discussing
- Break down into actionable tasks
- Choose appropriate models
- Generate properly formatted YAML
- Write to file and show usage

See [.claude/commands/README.md](./.claude/commands/README.md) for details.

## Model Selection & Pricing

Choose the right model for your task based on complexity and budget (December 2025 rates):

| Model | Use Case | Input (per 1M tokens) | Output (per 1M tokens) |
|-------|----------|----------------------|------------------------|
| **haiku** (default) | Simple fixes, linting, formatting | $0.25 | $1.25 |
| **sonnet** | Bug fixes, refactoring, medium complexity | $3.00 | $15.00 |
| **opus** | Planning, architecture, complex logic | $15.00 | $75.00 |

**Usage**:
```bash
# Use default (haiku)
uv run grind run -t "Fix linting" -v "ruff check ."

# Specify model explicitly
uv run grind run -t "Refactor auth" -v "pytest tests/auth/" -m sonnet
```

**Recommendation**: Start with haiku for most tasks. Use sonnet for medium complexity work. Reserve opus for architectural decisions and complex planning tasks.

## Tips

1. **Use `/generate-tasks`** in conversations to automatically create task files
2. **Start with decompose** for large problems - let Claude figure out the chunks
3. **Review generated tasks** before running batch - you can edit the YAML
4. **Use --verbose** while learning to see what Claude is doing
5. **Lower max_iterations** for quick tasks, higher for complex ones
6. **Good verification commands** give useful error output
7. **Choose models wisely** - haiku for simple tasks, sonnet for medium complexity, opus for planning/architecture

## Project Structure

```
grind/
  __init__.py    # Package exports
  models.py      # Data structures
  engine.py      # Core grind loop
  hooks.py       # Slash command hooks
  prompts.py     # Prompt templates
  tasks.py       # Task loading
  batch.py       # Batch execution
  cli.py         # Command-line interface
  utils.py       # Output formatting
grind.py         # Entry point
examples/
  example-tasks.yaml   # Example task definitions
```

## Using with Claude Code

Grind Loop is designed to work seamlessly with [Claude Code](https://claude.ai/code).

### Quick Setup

```bash
# Install dependencies
uv sync

# Install slash commands globally (optional but recommended)
make install-commands
```

Now use `/generate-tasks` in any Claude Code conversation to automatically generate task files!

See **[Using with Claude Code](docs/guide/using-with-claude-code.md)** for complete integration guide.

## Documentation

**📚 [Full Documentation](https://eddiedunn.github.io/claude-code-agent/)** (MkDocs site)

### Quick Links
- **[Using with Claude Code](docs/guide/using-with-claude-code.md)** - Integration guide and workflows
- **[Getting Started](docs/getting-started/installation.md)** - Installation and setup
- **[Features Guide](docs/guide/features.md)** - Complete feature reference
- **[Architecture](docs/architecture/overview.md)** - System design
- **[SDK Reference](docs/sdk/overview.md)** - Claude Agent SDK docs

### Local Development
```bash
# View documentation locally
make docs

# Or manually:
uv run mkdocs serve
```

Then open http://127.0.0.1:8000
