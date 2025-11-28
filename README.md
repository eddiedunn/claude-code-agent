# Grind Loop

Automated fix-verify loops using the Claude Agent SDK. Stop being a human message-passer between your terminal and Claude.

## What This Does

Instead of this manual cycle:
```
You see failure -> You paste to Claude -> Claude suggests fix ->
You apply fix -> You run tests -> You see failure -> repeat...
```

You run this:
```bash
uv run grind --task "Fix failing unit tests" --verify "pytest tests/ -v"
```

And walk away. The agent runs verification, analyzes failures, makes fixes, re-runs verification, and repeats until success (or asks for help).

## Prerequisites

1. **Claude Code CLI** must be installed and authenticated:
   ```bash
   npm install -g @anthropic-ai/claude-code
   claude  # Follow authentication prompts
   ```

2. **Python 3.11+** with uv:
   ```bash
   # Install uv if you don't have it
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

3. **Anthropic API Key** (recommended) or Claude Max subscription:
   ```bash
   export ANTHROPIC_API_KEY="sk-ant-..."
   ```

## Installation

```bash
# Clone and install
git clone <repo-url>
cd claude_code_agent
uv sync
```

## Usage

### Basic Usage

```bash
# Fix failing tests
uv run grind --task "Fix failing unit tests" --verify "pytest tests/ -v"

# Short form
uv run grind -t "Fix the tests" -v "pytest"
```

### Common Use Cases

#### Unit Tests (pytest)
```bash
uv run grind \
  --task "Fix all failing unit tests" \
  --verify "pytest tests/ -v --tb=short" \
  --max-iter 10
```

#### Unit Tests (Jest)
```bash
uv run grind \
  --task "Fix failing Jest tests" \
  --verify "npm test" \
  --max-iter 8
```

#### SonarQube Issues
```bash
uv run grind \
  --task "Fix SonarQube code smells in src/auth/" \
  --verify "sonar-scanner && ./check-quality-gate.sh" \
  --max-iter 8
```

#### Ansible Playbooks
```bash
uv run grind \
  --task "Fix the webserver playbook - it fails on nginx config" \
  --verify "ansible-playbook playbooks/webserver.yml --check" \
  --max-iter 6
```

#### Jenkins Pipeline
```bash
uv run grind \
  --task "Fix the Jenkinsfile - deploy stage is failing" \
  --verify "jenkins-cli build my-job -s -v" \
  --max-iter 5
```

#### Type Checking
```bash
uv run grind \
  --task "Fix all mypy type errors" \
  --verify "mypy src/ --strict" \
  --max-iter 10
```

#### Linting
```bash
uv run grind \
  --task "Fix all ruff linting errors" \
  --verify "ruff check src/" \
  --max-iter 5
```

### Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--task` | `-t` | required | What needs to be fixed |
| `--verify` | `-v` | required | Command to verify success (exit 0 = pass) |
| `--max-iter` | `-n` | 10 | Maximum fix-verify iterations |
| `--cwd` | `-c` | `.` | Working directory |
| `--verbose` | | false | Show full Claude output |
| `--quiet` | `-q` | false | Minimal output |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success - verification passed |
| 1 | Error during execution |
| 2 | Agent got stuck - needs human help |
| 3 | Max iterations reached |

## How It Works

1. **Initialize**: Agent receives task description and verification command
2. **Verify**: Agent runs verification to see current failures
3. **Analyze**: Agent reads error output and identifies issues
4. **Fix**: Agent makes targeted code changes
5. **Re-verify**: Agent runs verification again
6. **Loop**: Repeat until verification passes or agent signals it's stuck

The agent maintains full context of what it has tried, so it can adjust strategy if initial fixes don't work.

### Signal Words

The agent uses these signals to communicate status:
- `GRIND_COMPLETE` - Verification passed, task done
- `GRIND_STUCK: <reason>` - Agent needs human intervention
- `GRIND_PROGRESS: <summary>` - Progress update (shown in verbose mode)

## Programmatic Usage

```python
import asyncio
from grind_loop import grind, GrindStatus

async def main():
    result = await grind(
        task="Fix failing unit tests",
        verify_cmd="pytest tests/ -v",
        max_iterations=5,
        verbose=True
    )

    if result.status == GrindStatus.COMPLETE:
        print(f"Fixed in {result.iterations} iterations!")
    elif result.status == GrindStatus.STUCK:
        print(f"Agent stuck: {result.message}")
    else:
        print(f"Incomplete: {result.status}")

asyncio.run(main())
```

## Tips for Best Results

### Write Good Task Descriptions
```bash
# Good - specific and actionable
--task "Fix the authentication tests - they're failing because the mock isn't set up correctly"

# Less good - vague
--task "Fix tests"
```

### Write Good Verification Commands
```bash
# Good - clear pass/fail, useful output
--verify "pytest tests/auth/ -v --tb=short"

# Less good - no useful output on failure
--verify "pytest -q"
```

### Start with Lower Iterations
```bash
# Start conservative while learning what works
--max-iter 5

# Increase once you trust the workflow
--max-iter 15
```

### Use --verbose While Learning
```bash
# See what the agent is doing
uv run grind -t "Fix tests" -v "pytest" --verbose
```

## Project Structure

```
claude_code_agent/
  src/
    grind_loop/
      __init__.py      # Package exports
      core.py          # Main grind() function
      cli.py           # Command-line interface
  docs/
    sdk_reference/     # Claude Agent SDK documentation
  tests/               # Test files (TODO)
  pyproject.toml       # Project configuration
  README.md            # This file
```

## Troubleshooting

### "Claude Code not found"
Install and authenticate the CLI:
```bash
npm install -g @anthropic-ai/claude-code
claude
```

### "Authentication failed"
Set your API key:
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

### Agent keeps trying the same fix
The agent should detect repeated failures and try different approaches. If it doesn't:
1. Make your task description more specific
2. Reduce `--max-iter` to fail faster
3. Check if the verification command gives useful error messages

### Agent modifies wrong files
Be specific in your task:
```bash
# Better
--task "Fix tests in tests/auth/ - don't modify src/ files"
```

## License

MIT
