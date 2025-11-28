# Grind Loop - Features Guide

Complete guide to all features in the grind loop system.

---

## Core Features

### 1. Model Selection

Choose the right model for each task to optimize cost, speed, and quality.

**Models Available**:
- `haiku` - Fast, cheap, good for simple tasks
- `sonnet` - Balanced, best for most tasks (default)
- `opus` - Powerful, expensive, for complex tasks

**Usage**:
```yaml
tasks:
  - task: "Fix linting errors"
    verify: "ruff check ."
    model: haiku
    max_iterations: 5

  - task: "Refactor authentication"
    verify: "pytest tests/auth/"
    model: opus
    max_iterations: 15
```

**CLI**:
```bash
uv run grind.py run -t "Fix tests" -v "pytest" -m haiku
```

**Decision Guide**:
- **Haiku**: Linting, formatting, simple fixes, high volume
- **Sonnet**: Bug fixes, refactoring, test fixes, general work
- **Opus**: Architecture changes, security audits, complex logic

---

### 2. Slash Command Hooks

Execute custom slash commands at key lifecycle points.

**Hook Points**:
- `pre_grind` - Before loop starts
- `post_iteration` - After each iteration
- `post_grind` - After loop completes

**Hook Triggers**:
- `once` - Run one time only (default)
- `every` - Run every time
- `every_n` - Run every N iterations
- `on_error` - Run when errors detected
- `on_success` - Run when task succeeds

**Basic Example**:
```yaml
tasks:
  - task: "Fix tests"
    verify: "pytest"
    hooks:
      pre_grind:
        - "/compact"
      post_grind:
        - "/code-review"
```

**Advanced Example**:
```yaml
tasks:
  - task: "Optimize performance"
    verify: "pytest --benchmark"
    hooks:
      pre_grind:
        - "/compact"
        - "/explain-codebase"

      post_iteration:
        - command: "/compact"
          trigger: every_n
          trigger_count: 3
        - command: "/benchmark"
          trigger: every

      post_grind:
        - "/code-review"
        - "/performance-report"
```

**Common Patterns**:

Periodic cleanup:
```yaml
post_iteration:
  - command: "/compact"
    trigger: every_n
    trigger_count: 5
```

Error diagnostics:
```yaml
post_iteration:
  - command: "/debug-logs"
    trigger: on_error
```

Final validation:
```yaml
post_grind:
  - "/test"
  - "/lint"
  - "/type-check"
```

---

### 3. Custom Prompts

Customize the system prompt to add domain-specific instructions.

**Three Approaches**:

#### A. Add Preamble
```yaml
tasks:
  - task: "Fix security issues"
    verify: "bandit -r src/"
    prompt_config:
      preamble: "You are a security expert focused on preventing vulnerabilities."
```

#### B. Add Context & Rules
```yaml
tasks:
  - task: "Optimize queries"
    verify: "pytest tests/db/"
    prompt_config:
      additional_context: |
        Database: PostgreSQL 15
        Current issue: N+1 queries in user endpoints
        Focus on read performance

      additional_rules:
        - "Always measure performance before and after"
        - "Consider index usage and query plans"
        - "Minimize database round trips"
```

#### C. Complete Custom Prompt
```yaml
tasks:
  - task: "Security audit"
    verify: "bandit -r src/ && safety check"
    prompt_config:
      custom_prompt: |
        You are a security auditor. Your mission:

        ## TASK
        {task}

        ## VERIFICATION
        Run: {verify_cmd}

        ## SECURITY CHECKLIST
        1. Check for SQL injection vulnerabilities
        2. Verify input sanitization
        3. Review authentication/authorization
        4. Check for exposed secrets
        5. Validate HTTPS usage

        Signal GRIND_COMPLETE when all checks pass.
        Signal GRIND_STUCK if you need human review.
```

**Note**: Custom prompts must include `{task}` and `{verify_cmd}` placeholders.

---

### 4. Task Decomposition

Break large problems into independent subtasks automatically.

**Usage**:
```bash
uv run grind.py decompose \
  --problem "Fix all 47 failing tests" \
  --verify "pytest tests/ -v" \
  --output tasks.yaml
```

**What It Does**:
1. Runs the verification command
2. Analyzes failures
3. Groups related issues
4. Creates task list ordered by dependency
5. Saves to YAML file

**Example Output** (`tasks.yaml`):
```yaml
tasks:
  - task: "Fix authentication test failures in tests/auth/test_login.py"
    verify: "pytest tests/auth/test_login.py -v"
    max_iterations: 5

  - task: "Fix database test failures in tests/db/test_queries.py"
    verify: "pytest tests/db/test_queries.py -v"
    max_iterations: 5

  - task: "Fix API endpoint tests in tests/api/"
    verify: "pytest tests/api/ -v"
    max_iterations: 8
```

**Then Run**:
```bash
uv run grind.py batch tasks.yaml
```

---

### 5. Batch Execution

