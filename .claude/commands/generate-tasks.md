---
description: Generate a tasks.yaml file for grind from current conversation context
allowed-tools:
  - Write
  - Read
  - Bash
---

You are a task decomposition expert. Analyze the current conversation context and generate a `tasks.yaml` file for the grind loop system.

## Your Mission

Generate a YAML file containing one or more tasks based on conversation context:
- Conversation history and files discussed
- Problems, errors, or goals mentioned
- Dependencies between tasks (use DAG features when appropriate)

## Complete Task Schema

```yaml
tasks:
  # --- REQUIRED FIELDS ---
  - task: "Clear, actionable description"    # What to do (be specific!)
    verify: "command"                         # Must exit 0 on success

    # --- CORE OPTIONS ---
    model: sonnet                             # haiku|sonnet|opus
    max_iterations: 10                        # 5-20 typical
    cwd: "."                                  # Working directory

    # --- DAG EXECUTION (for task dependencies) ---
    id: task_name                             # Unique identifier
    depends_on: [other_task]                  # Wait for these tasks first

    # --- GIT WORKTREE ISOLATION (for parallel execution) ---
    branch: fix/feature                       # Shorthand: create worktree on branch
    merge_from: [fix/dep1, fix/dep2]          # Merge these branches before starting
    worktree:                                 # Full form (alternative to shorthand)
      branch: fix/feature
      base_branch: main                       # Create from this ref (default: HEAD)
      merge_from: []
      cleanup_on_success: true                # Remove worktree after success
      cleanup_on_failure: false               # Keep for debugging

    # --- HOOKS ---
    hooks:
      pre_grind:                              # Before task starts
        - "/implementation-engineer"          # Always include this!
      post_iteration:                         # After each iteration
        - command: "/compact"
          trigger: every_n                    # every|every_n|once|on_error|on_success
          trigger_count: 3
      post_grind:                             # After task completes
        - command: "/notify"
          trigger: on_success                 # Only on successful completion

    # --- PROMPT CUSTOMIZATION ---
    prompt_config:
      preamble: "You are a [domain] expert."
      additional_rules: ["Rule 1", "Rule 2"]
      additional_context: "Extra context here"
      custom_prompt: "Override entire prompt"  # Rarely needed

    # --- ADVANCED SDK SETTINGS ---
    allowed_tools: ["Read", "Edit", "Bash"]   # Restrict available tools (null = all)
    permission_mode: acceptEdits              # default|acceptEdits|bypassPermissions
    max_turns: 50                             # SDK conversation turn limit
    query_timeout: 300                        # Seconds before SDK timeout
    interactive:
      enabled: false                          # Press 'i' to interject during execution
```

## Quick Reference

| Field | Default | When to Change |
|-------|---------|----------------|
| `model` | sonnet | haiku for simple, opus for complex |
| `max_iterations` | 10 | Increase for complex multi-file changes |
| `max_turns` | 50 | Increase for very long tasks |
| `query_timeout` | 300 | Increase for slow operations |
| `permission_mode` | acceptEdits | bypassPermissions for trusted automation |
| `interactive` | false | true for debugging/guidance |

## Model Selection

- **haiku**: Linting, formatting, simple fixes, repetitive tasks
- **sonnet**: Bug fixes, refactoring, standard features (default)
- **opus**: Architecture, security, complex multi-system changes

## Hook Triggers

| Trigger | Runs When |
|---------|-----------|
| `every` | Every iteration |
| `every_n` | Every N iterations (set `trigger_count`) |
| `once` | First iteration only |
| `on_error` | Task ends in error/stuck |
| `on_success` | Task completes successfully |

## Examples

### Sequential Tasks (Simple)
```yaml
tasks:
  - task: "Fix ruff linting errors"
    verify: "ruff check ."
    model: haiku
    max_iterations: 5
    hooks:
      pre_grind: ["/implementation-engineer"]

  - task: "Fix mypy type errors"
    verify: "mypy src/ --strict"
    model: sonnet
    max_iterations: 10
    hooks:
      pre_grind: ["/implementation-engineer"]
```

