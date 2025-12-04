# Task Decomposition with Opus 4.5

Break complex problems into optimal task lists using Opus 4.5 with extended thinking.

---

## Overview

The `decompose` command uses **Opus 4.5 with extended thinking** to:
1. Analyze complex problems by running verification commands
2. Research your codebase to understand context
3. Intelligently assign models (haiku/sonnet/opus) per task
4. Order tasks by dependencies (DAG-aware)
5. Generate executable `tasks.yaml` files

**Why Opus for decompose?**
- 80.9% on SWE-bench Verified (best reasoning capability)
- Extended thinking for multi-step planning
- Better complexity assessment and model selection
- Improved dependency detection

---

## Quick Start

### CLI Decompose

```bash
# Analyze and generate tasks
uv run grind decompose \
  --problem "Fix all 47 failing tests" \
  --verify "pytest tests/ -v" \
  --output tasks.yaml

# Review generated tasks
cat tasks.yaml

# Execute with intelligent model routing
uv run grind dag tasks.yaml --parallel 4
```

### Conversation Decompose

In a Claude Code conversation:

```
User: I have 47 failing tests and lots of linting errors
Claude: Let me help you fix those...

User: /generate-tasks

Claude: Generated tasks.yaml with 12 tasks:
- 8 linting fixes (haiku)
- 3 test fixes (sonnet)
- 1 architecture fix (opus)

Run: uv run grind dag tasks.yaml
```

---

## How It Works

### 1. Verification Analysis

Opus runs your verification command to understand the problem scope:

```bash
uv run grind decompose \
  --problem "Fix all issues" \
  --verify "pytest && ruff check ." \
  --verbose
```

**Opus executes:**
```bash
pytest && ruff check .
```

**Opus sees:**
```
tests/auth/test_login.py::test_session_refresh FAILED
tests/api/test_pagination.py::test_large_dataset FAILED
src/auth/login.py:45:1: F401 'refresh_token' imported but unused
src/api/routes.py:123:5: E501 line too long (120 > 100 characters)
...
```

### 2. Codebase Research

Opus uses **WebSearch, Read, Glob, Grep** to understand your project:

```python
# Tools available to decompose (grind/engine.py)
allowed_tools=["Bash", "Read", "Glob", "Grep", "WebSearch", "WebFetch"]
```

**Example research:**
- Reads `tests/auth/test_login.py` to understand test structure
- Searches for similar authentication patterns
- Identifies dependencies between auth and API modules
- Looks up best practices for the libraries you're using

### 3. Complexity Analysis & Model Assignment

Opus evaluates each task and assigns the appropriate model:

**Prompt includes model selection guidelines:**
```
## MODEL SELECTION GUIDELINES

**haiku** - Fast, efficient model for simple tasks:
- Straightforward bug fixes with clear root cause
- Simple refactoring (rename, extract function)
- Adding basic tests or documentation
- Minor configuration changes
- Cosmetic/formatting changes

**sonnet** - Balanced model for medium complexity:
- Multi-file refactoring requiring coordination
- Feature additions with moderate logic
- Bug fixes requiring investigation
...
```

**Example output:**
```yaml
tasks:
  - task: "Fix unused import in auth/login.py"
    verify: "ruff check src/auth/login.py"
    model: haiku  # Simple fix
    max_iterations: 3

  - task: "Fix race condition in test_session_refresh"
    verify: "pytest tests/auth/test_login.py::test_session_refresh -v"
    model: sonnet  # Requires investigation
    max_iterations: 10

  - task: "Redesign pagination for large datasets"
    verify: "pytest tests/api/test_pagination.py -v"
    model: opus  # Architecture decision
    max_iterations: 15
```

### 4. DAG-Aware Ordering

Opus orders tasks to respect dependencies:

```yaml
tasks:
  # Infrastructure first
  - id: lint
    task: "Fix all linting errors"
    verify: "ruff check ."
    model: haiku

  # Core fixes depend on clean code
  - id: auth_fix
    task: "Fix authentication session handling"
    verify: "pytest tests/auth/ -v"
    model: sonnet
    depends_on: [lint]

  # Tests depend on fixes
  - id: integration
    task: "Fix integration tests"
    verify: "pytest tests/integration/ -v"
    model: sonnet
    depends_on: [auth_fix, lint]
```

### 5. Extended Thinking

Decompose uses **10,000 thinking tokens** for deep reasoning:

```python
# grind/engine.py - decompose function
options = ClaudeAgentOptions(
    model="opus",
    max_thinking_tokens=10000,  # Extended thinking enabled
    ...
)
```

**Why extended thinking?**
- Better multi-step planning
- Improved dependency detection
- More accurate complexity assessment
- Consideration of edge cases

---

## Command Reference

### CLI Options

```bash
uv run grind decompose [OPTIONS]
```

| Option | Short | Required | Description |
|--------|-------|----------|-------------|
| --problem | -p | Yes | Description of the problem to solve |
| --verify | -v | Yes | Command to verify success |
| --output | -o | No | Output file path (default: print to stdout) |
| --cwd | -c | No | Working directory (default: current) |
| --verbose | | No | Show detailed analysis |