Run multiple tasks sequentially with aggregated results.

**Usage**:
```bash
uv run grind.py batch tasks.yaml --verbose
```

**Options**:
- `--verbose` - Show full output from each task
- `--stop-on-stuck` - Stop if any task gets stuck

**Results Summary**:
```
============================================================
BATCH SUMMARY
============================================================
Total: 10  Completed: 8  Stuck: 1  Failed: 1
Duration: 245.3s

Needs attention:
  [stuck] Fix complex authentication logic
  [error] Fix database migration issues
```

---

### 6. Advanced Configuration

**Working Directory**:
```yaml
tasks:
  - task: "Fix frontend tests"
    verify: "npm test"
    cwd: "./frontend"
```

**Tool Restrictions**:
```yaml
tasks:
  - task: "Review code only"
    verify: "true"
    allowed_tools: ["Read", "Glob", "Grep"]
```

**Permission Mode**:
```yaml
tasks:
  - task: "Dangerous refactor"
    verify: "pytest"
    permission_mode: "requireApproval"
```

**Max Turns**:
```yaml
tasks:
  - task: "Complex refactor"
    verify: "pytest"
    max_turns: 100
```

---

## Feature Combinations

### Example: Production-Ready Task

```yaml
tasks:
  - task: "Implement user authentication with OAuth"
    verify: "pytest tests/auth/ -v && ruff check . && mypy ."
    model: opus
    max_iterations: 20
    cwd: "./backend"

    hooks:
      pre_grind:
        - "/compact"
        - "/explain-codebase auth/"

      post_iteration:
        - command: "/compact"
          trigger: every_n
          trigger_count: 5
        - command: "/security-check"
          trigger: every_n
          trigger_count: 3

      post_grind:
        - "/code-review"
        - "/security-audit"
        - "/test"

    prompt_config:
      preamble: "You are a senior backend engineer specializing in authentication systems."
      additional_rules:
        - "Follow OAuth 2.0 best practices"
        - "Store secrets securely"
        - "Implement PKCE flow"
        - "Add comprehensive tests"
        - "Log security events"
      additional_context: |
        Tech stack: FastAPI, SQLAlchemy, PostgreSQL
        OAuth provider: Google
        Session management: Redis

        Existing auth code is in:
        - backend/auth/oauth.py
        - backend/auth/session.py
```

---

## API Usage

Import the package directly:

```python
from grind import grind, TaskDefinition, GrindHooks, PromptConfig, SlashCommandHook

# Simple task
task = TaskDefinition(
    task="Fix linting",
    verify="ruff check .",
    model="haiku"
)

result = await grind(task)

# Complex task
task = TaskDefinition(
    task="Optimize queries",
    verify="pytest tests/db/ --benchmark",
    model="sonnet",
    max_iterations=15,
    hooks=GrindHooks(
        pre_grind=[SlashCommandHook("/compact")],
        post_iteration=[SlashCommandHook("/benchmark", trigger="every")],
        post_grind=[SlashCommandHook("/code-review")]
    ),
    prompt_config=PromptConfig(
        preamble="You are a database optimization expert.",
        additional_rules=[
            "Measure before and after",
            "Consider index usage"
        ]
    )
)

result = await grind(task, verbose=True)

if result.status == GrindStatus.COMPLETE:
    print(f"Success in {result.iterations} iterations!")
    print(f"Hooks executed: {len(result.hooks_executed)}")
```

---

## Best Practices

### 1. Start Simple
Don't add hooks and custom prompts until you need them. Start with basic tasks.

### 2. Choose Models Wisely
- Use haiku for volume work (linting, formatting)
- Use sonnet as default (good balance)
- Use opus sparingly (expensive, slow, but powerful)

### 3. Use Decompose
For large problems, let Claude break it down:
```bash
grind decompose -p "Fix all issues" -v "pytest" -o tasks.yaml
grind batch tasks.yaml
```

### 4. Hooks for Automation
Use hooks to automate manual steps:
- `/compact` to manage context
- `/test` to verify
- `/code-review` for quality

### 5. Custom Prompts for Domain Expertise
Add domain-specific knowledge via prompts:
```yaml
prompt_config:
  preamble: "You are a [domain] expert."
  additional_rules:
    - "Domain-specific rule 1"
    - "Domain-specific rule 2"
```

### 6. Verify Commands Are Good
The quality of verification commands determines success:
- Good: `pytest tests/ -v --tb=short`
- Bad: `pytest` (no useful error output)

---

## Troubleshooting

### Task Gets Stuck
- Increase `max_iterations`
- Change to more powerful model (opus)
- Add custom prompt with more context
- Break into smaller tasks via decompose

### Hooks Not Running
- Check trigger conditions
- Verify slash command exists
- Use `--verbose` to see hook execution

### Poor Results
- Check verification command output
- Add domain context via prompt_config
- Use more powerful model
- Add hooks for intermediate checks

---

**Last Updated**: 2025-11-28