### DAG with Dependencies
```yaml
tasks:
  - id: lint
    task: "Fix all linting errors in src/"
    verify: "ruff check ."
    model: haiku
    max_iterations: 5
    hooks:
      pre_grind: ["/implementation-engineer"]

  - id: typecheck
    task: "Fix type errors after linting is complete"
    verify: "mypy src/"
    model: sonnet
    depends_on: [lint]                        # Waits for lint
    hooks:
      pre_grind: ["/implementation-engineer"]

  - id: tests
    task: "Fix failing unit tests"
    verify: "pytest tests/unit/ -v"
    model: sonnet
    depends_on: [lint]                        # Parallel with typecheck
    hooks:
      pre_grind: ["/implementation-engineer"]

  - id: integration
    task: "Fix integration tests"
    verify: "pytest tests/integration/ -v"
    model: opus
    depends_on: [typecheck, tests]            # Waits for BOTH
    hooks:
      pre_grind: ["/implementation-engineer"]
      post_grind:
        - command: "/notify"
          trigger: on_success
```

### Parallel with Git Worktrees
```yaml
tasks:
  - id: lint
    task: "Fix linting errors"
    verify: "ruff check ."
    model: haiku
    branch: fix/lint                          # Isolated worktree

  - id: types
    task: "Fix type errors"
    verify: "mypy src/"
    model: sonnet
    depends_on: [lint]
    branch: fix/types
    merge_from: [fix/lint]                    # Get lint changes first

  - id: tests
    task: "Fix failing tests"
    verify: "pytest"
    model: sonnet
    depends_on: [lint]
    worktree:                                 # Full worktree config
      branch: fix/tests
      base_branch: main
      merge_from: [fix/lint]
      cleanup_on_success: true
      cleanup_on_failure: false               # Keep for debugging
```

### Complex Feature with All Options
```yaml
tasks:
  - id: auth
    task: |
      Implement OAuth2 authentication in src/auth/:
      - Add OAuth2Client class in src/auth/oauth.py
      - Implement token refresh in src/auth/tokens.py
      - Add /auth/oauth/callback endpoint in src/api/auth.py
      - Store tokens securely using existing SecretStore
      - Add tests in tests/auth/test_oauth.py
    verify: "pytest tests/auth/ -v && ruff check . && mypy src/"
    model: opus
    max_iterations: 20
    max_turns: 100                            # Complex task needs more turns
    query_timeout: 600                        # Allow longer operations
    hooks:
      pre_grind: ["/implementation-engineer"]
      post_iteration:
        - command: "/compact"
          trigger: every_n
          trigger_count: 5
      post_grind:
        - command: "/code-review"
          trigger: on_success
    prompt_config:
      preamble: "You are a senior security engineer specializing in OAuth2."
      additional_rules:
        - "Follow OAuth 2.0 RFC 6749 strictly"
        - "Never log tokens or secrets"
        - "Use constant-time comparison for tokens"
```

## Your Process

1. **Analyze Context**: What problems, goals, or issues have been discussed?
2. **Identify Tasks**: Break down into focused, actionable tasks
3. **Map Dependencies**: Use `id`/`depends_on` if tasks have ordering requirements
4. **Choose Models**: Match model to task complexity
5. **Set Limits**: Iterations, turns, timeouts based on complexity
6. **Add Hooks**: `/implementation-engineer` always; add others as needed
7. **Consider Worktrees**: For parallel execution with Git isolation

## Output Requirements

1. **Ask for filename** if not obvious (default: `tasks.yaml`)
2. **Show the YAML** to the user for review
3. **Write to file** using the Write tool
4. **Provide usage command**:

```
Generated tasks.yaml with N tasks.

To run sequentially:
  uv run grind batch tasks.yaml

To run as DAG (respects depends_on):
  uv run grind dag tasks.yaml

To run DAG with parallel execution:
  uv run grind dag tasks.yaml --parallel 3 --worktrees
```

## CRITICAL: Tasks Must Be Self-Contained

Each task runs in a **fresh context** with NO memory of previous tasks. Include EVERYTHING:

- **File paths**: Exact paths to modify
- **Function/class names**: Specific identifiers
- **Technical details**: Data structures, APIs, patterns
- **Context**: Why this change is needed
- **Constraints**: Any limitations or requirements

### BAD (too vague):
```yaml
- task: "Fix the login bug"
  verify: "pytest tests/auth/ -v"
```

### GOOD (self-contained):
```yaml
- task: |
    Fix the login bug in src/auth/login.py where the session token
    is not being refreshed after password change. The issue is in
    the `authenticate_user()` function around line 45. After successful
    password validation, call `refresh_session_token(user_id)` before
    returning the auth response. The function exists in src/auth/tokens.py.
  verify: "pytest tests/auth/test_login.py -v"
```

Write tasks as if briefing a new developer who just joined the project.

Now analyze the current context and generate an appropriate tasks.yaml file.
