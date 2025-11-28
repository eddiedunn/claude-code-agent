# Using Grind Loop with Claude Code

This guide shows how to use Grind Loop with Claude Code (claude.ai/code) for maximum productivity.

## What is Claude Code?

[Claude Code](https://claude.ai/code) is Anthropic's official CLI tool that lets you have AI-powered conversations with Claude while working on your codebase. It provides:

- Direct access to your code files
- Ability to read, edit, and create files
- Execute commands in your terminal
- Custom slash commands for workflows
- Context-aware conversations

## Installation

### Prerequisites

1. **Claude Code CLI** - Install from [claude.ai/code](https://claude.ai/code)
2. **UV package manager** - Install from [astral.sh/uv](https://astral.sh/uv)
3. **Python 3.11+**

### Install Grind Loop

```bash
# Clone the repository
git clone https://github.com/eddiedunn/claude-code-agent.git
cd claude-code-agent

# Install dependencies
uv sync

# Verify installation
uv run grind --help
```

## Using the `/generate-tasks` Slash Command

The `/generate-tasks` command is the most powerful way to create task lists through conversation.

### Setup: Make the Command Portable

You have two options:

#### Option 1: Project-Specific (Default)
The command already exists in `.claude/commands/generate-tasks.md` and works only in this project.

#### Option 2: Global Command (Recommended)
Make it available in all your projects:

```bash
# Create global commands directory if needed
mkdir -p ~/.claude/commands

# Copy the command
cp .claude/commands/generate-tasks.md ~/.claude/commands/

# Optional: Copy the README for reference
cp .claude/commands/README.md ~/.claude/commands/
```

Now `/generate-tasks` works in any project where you use Claude Code!

### How to Use It

1. **Start a Claude Code conversation** about your problems:

```bash
claude
```

2. **Discuss what needs fixing**:

```
You: I have 47 failing tests across 3 modules and tons of linting errors.
     The auth tests are failing because of JWT changes, API tests have
     validation issues, and database tests have migration problems.

Claude: I can help break this down into manageable tasks...
```

3. **Generate tasks from the conversation**:

```
You: /generate-tasks
```

4. **Claude analyzes and creates tasks.yaml**:

```yaml
tasks:
  - task: "Fix JWT authentication in auth test suite"
    verify: "pytest tests/auth/ -v"
    model: sonnet
    max_iterations: 10

  - task: "Fix API validation test failures"
    verify: "pytest tests/api/ -v"
    model: sonnet
    max_iterations: 8

  - task: "Fix database migration test issues"
    verify: "pytest tests/db/ -v"
    model: sonnet
    max_iterations: 10

  - task: "Fix ruff linting errors"
    verify: "ruff check ."
    model: haiku
    max_iterations: 5
```

5. **Run the tasks**:

```bash
uv run grind batch tasks.yaml
```

## Real-World Workflows

### Workflow 1: Test-Driven Development

```
You: I'm implementing user authentication. I've written the tests but
     they're all failing. Can you help me get them passing?

Claude: I'll help. Let me look at the test files...

You: /generate-tasks

Claude: Generated tasks.yaml:
        1. Implement User model with password hashing
        2. Implement login endpoint
        3. Implement JWT token generation
        4. Implement authentication middleware

        To run: uv run grind batch tasks.yaml
```

### Workflow 2: Legacy Code Cleanup

```
You: I have a legacy codebase with 200+ linting errors, no type hints,
     and failing tests. Where do I start?

Claude: Let's break this down systematically...

You: /generate-tasks

Claude: Generated tasks.yaml with ordered tasks:
        1. Fix critical test failures (sonnet)
        2. Fix linting errors (haiku)
        3. Add type hints to core modules (sonnet)
        4. Add type hints to utility modules (haiku)
        5. Verify all tests pass (sonnet)
```

### Workflow 3: Bug Hunt

```
You: Production is broken. Users can't login. The logs show JWT errors
     and database connection issues.

Claude: Let me help debug this...
        [investigates code]

You: /generate-tasks

Claude: Generated tasks.yaml:
        1. Fix JWT secret configuration (opus, urgent)
        2. Fix database connection pool settings (sonnet)
        3. Add error handling and logging (sonnet)
        4. Verify fix with integration tests (sonnet)
```

## Integration Patterns

### Pattern 1: Interactive Debugging

Use Claude Code to investigate, then grind to fix:

```bash
# Start conversation
claude

# Investigate interactively
You: Why are the auth tests failing?
Claude: [analyzes code, finds issues]

You: /generate-tasks
Claude: [creates targeted task list]

# Exit conversation
You: exit

# Run the fixes
uv run grind batch tasks.yaml
```

### Pattern 2: Continuous Improvement

Keep a running conversation for ongoing work:

```bash
claude

# Session 1: Tests
You: Fix all failing tests
You: /generate-tasks
[exit and run grind]

# Session 2: Linting
You: Now the linting errors
You: /generate-tasks
[exit and run grind]

# Session 3: Refactoring
You: Let's refactor the auth module
You: /generate-tasks
[exit and run grind]
```

### Pattern 3: Code Review Driven

Generate tasks from code review feedback:

```bash
claude

You: I got code review feedback on PR #123:
     1. Add error handling to API endpoints
     2. Extract database queries to repository layer
     3. Add integration tests
     4. Fix type hints in auth module

You: /generate-tasks

Claude: Generated tasks.yaml with 4 focused tasks...
```

## Advanced: Custom Slash Commands

Create your own slash commands for project-specific workflows.

### Example: `/fix-security`

Create `.claude/commands/fix-security.md`:

```markdown
---
description: Generate tasks for security issues
allowed-tools:
  - Write
  - Read
  - Bash
---

Analyze the codebase for security issues and generate a tasks.yaml file with:

1. SQL injection vulnerabilities
2. XSS vulnerabilities
3. Authentication/authorization issues
4. Secrets in code
5. Dependency vulnerabilities

Use opus model for security-critical fixes.
Set max_iterations high (15-20).
Add security-focused prompt_config.
```

Usage:
```
You: We need to pass security audit
You: /fix-security
Claude: [generates security-focused tasks.yaml]
```

### Example: `/prepare-release`

Create `.claude/commands/prepare-release.md`:

```markdown
---
description: Generate pre-release checklist as tasks
allowed-tools:
  - Write
  - Read
  - Bash
---

Generate tasks.yaml for release preparation:

1. Ensure all tests pass
2. Fix all linting errors
3. Update version numbers
4. Update CHANGELOG.md
5. Verify documentation is current
6. Run security checks
7. Build and test package

Order tasks by dependency.
Use appropriate models per task complexity.
```

## Tips and Best Practices

### For Better Task Generation

1. **Be Specific in Conversation** - More context = better tasks
   - Bad: "Fix tests"
   - Good: "Fix auth tests - JWT validation is failing"

2. **Discuss Strategy First** - Let Claude understand approach
   ```
   You: Should we refactor the auth module before fixing tests?
   Claude: Yes, here's why...
   You: /generate-tasks
   ```

3. **Mention Constraints** - Help Claude choose right models/iterations
   ```
   You: These are simple formatting fixes, nothing complex
   You: /generate-tasks
   Claude: [uses haiku with low iterations]
   ```

### For Running Tasks

1. **Review Before Running** - Always check the generated YAML
   ```bash
   cat tasks.yaml  # Review first
   uv run grind batch tasks.yaml
   ```

2. **Edit as Needed** - Generated tasks are starting points
   ```bash
   vim tasks.yaml  # Adjust iterations, models, etc.
   uv run grind batch tasks.yaml
   ```

3. **Use Verbose Mode While Learning**
   ```bash
   uv run grind batch tasks.yaml --verbose
   ```

### For Iterative Development

1. **Start Small** - Generate tasks for one area at a time
2. **Review Results** - Check what worked before generating more
3. **Adjust Strategy** - Use learnings to refine next task generation

## Troubleshooting

### Slash Command Not Found

If `/generate-tasks` doesn't work:

1. Check file exists:
   ```bash
   ls .claude/commands/generate-tasks.md
   ```

2. Check file format (needs frontmatter):
   ```markdown
   ---
   description: Generate tasks
   allowed-tools:
     - Write
   ---
   ```

3. Try global install:
   ```bash
   cp .claude/commands/generate-tasks.md ~/.claude/commands/
   ```

### Tasks Don't Match Conversation

The command needs good context:

```
Bad:
You: /generate-tasks  # No context!

Good:
You: I have auth test failures and linting errors
Claude: [discusses the issues]
You: /generate-tasks  # Has context to work with
```

### Generated Tasks Too Generic

Be more specific in conversation:

```
Before:
You: Fix the tests
You: /generate-tasks
Result: Generic "fix all tests" task

After:
You: The auth tests are failing because JWT validation changed.
     Need to update test fixtures and mock data.
You: /generate-tasks
Result: Specific targeted tasks
```

## Next Steps

- **[Features Guide](features.md)** - Learn about hooks, custom prompts, model selection
- **[Task Definitions](task-definitions.md)** - YAML format reference
- **[Batch Mode](batch-mode.md)** - Running multiple tasks
- **[Slash Commands](slash-commands.md)** - Complete slash command reference
