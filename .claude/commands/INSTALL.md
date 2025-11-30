# Installing Grind Loop Slash Commands Globally

This guide shows how to make the Grind Loop slash commands available in all your projects.

## Quick Install

```bash
# From the grind loop project root
make install-commands
```

Or manually:

```bash
# Create global commands directory
mkdir -p ~/.claude/commands

# Copy commands
cp .claude/commands/generate-tasks.md ~/.claude/commands/

# Optional: Copy documentation
cp .claude/commands/README.md ~/.claude/commands/grind-loop-commands.md
```

## What Gets Installed

### `/generate-tasks`
Generate a `tasks.yaml` file from conversation context.

**Location**: `~/.claude/commands/generate-tasks.md`

**Use Case**: After discussing problems with Claude, automatically generate a structured task list for grind to execute.

**Example**:
```
You: I have 47 failing tests and linting errors
You: /generate-tasks

Claude: Generated tasks.yaml with 5 tasks...
        To run: uv run grind batch tasks.yaml
```

## Verifying Installation

Start a Claude Code conversation in any project:

```bash
cd ~/any-project
claude
```

Check available commands:
```
You: /
```

You should see `/generate-tasks` in the list.

## Updating Commands

When Grind Loop is updated, reinstall:

```bash
cd /path/to/claude-code-agent
git pull
make install-commands
```

## Uninstalling

```bash
rm ~/.claude/commands/generate-tasks.md
```

## Project-Specific vs Global

### Project-Specific (Default)
Commands in `.claude/commands/` only work in this project.

**Pros**:
- Version controlled with project
- Can customize per project
- No global pollution

**Cons**:
- Only available in this project
- Need to reinstall per project

### Global (Recommended for Grind)
Commands in `~/.claude/commands/` work everywhere.

**Pros**:
- Available in all projects
- Install once, use everywhere
- Consistent workflow

**Cons**:
- Not version controlled
- Manual updates needed
- Same command across all projects

## Best Practice

For Grind Loop, we recommend:

1. **Install globally**: Use the command everywhere
2. **Keep project copy**: Track changes in git
3. **Sync updates**: Run `make install-commands` after git pull

This gives you both portability and version control.

## Troubleshooting

### Command Not Found After Install

Check file exists:
```bash
ls -la ~/.claude/commands/generate-tasks.md
```

Check permissions:
```bash
chmod 644 ~/.claude/commands/generate-tasks.md
```

Restart Claude Code:
```bash
# Exit current session
exit

# Start new session
claude
```

### Command Works in One Project But Not Another

This means you're using the project-specific version. Install globally:
```bash
cp .claude/commands/generate-tasks.md ~/.claude/commands/
```

### Multiple Versions Conflict

Claude Code checks in this order:
1. `.claude/commands/` (project-specific)
2. `~/.claude/commands/` (global)

Project-specific takes precedence. To force global:
```bash
rm .claude/commands/generate-tasks.md
```

## Advanced: Custom Commands

You can create your own commands in `~/.claude/commands/`:

```bash
# Create a new command
cat > ~/.claude/commands/my-command.md << 'EOF'
---
description: My custom workflow
allowed-tools:
  - Write
  - Read
---

Your command prompt here...
EOF
```

See [README.md](./README.md) for command format details.
