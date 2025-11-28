# Slash Commands

Custom slash commands for use in Claude Code conversations.

## `/generate-tasks`

Generate a `tasks.yaml` file from the current conversation context.

### Usage

1. Have a conversation with Claude about problems, goals, or issues
2. Type `/generate-tasks`
3. Claude analyzes the context and generates a task file

### Example

```
You: I have 47 failing tests across auth/, api/, and db/ modules.
     Also ruff is showing 200+ linting errors.

You: /generate-tasks

Claude: I'll generate a tasks.yaml file based on our discussion.

        Generated tasks.yaml with 4 tasks:
        1. Fix auth test failures (sonnet, 8 iterations)
        2. Fix API test failures (sonnet, 10 iterations)
        3. Fix database test failures (sonnet, 8 iterations)
        4. Fix ruff linting errors (haiku, 5 iterations)

        To run:
          uv run grind.py batch tasks.yaml
```

### What It Does

1. **Analyzes Context** - Reviews full conversation history
2. **Identifies Tasks** - Breaks problems into actionable tasks
3. **Chooses Models** - Selects haiku/sonnet/opus based on complexity
4. **Sets Iterations** - Estimates based on task difficulty
5. **Adds Hooks** - Includes hooks for complex workflows (optional)
6. **Custom Prompts** - Adds domain expertise when needed (optional)
7. **Writes File** - Creates properly formatted YAML
8. **Shows Usage** - Provides commands to run

### Features

**Context-Aware**
- Uses full conversation history
- Understands goals and intentions
- Can incorporate discussion about approach

**Smart Defaults**
- Appropriate model selection
- Reasonable iteration limits
- Real verification commands

**Optional Enhancements**
- Hooks for complex tasks
- Custom prompts for domain expertise
- Working directory configuration

### Comparison: CLI vs Slash Command

**CLI decompose**:
```bash
uv run grind decompose -p "Fix failures" -v "pytest" -o tasks.yaml
```
- Good for: Automated scripts, CI/CD
- Runs verification command first
- Generates based on output

**Slash command**:
```
/generate-tasks
```
- Good for: Interactive conversations
- Uses full conversation context
- More nuanced task breakdown
- Understands discussion history

### Tips

1. **Discuss First** - Talk through problems before generating
2. **Be Specific** - More context = better task breakdown
3. **Review Generated File** - Always check before running
4. **Edit as Needed** - Generated YAML is just a starting point
5. **Iterate** - Regenerate if first attempt isn't quite right

### Command Location

The slash command is defined in:
```
.claude/commands/generate-tasks.md
```

You can create your own slash commands by adding markdown files to `.claude/commands/`.

### Creating Custom Slash Commands

See `.claude/commands/README.md` for details on creating your own commands.

Example command structure:
```markdown
---
description: Brief description
allowed-tools:
  - Write
  - Read
  - Bash
---

Your command prompt here...
```