### Examples

**Simple decomposition:**
```bash
uv run grind decompose \
  -p "Fix failing tests" \
  -v "pytest tests/ -v" \
  -o tasks.yaml
```

**With specific directory:**
```bash
uv run grind decompose \
  -p "Fix API integration tests" \
  -v "pytest tests/api/ -v" \
  -c ./backend \
  -o api-tasks.yaml
```

**Verbose mode (see Opus thinking):**
```bash
uv run grind decompose \
  -p "Fix security vulnerabilities" \
  -v "bandit -r src/" \
  --verbose
```

---

## Output Format

### Generated tasks.yaml

```yaml
tasks:
  - task: "Clear, actionable description"
    verify: "command that exits 0 on success"
    model: haiku|sonnet|opus
    max_iterations: 3-15
    depends_on: []  # Optional dependencies

  - task: "Another task"
    verify: "verification command"
    model: sonnet
    max_iterations: 10
    depends_on: [first_task_id]
```

### Real-World Example

**Input:**
```bash
uv run grind decompose \
  -p "Fix all issues in CI pipeline" \
  -v "pytest && ruff check . && mypy src/" \
  -o ci-tasks.yaml
```

**Output (ci-tasks.yaml):**
```yaml
tasks:
  # Phase 1: Linting (simple, fast)
  - id: lint_imports
    task: "Fix import order violations in src/"
    verify: "ruff check --select I src/"
    model: haiku
    max_iterations: 3

  - id: lint_line_length
    task: "Fix line length violations"
    verify: "ruff check --select E501 src/"
    model: haiku
    max_iterations: 3

  # Phase 2: Type errors (medium complexity)
  - id: type_auth
    task: "Fix type errors in auth module"
    verify: "mypy src/auth/"
    model: sonnet
    max_iterations: 10
    depends_on: [lint_imports]

  - id: type_api
    task: "Fix type errors in API module"
    verify: "mypy src/api/"
    model: sonnet
    max_iterations: 10
    depends_on: [lint_imports]

  # Phase 3: Test fixes (varies by complexity)
  - id: test_unit
    task: "Fix unit test failures"
    verify: "pytest tests/unit/ -v"
    model: haiku
    max_iterations: 5
    depends_on: [type_auth, type_api]

  - id: test_integration
    task: "Fix integration test race conditions"
    verify: "pytest tests/integration/ -v --count=5"
    model: opus  # Complex debugging
    max_iterations: 15
    depends_on: [test_unit, type_auth, type_api]
```

---

## Execution Strategies

### Sequential Execution

Run tasks one at a time:

```bash
uv run grind batch tasks.yaml
```

**Pros:**
- Simple
- No Git conflicts
- Easy to debug

**Cons:**
- Slower (no parallelism)

### DAG Execution

Respect dependencies, parallelize when possible:

```bash
uv run grind dag tasks.yaml
```

**Pros:**
- Automatically parallelizes independent tasks
- Respects `depends_on` relationships
- Faster than sequential

**Cons:**
- Potential Git conflicts without worktrees

### Parallel DAG with Worktrees

Best of both worlds:

```bash
uv run grind dag tasks.yaml --parallel 4 --worktrees
```

**Pros:**
- Maximum parallelism (4 tasks at once)
- No Git conflicts (isolated worktrees)
- Automatic branch management

**Cons:**
- More complex Git history
- Requires Git worktree support

---

## Best Practices

### 1. Start with Verbose Mode

See what Opus is thinking:

```bash
uv run grind decompose -p "..." -v "..." --verbose
```

Learn how Opus:
- Analyzes your codebase
- Makes complexity decisions
- Detects dependencies

### 2. Review Before Executing

**Always review the generated tasks:**

```bash
# Generate
uv run grind decompose -p "..." -v "..." -o tasks.yaml

# Review
cat tasks.yaml

# Edit if needed
vim tasks.yaml

# Execute
uv run grind dag tasks.yaml
```

### 3. Provide Good Verification Commands

**Good verification commands:**
```bash
# ✅ Clear success criteria
--verify "pytest tests/ -v"

# ✅ Specific to the problem
--verify "pytest tests/auth/ && ruff check src/auth/"

# ✅ Fast feedback
--verify "pytest tests/unit/ -v"
```

**Poor verification commands:**
```bash
# ❌ Too broad
--verify "make test"

# ❌ No output
--verify "pytest -q"

# ❌ Slow
--verify "pytest --cov=. --cov-report=html"
```

### 4. Use Descriptive Problem Statements

**Good problem statements:**
```bash
# ✅ Specific scope
-p "Fix all authentication test failures"

# ✅ Clear goal
-p "Reduce memory usage in data processing pipeline"

# ✅ Actionable
-p "Migrate from requests to httpx library"
```

**Poor problem statements:**
```bash
# ❌ Too vague
-p "Fix stuff"

# ❌ Multiple unrelated issues
-p "Fix tests and add new features and refactor everything"

# ❌ Non-actionable
-p "Make code better"
```

