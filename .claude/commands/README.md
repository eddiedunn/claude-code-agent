# Grind Loop Slash Commands

Slash commands for use within Claude Code conversations to enhance Grind Loop workflows.

## Available Commands

### `/generate-tasks`

Analyze conversation context and generate a structured `tasks.yaml` file for batch or DAG execution.

**Usage**: Just type `/generate-tasks` after discussing problems or goals.

**Output**: Creates `tasks.yaml` with:
- Auto-generated tasks from conversation context
- Intelligent model selection (haiku/sonnet/opus by complexity)
- Reasonable iteration limits per task
- Optional task dependencies for DAG execution

**Next steps**: Run `uv run grind spawn -t tasks.yaml` to spawn agents from the generated file.

See [generate-tasks.md](generate-tasks.md) for complete details.

## Installing Commands Globally

Make these commands available in all Claude Code projects:

```bash
make install-commands
```

This copies all `*.md` files to `~/.claude/commands/` so they work in any project.

## How They Work

These are Claude Code slash commands that run special instructions. They help you:

1. Break down complex problems into tasks
2. Generate structured task definitions
3. Integrate with Grind Loop automation

Each command file is a Markdown document that Claude reads and executes as a special prompt.