### 5. Iterate on Complex Problems

For very large problems, decompose iteratively:

```bash
# Step 1: High-level decompose
uv run grind decompose \
  -p "Modernize entire backend" \
  -v "make test" \
  -o phase1.yaml

# Step 2: Decompose sub-problems
uv run grind decompose \
  -p "Fix all auth module issues from phase 1" \
  -v "pytest tests/auth/" \
  -o phase2-auth.yaml

uv run grind decompose \
  -p "Fix all API module issues from phase 1" \
  -v "pytest tests/api/" \
  -o phase2-api.yaml
```

---

## Advanced Features

### Custom Prompts

Override the decompose prompt with your own:

```python
from grind.engine import decompose
from grind.models import PromptConfig

# Custom decompose logic
config = PromptConfig(
    preamble="You are an expert in our specific domain...",
    additional_rules=[
        "Always create tasks with max 5 iterations",
        "Prefer haiku unless complexity requires sonnet"
    ]
)

# Note: Currently decompose doesn't accept PromptConfig
# This is a future enhancement
```

### Model Override

Force all tasks to use a specific model:

```python
# After decompose, modify all tasks
import yaml

with open('tasks.yaml') as f:
    data = yaml.safe_load(f)

# Override all to sonnet
for task in data['tasks']:
    task['model'] = 'sonnet'

with open('tasks-sonnet.yaml', 'w') as f:
    yaml.dump(data, f)
```

### Dependency Extraction

Extract dependency graph for visualization:

```python
import yaml
import networkx as nx
import matplotlib.pyplot as plt

with open('tasks.yaml') as f:
    data = yaml.safe_load(f)

G = nx.DiGraph()
for task in data['tasks']:
    task_id = task.get('id', task['task'][:20])
    G.add_node(task_id)
    for dep in task.get('depends_on', []):
        G.add_edge(dep, task_id)

nx.draw(G, with_labels=True)
plt.savefig('task-graph.png')
```

---

## Troubleshooting

### "No JSON found in response"

**Cause:** Opus didn't output valid JSON

**Solutions:**
1. Check verification command works:
   ```bash
   pytest tests/ -v  # Run manually first
   ```

2. Use more specific problem statement:
   ```bash
   # ❌ Too vague
   -p "Fix everything"

   # ✅ Specific
   -p "Fix failing authentication tests in tests/auth/"
   ```

3. Check for timeout (very large codebases):
   ```bash
   # Increase timeout in code if needed
   # Or narrow scope
   ```

### Tasks Too Granular

**Cause:** Opus is being too cautious

**Solution:** Provide guidance in problem statement:
```bash
-p "Fix all linting errors in one task - they're all simple"
```

### Tasks Too Coarse

**Cause:** Opus grouped too much together

**Solution:** Manually split the generated tasks, or re-decompose:
```bash
# After initial decompose
uv run grind decompose \
  -p "Fix only the authentication test failures" \
  -v "pytest tests/auth/ -v" \
  -o auth-only.yaml
```

### Wrong Model Assignment

**Cause:** Heuristics don't match your project

**Solution:** Manually edit `tasks.yaml` before execution:
```yaml
# Change from haiku to sonnet
- task: "Fix auth bug"
  model: sonnet  # Was haiku, but this is complex in our codebase
```

---

## Technical Details

### Decompose Implementation

**Location:** `grind/engine.py:820-862`

```python
async def decompose(
    problem: str,
    verify_cmd: str,
    cwd: str | None = None,
    verbose: bool = False
) -> list[TaskDefinition]:
    options = ClaudeAgentOptions(
        allowed_tools=["Bash", "Read", "Glob", "Grep", "WebSearch", "WebFetch"],
        permission_mode="acceptEdits",
        cwd=cwd,
        max_turns=10,
        model="opus",
        max_thinking_tokens=10000,  # Extended thinking
    )

    # Query Opus with decompose prompt
    collected = ""
    async with ClaudeSDKClient(options=options) as client:
        await client.query(DECOMPOSE_PROMPT.format(...))
        # Collect response...

    # Parse JSON response
    data = json.loads(collected[start:end])

    # Apply CostAwareRouter if model not specified
    router = CostAwareRouter()
    return [
        TaskDefinition(
            task=t["task"],
            verify=t["verify"],
            max_iterations=t.get("max_iterations", 5),
            model=t.get('model') or router.route_task(t["task"]),
            depends_on=t.get('depends_on', []),
        )
        for t in data.get("tasks", [])
    ]
```

### Prompt Template

**Location:** `grind/prompts.py:45-111`

Key sections:
1. Problem analysis instructions
2. Research capability guidance
3. Model selection guidelines (haiku/sonnet/opus)
4. DAG-aware ordering rules
5. JSON output format

---

## See Also

- [Model Selection Guide](model-selection.md) - Understand model tiers
- [DAG Execution](dag-execution.md) - Execute with dependencies
- [Git Worktrees](git-worktrees.md) - Parallel execution isolation
- [Features Guide](features.md) - Complete feature reference
- CostAwareRouter - Automatic model routing (see `grind/router.py`)
